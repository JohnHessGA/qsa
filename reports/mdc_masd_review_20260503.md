# MDC / MASD Qualitative Collection Review

*Generated: 2026-05-03 — peer to QSA audit `qsa_audit_20260503.md`*

This review answers: **is MDC collecting and ingesting the qualitative-signal
sources correctly, completely, and consistently?** Scope is MDC + MASD only.
SHDB / UDC / MEF / RSE / CCW are explicitly out of scope for this round.

Sources of evidence:
- `ow.job_provider`, `ow.mdc_ingest_event` — collector run history, status, files written
- `masd.sys_raw_file` — authoritative archive of every raw file collected (16 days of `mdc_ingest_event` history vs 5+ years in `sys_raw_file`, so `sys_raw_file` is the long-record)
- MASD per-table `MAX(date)` and row counts
- Spot-checks of recent JSON files under `/mnt/aftdata/{provider}_{schema}/`
- MDC config files under `~/repos/mdc/config/providers/`

## TL;DR

- **One collector is fully dead by design**: `finnhub_news` (disabled 2026-02-15, free tier limited value).
- **One collector is running but dry**: `massive` short_interest — daily success in Overwatch but every file since 2026-02-28 is a `__mdc_no_data__` placeholder. **Polygon is no longer returning data on this dataset.** This is the most actionable finding.
- **Three "thin coverage" cases are configuration choices, not bugs**: FMP analyst grades / price targets cap at 25 S&P top names; Finnhub had a static 20-name list. Source returns exactly what config asks for.
- **One thin case is true source thinness**: Polygon `stock_news` returns 750+ ticker keys per file but most have empty article arrays — 38 MEF-gap symbols are present-but-empty; AlphaVantage covers those names better.
- **Symbol-mapping issues split three ways**:
  - `secapi_regulatory_penalties`: 100% NULL symbols are correct — entries are individual defendants, not tradable entities. Fix is filter, not map.
  - `secapi_regulatory_enforcement`: 88% NULL is mostly structural (private LLCs, individuals); CIK→ticker would help the company subset.
  - `sec_edgar_filing_events`: 75% NULL `ticker_derived` is fixable — CIK is present, lookup via `dim_security`/`symbol_master`.
- **Two MASD tables have invalid rows that should be quarantined at ingest**: 632 future-dated rows in `fmp_stocks_insider_trades`; 2 BC-era timestamps in `finnhub_news_articles`.

---

## Per-source summary table

Legend: 🟢 healthy, 🟡 partial, 🔴 broken/disabled.
"Last data" = latest `data_date` in the MASD target table or its source archive.

