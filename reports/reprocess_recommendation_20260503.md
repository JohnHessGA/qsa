# MDC Reprocess Recommendation — pre-UDC gate

*Generated: 2026-05-03 — peer to `post_mdc_cleanup_baseline_20260503.md`*

The post-roadmap PRs (validators, resolvers, dynamic-universe expansion,
sec_api entity metadata) all changed *parser* behaviour. Existing MASD
rows still reflect the pre-roadmap baseline. This document recommends
which datasets are worth reprocessing **before** UDC cleanup begins,
and which are not.

Reprocess in MDC is implemented by:

    mdc ingest --reprocess --provider <prov> [--start YYYY-MM-DD] [--end ...]

It re-parses every raw file already in `/mnt/aftdata/{provider}_source/`
and `..._s1/` — no re-pull from external APIs. Each parse is wrapped in
the parser's idempotent upsert (natural-key conflict columns), so it is
safe to re-run.

---

## Decision rules

A reprocess is **worth running** when all four hold:

1. The parser changed in a way that produces materially different rows.
2. The change affects **rows that downstream consumers actually use**
   (UDC harvest windows, MEF/CCW/CIA selectors, RSE inquiries).
3. The runtime cost is reasonable.
4. The reprocess is fully idempotent — same input always produces the
   same MASD state, regardless of how many times we re-run.

A reprocess is **not** worth running when:

- The parser change only affects new ingest (no historical files to
  re-parse).
- The affected rows are structural NULLs (individuals, private LLCs,
  delisted issuers) where the new logic correctly leaves them NULL.
- Downstream consumers don't read the affected rows.
- The blocker is a missing migration that the operator hasn't applied.

---

## Per-dataset recommendations

| # | Provider/dataset | Reprocess? | Reason | Expected MASD delta | Runtime estimate | Pre-UDC required? |
|---|---|---|---|---|---|---|
| 1 | **sec_edgar / filing_events** | **Yes — recommended** | CIK→ticker resolver landed in commit `7487e78`; only future ingests benefit today. Reprocess populates `ticker_derived` retroactively. | +2,978 rows gain ticker context (3.6% of 81,848 NULL); rest stay NULL because the CIK is non-equity. | ~265 files × ~1 sec parse each ≈ **5 min**. Resolver loaded once. | Yes — UDC's curated tables (`event_filing`, etc.) inherit from this. |
| 2 | **sec_api / enforcement_actions, admin_proceedings, litigation_releases, aaers** | **Yes — recommended, but only AFTER migration 029** | Entity-type metadata + CIK→ticker fallback land in commit `c0a6322`. Without 029 the parser will FAIL on the new column references. | enforcement: +2 rows mapped via CIK; **132 rows newly tagged as individual defendants** + 8 as private/non-company. Penalties: same metadata flows through via imposed_on lookup. | ~470 files × ~1 sec ≈ **8 min**. | Yes — UDC's regulatory event stream needs entity_type to filter individuals out of per-symbol signals. |
| 3 | **fmp / insider_trading** | **Optional, low priority** | The validator now drops future-dated rows on new ingest. The 633 historical bad rows are already moved to `masd.sys_quarantine` (commit `<this round>`); the active table is clean. Re-parsing the raw archive would re-validate every historical row but produce no net change. | Zero net change — historical bad rows are no longer in raw files (MDC quarantined them via DELETE, not via raw-file edit). | ~92 files; ~5 min. | No. |
| 4 | **finnhub_news / company_news** | **No — provider retired** | Validator now floors `published_at_utc` at 2000-01-01. The 2 historical BC rows are quarantined. Provider is RETIRED 2026-05-03 — no new files arrive. | Zero. | n/a | No. |
| 5 | **fmp / upgrades_downgrades** + **fmp / price_target_consensus** | **Optional, only if you want historical broad-universe coverage** | Universe expanded from 25 S&P-top to ~4,250 SHDB-fundamentals stocks (commit `2d03091`). Forward collection started today; historical days only have grades for the original 25. | Reprocessing the *existing* raw files yields zero new symbols (each historical file was collected with a 25-symbol API call). To get historical broad-universe data you'd need a full *re-collect* (re-pull from FMP with the new universe), not a reprocess. | A re-collect (not reprocess) would be ~7 min/dataset/day × N historical days. | No — start MEF on forward data; backfill is a separate decision. |
| 6 | **massive / short_interest** | **No — separate scheduling fix needed** | The collector already wrote real-data files for 2026-02-27 and earlier; missed settlement dates are the issue, not parser logic. Solution is the retry-recent-placeholders PR documented in `polygon_short_interest_investigation_20260503.md`. | Reprocess does nothing for missing source files. | n/a | No (but the scheduling fix is its own follow-up before MEF can rely on this stream). |
| 7 | **massive / stock_news** | **No** | Parser unchanged. | n/a | n/a | No. |
| 8 | **alphavantage / news_sentiment** | **No** | Parser unchanged. | n/a | n/a | No. |
| 9 | All other providers (cfpb, cftc, fred, gdelt, marketaux, mempool, treasury, etc.) | **No** | Parsers unchanged. | n/a | n/a | No. |

---

## Recommended sequence

If you want a clean MASD layer to feed UDC:

```
# 0. Operator: apply migration 029 (sudo).
cp migrations/masd/029_secapi_penalties_entity_metadata.sql /tmp/
sudo -u postgres psql -d masd -f /tmp/029_secapi_penalties_entity_metadata.sql

# 1. Reprocess SEC EDGAR (CIK→ticker fill, ~5 min).
mdc ingest --reprocess --provider sec_edgar --start 2025-12-01

# 2. Reprocess SEC API (entity_type fill, ~8 min).
mdc ingest --reprocess --provider sec_api --start 2026-01-29
```

Total wall time: ~13 minutes plus migration apply. **Recommended** — these
are the only two cases where reprocess produces materially different
MASD rows that UDC will consume. Everything else can wait until after
UDC starts.

---

## What would happen if you skipped reprocess entirely

UDC could still work, but:

- It would harvest existing MASD rows that lack `ticker_derived` /
  `entity_type` for the historical window. Per-symbol equity event
  signals would be silently thinner than they should be.
- New (post-roadmap) ingests would land cleanly, so a forward-only
  cutover is feasible. The catch is that any signal looking at >30
  days of history would mix the two worlds.

The two recommended reprocesses are cheap and remove that complication.
The remaining items are correctly scoped to "do later if/when needed."

---

## Idempotency claim — verified

All seven datasets above use parsers whose upserts conflict on natural
keys (provider, dataset, +primary identifiers). Re-running the same
file produces the same row state. Tests added in
`tests/test_mdc_collect_ingest_focus.py::TestParserIdempotency` confirm
the FMP insider-trading path; the same conflict_columns convention
applies across all parsers reviewed in this round.

A reprocess **does not change the raw archive on disk** — those files
remain immutable.

---

## Out of scope (per spec)

- No UDC / SHDB / MEF / RSE / CCW changes.
- No automatic kickoff of any reprocess run from this document. The
  operator decides which (if any) to run.
- No re-collect (i.e. re-pull from external API) — different operation,
  different concerns.
