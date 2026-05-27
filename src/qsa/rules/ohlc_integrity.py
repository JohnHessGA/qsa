"""R010 — OHLC price-bar integrity (AFT investable universe).

QSA's first *quantitative* rule. It scans the curated mart price tables for
the AFT investable universe of stocks and ETFs and flags bars whose OHLC
values are impossible or implausible.

The motivating defect: ``mart.stock_etf_daily`` SPY 2026-02-02 carried
``low = 69.005`` against an open/close near 690 — a dropped-digit/misplaced-
decimal error that passed every existing check (it is still <= open/close, so
ordering holds, and the close-to-close return is unaffected so UDC's
return-outlier flag never fired) and propagated verbatim into every
downstream consumer. The same scan surfaced VZ 2026-01-08 (low 10.60 vs ~40)
and UBS 2022-08-30 (low 0.92 vs ~16).

Sub-checks (deterministic, no LLM):

  * **ordering invariant** — ``low <= min(open,close)``, ``high >= max(open,
    close)``, ``low <= high``, all four ``> 0``. ``critical``. Zero false
    positives by construction; catches impossible bars (e.g. low > open).
  * **dropped-digit low** — ``low < low_factor * min(open,close)``.
    ``critical``. Catches SPY / VZ / UBS; zero false positives across the AFT
    universe over all history once scoped to liquid names.
  * **high spike / wide range** — ``high > high_factor * max(open,close)`` or
    ``high/low > range_factor``. ``warning`` only — these fire on genuine
    micro-cap / SPAC intraday volatility, so they are reported as *suspect*,
    not as a cron-gating critical.

Scope is restricted to ``shdb.v_investable_universe_active`` (stocks + ETFs)
so the plausibility checks stay clean — the false positives that would
otherwise swamp this rule are all sub-$5 micro-caps that are not in the AFT
universe. The target tables are the mart front-door consumers actually read;
the silver ``*_price_1d`` tables can be added to ``targets`` in
``config/qsa.yaml`` later without code changes.
"""

from __future__ import annotations

import re
from typing import Any

from qsa.db import fetch_dicts
from qsa.finding import Finding

# Default scan targets if `ohlc_integrity.targets` is absent from qsa.yaml.
# Each entry: schema-qualified mart table + its asset_type in
# shdb.v_investable_universe_active.
_DEFAULT_TARGETS: list[dict[str, str]] = [
    {"table": "mart.stock_equity_daily", "asset_type": "stock"},
    {"table": "mart.stock_etf_daily", "asset_type": "etf"},
]

_DEFAULT_LOW_FACTOR = 0.5     # low < low_factor * min(open,close)  -> dropped-digit low (critical)
_DEFAULT_HIGH_FACTOR = 2.0    # high > high_factor * max(open,close) -> high spike (warning)
_DEFAULT_RANGE_FACTOR = 2.0   # high/low > range_factor              -> wide intraday range (warning)
_DEFAULT_MAX_SAMPLES = 25

_TABLE_RE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")


def _classify(
    o: float, h: float, l: float, c: float,
    *, low_factor: float, high_factor: float, range_factor: float,
) -> tuple[str, str] | None:
    """Classify one OHLC bar. Returns (severity, violation) or None if clean.

    Pure function (no DB) so the invariant logic is unit-testable. Mirrors the
    SQL WHERE in :func:`check`; every row that SQL returns must classify to a
    non-None severity here.
    """
    # Ordering invariant — impossible bar (also catches non-positive values).
    if not (l <= min(o, c) and h >= max(o, c) and l <= h and o > 0 and h > 0 and l > 0 and c > 0):
        return ("critical", "ordering invariant violated (require low <= min(open,close), "
                             "high >= max(open,close), low <= high, all > 0)")
    if l < low_factor * min(o, c):
        return ("critical", f"low {l:g} < {low_factor:g}x min(open,close) {min(o, c):g} "
                            f"— implausible drop, likely dropped-digit / misplaced decimal")
    if h > high_factor * max(o, c):
        return ("warning", f"high {h:g} > {high_factor:g}x max(open,close) {max(o, c):g} "
                          f"— suspicious high spike (may be real volatility)")
    if h / l > range_factor:
        return ("warning", f"intraday range high/low = {h / l:.2f} > {range_factor:g}x "
                          f"— wide bar (often genuine micro-cap volatility)")
    return None


def _bar_sample(row: dict[str, Any], violation: str) -> dict[str, Any]:
    return {
        "symbol": row["symbol"],
        "bar_date": str(row["bar_date"]),
        "open": row["open"],
        "high": row["high"],
        "low": row["low"],
        "close": row["close"],
        "prev_close": row["prev_close"],
        "next_close": row["next_close"],
        "violation": violation,
    }


