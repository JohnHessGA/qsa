# AFT Qualitative-Signal Cleanup — Completion Note

*Generated: 2026-05-03. Final-final update: 2026-05-04 after the
short_interest scheduling fix landed and the lone monitoring item closed.*

*This note records the final clean baseline and the decisions that got us
here. It is intentionally short — the deeper rationale for each step
already lives in the per-round commit messages and prior reports.*

---

## Final QSA category counts (2026-05-04, post short_interest recovery)

```
🛠  Active defects        0   ✅
👀 Monitoring             0   ✅
🗄  Retired sources      14   (Finnhub + 3 retired sources — known)
📐 Structural / by-design 5   (SEC API + EDGAR — explained NULLs)
📊 Coverage info         38   (informational)

Total findings:          57
```

**Both Active and Monitoring are zero.** The 14 retired-source and 38
coverage-info entries are informational by design. The 5 structural
findings are explained NULLs (SEC API individuals; SEC EDGAR Form 4
insiders). For the first time, every single finding in the audit has a
known explanation.

---

## Sources retired during the cleanup

| Source | Reason | Date |
|---|---|---|
| `finnhub_news` (3 datasets) | Free tier limited value; paid sentiment $3K/mo not justified; redundant with AlphaVantage / FMP / SEC EDGAR | 2026-02-15 disabled, formally retired 2026-05-03 |
| `aaii / sentiment_survey` | Imperva bot protection blocks scripted access; no paid tier justifies cost | 2026-02 disabled, retired 2026-05-03 |
| `coingecko / crypto_daily` | Superseded by `coingecko/crypto_market_daily` (same provider, richer data) | 2026-05-03 |
| `yahoo / us_stocks_daily` | Superseded by `massive/us_stocks_daily` (Polygon) since 2026-02-09 | 2026-05-03 |

All four are now provider/dataset-disabled in MDC config, suppressed in
QSA's `no_data_alerting` block, and excluded from coverage / staleness
rules. Historical raw files and MASD rows were preserved for lineage in
every case — the parser/provider code stays dormant rather than deleted
so re-enable is possible if circumstances change. Re-enable policies are
documented in each retired provider's YAML header.

---

## Invalid rows quarantined

A new MASD-wide quarantine convention shipped on 2026-05-03 (migration
`030_sys_quarantine.sql` + `mdc quarantine` CLI). Every row carries its
full payload as JSONB plus a JSON-encoded primary key, a rule_id, and a
reason — fully reversible, fully auditable.

| rule_id | Source table | Rows | Reason |
|---|---|---:|---|
| `R002-future-dates` | `masd.fmp_stocks_insider_trades` | 633 | `bar_date > CURRENT_DATE`, max date `2031-03-03` |
| `R001-invalid-timestamps` | `masd.finnhub_news_articles` | 2 | `published_at_utc` NULL or pre-2000 (BC-era sentinel) |
| **Total** | | **635** | |

The MDC parser-side validators (commit `05ef483`) prevent new invalid
rows from arriving; the quarantine action cleaned up the historical
backlog. Both QSA rules dropped from "1 finding each" to "0 findings"
after the action.

---

## SEC / EDGAR NULL-symbol explanation

The biggest "apparent defect" turned out to be largely structural. Rather
than try to force-map symbols onto rows that legitimately have none, the
platform now records WHY each NULL exists — and QSA reads those tags to
classify findings correctly.

### MDC tagging at ingest

Two small schema additions on the MASD side make the explanation explicit:

| Migration | Table | New columns | Purpose |
|---|---|---|---|
| `029_secapi_penalties_entity_metadata.sql` | `masd.secapi_regulatory_penalties` | `entity_type`, `entity_role`, `cik` | Mirrors the schema already on `secapi_regulatory_enforcement`. |
| `031_sec_edgar_filer_type.sql` | `masd.sec_edgar_filing_events` | `filer_type`, `ticker_mapping_status`, `mapping_reason` | Form 4 / 4-A → `filer_type='person'` (cik refers to the insider, not a tradable entity). 8-K → `public_company`. SCHEDULE 13D/G → `subject_company`. |

### Final distribution after reprocess

**SEC API enforcement** (597 rows): 312 `company`, 270 `individual`,
6 `fund`, 4 `other`, 1 each `agency`/`system`, 3 NULL.

**SEC API penalties** (130 rows post-reprocess): 109 `individual`,
14 `company`, 7 unmatched.

**SEC EDGAR filing events** (154,112 rows):

| filer_type | mapping_status | rows |
|---|---|---:|
| person | non_equity_filer | **100,097** *(structurally NULL)* |
| person | source_provided | 160 |
| public_company | source_provided | 29,628 |
| public_company | cik_resolved | 3,452 |
| public_company | delisted_or_unmapped | 5,603 |
| public_company | ambiguous | 2,335 |
| subject_company | source_provided | 9,672 |
| subject_company | cik_resolved | 920 |
| subject_company | delisted_or_unmapped | 1,192 |
| subject_company | ambiguous | 1,053 |

