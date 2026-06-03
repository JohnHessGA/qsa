"""R011 — ticker-reuse / spliced price series.

Reports the population of ticker-reuse boundaries: symbols whose
``shdb.stock_price_1d`` series splices two different companies under one
``security_id`` because a delisted issuer's ticker was later adopted by a new
company (e.g. ALF Alfi->Centurion, BBBY Bed Bath & Beyond->Beyond, AKTS
Akoustis->Aktis). A long-horizon return that reaches across the boundary
silently compares two companies — the I-000189 phantom-gainer defect.

Design source of truth:
``~/repos/aft-platform/docs/platform/security-identity-and-ticker-reuse.md``
(Option B — lightweight boundary guard). The authoritative boundary set is
``shdb.security_ticker_boundary`` (origin ``masd.security_ticker_boundary``,
seeded by ``mdc security-identity boundaries``). QSA does not fix data — it
reports — so R011 has two parts:

  * **Report the boundaries.** One ``warning`` finding for the full population,
    escalated to ``critical`` for boundaries on symbols in the active AFT
    investable universe (a spliced series there poisons MEF/CCW/GDE/RSE return
    features), mirroring R010's universe-scoped posture.
  * **Drift cross-check.** Independently recompute >``gap_trading_days`` voids
    in ``shdb.stock_price_1d`` over the investable universe and flag any that
    are **absent** from the boundary table — i.e. the table is stale and the
    monthly ``mdc security-identity boundaries`` scan should be re-run.

This is detection only; remediation (the guard) lives in the consumers
(RSE return-rank reads the same boundary table).
"""

from __future__ import annotations

from typing import Any

from qsa.db import fetch_dicts
from qsa.finding import Finding

# Drift cross-check threshold. The detector seeds boundaries at a >150 calendar
# day void; R011 recomputes in calendar days too, scoped to the universe.
_DEFAULT_GAP_DAYS = 150
_DEFAULT_MAX_SAMPLES = 50


def _boundary_sample(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": row["symbol"],
        "boundary_date": str(row["boundary_date"]),
        "prior_last_bar": str(row["prior_last_bar"]),
        "gap_days": row["gap_days"],
        "signal": row["signal"],
        "predecessor_note": row.get("predecessor_note") or "",
    }