def check(*, masd, shdb, mefdb, app_cfg: dict[str, Any]) -> list[Finding]:
    cfg = app_cfg.get("ohlc_integrity") or {}
    targets = cfg.get("targets") or _DEFAULT_TARGETS
    low_factor = float(cfg.get("low_factor", _DEFAULT_LOW_FACTOR))
    high_factor = float(cfg.get("high_factor", _DEFAULT_HIGH_FACTOR))
    range_factor = float(cfg.get("range_factor", _DEFAULT_RANGE_FACTOR))
    max_samples = int(cfg.get("max_samples", _DEFAULT_MAX_SAMPLES))

    findings: list[Finding] = []

    for target in targets:
        table = target["table"]
        asset_type = target["asset_type"]
        if not _TABLE_RE.match(table):
            raise ValueError(f"ohlc_integrity target table is not a safe schema.table identifier: {table!r}")

        # Universe-scoped scan with neighbour closes; SQL returns only the bars
        # that trip at least one check (the window runs over the ~few-hundred
        # universe symbols, so this is cheap despite the multi-million-row mart).
        sql = f"""
            WITH scoped AS (
                SELECT p.symbol, p.bar_date, p.open, p.high, p.low, p.close,
                       lag(p.close)  OVER w AS prev_close,
                       lead(p.close) OVER w AS next_close
                FROM {table} p
                JOIN shdb.v_investable_universe_active u
                  ON u.symbol = p.symbol AND u.asset_type = %(atype)s
                WHERE p.open IS NOT NULL AND p.high IS NOT NULL
                  AND p.low IS NOT NULL AND p.close IS NOT NULL
                WINDOW w AS (PARTITION BY p.symbol ORDER BY p.bar_date)
            )
            SELECT symbol, bar_date, open, high, low, close, prev_close, next_close
            FROM scoped
            WHERE NOT (low <= least(open, close) AND high >= greatest(open, close)
                       AND low <= high AND low > 0 AND high > 0 AND open > 0 AND close > 0)
               OR (low > 0 AND low < %(low_factor)s * least(open, close))
               OR (high > %(high_factor)s * greatest(open, close))
               OR (low > 0 AND high / low > %(range_factor)s)
            ORDER BY bar_date DESC
        """
        params = {
            "atype": asset_type,
            "low_factor": low_factor,
            "high_factor": high_factor,
            "range_factor": range_factor,
        }
        rows = fetch_dicts(shdb, sql, params)

        # Bucket each offending bar by its (most severe) classification.
        buckets: dict[str, list[dict[str, Any]]] = {"critical": [], "warning": []}
        for row in rows:
            verdict = _classify(
                row["open"], row["high"], row["low"], row["close"],
                low_factor=low_factor, high_factor=high_factor, range_factor=range_factor,
            )
            if verdict is None:
                continue  # defensive: SQL and _classify should agree
            severity, violation = verdict
            buckets[severity].append(_bar_sample(row, violation))

        for severity, bars in buckets.items():
            if not bars:
                continue
            symbols = sorted({b["symbol"] for b in bars})
            if severity == "critical":
                summary = (f"{len(bars)} impossible/implausible OHLC bar(s) in {table} "
                           f"(AFT {asset_type} universe): {', '.join(symbols[:8])}"
                           + (" …" if len(symbols) > 8 else ""))
                recommendation = (
                    "Almost certainly dropped-digit / misplaced-decimal corruption that "
                    "entered the silver *_price_1d table and propagated to mart. Correct the "
                    "source bar via UDC ingest (and populate data_quality_flag), then rebuild "
                    "the mart. These bars distort support/resistance, drawdown, 30-day "
                    "high/low, Bollinger bands and volatility for every downstream consumer."
                )
            else:
                summary = (f"{len(bars)} wide/suspect OHLC bar(s) in {table} "
                           f"(AFT {asset_type} universe): {', '.join(symbols[:8])}"
                           + (" …" if len(symbols) > 8 else ""))
                recommendation = (
                    "Suspect-only: a wide intraday range or high spike often reflects genuine "
                    "micro-cap / SPAC volatility rather than corruption. Eyeball against the "
                    "neighbour closes; escalate only if the value fails to revert."
                )

            findings.append(Finding(
                rule_id="R010-ohlc-integrity",
                severity=severity,
                database="shdb",
                table=table,
                summary=summary,
                detail=(
                    f"Scanned {table} restricted to the active AFT {asset_type} universe "
                    f"(shdb.v_investable_universe_active). Thresholds: low<{low_factor:g}x "
                    f"min(o,c), high>{high_factor:g}x max(o,c), high/low>{range_factor:g}x."
                ),
                affected_rows=len(bars),
                affected_symbols=len(symbols),
                sample=bars[:max_samples],
                recommendation=recommendation,
            ))

    return findings
