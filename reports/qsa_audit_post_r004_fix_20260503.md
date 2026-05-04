# QSA — Qualitative Signal Audit Report

*Generated: 2026-05-03T22:33:06*

Read-only audit of qualitative / sentiment / event data across MASD and SHDB.
This report identifies data-quality issues; it does not modify any database.

## Summary

- 🔴 Critical: **9**
- 🟡 Warning:  **9**
- 🟢 Info:     **34**
- Total:      **52**

## Findings by Rule

| Rule | Severity counts | Description |
|---|---|---|
| `R003-missing-symbols` | 🔴 2 🟡 3 | Rows missing a symbol where one is required |
| `R006-staleness` | 🔴 1 🟡 2 | Streams whose most-recent observation is past threshold |
| `R007-deprecated-tables` | 🟡 2 | Tables marked deprecated; live consumers across AFT |
| `R008-mef-coverage` | 🔴 6 🟢 34 | MEF universe coverage per qualitative table |
| `R009-thin-coverage` | 🟡 2 | Tables with unexpectedly low distinct-symbol counts |

## 🔴 CRITICAL (9)

### `R008-mef-coverage` — masd.finnhub_news_article_symbols

**Finnhub news per-symbol: 19/305 MEF stocks (6.2%)**

Expected coverage: broad. 19 of 305 MEF universe stocks present in masd.finnhub_news_article_symbols.symbol.

- affected symbols: **286**

**Sample:**

| missing_symbol |
|---|
| A |
| ABBV |
| ABNB |
| ABT |
| ACGL |
| ACN |
| ADBE |
| ADI |
| ADP |
| ADSK |

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — masd.fmp_stocks_analyst_grades

**FMP analyst grades: 21/305 MEF stocks (6.9%)**

Expected coverage: broad. 21 of 305 MEF universe stocks present in masd.fmp_stocks_analyst_grades.symbol.

- affected symbols: **284**

**Sample:**

| missing_symbol |
|---|
| A |
| ABNB |
| ABT |
| ACGL |
| ACN |
| ADBE |
| ADI |
| ADP |
| ADSK |
| AEP |

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — masd.fmp_stocks_price_targets_1d

**FMP price targets: 22/305 MEF stocks (7.2%)**

Expected coverage: broad. 22 of 305 MEF universe stocks present in masd.fmp_stocks_price_targets_1d.symbol.

- affected symbols: **283**

**Sample:**

| missing_symbol |
|---|
| A |
| ABNB |
| ABT |
| ACGL |
| ACN |
| ADBE |
| ADI |
| ADP |
| ADSK |
| AEP |

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — masd.marketaux_news_entity_sentiment

**Marketaux entity sentiment: 37/305 MEF stocks (12.1%)**

Expected coverage: broad. 37 of 305 MEF universe stocks present in masd.marketaux_news_entity_sentiment.symbol.

- affected symbols: **268**

**Sample:**

| missing_symbol |
|---|
| A |
| ABBV |
| ABNB |
| ABT |
| ACGL |
| ADBE |
| ADI |
| ADP |
| ADSK |
| AEP |

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R003-missing-symbols` — masd.secapi_regulatory_penalties

**128/130 (98.5%) rows with missing symbol**

Penalties without a symbol cannot drive per-stock signals.

Rows missing symbol: 128 of 130 (98.5%).

- affected rows: **128**

_Recommendation:_ Investigate whether company_name / CIK / URL fields in the source can be resolved to a ticker (via dim_security or symbol_master) and add a resolution step in MDC or UDC. Until then, mark such rows as unmapped rather than silently surfacing them as actionable.

---

### `R008-mef-coverage` — shdb.analyst_grades

**Curated analyst grades: 21/305 MEF stocks (6.9%)**

Expected coverage: broad. 21 of 305 MEF universe stocks present in shdb.analyst_grades.symbol.

- affected symbols: **284**

**Sample:**

| missing_symbol |
|---|
| A |
| ABNB |
| ABT |
| ACGL |
| ACN |
| ADBE |
| ADI |
| ADP |
| ADSK |
| AEP |

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — shdb.analyst_price_targets_1d

**Curated price targets: 22/305 MEF stocks (7.2%)**

Expected coverage: broad. 22 of 305 MEF universe stocks present in shdb.analyst_price_targets_1d.symbol.

- affected symbols: **283**

**Sample:**

| missing_symbol |
|---|
| A |
| ABNB |
| ABT |
| ACGL |
| ACN |
| ADBE |
| ADI |
| ADP |
| ADSK |
| AEP |

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R003-missing-symbols` — shdb.sec_penalties