def check(*, masd, shdb, mefdb, app_cfg: dict[str, Any]) -> list[Finding]:
    cfg = app_cfg.get("ticker_reuse") or {}
    gap_days = int(cfg.get("gap_trading_days", _DEFAULT_GAP_DAYS))
    max_samples = int(cfg.get("max_samples", _DEFAULT_MAX_SAMPLES))

    findings: list[Finding] = []

    # ── Part 1: report the recorded boundaries, escalating universe members ──
    rows = fetch_dicts(shdb, """
        SELECT b.symbol, b.boundary_date, b.prior_last_bar, b.gap_days,
               b.signal, b.predecessor_note,
               (u.symbol IS NOT NULL) AS in_universe
        FROM shdb.security_ticker_boundary b
        LEFT JOIN (
            SELECT DISTINCT symbol FROM shdb.v_investable_universe_active
        ) u ON u.symbol = b.symbol
        ORDER BY (u.symbol IS NOT NULL) DESC, b.gap_days DESC
    """)

    crit = [r for r in rows if r["in_universe"]]
    warn = [r for r in rows if not r["in_universe"]]

    if crit:
        symbols = [r["symbol"] for r in crit]
        findings.append(Finding(
            rule_id="R011-ticker-reuse",
            severity="critical",
            database="shdb",
            table="shdb.security_ticker_boundary",
            summary=(
                f"{len(crit)} ticker-reuse boundary(ies) on AFT investable-universe "
                f"symbol(s): {', '.join(symbols[:8])}"
                + (" …" if len(symbols) > 8 else "")
            ),
            detail=(
                "A recorded reuse/long-void boundary on a universe symbol means its "
                "shdb.stock_price_1d series splices two issuers under one security_id. "
                "Any long-horizon return/drawdown that anchors before the boundary "
                "compares two different companies and is wrong."
            ),
            affected_symbols=len(symbols),
            sample=[_boundary_sample(r) for r in crit[:max_samples]],
            recommendation=(
                "Consumers must not anchor a long-horizon return across the boundary "
                "(RSE return-rank already reads shdb.security_ticker_boundary and "
                "drops these). Verify each universe member is genuinely a reuse vs a "
                "same-company relisting; if a true reuse should be excluded from a "
                "fixed universe, prune it upstream."
            ),
        ))

    if warn:
        symbols = [r["symbol"] for r in warn]
        findings.append(Finding(
            rule_id="R011-ticker-reuse",
            severity="warning",
            database="shdb",
            table="shdb.security_ticker_boundary",
            summary=(
                f"{len(warn)} ticker-reuse boundary(ies) outside the investable "
                f"universe (open-universe consumers, e.g. RSE/CIA)"
            ),
            detail=(
                "Boundaries on non-universe symbols. Not universe-critical, but "
                "open-universe screens (RSE 'biggest gainers', CIA) can surface them; "
                "the RSE return-rank guard reads the same boundary table to exclude "
                "them. Listed for visibility / tracking through the migration."
            ),
            affected_symbols=len(symbols),
            sample=[_boundary_sample(r) for r in warn[:max_samples]],
            recommendation=(
                "No action required if the consumer guards are in place. Track the "
                "population; investigate any symbol that later enters the universe."
            ),
        ))

    # ── Part 2: drift cross-check — universe voids missing from the table ──
    drift = fetch_dicts(shdb, """
        WITH s AS (
            SELECT p.symbol, p.bar_date,
                   lag(p.bar_date) OVER (PARTITION BY p.symbol ORDER BY p.bar_date) AS prev_bar
            FROM shdb.stock_price_1d p
            JOIN (SELECT DISTINCT symbol FROM shdb.v_investable_universe_active) u
              ON u.symbol = p.symbol
        ), voids AS (
            SELECT symbol, prev_bar AS prior_last_bar, bar_date AS boundary_date,
                   (bar_date - prev_bar) AS gap_days
            FROM s
            WHERE prev_bar IS NOT NULL AND (bar_date - prev_bar) > %(gap_days)s
        )
        SELECT v.symbol, v.boundary_date, v.prior_last_bar, v.gap_days
        FROM voids v
        LEFT JOIN shdb.security_ticker_boundary b
          ON b.symbol = v.symbol AND b.boundary_date = v.boundary_date
        WHERE b.symbol IS NULL
        ORDER BY v.gap_days DESC
    """, {"gap_days": gap_days})

    if drift:
        symbols = sorted({r["symbol"] for r in drift})
        findings.append(Finding(
            rule_id="R011-ticker-reuse",
            severity="warning",
            database="shdb",
            table="shdb.security_ticker_boundary",
            summary=(
                f"{len(drift)} universe void(s) > {gap_days}d NOT in the boundary "
                f"table (stale?): {', '.join(symbols[:8])}"
                + (" …" if len(symbols) > 8 else "")
            ),
            detail=(
                f"R011 independently found {len(drift)} trading void(s) > {gap_days} "
                "calendar days in shdb.stock_price_1d over the active investable "
                "universe that are absent from shdb.security_ticker_boundary. The "
                "boundary table is likely stale relative to the latest harvest."
            ),
            affected_symbols=len(symbols),
            sample=[
                {
                    "symbol": r["symbol"],
                    "boundary_date": str(r["boundary_date"]),
                    "prior_last_bar": str(r["prior_last_bar"]),
                    "gap_days": r["gap_days"],
                }
                for r in drift[:max_samples]
            ],
            recommendation=(
                "Re-run `mdc security-identity boundaries` to refresh "
                "masd.security_ticker_boundary (the shdb view is a live FDW mirror, "
                "so it updates immediately). Then re-audit."
            ),
        ))

    return findings