| Source / Dataset | MASD target | Last data | Last collect (Overwatch) | Files in 14d | Symbol coverage | State | Defect (if any) |
|---|---|---|---|---:|---|:-:|---|
| **alphavantage** / news_sentiment | `alphavantage_news_sentiment_1d` (+ ticker_sentiment, topics) | 2026-05-02 | 2026-05-03 ok | 12 | 8,032 distinct tickers (broad) | 🟢 | — |
| **finnhub_news** / company_news | `finnhub_news_articles` (+ article_symbols) | 2026-02-14 | none since 2026-02-15 | 0 | 20 static symbols | 🔴 | Provider disabled by config (free-tier value too low). 2 historic rows have BC timestamps (ingest bug). |
| **finnhub_news** / insider_transactions | `finnhub_stocks_insider_txn` | 2026-02-15 | none since 2026-02-15 | 0 | 641 distinct symbols | 🔴 | Provider disabled. |
| **finnhub_news** / insider_sentiment | `finnhub_stocks_insider_mspr_1m` | 2026-02 (Feb) | none since 2026-02-15 | 0 | 597 distinct symbols | 🔴 | Provider disabled. |
| **marketaux** / news_sentiment | `marketaux_news_articles_1d` (+ entity_sentiment) | 2026-05-02 | 2026-05-03 ok | 14 | 671 cumulative; 354 distinct in 63 raw files (broad globally; foreign-heavy) | 🟢 | None on collection. Coverage skews ex-US (`.KS`, `.L`, `.HK`, `.T`, `.DE`); MEF coverage (37/305) reflects what Marketaux happens to write about. |
| **gdelt** / news_sentiment | `gdelt_news_sentiment_1d` | 2026-05-01 | 2026-05-03 ok | 14 | macro / market-wide (no per-symbol) | 🟢 | — |
| **gdelt** / article_trends | `gdelt_article_trends_1d` | 2026-05-02 | 2026-05-03 ok | 14 | macro / market-wide | 🟢 | — |
| **massive** (Polygon) / stock_news | `massive_stocks_news_1d` | 2026-05-01 | 2026-05-03 ok | 10,166 | 582 cumulative; 38 MEF "gap" symbols are present in source but with empty article arrays | 🟡 | Source returns 750+ ticker keys per file but ~70% are empty arrays — true source thinness, not ingest drop. |
| **massive** / short_interest | `massive_stocks_short_int` | **2026-02-27 (65d)** | **2026-05-03 ok (collector ran)** | 14 | 39,191 cumulative | 🔴 | **Collector ran successfully every day; every file since 2026-02-28 is `{__mdc_no_data__: true}`.** Polygon stopped returning short-interest data. Top action item. |
| **massive** / short_volume | `massive_stocks_short_vol_1d` | 2026-05-01 | 2026-05-02 ok | 10,166 | 782 cumulative | 🟢 | — |
| **fmp** / insider_trading | `fmp_stocks_insider_trades` | 2031-03-03 (max — bad data) / 2026-05-01 (real) | 2026-05-02 ok | 14 | 4,933 distinct | 🟡 | **632 future-dated rows** (max 2031-03-03). Source returns them; ingest accepts them. Forward-only ingest validation needed. |
| **fmp** / house_trading | `fmp_congress_house_trades` | 2026-04-23 | 2026-05-02 ok | 14 | 389 distinct | 🟢 | Sparse by nature. |
| **fmp** / senate_trading | `fmp_congress_senate_trades` | 2026-03-31 | 2026-05-02 ok | 14 | 98 distinct | 🟡 | Collector runs daily but Senate disclosures are slow / sparse — not a bug, just thin source. |
| **fmp** / upgrades_downgrades | `fmp_stocks_analyst_grades` | 2026-05-01 | 2026-05-02 ok | 336 (24/day × 14d) | 23 distinct (= **25-symbol config cap**) | 🟡 | Source-by-design: only 25 S&P top symbols. Each daily file has all 25 keys. Coverage gap is a config choice, not a bug. |
| **fmp** / price_target_consensus | `fmp_stocks_price_targets_1d` | 2026-05-02 | 2026-05-03 ok | 336 | 24 distinct (= **25-symbol config cap**) | 🟡 | Same 25-symbol cap. |
| **fmp** / analyst_estimates | `fmp_analyst_estimates_1d` | 2026-05-02 | 2026-05-03 ok | 114,750 | 3,821 distinct (dynamic from SHDB) | 🟢 | Universe sourced dynamically from SHDB; broad. |
| **yahoo** / analyst_research | `yahoo_stocks_analyst_estimates_1d`, `yahoo_stocks_eps_momentum_1d` | 2026-05-02 | 2026-05-02 ok | 14 | 756 distinct | 🟢 | — |
| **yahoo** / institutional_holders | `yahoo_stocks_institutional_holders_1q` | 2026-05-02 | varies | n/a (quarterly) | 667 distinct | 🟢 | — |
| **sec_edgar** / filing_events | `sec_edgar_filing_events` | 2026-05-01 | 2026-05-03 ok | 125 | 4,898 distinct `ticker_derived`; **74.6% of rows have NULL `ticker_derived`** | 🟡 | CIK is present on every row; `ticker_derived` is the only mapping path used today. Fixable in MDC ingest by adding CIK→symbol resolution. |
| **sec_api** / enforcement_actions, admin_proceedings, litigation_releases | `secapi_regulatory_enforcement` | 2026-05-01 | 2026-05-03 ok | 14+/dataset | 25 distinct symbols on 291 rows; **88% NULL symbol** | 🟡 | Most enforcement targets are individuals or private LLCs — structurally not mappable to public tickers. Fix is *filter* in UDC, not map in MDC. |
| **sec_api** / penalties (subset) | `secapi_regulatory_penalties` | 2026-04-30 | 2026-05-03 ok | 14 | **0 distinct symbols on 58 rows; 100% NULL** | 🟡 | All recent entries are *individuals* (defendants in SEC litigation). Symbol cannot exist. Fix is recognise these are non-public-entity rows; don't try to symbol-map; let UDC filter out or move to a separate "individual_actions" table. |
| **sec_api** / ipo_filings | `sec_api_ipo_filings` | 2026-05-02 | 2026-05-03 ok | 14 | n/a | 🟢 | — |
| **sec_api** / aaers | `secapi_regulatory_enforcement` | 2026-04-21 | 2026-05-03 ok | 1 | n/a | 🟡 | AAERs are infrequent by nature; collector ran but source returned new rows only on 2026-04-21. |
| **alternative_me** / fear_greed_index | `altme_sentiment_feargreed_1d` | 2026-05-02 | 2026-05-03 ok | 14 | n/a (single index) | 🟢 | — |
| **apewisdom** / social_mentions | `apewisdom_social_mentions_1d` | 2026-05-02 | 2026-05-03 ok | 12 | 3,451 cumulative | 🟢 | — |
| **cfpb** / consumer_complaints | `cfpb_regulatory_complaints_1d` | 2026-04-18 | 2026-05-03 ok | 14 | 22 distinct (banks/financials only) | 🟢 | Sparse by nature; small population of public banks/financial issuers. |
| **cftc_cot** / futures_positioning | `cftc_futures_positioning_1w` | 2026-04-28 | 2026-05-03 ok | 2 | n/a (futures contracts) | 🟢 | Weekly cadence; on schedule. |

