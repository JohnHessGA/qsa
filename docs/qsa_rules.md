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

## Adding or tuning a rule

1. Add a module under `src/qsa/rules/` exposing `def check(*, masd, shdb,
   mefdb, app_cfg) -> list[Finding]`.
2. Register it in `src/qsa/rules/__init__.py::ALL_RULES` with a stable
   canonical ID (`Rxxx-short-name`).
3. If the rule needs configuration, add it to `config/qsa.yaml` and read it
   via `app_cfg`.
4. Run `qsa audit qualitative --rules Rxxx --stdout` to inspect findings,
   then run a full audit and commit the new dated baseline under `reports/`.