**43/43 (100.0%) rows with missing symbol**

Curated penalties inherit the MASD link gap.

Rows missing symbol: 43 of 43 (100.0%).

- affected rows: **43**

_Recommendation:_ Investigate whether company_name / CIK / URL fields in the source can be resolved to a ticker (via dim_security or symbol_master) and add a resolution step in MDC or UDC. Until then, mark such rows as unmapped rather than silently surfacing them as actionable.

---

### `R006-staleness` — shdb.stock_short_interest

**shdb.stock_short_interest stale: max(settlement_date)=2026-02-27 (65d ago)**

Cadence=daily, threshold=5d. Most recent observation is 2026-02-27 (65 days ago). 504,559 total rows.

- affected rows: **504,559**

_Recommendation:_ Check the upstream collector/ingest cron and whether the source API is still returning data. Some streams (Finnhub MSPR, free-tier APIs) may have expired entitlements rather than pipeline bugs.

---

## 🟡 WARNING (9)

### `R007-deprecated-tables` — shdb.insider_activity_signals

**40 reference(s) to deprecated shdb.insider_activity_signals in 21 file(s)**

Scanned 8 repos.
Preferred replacement: shdb.insider_conviction_signals

Each match is a literal occurrence of the bare table name. Some hits will be deprecation notes / READMEs (which is fine); only code/SQL hits are live consumers.

- affected rows: **40**

**Sample:**

