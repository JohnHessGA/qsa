# AFT Qualitative Cleanup — Post-Roadmap Baseline

*Generated: 2026-05-03 — peer to `qsa_audit_20260503.md` (re-run today),
`mdc_no_data_check_20260503.txt`, `mdc_masd_review_20260503.md`,
`polygon_short_interest_investigation_20260503.md`,
`finnhub_retire_recommendation_20260503.md`*

This is the consolidated baseline after completing all seven items on the
original qualitative-cleanup roadmap. It captures **the actual state of
MASD/SHDB data right now** (not the post-reprocess potential), summarises
the fresh QSA audit + no-data-check, and proposes the next decision.

---

## TL;DR

- **Roadmap: 7/7 complete** in code, tests, docs, and migration files.
  All MDC PRs merged to `JohnHessGA/mdc`; QSA artefacts on
  `JohnHessGA/qsa`. 252/252 MDC tests passing.
- **MASD content state today is largely unchanged** from the
  2026-05-03 baseline. The roadmap's parser/validator/resolver work is
  forward-looking — it improves the next ingest, not the existing rows.
  Two operator actions are pending before MASD reflects the new logic:
  apply migration `029_secapi_penalties_entity_metadata.sql`, and run
  `mdc ingest --reprocess` for the providers that should be backfilled.
- **QSA audit: 56 findings** — same total as the original audit. Rule
  severities were left untouched per spec. The semantic meaning of many
  findings has changed (e.g. SEC API rows now have entity-type metadata
  that explains the NULL symbols), but QSA hasn't been told about it
  yet.
- **`mdc no-data-check`**: 3 critical, 0 warning, 18 info, 51 ok, 3
  suppressed. The 3 criticals are all disabled-but-not-formally-retired
  sources (`aaii`, `coingecko/crypto_daily`, `yahoo/us_stocks_daily`)
  and represent the next obvious cleanup decisions.
- **One new defect surfaced this round** that wasn't on the original
  roadmap: `shdb.news_av_ticker_sentiment` has **85,405 duplicate
  (symbol, obs_date) rows** — the UDC builder is missing an upsert.
  This is QSA finding `R004-duplicate-keys` and predates the cleanup
  sequence; it just hasn't been addressed yet.
- **One blind spot in `mdc no-data-check`** identified during this
  re-run: it only treats `__mdc_no_data__: true` as a placeholder, but
  the Polygon short_interest collector also emits `recordCount: 0` with
  `httpStatus: 0` on transport errors. That format doesn't carry the
  marker. Result: the check shows `massive/short_interest` with "last
  real 2026-04-24" when the ACTUAL last real data in MASD is
  `2026-02-27`. Tunable in a small follow-up PR.

---

## What shipped (final commit list)

| # | Item | Commit | Repo |
|---|---|---|---|
| 1 | Polygon short_interest investigation | n/a (report) | qsa |
| 2 | MDC ingest validators (FMP / Finnhub) | `05ef483` | mdc |
| 3 | SEC EDGAR CIK→ticker mapping | `7487e78` | mdc |
| 4 | FMP grades/price-targets dynamic universe | `2d03091` | mdc |
| 5 | Finnhub formal retirement | `d75881c` | mdc |
| 6 | `mdc no-data-check` placeholder alerting | `500acc8` | mdc |
| 7 | SEC API entity-type / CIK→ticker resolution | `c0a6322` | mdc |

Plus two non-roadmap PRs from the same window: QSA tool itself
(`699044c` initial), QSA reports policy fix (`3577107`).

---

## MASD content state — actually right now (no reprocess applied)

| Metric | 2026-05-03 baseline | Today | Why unchanged |
|---|---:|---:|---|
| `fmp_stocks_insider_trades` future-dated rows | 632 | **633** | New row arrived in this morning's 14:00 ingest — *before* the validator commit landed. Tomorrow's run will be the first guarded one. |
| `finnhub_news_articles` BC-era timestamps | 2 | 2 | Finnhub retired; no new rows can arrive. |
| `sec_edgar_filing_events` NULL `ticker_derived` | 81,848 | 81,848 | CIK resolver only fires on new ingest. Historical population needs `mdc ingest --reprocess --provider sec_edgar`. |
| `sec_edgar_filing_events` populated `ticker_derived` | 27,916 | 27,916 | Same. |
| `secapi_regulatory_enforcement` NULL symbol | 257 / 291 | 257 / 291 | Same — needs `--reprocess --provider sec_api`. |
| `secapi_regulatory_penalties` NULL symbol | 58 / 58 | 58 / 58 | Same. |
| `secapi_regulatory_penalties` has entity_type column | no | **yes (parser writes it)** | But migration 029 not yet applied → re-ingest will fail until then. |
| `massive_stocks_short_int` max settlement_date | 2026-02-27 | 2026-02-27 | Still 65 days stale. The proposed retry-placeholders fix has not been implemented; this was always a separate scheduled follow-up. |
| `fmp_stocks_analyst_grades` distinct symbols | 23 | 23 | Dynamic-universe expansion lands on next 4 AM ET cron run (uses `shdb_stocks_with_fundamentals` → ~4,250 symbols). |
| `fmp_stocks_price_targets_1d` distinct symbols | 24 | 24 | Same. |

