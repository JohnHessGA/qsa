# AFT Qualitative-Signal Cleanup — Completion Note

*Generated: 2026-05-03. Final artefact of the qualitative-cleanup sequence
that began with `qsa_audit_20260503.md` and ran across MDC, MASD, UDC,
SHDB, and QSA.*

This note records the final clean baseline and the decisions that got us
here. It is intentionally short — the deeper rationale for each step
already lives in the per-round commit messages and prior reports.

---

## Final QSA category counts

```
🛠  Active defects        0   ✅
👀 Monitoring             1   (Polygon short_interest scheduling — known)
🗄  Retired sources      14   (Finnhub + 3 retired sources — known)
📐 Structural / by-design 5   (SEC API + EDGAR — explained NULLs)
📊 Coverage info         38   (informational)

Total findings:          58   (severity 6 critical / 16 warning / 36 info)
```

The 6 critical and 16 warning entries all live in the *Coverage* or
*Retired* buckets. None is an active defect. **Zero active defects** is
the first time the audit has hit that state.

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

## Remaining monitoring item

**`massive/short_interest` — last real data 2026-02-27 (65+ days).**

Diagnosed in `polygon_short_interest_investigation_20260503.md`. Not a
provider outage / endpoint move / entitlement change / MDC code
regression — the collector queries `settlement_date=today` while FINRA
publishes short-interest reports with a ~12 calendar-day lag, and
nothing currently re-runs collection for those placeholder dates once
FINRA publishes.

Two reasonable fix shapes documented in the investigation report:

- **Option A (preferred)** — `mdc backfill --retry-placeholders` pass
  that walks recent `__mdc_no_data__` files and re-runs the per-date
  collector if the source now has data. Generic; reusable for any future
  publication-lag dataset.
- **Option B** — query `settlement_date = today − 14 days` directly. Simpler
  but couples this dataset's filename convention to its publication
  cadence in a way no other dataset uses.

Estimated effort: ~50 lines + tests + a one-off backfill run for the
~65 missed days. Self-contained and ready whenever convenient.

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

- `JohnHessGA/mdc`: `6a2d685` (docs catch-up after `a0c3973` filer-type tagging)
- `JohnHessGA/udc`: `f6e823a` (sec_penalties entity metadata propagation)
- `JohnHessGA/qsa`: `1481d9f` (post-UDC verification audit)

The qualitative cleanup phase is closed. Ready for design.
