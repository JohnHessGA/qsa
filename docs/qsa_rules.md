# QSA — Rule Catalog

Each rule lives in `src/qsa/rules/` and exposes a single function:

```python
def check(*, masd, shdb, mefdb, app_cfg) -> list[Finding]
```

The audit orchestrator opens read-only connections once and passes them to
every rule. Rules return zero or more `Finding` records. A rule that raises
is captured as a single `critical` `(rule-error)` finding; the rest of the
audit continues.

## Severity ladder

- **critical** — invalid data shape, exceptions, future timestamps in
  business-meaningful tables. Drives exit code `1`.
- **warning** — quality issues to track over time (staleness, thin coverage,
  deprecated tables with live consumers).
- **info** — informational signals (sparse-expected coverage, deprecated
  tables with no live consumer, etc.). Does not affect exit code.

## Rules

### R001 — invalid-timestamps

Flags rows whose primary date column is below `min_valid_date` (default
`2000-01-01`). Catches the historical `0001-12-31 BC` Finnhub case and
similar zero/sentinel dates that get cast into PostgreSQL as pre-modern
timestamps.

- **Severity:** critical
- **Source:** `src/qsa/rules/invalid_timestamps.py`
- **Config:** `min_valid_date`

### R002 — future-dates

Flags rows whose primary date column is more than `future_date_tolerance_days`
ahead of today. Insider-transaction dates and news publish dates should
never be in the future; a small tolerance covers normal time-zone drift.

- **Severity:** critical
- **Source:** `src/qsa/rules/future_dates.py`
- **Config:** `future_date_tolerance_days` (default 1)

### R003 — missing-symbols

Flags rows whose `symbol` does not resolve via `shdb.symbol_master`. SEC
EDGAR rows are evaluated against `filer_type` and `ticker_mapping_status`
rather than the generic symbol-master path, since many legitimate filers
(funds, foreign issuers, etc.) lack a tradable ticker.

- **Severity:** critical for clearly broken joins, warning for ambiguous
  mapping states.
- **Source:** `src/qsa/rules/missing_symbols.py`

### R004 — duplicate-keys

Flags duplicate natural keys in qualitative tables. Each table declares its
expected uniqueness vector internally; article-level tables (news) use the
article-level key, not the article-symbol cross product (the v0 bug fixed
in commit `b8734b2`).

- **Severity:** critical
- **Source:** `src/qsa/rules/duplicate_keys.py`

### R005 — orphan-rows

Flags curated rows whose parent reference no longer exists. Common shape:
SHDB derived signal rows pointing at MASD raw rows that were purged or
re-keyed.

- **Severity:** warning by default; critical when the orphan rate is high
  enough that downstream consumers will see broken joins.
- **Source:** `src/qsa/rules/orphans.py`

### R006 — staleness

Flags streams whose most recent observation is older than the cadence
threshold in `staleness_thresholds_days`. Cadences:

| Cadence              | Threshold (days) | Notes                                      |
|----------------------|-----------------:|--------------------------------------------|
| `daily`              | 5                | 1d cadence, allows weekend slack           |
| `weekly`             | 14               |                                            |
| `monthly`            | 45               |                                            |
| `quarterly`          | 130              |                                            |
| `bi_monthly_lagged`  | 21               | FINRA short interest — settles ~24×/year   |
|                      |                  | (15th + EOM), publishes ~T+8 business days.|
|                      |                  | Mirrors MDC's `massive/short_interest`     |
|                      |                  | 21/45 no-data alerting window.             |

- **Severity:** warning when past threshold, critical when far past it.
- **Source:** `src/qsa/rules/staleness.py`

### R007 — deprecated-tables

Each entry in `deprecated_tables` (in `qsa.yaml`) is reported, and QSA also
greps the repos in `consumer_grep_repos` for textual references to
`schema.table` to surface live consumers.

- **Severity:** warning when a live consumer is found, info when no
  consumer is found anywhere on disk.
- **Source:** `src/qsa/rules/deprecated.py` + `src/qsa/consumers.py`
- **Currently deprecated (2026-05-04):**
  - `shdb.insider_activity_signals` → `shdb.insider_conviction_signals`
  - All `masd.finnhub_*` tables (provider retired 2026-05-03) → AlphaVantage
    news / FMP insider / SEC EDGAR replacements.
  - `shdb.insider_mspr_1m`, `shdb.insider_mspr_signals` →
    `shdb.insider_conviction_signals`.

### R008 — mef-coverage

For tables expected to be per-symbol broad, computes coverage against MEF's
305-stock universe (`mef.universe_stock`):

| Tier                | Coverage    | Severity                                   |
|---------------------|-------------|--------------------------------------------|
| healthy             | ≥ `warn_below_pct`     | (no finding)                    |
| warn                | < `warn_below_pct`     | warning                         |
| critical            | < `critical_below_pct` | critical                        |
| `sparse_expected`   | n/a                    | info — table is inherently sparse (sec_enforcement, congress_trades, cfpb_complaints) |

