# Proposed rule R011 — ticker-reuse / spliced price series

**Date:** 2026-06-02
**Status:** Proposed (not yet implemented)
**Motivation:** RSE inquiry I-000189 ("stocks up >100% over 2 years") returned
ALF, BBBY, AKTS as ~9,000% gainers because their `shdb.stock_price_1d` series
splice **two different companies** under one `security_id` (a delisted issuer's
ticker reused by a new company). Full cross-system design + the staged
MDC→UDC→consumer fix (this rule is the detection/guard slice):
`~/repos/aft-platform/docs/platform/security-identity-and-ticker-reuse.md`.

R011 is the **detection/guard** half: QSA finds existing spliced series (so UDC
can remediate and downstream consumers can pre-prune) and flags new ones on each
weekly run. It does not fix the data (QSA writes no DB) — it reports.

## What it detects

A single `security_id` in `shdb.stock_price_1d` (and the sibling `adr_price_1d`,
`etf_price_1d`) whose bars actually belong to **more than one issuer** — i.e. the
ticker was reassigned. Two complementary detection strategies; run both, dedupe
by `security_id`.

### Strategy A — intrinsic (no security master needed)

Scan each symbol's daily series for the splice signature:

1. a **trading gap** of more than `gap_trading_days` (default ~60 trading days /
   ~3 months) with no bars, **and**
2. a **split-unadjusted level discontinuity** across the gap — the first
   `close` after the gap differs from the last `close` before it by more than
   `level_jump_ratio` (default ≥ 5×, in either direction), after dividing out any
   `cumulative_split_factor` change so real splits are not mistaken for a swap.

Both conditions together are the high-precision signal. A gap alone can be a
trading halt; a jump alone can be a real move; gap **plus** a 5–100× level
change is a company swap. Confirmed cases (BBBY ~$0.38→$9.99 after ~2y gap; ALF
$0.94→$10.01; AKTS $0.076→$17.07) all clear this easily.

### Strategy B — authoritative (cross-check the security master)

QSA already reads MASD, which holds the point-in-time security master UDC is not
yet applying to prices:

- `masd.dim_security_ticker` — effective-dated `(symbol, security_id, valid_from,
  valid_to, change_reason)`.
- `masd.dim_security` — `composite_figi`, `share_class_figi`, `cik`,
  `successor_security_id`, `status`.

Flag a `security_id` when the span of its `stock_price_1d` bars crosses a
boundary where the **effective ticker→security mapping changes**, or where the
issuer's `composite_figi` / `cik` changes within the bar span. This is exact (no
thresholds) wherever the master has the entity split recorded; Strategy A is the
fallback when the master itself is incomplete (e.g. ALF/Centurion carry no FIGI).

## Finding shape

One `Finding` per affected `security_id`/symbol:

```python
Finding(
    rule_id="R011-ticker-reuse",
    severity="warning",            # critical if the symbol is in the AFT investable universe
    database="shdb",
    table="shdb.stock_price_1d",
    summary=f"{symbol}: price series splices >1 issuer (ticker reuse)",
    detail=(
        f"Gap {gap_days}d ending {gap_end}; level {pre_close} -> {post_close} "
        f"({ratio:.0f}x). dim_security_ticker: {old_sid} [{vf1}..{vt1}] -> "
        f"{new_sid} [{vf2}..]. composite_figi {old_figi} -> {new_figi}."
    ),
    affected_symbols=1,
    sample=[...],                  # the boundary bars
    recommendation=(
        "Re-key the price series by effective-dated dim_security_ticker so the "
        "old issuer's bars end at valid_to (UDC fix). Until then, long-horizon "
        "return consumers should gap-guard the anchor lookup."
    ),
)
```

## Severity

- **warning** by default (these are uncommon and not data-shape-invalid).
- **critical** when the affected symbol is in `shdb.v_investable_universe_active`
  — a spliced series there poisons MEF/CCW/GDE/RSE return features and should
  gate the weekly exit code, matching R010's universe-scoped posture.

## Scope & config

- **Tables:** `shdb.stock_price_1d`, `shdb.adr_price_1d`, `shdb.etf_price_1d`.
- **Universe:** start scoped to `v_investable_universe_active` (like R010, to keep
  runtime bounded and findings actionable), with an opt-in `--full` for the whole
  price universe.
- **Config keys:** `gap_trading_days` (60), `level_jump_ratio` (5.0),
  `restrict_to_investable` (true).
- **Source:** new `src/qsa/rules/ticker_reuse.py`; register in the rule list and
  add an R011 section to `docs/qsa_rules.md`.

## Relationship to existing rules

- **R010 (ohlc-integrity)** checks bar-level OHLC sanity within a series; R011
  checks *cross-time identity* of the series. Complementary — R010 would pass a
  spliced series (each bar is individually valid).
- **R006 (staleness)** flags series that stop; R011 flags series that stop *and
  resume as a different company*.

## Limitations

- Strategy A can theoretically false-positive on a legitimate long halt followed
  by a real gap-up; requiring both gap **and** ≥5× level change makes this rare,
  and Strategy B disambiguates when the master has the entity split.
- Detection is only as complete as MASD's security master for Strategy B; Strategy
  A covers the gaps (e.g. SPAC tickers with no FIGI).