So the cleanup is in code, and **none of it has touched a historical row
yet**. That is intentional — every PR was scoped "forward-only" with
explicit out-of-scope notes for backfill. The decision of which rows to
reprocess sits with the operator.

---

## Pending operator actions (deliberately not done in this session)

1. **Apply migration 029** (cannot be done from this session — sudo
   needs your password):

       cp migrations/masd/029_secapi_penalties_entity_metadata.sql /tmp/
       sudo -u postgres psql -d masd -f /tmp/029_secapi_penalties_entity_metadata.sql

   Without this, the next sec_api ingest will fail loudly. Until you
   apply it, you can either roll back the parser or skip the next
   sec_api collection.

2. **Optional reprocess passes** (each is independent, idempotent, and
   safe — re-running parses the existing raw archive without re-pulling
   from the API):

   | Provider | Effect | Approx scope |
   |---|---|---|
   | `sec_edgar` | populates `ticker_derived` for ~3K of 81K NULL rows; rest stay NULL because the CIK refers to non-equity entities | ~265 files |
   | `sec_api` | populates `entity_type / cik / symbol` on enforcement and penalties; classifies ~132 rows as individual defendants | ~470 files |
   | `fmp` (`upgrades_downgrades` + `price_target_consensus`) | brings the dynamic-universe expansion to historical days | optional |

   ```
   mdc ingest --reprocess --provider sec_edgar  --start 2025-12-01
   mdc ingest --reprocess --provider sec_api    --start 2026-01-29
   ```

3. **Polygon short_interest scheduling fix** (still pending — separate
   from this roadmap). Investigation report from 2026-05-03 covers the
   diagnosis. The fix needs its own PR; the no-data-check now provides
   a feedback loop so a future regression won't go unnoticed for 65 days.

---

## QSA audit re-run — same 56 findings, different meaning

Full report: `qsa_audit_20260503.md` (re-generated today, overwrites
the earlier copy). Severity counts:

- 🔴 Critical: **11** (unchanged)
- 🟡 Warning: **10** (unchanged)
- 🟢 Info: **35** (unchanged)

Rule severities were intentionally left untouched in this round (the
spec said no QSA rule changes). What's *different* — but invisible to
QSA today — is the underlying data semantics:

- **`R003-missing-symbols` on SEC API tables** still fires critical/warning,
  but the new entity_type column makes those NULL symbols *explicable*.
  Tunable in a small QSA PR: when `entity_type IN ('individual',
  'company')` AND the row is in a known-sparse-by-design table, demote
  the finding to info.
- **`R007-deprecated-tables`** still flags `insider_activity_signals`
  but doesn't yet flag the four Finnhub MASD tables that were
  formally retired in commit `d75881c`. Adding them to
  `config/qsa.yaml` `deprecated_tables:` is one config change away.
- **`R006-staleness`** still flags `finnhub_*` and `insider_mspr_*`;
  same suppression.
- **`R002-future-dates`** count is 633 (vs 632 yesterday) — the
  one extra is from this morning's pre-validator ingest. Should
  drop tomorrow.

---

## `mdc no-data-check` — 3 criticals, all known retirement candidates

Full output: `mdc_no_data_check_20260503.txt`. Headline:

```
Critical: 3   Warning: 0   Info: 18   OK: 51   Suppressed: 3

CRITICAL (3):
  aaii/sentiment_survey       — last real 2026-02-03 (89d)
  coingecko/crypto_daily      — last real 2026-02-05 (87d)
  yahoo/us_stocks_daily       — last real 2026-02-07 (85d)

Suppressed (3):
  finnhub_news/* — RETIRED 2026-05-03
```