**Net effect on QSA:**
- `sec_edgar_filing_events` actionable-missing: **110,218 → 0** (every
  NULL is now classified)
- `secapi_regulatory_penalties` / `enforcement`: severity dropped from
  critical/warning to **info** (most NULLs are individuals / private
  entities)

QSA's R003-missing-symbols rule runtime-probes for `entity_type` and
`filer_type` columns and applies the right filter automatically — robust
to future schema additions.

---

## UDC `sec_penalties` propagation

Closed the last active defect on 2026-05-03 via UDC migration `045` +
builder update. The curated `shdb.sec_penalties` table now carries the
same `entity_type` / `entity_role` / `cik` columns its MASD source
gained from migration 029.

| | Before | After |
|---|---:|---:|
| total rows | 43 | 55 |
| NULL symbol | 43 | 53 |
| `entity_type` populated | n/a (column missing) | 53 |
| `individual` | 0 | 46 |
| `company` | 0 | 7 |
| QSA active-defect status | **critical** | **none** |

Builder is idempotent (`ON CONFLICT DO UPDATE` refreshes the entity
metadata so re-harvests pick up newly-resolved values from MDC). The
migration also documents the FDW-refresh pattern (`DROP FOREIGN TABLE
... + IMPORT FOREIGN SCHEMA LIMIT TO ...`) for future incremental MASD
schema bumps.

---

## Polygon short_interest — closed 2026-05-04

The lone monitoring item from the 2026-05-03 baseline has been resolved.

Root cause was a publication-lag mismatch: the daily collector queried
`settlement_date=today` while FINRA publishes short-interest reports
~T+8 business days after settlement; nothing re-ran collection for the
placeholder dates once FINRA published.

Fix shipped (`JohnHessGA/mdc` commit `e430282`): new top-level CLI
`mdc retry-placeholders` that walks `masd.sys_raw_file` for
placeholder rows in a `[today − max_age, today − lag]` window, re-runs
the provider's `collect()` per candidate date, and overwrites the
placeholder when real data lands. Conservative default lag floor
(12 calendar days) and 60-day max-age cap; idempotent; only candidates
verified as placeholders get retried.

One-off recovery run results:

  Candidates in window:    49
  Recovered (real data):    3   (2026-03-13, 2026-03-31, 2026-04-15)
  Still empty:             46   (non-settlement dates, correctly so)
  Failed:                   0

After ingest + UDC SHDB refresh:

  masd.massive_stocks_short_int  MAX(settlement_date)  2026-02-27 → 2026-04-15
  shdb.stock_short_interest      MAX(settlement_date)  2026-02-27 → 2026-04-15

QSA `R006-staleness` cadence label for `stock_short_interest` was
tuned from `daily` (5d threshold) to a new `bi_monthly_lagged` cadence
(21d threshold) so the rule no longer fires on dates that are within
FINRA's normal publication-lag window. This mirrors MDC's
`no_data_alerting` rule for the same dataset.

Outstanding question for the long term: **scheduling**. The recovery
command is operator-driven for now. A future cron entry would invoke
it daily for any (provider, dataset) pair with a known publication-lag
pattern. We chose to defer cron until we see one full cycle of
operator-driven runs against this and any other dataset that benefits
from the pattern. No action required to start the next phase.

---

## What follows the cleanup

The data layer is now clean enough for product-shaped work to begin.
Three reasonable directions, each well-defined and independent:

1. **Signal-confidence design.** The cleaned, self-describing data
   layer (entity_type / filer_type / mapping_status / quarantine
   audit-trail) is exactly the substrate a confidence model needs.
   Downstream consumers (MEF, RSE, CCW) can filter populations
   correctly without re-deriving classification logic. Recommended
   first design output: a per-source confidence rubric covering
   freshness, coverage, mapping certainty, and structural-vs-actionable
   tagging.
2. **Canonical qualitative-signal mart design.** A Level-2 mart over
   the curated SHDB layer, optimised for application-stream
   consumption. The existing `mart.stock_equity_daily` is the
   structural template. The qualitative mart would aggregate:
   sentiment (news_ticker_sentiment_1d), insider activity
   (insider_conviction_signals), regulatory events (sec_enforcement
   filtered to entity_type=company), congressional activity
   (congress_activity_signals), short-interest (once Polygon scheduling
   is fixed), and any others the user decides to include.
3. **Source expansion review.** Some sources we examined are thin
   (Marketaux delivering ~7 articles/day vs 2,000/day cap; FMP
   senate_trading sparse). A focused review of source quality vs cost
   for a few specific gaps would inform the next contract cycle.

Pick whichever fits your current goals; the cleanup baseline supports
all three.

---

## Reference — final commit hashes

- `JohnHessGA/mdc`: `e430282` (mdc retry-placeholders + short_interest recovery)
- `JohnHessGA/udc`: `f6e823a` (sec_penalties entity metadata propagation)
- `JohnHessGA/qsa`: this commit (R006 cadence tuning for short_interest +
  post-recovery audit + this updated completion note)

The qualitative cleanup phase is closed. **Active: 0, Monitoring: 0.**
Ready for design.