- **Source:** `src/qsa/rules/mef_coverage.py`
- **Config:** `mef_coverage.warn_below_pct` (default 50), `critical_below_pct`
  (default 25).

### R009 — thin-coverage

Cross-cuts R008 by flagging tables whose absolute row/symbol counts are too
low to support analysis even if MEF-coverage isn't the right framing.

- **Severity:** warning, info for sparse-expected tables.
- **Source:** `src/qsa/rules/thin_coverage.py`

### R010 — ohlc-integrity (quantitative)

QSA's first **quantitative** rule. Scans the curated mart price tables for the
**AFT investable universe** of stocks and ETFs and flags bars whose OHLC
values are impossible or implausible. Restricting to
`shdb.v_investable_universe_active` is what keeps the plausibility checks
false-positive-free — the noise that would otherwise dominate is all sub-$5
micro-caps that are not in the AFT universe.

Motivating defect: `mart.stock_etf_daily` SPY 2026-02-02 carried `low =
69.005` against an open/close near 690 — a dropped-digit error that passed
every existing check (it is still ≤ open/close, and the close-to-close return
is unaffected so UDC's return-outlier flag never fired) and propagated into
every downstream consumer. The same scan also surfaced VZ 2026-01-08
(low 10.60 vs ~40) and UBS 2022-08-30 (low 0.92 vs ~16).

Sub-checks:

| Sub-check | Condition | Severity |
|---|---|---|
| ordering invariant | `low ≤ min(o,c)`, `high ≥ max(o,c)`, `low ≤ high`, all > 0 | critical |
| dropped-digit low  | `low < low_factor · min(o,c)` | critical |
| high spike         | `high > high_factor · max(o,c)` | warning |
| wide intraday range| `high / low > range_factor` | warning |

The ordering invariant and dropped-digit-low checks gate the exit code; the
high-spike / wide-range checks are *suspect-only* because they fire on
genuine micro-cap / SPAC volatility, not corruption. Each finding includes
the offending bar's OHLC plus the neighbouring closes (`prev_close` /
`next_close`) as the reference for whether the value reverts.

- **Severity:** critical (ordering / dropped-digit low), warning (high spike /
  wide range).
- **Source:** `src/qsa/rules/ohlc_integrity.py`
- **Config:** `ohlc_integrity.targets` (schema.table + `asset_type`),
  `low_factor` (default 0.5), `high_factor` (default 2.0), `range_factor`
  (default 2.0), `max_samples` (default 25). Add the silver `*_price_1d`
  tables to `targets` to extend coverage without code changes.

### R011 — ticker-reuse

Reports the population of **ticker-reuse / long-void boundaries** — symbols
whose `shdb.stock_price_1d` series splices two different companies under one
`security_id` because a delisted issuer's ticker was later adopted by a new
company (ALF Alfi→Centurion, BBBY Bed Bath & Beyond→Beyond, AKTS
Akoustis→Aktis). A long-horizon return that anchors before the boundary
silently compares two companies — the RSE I-000189 phantom-gainer defect.

Part of the ticker-reuse initiative (Option B — lightweight boundary guard;
design SSoT `~/repos/aft-platform/docs/platform/security-identity-and-ticker-reuse.md`).
QSA detects/reports only — the guard lives in consumers (RSE return-rank). Two
parts:

| Part | What | Severity |
|---|---|---|
| boundary report (universe) | a recorded boundary on a symbol in `shdb.v_investable_universe_active` | critical |
| boundary report (other) | a recorded boundary outside the investable universe | warning |
| drift cross-check | a > `gap_trading_days` void in `shdb.stock_price_1d` over the universe that is **absent** from the boundary table (table is stale) | warning |

Reads the propagated SSOT `shdb.security_ticker_boundary` (origin
`masd.security_ticker_boundary`, seeded by `mdc security-identity boundaries`).
The universe-critical bucket gates the exit code, matching R010's posture.

- **Severity:** critical (universe boundary), warning (non-universe boundary,
  drift).
- **Source:** `src/qsa/rules/ticker_reuse.py`
- **Config:** `ticker_reuse.gap_trading_days` (default 150, drift cross-check
  threshold), `max_samples` (default 50).

## Adding or tuning a rule

1. Add a module under `src/qsa/rules/` exposing `def check(*, masd, shdb,
   mefdb, app_cfg) -> list[Finding]`.
2. Register it in `src/qsa/rules/__init__.py::ALL_RULES` with a stable
   canonical ID (`Rxxx-short-name`).
3. If the rule needs configuration, add it to `config/qsa.yaml` and read it
   via `app_cfg`.
4. Run `qsa audit --rules Rxxx --stdout` to inspect findings,
   then run a full audit; the new dated baseline lands under `artifacts_dir`
   (default `/mnt/aftdata/qsa/artifacts/YYYY/MM/`).