---

## Confirmation of QSA's known issues, with MDC-side root cause

### 1. `fmp_stocks_insider_trades` future-dated rows (632 rows, max 2031-03-03)

- Confirmed: 632 rows, 193 distinct future dates.
- **Root cause is upstream**: FMP returns these dates in the `transactionDate` field of the bulk insider-trading response. MDC currently passes them through unchanged.
- **Fix belongs in MDC ingest**: add a future-date validator on `transaction_date` and `bar_date` (tolerance: 0 days). Two options:
  - Reject the row outright with a `parse_status` flag, or
  - Move to a quarantine table (per QSA design).
- Scope is small; the 632 invalid rows are <0.5% of the table. Safe to forward-only validate.

### 2. `finnhub_news_articles` BC-era timestamps (2 rows)

- Confirmed: 2 rows with `EXTRACT(year FROM published_at_utc) = -1`.
- **Root cause**: Finnhub returns a sentinel epoch on a small number of malformed records; MDC's ingest accepts whatever `datetime` comes back without a sanity floor.
- **Fix belongs in MDC ingest**: enforce a minimum-valid-date floor (e.g., 2000-01-01) on news timestamp columns at ingest time. Reject or null-out below.
- **Caveat**: Finnhub is currently disabled, so any fix is for the day this collector is re-enabled. Low priority right now.

### 3. `secapi_regulatory_penalties` — 100% NULL symbols

- Confirmed: all 58 rows have NULL symbol; all visible defendants are *individuals*.
  - Sample: Daquan Lloyd, Aaron Verdugo, Christopher Flagg, Travis Treusch, Alvin Christopher Jones, Anthony J. Cataldo, Fredi Nisan…
- **Root cause is structural, not a pipeline bug**: SEC penalties are levied on the named defendant. When that defendant is an individual, no ticker can exist.
- **Fix does NOT belong in MDC symbol resolution.** Instead:
  - **Pointer:** Have MDC populate (or carry through) `entity_type` (`individual` / `company`) — already present in `secapi_regulatory_enforcement` schema, missing here.
  - **UDC** (later) should filter or split: company-defendant rows feed a per-symbol penalty signal; individual-defendant rows go to a separate non-equity table (or are dropped).