| file | line | text |
|---|---|---|
| /home/johnh/repos/rse/docs/rse_shdb_intake_reference.md | 158 | | Insider / institutional | Insider trades | `shdb.insider_trades` (81K rows, 2021→), `insider_activity_signals`, `insider_mspr_1m`, `insider_mspr_signals` | | |
| /home/johnh/repos/udc/CLAUDE.md | 313 | futures_positioning_signals_1w, insider_activity_signals, |
| /home/johnh/repos/udc/config/datasets/insider_activity_signals.yaml | 1 | name: insider_activity_signals |
| /home/johnh/repos/udc/config/shdb_catalog.yaml | 2433 | lineage: { source_systems: [FMP], source_tables: [masd_foreign.fmp_stocks_insider_trades], upstream_dependencies: [symbol_master], downstream_dependencies: [ins |
| /home/johnh/repos/udc/config/shdb_catalog.yaml | 2434 | usage: { tags: [timeseries, symbol-level, event-driven, cleaned], common_join_keys: [symbol, bar_date], join_guidance: "Event-driven. Feeds insider_activity_sig |
| /home/johnh/repos/udc/config/shdb_catalog.yaml | 2436 | insider_activity_signals: |
| /home/johnh/repos/udc/config/table_meta/corporate_events/insider_activity_signals.yaml | 2 | # shdb.insider_activity_signals — Per-Table Metadata |
| /home/johnh/repos/udc/config/table_meta/corporate_events/insider_activity_signals.yaml | 8 | table_name: insider_activity_signals |
| /home/johnh/repos/udc/config/table_meta/corporate_events/insider_activity_signals.yaml | 10 | full_name: shdb.insider_activity_signals |
| /home/johnh/repos/udc/config/table_meta/corporate_events/insider_conviction_signals.yaml | 25 | insider_activity_signals (which lumps those grant rows in as buys/sells). Consumed by the CIA |

_Recommendation:_ Migrate live code/SQL consumers to shdb.insider_conviction_signals. Comment-only hits (READMEs, notes, this audit) are not action items.

---

### `R006-staleness` — masd.finnhub_stocks_insider_mspr_1m

**masd.finnhub_stocks_insider_mspr_1m stale: max(year+month)=2026-02-01 (91d ago)**

Cadence=monthly, threshold=45d. Most recent observation is 2026-02-01 (91 days ago). 3,796 total rows.

- affected rows: **3,796**

_Recommendation:_ Check the upstream collector/ingest cron and whether the source API is still returning data. Some streams (Finnhub MSPR, free-tier APIs) may have expired entitlements rather than pipeline bugs.

---

### `R003-missing-symbols` — masd.sec_edgar_filing_events

**110,218/154,112 (71.5%) rows with missing ticker_derived**

Filings without a derived ticker still have a CIK; the curated event_filing layer can resolve.

Rows missing ticker_derived: 110,218 of 154,112 (71.5%).

- affected rows: **110,218**

_Recommendation:_ Investigate whether company_name / CIK / URL fields in the source can be resolved to a ticker (via dim_security or symbol_master) and add a resolution step in MDC or UDC. Until then, mark such rows as unmapped rather than silently surfacing them as actionable.

---

### `R003-missing-symbols` — masd.secapi_regulatory_enforcement

**525/597 (87.9%) rows with missing symbol**

Enforcement rows sometimes target individuals; not always linkable to a ticker.

Rows missing symbol: 525 of 597 (87.9%).

- affected rows: **525**

_Recommendation:_ Investigate whether company_name / CIK / URL fields in the source can be resolved to a ticker (via dim_security or symbol_master) and add a resolution step in MDC or UDC. Until then, mark such rows as unmapped rather than silently surfacing them as actionable.

---

### `R009-thin-coverage` — shdb.analyst_grades

**analyst-grades: thin coverage — MASD 23 sym / SHDB 23 sym**

MASD masd.fmp_stocks_analyst_grades: 377 rows / 23 distinct symbol.
SHDB shdb.analyst_grades: 377 rows / 23 distinct symbol.
Delta: 0 rows, 0 symbols.

A near-equal MASD↔SHDB count means the bottleneck is upstream (API entitlement, rate-limited collection). A large drop from MASD to SHDB means a curation builder is filtering data out.

- affected symbols: **282**

_Recommendation:_ Determine whether this is a source limitation (API plan, free-tier cap), a symbol-mapping issue (curation step rejects rows that don't resolve to symbol_master), or a date-window issue (refresh cadence too tight). If source-limited: document and exclude from hard gates until fixed.

---

### `R009-thin-coverage` — shdb.analyst_price_targets_1d

**analyst-price-targets: thin coverage — MASD 24 sym / SHDB 24 sym**

MASD masd.fmp_stocks_price_targets_1d: 2,208 rows / 24 distinct symbol.
SHDB shdb.analyst_price_targets_1d: 2,208 rows / 24 distinct symbol.
Delta: 0 rows, 0 symbols.

A near-equal MASD↔SHDB count means the bottleneck is upstream (API entitlement, rate-limited collection). A large drop from MASD to SHDB means a curation builder is filtering data out.

- affected symbols: **281**

_Recommendation:_ Determine whether this is a source limitation (API plan, free-tier cap), a symbol-mapping issue (curation step rejects rows that don't resolve to symbol_master), or a date-window issue (refresh cadence too tight). If source-limited: document and exclude from hard gates until fixed.

---

### `R007-deprecated-tables` — shdb.insider_activity_signals

**Deprecated table shdb.insider_activity_signals still present (24,562 rows)**

Reason: Legacy/contaminated — mixes grants with conviction transactions.
Preferred source: shdb.insider_conviction_signals

Consumer-grep results are listed in the cross-cutting findings section.

- affected rows: **24,562**

_Recommendation:_ Do not consume this table from new pipelines. Migrate any existing consumers to shdb.insider_conviction_signals. Optionally add a DB COMMENT marking the table deprecated so anyone inspecting the schema sees the warning.

---

### `R006-staleness` — shdb.insider_mspr_signals

**shdb.insider_mspr_signals stale: max(bar_date)=2026-02-01 (91d ago)**

Cadence=monthly, threshold=45d. Most recent observation is 2026-02-01 (91 days ago). 3,742 total rows.

- affected rows: **3,742**

_Recommendation:_ Check the upstream collector/ingest cron and whether the source API is still returning data. Some streams (Finnhub MSPR, free-tier APIs) may have expired entitlements rather than pipeline bugs.

---

### `R003-missing-symbols` — shdb.sec_enforcement

**256/290 (88.3%) rows with missing symbol**

Curated enforcement; same as MASD — individuals not linkable.

Rows missing symbol: 256 of 290 (88.3%).

- affected rows: **256**

_Recommendation:_ Investigate whether company_name / CIK / URL fields in the source can be resolved to a ticker (via dim_security or symbol_master) and add a resolution step in MDC or UDC. Until then, mark such rows as unmapped rather than silently surfacing them as actionable.

---

## 🟢 INFO (34)

### `R008-mef-coverage` — masd.alphavantage_news_ticker_sentiment

**AlphaVantage news sentiment: 305/305 MEF stocks (100.0%)**

Expected coverage: broad. 305 of 305 MEF universe stocks present in masd.alphavantage_news_ticker_sentiment.ticker.

- affected symbols: **0**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — masd.apewisdom_social_mentions_1d

**ApeWisdom social mentions: 275/305 MEF stocks (90.2%)**

Expected coverage: broad. 275 of 305 MEF universe stocks present in masd.apewisdom_social_mentions_1d.ticker.

- affected symbols: **30**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — masd.cfpb_regulatory_complaints_1d

**CFPB complaints: 13/305 MEF stocks (4.3%)**

Expected coverage: sparse_expected. 13 of 305 MEF universe stocks present in masd.cfpb_regulatory_complaints_1d.symbol.

- affected symbols: **292**

_Recommendation:_ Sparse-expected source: low coverage is by nature, not a quality issue. Only relevant when paired with a real-world event.

---

### `R008-mef-coverage` — masd.finnhub_stocks_insider_mspr_1m

**Finnhub insider MSPR: 296/305 MEF stocks (97.0%)**

Expected coverage: broad. 296 of 305 MEF universe stocks present in masd.finnhub_stocks_insider_mspr_1m.symbol.

- affected symbols: **9**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — masd.finnhub_stocks_insider_txn

**Finnhub insider txn: 301/305 MEF stocks (98.7%)**

Expected coverage: broad. 301 of 305 MEF universe stocks present in masd.finnhub_stocks_insider_txn.symbol.

- affected symbols: **4**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — masd.fmp_analyst_estimates_1d

**FMP analyst estimates: 305/305 MEF stocks (100.0%)**

Expected coverage: broad. 305 of 305 MEF universe stocks present in masd.fmp_analyst_estimates_1d.symbol.

- affected symbols: **0**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — masd.fmp_congress_house_trades

**FMP House trades: 169/305 MEF stocks (55.4%)**

Expected coverage: sparse_expected. 169 of 305 MEF universe stocks present in masd.fmp_congress_house_trades.symbol.

- affected symbols: **136**

_Recommendation:_ Sparse-expected source: low coverage is by nature, not a quality issue. Only relevant when paired with a real-world event.

---

### `R008-mef-coverage` — masd.fmp_congress_senate_trades

**FMP Senate trades: 47/305 MEF stocks (15.4%)**

Expected coverage: sparse_expected. 47 of 305 MEF universe stocks present in masd.fmp_congress_senate_trades.symbol.

- affected symbols: **258**

_Recommendation:_ Sparse-expected source: low coverage is by nature, not a quality issue. Only relevant when paired with a real-world event.

---

### `R008-mef-coverage` — masd.fmp_stocks_insider_trades

**FMP insider trades: 300/305 MEF stocks (98.4%)**

Expected coverage: broad. 300 of 305 MEF universe stocks present in masd.fmp_stocks_insider_trades.symbol.

- affected symbols: **5**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — masd.massive_stocks_news_1d

**Polygon stock news: 267/305 MEF stocks (87.5%)**

Expected coverage: broad. 267 of 305 MEF universe stocks present in masd.massive_stocks_news_1d.symbol.

- affected symbols: **38**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — masd.massive_stocks_short_int

**Polygon short interest: 305/305 MEF stocks (100.0%)**

Expected coverage: broad. 305 of 305 MEF universe stocks present in masd.massive_stocks_short_int.ticker.

- affected symbols: **0**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — masd.massive_stocks_short_vol_1d

**Polygon short volume: 305/305 MEF stocks (100.0%)**

Expected coverage: broad. 305 of 305 MEF universe stocks present in masd.massive_stocks_short_vol_1d.symbol.

- affected symbols: **0**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — masd.sec_edgar_filing_events

**SEC EDGAR filings: 294/305 MEF stocks (96.4%)**

Expected coverage: broad. 294 of 305 MEF universe stocks present in masd.sec_edgar_filing_events.ticker_derived.

- affected symbols: **11**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — masd.secapi_regulatory_enforcement

**SEC enforcement: 5/305 MEF stocks (1.6%)**

Expected coverage: sparse_expected. 5 of 305 MEF universe stocks present in masd.secapi_regulatory_enforcement.symbol.

- affected symbols: **300**

_Recommendation:_ Sparse-expected source: low coverage is by nature, not a quality issue. Only relevant when paired with a real-world event.

---

### `R008-mef-coverage` — masd.yahoo_stocks_analyst_estimates_1d

**Yahoo analyst estimates: 305/305 MEF stocks (100.0%)**

Expected coverage: broad. 305 of 305 MEF universe stocks present in masd.yahoo_stocks_analyst_estimates_1d.symbol.

- affected symbols: **0**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — masd.yahoo_stocks_eps_momentum_1d

**Yahoo EPS momentum: 305/305 MEF stocks (100.0%)**

Expected coverage: broad. 305 of 305 MEF universe stocks present in masd.yahoo_stocks_eps_momentum_1d.symbol.

- affected symbols: **0**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — shdb.analyst_estimates_1d

**Curated analyst estimates: 305/305 MEF stocks (100.0%)**

Expected coverage: broad. 305 of 305 MEF universe stocks present in shdb.analyst_estimates_1d.symbol.

- affected symbols: **0**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — shdb.congress_activity_signals

**Congress activity signals: 178/305 MEF stocks (58.4%)**

Expected coverage: sparse_expected. 178 of 305 MEF universe stocks present in shdb.congress_activity_signals.symbol.

- affected symbols: **127**

_Recommendation:_ Sparse-expected source: low coverage is by nature, not a quality issue. Only relevant when paired with a real-world event.

---

### `R008-mef-coverage` — shdb.eps_momentum_1d

**Curated EPS momentum: 305/305 MEF stocks (100.0%)**

Expected coverage: broad. 305 of 305 MEF universe stocks present in shdb.eps_momentum_1d.symbol.

- affected symbols: **0**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — shdb.event_filing

**SEC filing events (curated): 259/305 MEF stocks (84.9%)**

Expected coverage: broad. 259 of 305 MEF universe stocks present in shdb.event_filing.symbol.

- affected symbols: **46**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — shdb.event_market_news

**Curated market news: 305/305 MEF stocks (100.0%)**

Expected coverage: broad. 305 of 305 MEF universe stocks present in shdb.event_market_news.symbol.

- affected symbols: **0**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — shdb.insider_conviction_signals

**Insider conviction signals: 266/305 MEF stocks (87.2%)**

Expected coverage: broad. 266 of 305 MEF universe stocks present in shdb.insider_conviction_signals.symbol.

- affected symbols: **39**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — shdb.insider_mspr_signals

**Insider MSPR signals: 296/305 MEF stocks (97.0%)**

Expected coverage: broad. 296 of 305 MEF universe stocks present in shdb.insider_mspr_signals.symbol.

- affected symbols: **9**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — shdb.insider_trades

**Curated insider trades: 300/305 MEF stocks (98.4%)**

Expected coverage: broad. 300 of 305 MEF universe stocks present in shdb.insider_trades.symbol.

- affected symbols: **5**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — shdb.institutional_flow_signals

**13F flow signals: 305/305 MEF stocks (100.0%)**

Expected coverage: broad. 305 of 305 MEF universe stocks present in shdb.institutional_flow_signals.symbol.

- affected symbols: **0**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — shdb.institutional_holders_1q

**13F institutional holders: 305/305 MEF stocks (100.0%)**

Expected coverage: broad. 305 of 305 MEF universe stocks present in shdb.institutional_holders_1q.symbol.

- affected symbols: **0**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — shdb.news_av_ticker_sentiment

**Curated AV news sentiment: 305/305 MEF stocks (100.0%)**

Expected coverage: broad. 305 of 305 MEF universe stocks present in shdb.news_av_ticker_sentiment.symbol.

- affected symbols: **0**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — shdb.news_ticker_sentiment_1d

**Unified news sentiment: 305/305 MEF stocks (100.0%)**

Expected coverage: broad. 305 of 305 MEF universe stocks present in shdb.news_ticker_sentiment_1d.symbol.

- affected symbols: **0**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — shdb.sec_enforcement

**Curated SEC enforcement: 4/305 MEF stocks (1.3%)**

Expected coverage: sparse_expected. 4 of 305 MEF universe stocks present in shdb.sec_enforcement.symbol.

- affected symbols: **301**

_Recommendation:_ Sparse-expected source: low coverage is by nature, not a quality issue. Only relevant when paired with a real-world event.

---

### `R008-mef-coverage` — shdb.sentiment_consumer_complaints_1d

**Curated CFPB complaints: 13/305 MEF stocks (4.3%)**

Expected coverage: sparse_expected. 13 of 305 MEF universe stocks present in shdb.sentiment_consumer_complaints_1d.symbol.

- affected symbols: **292**

_Recommendation:_ Sparse-expected source: low coverage is by nature, not a quality issue. Only relevant when paired with a real-world event.

---

### `R008-mef-coverage` — shdb.stock_news_1d

**Curated Polygon news: 267/305 MEF stocks (87.5%)**

Expected coverage: broad. 267 of 305 MEF universe stocks present in shdb.stock_news_1d.symbol.

- affected symbols: **38**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — shdb.stock_short_interest

**Curated short interest: 305/305 MEF stocks (100.0%)**

Expected coverage: broad. 305 of 305 MEF universe stocks present in shdb.stock_short_interest.symbol.

- affected symbols: **0**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — shdb.stock_short_volume_1d

**Curated short volume: 305/305 MEF stocks (100.0%)**

Expected coverage: broad. 305 of 305 MEF universe stocks present in shdb.stock_short_volume_1d.symbol.

- affected symbols: **0**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R008-mef-coverage` — shdb.symbol_event_sentiment_1d

**Symbol event sentiment: 305/305 MEF stocks (100.0%)**

Expected coverage: broad. 305 of 305 MEF universe stocks present in shdb.symbol_event_sentiment_1d.symbol.

- affected symbols: **0**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

## Methodology

This report was generated by **QSA** (Qualitative Signal Audit), a read-only audit tool that opens MASD, SHDB, and MEFDB connections in `readonly=true` mode and runs a fixed set of validation rules. No table is modified. To re-run:

```
cd ~/repos/qsa && source venv/bin/activate
qsa audit qualitative
```