These three criticals are exactly the disabled-but-not-formally-retired
sources surfaced by the first run. They're ripe for the same
Finnhub-style retirement treatment.

### Blind spot: HTTP-error empties

While confirming the no-data-check output I noticed it reports
`massive/short_interest` as having `last real 2026-04-24` — but MASD's
actual `MAX(settlement_date)` on `massive_stocks_short_int` is still
`2026-02-27`. Investigation:

- The 2026-04-24 file is **263 bytes**, contains
  `recordCount: 0, shortInterest: [], meta: {status: "http_error", httpStatus: 0}`
- It does NOT carry the `__mdc_no_data__` marker.

The no-data-check classifies it as real data. It isn't — it's a transport
error producing an empty result. **Small follow-up PR**: extend
`is_placeholder()` to also treat files with a top-level
`recordCount == 0` (or a known-empty data field) as placeholders.
Two-line change.

---

## Newly-identified follow-up: `shdb.news_av_ticker_sentiment` duplicates

QSA `R004-duplicate-keys` reports **22,312 duplicate (symbol, obs_date)
groups, 85,405 extra rows** in this curated SHDB table. This isn't a new
finding — it was flagged in the original 2026-05-03 audit — but it
hasn't been touched yet and it's the largest single data-quality issue
on the SHDB side. Investigation belongs in UDC (the builder needs an
upsert / unique index), not MDC.

Sample (from QSA): JPM 2026-03-12 has 119 rows; GOOGL 2026-04-19 has
107; NVDA 2026-04-17 has 105; MSFT 2026-04-20 has 100. These are not
real-world duplicates — they're the same article-level sentiment
landing N times.

---

## Decision menu (per the user's prompt)

The original prompt offered four options. My read on each:

### 1. Tune QSA severities for known structural cases — recommended next

Smallest effort, highest signal-to-noise improvement. Concrete edits:

- Add the four Finnhub MASD tables to `config/qsa.yaml`
  `deprecated_tables:` block (mirrors how `insider_activity_signals`
  is handled).
- Demote `R003-missing-symbols` on SEC API tables when `entity_type
  IN ('individual', 'company')` is present — these are correctly NULL.
  Requires one small rule change to query `entity_type` alongside `symbol`.
- Demote `R006-staleness` on retired sources — same as Finnhub, applies
  to whichever of `aaii / coingecko_crypto_daily / yahoo_us_stocks_daily`
  the user formally retires.
- Estimated work: 1 small QSA PR. Total findings drop from 56 to ~30,
  and what remains will all be genuinely actionable.

### 2. UDC/SHDB cleanup

The single big win is the 85K-row dup explosion in
`shdb.news_av_ticker_sentiment`. Other UDC follow-ups are documented
in the MDC `plan_backlog.md` (deprecate `insider_mspr_signals`, split
SEC API regulatory data by entity_type). The user's prompt explicitly
says "Do not start UDC/SHDB cleanup yet until we review the new
baseline" — so this is gated on the user's call after reading this.

### 3. Source expansion (news / sentiment / analyst)

Less urgent. Open questions from earlier reports:

- Marketaux uses ~7 articles/day vs 2,000/day cap — likely a query-
  filter issue. Tuning would take ~1 hour.
- FMP `senate_trading` is sparse (~14 files in 14 days, but minimal
  rows) — by source nature, not a config issue.
- Polygon `stock_news` covers 267/305 MEF; AlphaVantage already covers
  the gap, so this is an "if we want a 2nd opinion" expansion.

Nothing urgent. Defer until signal-design phase has a concrete need.

### 4. Signal confidence / canonical qualitative mart — premature

Per the original spec "build it after we understand quality". The
quality picture is now clear: most "missing symbol" rows are
structurally correct, news/sentiment is well-covered for MEF, the
biggest remaining defect is the 85K dup explosion. Designing the
canonical mart on top of an unfixed dup defect would bake the bug
into the layer above. **Recommend deferring until item 1 is done and
the dup issue is fixed.**

---

## Recommendation

Do these two in order:

1. **Apply migration 029** (already-staged work; one sudo command).
2. **Small QSA tuning PR** (option 1 above): suppress the four Finnhub
   tables, demote SEC API `R003` when `entity_type` is set, optionally
   add the three retirement-candidate sources to `deprecated_tables:`.

That gets you a clean, decision-grade audit baseline. *Then* pick
between option 2 (UDC dup fix) and the optional reprocess passes —
those are independent and can run in either order.

Item 4 (canonical mart, signal confidence) is the next phase after the
quality work is fully closed.