- For the small subset where the penalty *is* against a company, a CIK→ticker lookup *might* help — but the sample data doesn't show CIKs populated either. Worth verifying on a fresh paid-API pull before designing a mapping step.

### 4. `secapi_regulatory_enforcement` — 88% NULL symbols (257/291)

- Confirmed: 88.3% NULL. Sample of NULL rows:
  - "Prime Group Holdings, LLC" (private LLC)
  - "Rimar Capital USA, Inc." (private RIA)
  - "Itai Royi Liptz" (individual)
  - "Clayton 'Charlie' Thomas" (individual)
- `entity_type` exists (`company` / `individual`); `cik` exists but is NULL in the samples shown.
- **Root cause is mostly structural**: the SEC enforces against individuals and private firms, not just public companies. Most NULL rows correctly have no ticker.
- **Pointer for fix**: When `entity_type=company` AND `cik IS NOT NULL`, attempt a CIK→ticker lookup. Belongs in **MDC ingest** so the raw record carries an authoritative `symbol` plus a `mapping_method`/`mapping_confidence` field (per the user's corrected guidance — never overstate certainty).
- Don't try to fuzzy-match on `entity_name` for enforcement; false-positives risk linking the wrong public company.

### 5. `sec_edgar_filing_events` — 75% NULL `ticker_derived` (81,848 / 109,764)

- Different from above: these are 8-K / Form 4 / SCHEDULE 13D/G filings, **all by reporting entities that have a CIK** and most of which *are* publicly traded (8-K and Form 4 are filed by reporting issuers / their insiders).
- `cik` is present on every row.
- **Root cause is a missed mapping step**: MDC's `sec_edgar` provider doesn't currently resolve CIK→ticker. The QSA already flagged: "filings without a derived ticker still have a CIK; the curated event_filing layer can resolve."
- **Pointer for fix**: Resolve CIK→ticker during MDC ingest using `masd.dim_security`/`masd.dim_security_ticker` (or whatever the live mapping table is — see `masd_foreign.dim_security` for the curated SHDB equivalent). Belongs in **MDC ingest** so MASD itself becomes correct; UDC just reads what MDC provides.
- This is the **highest-impact symbol-mapping fix** in the review — 81K rows would gain ticker context.
- Add `mapping_confidence` if the CIK has multiple historical tickers; default to most recent.

### 6. Finnhub MSPR appears stale

- Confirmed: latest data is February 2026; collector hasn't run since 2026-02-15.
- **Root cause**: provider disabled by explicit decision in `config/providers/finnhub_news.yaml` ("free tier limited value, paid sentiment tier $3,000/mo not justified"). This is **expected** state, not a defect.
- **Fix belongs in source/strategy, not code**: either re-enable on a paid plan, or formally retire the table (mark deprecated; let UDC stop building `insider_mspr_signals` once nothing reads it).

### 7. Polygon short-interest collection appears stale

- **This is the most important new finding in the review.**
- `ow.job_provider` says `massive` runs successfully every day with files written.
- `masd.sys_raw_file` confirms a `short_interest-YYYY-MM-DD.json` file is being written daily.
- BUT: every such file since 2026-02-28 is exactly 230 bytes and contains:
  ```json
  { "__mdc_no_data__": true, "provider": "massive", "schema": "s1",
    "dataset": "short_interest", "dataDate": "2026-05-02",
    "collectedAtUtc": "...", "meta": { "skippedReason": "weekend" } }
  ```
  — and weekday placeholders use `"skippedReason": "no_data"`.
- **Root cause**: Polygon's short-interest endpoint has stopped returning data (or the endpoint URL/auth/contract changed). The MDC collector correctly logs "no data" rather than fabricating rows, but this means MASD has been frozen at 2026-02-27 for 65 days while looking healthy at the provider/Overwatch level.
- **Fix is not in MDC code first**: investigate the source side. Likely answers:
  - (a) Polygon discontinued FINRA short-interest in their API (check Polygon changelog),
  - (b) endpoint moved (URL, auth header, query param),
  - (c) entitlement / plan change.
- Once root cause is known, the **monitoring fix belongs in MDC**: emit an Overwatch warning when N consecutive `__mdc_no_data__` placeholders accumulate for a dataset that should be at least bi-monthly. That gap should have paged us within ~30 days, not gone unnoticed for 65.

### 8. FMP analyst grades / price targets weak MEF coverage

- Confirmed via raw-archive spot-check:
  - `upgrades_downgrades-2026-05-02.json`: exactly **25 ticker keys** = `[AAPL, ABBV, AMD, AMZN, AVGO, BAC, BRK-B, COST, CRM, GOOGL, HD, JNJ, JPM, LLY, MA, META, MSFT, NFLX, NVDA, PG, TSLA, UNH, V, WMT, XOM]`.
  - `price_target_consensus-2026-05-02.json`: same 25 ticker keys.
- Matches the explicit `symbols:` block in `config/providers/fmp.yaml` (S&P 500 top 25 by market cap).
- **Root cause**: source-side **configuration**, not bug. FMP Premium ($59/mo) does support broader per-symbol queries, but each call costs API budget — the team chose to limit to 25 names.
- **Fix belongs in source configuration**, not code:
  - To cover the full MEF universe, expand `symbols:` to MEF's 305 (or use the `shdb_stocks_with_fundamentals` dynamic resolution that `fmp_analyst_estimates` already uses).
  - Cost question first: 305 symbols × 2 datasets × daily ≈ 610 calls/day vs FMP's 750 req/min Premium limit — fits easily.
- Bonus observation: each daily `upgrades_downgrades` file has **18,019 grade rows for those 25 tickers** (FMP returns the entire historical grade list per call). MDC's ingest is dedup'ing or upserting and only landing 377 total rows in MASD over the whole window. That's correct behaviour but worth verifying the dedup logic still picks up *new* grades when FMP backdates them.

### 9. Finnhub & Marketaux news mappings have weak MEF coverage

- **Finnhub**: 19/305 MEF stocks. Confirmed by config — `finnhub_news.yaml` declares 20 hardcoded symbols (the static `&stock_symbols` list); MASD shows exactly 20 distinct symbols in `finnhub_news_article_symbols`. Provider is disabled anyway. **Source-side cap by design.**
- **Marketaux**: 37/305 MEF stocks. Spot-check of 63 raw files (Mar–May 2026): 168 articles total, 354 distinct entity symbols — but **dominated by foreign listings** (`.KS` Korea, `.L` London, `.HK` Hong Kong, `.T` Tokyo, `.DE` Germany, `.AX` Australia). **Source returns broad data; the MEF coverage gap is a function of what Marketaux happens to write about US large-caps.** Not an ingest bug.
- One related observation: Marketaux config allows up to 2,000 articles/day (100 pages × 20 articles). Actual is ~7 articles/day. Could be a query/filter narrowing that throws away breadth — worth a separate pass on the request parameters in `marketaux.yaml` (out of scope for this review).

---

## Active vs failing collectors — operational view

| Collector | Status | Evidence | Note |
|---|:-:|---|---|
| alphavantage | 🟢 active | 14d: 14 ok / 0 error | Daily news_sentiment + ticker_sentiment + topics |
| alternative_me | 🟢 active | 14d: 18 ok / 1 error (2026-04-25) | Single error, recovered |
| apewisdom | 🟢 active | 14d: 15 ok / 0 error | — |
| cfpb | 🟢 active | 14d: 17 ok / 1 error (2026-04-25) | Single error, recovered |
| cftc_cot | 🟢 active | 14d: 18 ok / 0 error | Weekly cadence |
| **finnhub_news** | 🔴 disabled | 14d: 0 runs | By config decision (free-tier value too low) |
| fmp | 🟢 active | 14d: 18 ok / 1 error (2026-04-25) | All 11 datasets running |
| gdelt | 🟢 active | 14d: 19 ok / 0 error | — |
| marketaux | 🟢 active | 14d: 15 ok / 0 error | Underutilising 2,000-article daily cap (~7/day actual) |
| **massive** (Polygon) | 🟡 mixed | 14d: 70 ok / 0 error | Most datasets healthy; **short_interest dataset returns no_data placeholders since 2026-02-28** |
| sec_api | 🟢 active | 14d: 17 ok / 1 error | All 5 datasets running |
| sec_edgar | 🟢 active | 14d: 17 ok / 0 error | 75% rows lack ticker_derived (mapping issue, see §5) |
| yahoo | 🟢 active | 14d: 23 ok / 0 error | — |

The `2026-04-25` cluster of single errors across multiple providers (alternative_me, cfpb, fmp, mempool, sec_api) suggests a one-off platform-level hiccup that day rather than per-provider issues — all recovered the next run. Worth confirming, not actionable on its own.

---

## Where each fix belongs

This is the user's question made concrete:

| Issue | Goes in MDC | Goes in source/API config | Goes in symbol mapping (MDC-side) | Goes in UDC curation (later) |
|---|:-:|:-:|:-:|:-:|
| FMP future-dated insider trades | ✅ ingest validator | — | — | — |
| Finnhub BC timestamps | ✅ ingest validator | — | — | — |
| Polygon short-interest stalled | ✅ no-data alert threshold | ✅ investigate API | — | — |
| Finnhub disabled | — | ✅ re-enable or retire | — | ✅ deprecate dependent SHDB tables |
| FMP grades/targets thin | — | ✅ expand `symbols:` block | — | — |
| Marketaux thin US-large-cap | — | ✅ tune query params (later) | — | — |
| Polygon news US-large-cap gap | — | (real source thinness — none) | — | ✅ rely on AlphaVantage fallback in unified table |
| `secapi_regulatory_penalties` 100% NULL | — | — | (no — these are individuals) | ✅ filter / split table by entity type |
| `secapi_regulatory_enforcement` 88% NULL | — | — | ✅ CIK→ticker for `entity_type=company` rows | ✅ filter individuals |
| `sec_edgar_filing_events` 75% NULL ticker_derived | — | — | ✅ CIK→ticker (highest-impact mapping) | — |

---

## Recommended next-action ordering (for after this review)

1. **Investigate Polygon short_interest** — is the API still publishing the dataset? Single most actionable item; all of QSA's downstream short-interest signals will keep degrading until this is answered.
2. **Add MDC ingest validators**: future-date floor on FMP insider trades; min-valid-date floor on Finnhub news (deferred but trivial).
3. **Add CIK→ticker resolution to `sec_edgar` ingest** — biggest payoff (81K rows gain ticker context).
4. **Decide Finnhub strategy**: re-enable on paid plan, or formally deprecate the three target tables.
5. **Expand FMP grades/targets `symbols:` block to MEF universe** (or `shdb_stocks_with_fundamentals`) — config-only change, clears two of QSA's critical findings at once.
6. **Add no-data placeholder threshold alerts** in MDC so the next "collector is running but source returns nothing" case pages within 30 days, not 65.
7. **Carry `entity_type` and (where present) CIK on `secapi_regulatory_penalties`** so UDC can filter cleanly later.

Items 4–7 are config / additive; only items 2–3 require new code paths in MDC. None require SHDB or UDC changes for this round.

---

## Open questions / not yet answered in this review

- The 2026-04-25 single-error cluster across multiple providers — what was the root cause? (Likely platform / network hiccup; not investigated here.)
- Why is Marketaux delivering ~7 articles/day against a 2,000/day cap? Worth a follow-up review of the request filter set.
- Is `dim_security` / `dim_security_ticker` populated and current enough to support a CIK→ticker resolution step? Spot-check needed before committing to the SEC EDGAR fix.
- The `__mdc_no_data__` placeholder convention — is it documented anywhere in MDC, or implicit? Worth surfacing if the audit story will rely on it.

This review does not propose code; it produces the picture needed to decide
which MDC changes to make first. Next decision: pick from the seven-item
list and proceed source-by-source.
