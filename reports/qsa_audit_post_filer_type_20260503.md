# QSA — Qualitative Signal Audit Report

*Generated: 2026-05-03T23:01:09*

Read-only audit of qualitative / sentiment / event data across MASD and SHDB.
This report identifies data-quality issues; it does not modify any database.

## Summary

- 🔴 Critical: **7**
- 🟡 Warning:  **16**
- 🟢 Info:     **35**
- Total:      **58**

### By category

- 🛠  **Active defects**     — likely real issues, action recommended: **1**
- 👀 **Monitoring**           — staleness / thin coverage; watch but not broken: **1**
- 🗄  **Retired sources**     — formally retired; tracked here for visibility: **14**
- 📐 **Structural / by-design** — known correct NULLs (e.g. individual defendants): **4**
- 📊 **Coverage info**         — population stats vs the MEF universe: **38**

## Findings by Rule

| Rule | Severity counts | Description |
|---|---|---|
| `R003-missing-symbols` | 🔴 1 🟢 4 | Rows missing a symbol where one is required |
| `R006-staleness` | 🔴 1 | Streams whose most-recent observation is past threshold |
| `R007-deprecated-tables` | 🟡 14 | Tables marked deprecated; live consumers across AFT |
| `R008-mef-coverage` | 🔴 5 🟢 31 | MEF universe coverage per qualitative table |
| `R009-thin-coverage` | 🟡 2 | Tables with unexpectedly low distinct-symbol counts |

## 🔴 CRITICAL (7)

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

**43/43 (100.0%) actionable missing symbol**

Curated penalties; entity_type filter applied if column present.

NULL symbol: 43 of 43 (100.0%). Table has no entity_type / filer_type column to disambiguate; UDC follow-up needed to surface entity context here.

- affected rows: **43**

_Recommendation:_ Add an entity_type or filer_type column at the producing layer (MDC ingest or UDC curation) so this finding can distinguish structural NULLs from actionable ones. Until then every NULL is treated as actionable, which inflates this finding.

---

### `R006-staleness` — shdb.stock_short_interest

**shdb.stock_short_interest stale: max(settlement_date)=2026-02-27 (65d ago)**

Cadence=daily, threshold=5d. Most recent observation is 2026-02-27 (65 days ago). 504,559 total rows.

- affected rows: **504,559**

_Recommendation:_ Check the upstream collector/ingest cron and whether the source API is still returning data. Some streams (Finnhub MSPR, free-tier APIs) may have expired entitlements rather than pipeline bugs.

---

## 🟡 WARNING (16)

### `R007-deprecated-tables` — masd.finnhub_news_article_symbols

**1 reference(s) to deprecated masd.finnhub_news_article_symbols in 1 file(s)**

Scanned 8 repos.
Preferred replacement: news_av_ticker_sentiment

Each match is a literal occurrence of the bare table name. Some hits will be deprecation notes / READMEs (which is fine); only code/SQL hits are live consumers.

- affected rows: **1**

**Sample:**

| file | line | text |
|---|---|---|
| /home/johnh/repos/udc/docs/shdb_design.md | 90 | | `finnhub_news_article_symbols` | Provider disabled; retired in catalog | 2026-02 | |

_Recommendation:_ Migrate live code/SQL consumers to news_av_ticker_sentiment. Comment-only hits (READMEs, notes, this audit) are not action items.

---

### `R007-deprecated-tables` — masd.finnhub_news_articles

**1 reference(s) to deprecated masd.finnhub_news_articles in 1 file(s)**

Scanned 8 repos.
Preferred replacement: alphavantage_news_sentiment_1d / news_av_ticker_sentiment

Each match is a literal occurrence of the bare table name. Some hits will be deprecation notes / READMEs (which is fine); only code/SQL hits are live consumers.

- affected rows: **1**

**Sample:**

| file | line | text |
|---|---|---|
| /home/johnh/repos/udc/docs/shdb_design.md | 89 | | `finnhub_news_articles` | Provider disabled; retired in catalog | 2026-02 | |

_Recommendation:_ Migrate live code/SQL consumers to alphavantage_news_sentiment_1d / news_av_ticker_sentiment. Comment-only hits (READMEs, notes, this audit) are not action items.

---

### `R007-deprecated-tables` — masd.finnhub_stocks_insider_mspr_1m

**8 reference(s) to deprecated masd.finnhub_stocks_insider_mspr_1m in 5 file(s)**

Scanned 8 repos.
Preferred replacement: insider_conviction_signals

Each match is a literal occurrence of the bare table name. Some hits will be deprecation notes / READMEs (which is fine); only code/SQL hits are live consumers.

- affected rows: **8**

**Sample:**

| file | line | text |
|---|---|---|
| /home/johnh/repos/udc/config/datasets/insider_mspr_1m.yaml | 7 | source_table: masd_foreign.finnhub_stocks_insider_mspr_1m |
| /home/johnh/repos/udc/config/datasets/insider_mspr_1m.yaml | 10 | - masd.finnhub_stocks_insider_mspr_1m |
| /home/johnh/repos/udc/config/table_meta/corporate_events/insider_mspr_1m.yaml | 59 | - masd_foreign.finnhub_stocks_insider_mspr_1m |
| /home/johnh/repos/udc/docs/shdb_design.md | 92 | | `finnhub_stocks_insider_mspr_1m` | Provider disabled; retired in catalog | 2026-02 | |
| /home/johnh/repos/udc/sql/shdb/018_new_layer1_tables.sql | 125 | source_table        TEXT             NOT NULL DEFAULT 'masd.finnhub_stocks_insider_mspr_1m', |
| /home/johnh/repos/udc/src/udc/builders/shdb/research.py | 421 | 'masd.finnhub_stocks_insider_mspr_1m'::text AS source_table |
| /home/johnh/repos/udc/src/udc/builders/shdb/research.py | 422 | FROM masd_foreign.finnhub_stocks_insider_mspr_1m im |
| /home/johnh/repos/udc/src/udc/builders/shdb/research.py | 466 | source_table="masd.finnhub_stocks_insider_mspr_1m", |

_Recommendation:_ Migrate live code/SQL consumers to insider_conviction_signals. Comment-only hits (READMEs, notes, this audit) are not action items.

---

### `R007-deprecated-tables` — masd.finnhub_stocks_insider_txn

**1 reference(s) to deprecated masd.finnhub_stocks_insider_txn in 1 file(s)**

Scanned 8 repos.
Preferred replacement: fmp_stocks_insider_trades / sec_edgar_filing_events (Form 4)

Each match is a literal occurrence of the bare table name. Some hits will be deprecation notes / READMEs (which is fine); only code/SQL hits are live consumers.

- affected rows: **1**

**Sample:**

| file | line | text |
|---|---|---|
| /home/johnh/repos/udc/docs/shdb_design.md | 91 | | `finnhub_stocks_insider_txn` | Provider disabled; FMP used for insider data instead | 2026-02 | |

_Recommendation:_ Migrate live code/SQL consumers to fmp_stocks_insider_trades / sec_edgar_filing_events (Form 4). Comment-only hits (READMEs, notes, this audit) are not action items.

---

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

### `R007-deprecated-tables` — shdb.insider_mspr_1m

**52 reference(s) to deprecated shdb.insider_mspr_1m in 17 file(s)**

Scanned 8 repos.
Preferred replacement: insider_conviction_signals

Each match is a literal occurrence of the bare table name. Some hits will be deprecation notes / READMEs (which is fine); only code/SQL hits are live consumers.

- affected rows: **52**

**Sample:**

| file | line | text |
|---|---|---|
| /home/johnh/repos/rse/docs/rse_shdb_intake_reference.md | 158 | | Insider / institutional | Insider trades | `shdb.insider_trades` (81K rows, 2021→), `insider_activity_signals`, `insider_mspr_1m`, `insider_mspr_signals` | | |
| /home/johnh/repos/udc/config/datasets/insider_mspr_1m.yaml | 1 | name: insider_mspr_1m |
| /home/johnh/repos/udc/config/datasets/insider_mspr_1m.yaml | 7 | source_table: masd_foreign.finnhub_stocks_insider_mspr_1m |
| /home/johnh/repos/udc/config/datasets/insider_mspr_1m.yaml | 8 | target_table: shdb.insider_mspr_1m |
| /home/johnh/repos/udc/config/shdb_catalog.yaml | 2443 | insider_mspr_1m: |
| /home/johnh/repos/udc/config/shdb_catalog.yaml | 2454 | lineage: { source_systems: [internal], source_tables: [shdb.insider_mspr_1m], upstream_dependencies: [insider_mspr_1m], downstream_dependencies: [], refresh_fre |
| /home/johnh/repos/udc/config/table_meta/corporate_events/insider_mspr_1m.yaml | 2 | # shdb.insider_mspr_1m — Per-Table Metadata |
| /home/johnh/repos/udc/config/table_meta/corporate_events/insider_mspr_1m.yaml | 8 | table_name: insider_mspr_1m |
| /home/johnh/repos/udc/config/table_meta/corporate_events/insider_mspr_1m.yaml | 10 | full_name: shdb.insider_mspr_1m |
| /home/johnh/repos/udc/config/table_meta/corporate_events/insider_mspr_signals.yaml | 24 | Z-scored MSPR with extreme buying/selling flags derived from insider_mspr_1m. |

_Recommendation:_ Migrate live code/SQL consumers to insider_conviction_signals. Comment-only hits (READMEs, notes, this audit) are not action items.

---

### `R007-deprecated-tables` — shdb.insider_mspr_signals

**34 reference(s) to deprecated shdb.insider_mspr_signals in 16 file(s)**

Scanned 8 repos.
Preferred replacement: insider_conviction_signals

Each match is a literal occurrence of the bare table name. Some hits will be deprecation notes / READMEs (which is fine); only code/SQL hits are live consumers.

- affected rows: **34**

**Sample:**

| file | line | text |
|---|---|---|
| /home/johnh/repos/rse/docs/rse_shdb_intake_reference.md | 158 | | Insider / institutional | Insider trades | `shdb.insider_trades` (81K rows, 2021→), `insider_activity_signals`, `insider_mspr_1m`, `insider_mspr_signals` | | |
| /home/johnh/repos/udc/config/datasets/insider_mspr_signals.yaml | 1 | name: insider_mspr_signals |
| /home/johnh/repos/udc/config/shdb_catalog.yaml | 2447 | lineage: { source_systems: [FMP], source_tables: [masd_foreign.fmp_stocks_insider_trades], upstream_dependencies: [symbol_master], downstream_dependencies: [ins |
| /home/johnh/repos/udc/config/shdb_catalog.yaml | 2448 | usage: { tags: [timeseries, symbol-level, monthly, cleaned], common_join_keys: [symbol, year, month], join_guidance: "Monthly grain. Feeds insider_mspr_signals. |
| /home/johnh/repos/udc/config/shdb_catalog.yaml | 2450 | insider_mspr_signals: |
| /home/johnh/repos/udc/config/table_meta/corporate_events/insider_mspr_1m.yaml | 63 | - insider_mspr_signals |
| /home/johnh/repos/udc/config/table_meta/corporate_events/insider_mspr_1m.yaml | 125 | - target_table: insider_mspr_signals |
| /home/johnh/repos/udc/config/table_meta/corporate_events/insider_mspr_signals.yaml | 2 | # shdb.insider_mspr_signals — Per-Table Metadata |
| /home/johnh/repos/udc/config/table_meta/corporate_events/insider_mspr_signals.yaml | 8 | table_name: insider_mspr_signals |
| /home/johnh/repos/udc/config/table_meta/corporate_events/insider_mspr_signals.yaml | 10 | full_name: shdb.insider_mspr_signals |

_Recommendation:_ Migrate live code/SQL consumers to insider_conviction_signals. Comment-only hits (READMEs, notes, this audit) are not action items.

---

### `R007-deprecated-tables` — masd.finnhub_news_article_symbols

**Deprecated table masd.finnhub_news_article_symbols still present (123,114 rows)**

Reason: RETIRED 2026-05-03 — Finnhub provider retired.
Preferred source: news_av_ticker_sentiment

Consumer-grep results are listed in the cross-cutting findings section.

- affected rows: **123,114**

_Recommendation:_ Do not consume this table from new pipelines. Migrate any existing consumers to news_av_ticker_sentiment. Optionally add a DB COMMENT marking the table deprecated so anyone inspecting the schema sees the warning.

---

### `R007-deprecated-tables` — masd.finnhub_news_articles

**Deprecated table masd.finnhub_news_articles still present (87,278 rows)**

Reason: RETIRED 2026-05-03 — Finnhub provider retired; news superseded by AlphaVantage.
Preferred source: alphavantage_news_sentiment_1d / news_av_ticker_sentiment

Consumer-grep results are listed in the cross-cutting findings section.

- affected rows: **87,278**

_Recommendation:_ Do not consume this table from new pipelines. Migrate any existing consumers to alphavantage_news_sentiment_1d / news_av_ticker_sentiment. Optionally add a DB COMMENT marking the table deprecated so anyone inspecting the schema sees the warning.

---

### `R007-deprecated-tables` — masd.finnhub_stocks_insider_mspr_1m

**Deprecated table masd.finnhub_stocks_insider_mspr_1m still present (3,796 rows)**

Reason: RETIRED 2026-05-03 — Finnhub MSPR retired; smooth proxy derivable from insider_conviction_signals.
Preferred source: insider_conviction_signals

Consumer-grep results are listed in the cross-cutting findings section.

- affected rows: **3,796**

_Recommendation:_ Do not consume this table from new pipelines. Migrate any existing consumers to insider_conviction_signals. Optionally add a DB COMMENT marking the table deprecated so anyone inspecting the schema sees the warning.

---

### `R007-deprecated-tables` — masd.finnhub_stocks_insider_txn

**Deprecated table masd.finnhub_stocks_insider_txn still present (59,887 rows)**

Reason: RETIRED 2026-05-03 — Finnhub provider retired; insider data superseded by FMP + SEC EDGAR.
Preferred source: fmp_stocks_insider_trades / sec_edgar_filing_events (Form 4)

Consumer-grep results are listed in the cross-cutting findings section.

- affected rows: **59,887**

_Recommendation:_ Do not consume this table from new pipelines. Migrate any existing consumers to fmp_stocks_insider_trades / sec_edgar_filing_events (Form 4). Optionally add a DB COMMENT marking the table deprecated so anyone inspecting the schema sees the warning.

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

### `R007-deprecated-tables` — shdb.insider_mspr_1m

**Deprecated table shdb.insider_mspr_1m still present (3,742 rows)**

Reason: RETIRED 2026-05-03 — built from frozen Finnhub MSPR; no live consumers.
Preferred source: insider_conviction_signals

Consumer-grep results are listed in the cross-cutting findings section.

- affected rows: **3,742**

_Recommendation:_ Do not consume this table from new pipelines. Migrate any existing consumers to insider_conviction_signals. Optionally add a DB COMMENT marking the table deprecated so anyone inspecting the schema sees the warning.

---

### `R007-deprecated-tables` — shdb.insider_mspr_signals

**Deprecated table shdb.insider_mspr_signals still present (3,742 rows)**

Reason: RETIRED 2026-05-03 — derived from frozen Finnhub MSPR.
Preferred source: insider_conviction_signals

Consumer-grep results are listed in the cross-cutting findings section.

- affected rows: **3,742**

_Recommendation:_ Do not consume this table from new pipelines. Migrate any existing consumers to insider_conviction_signals. Optionally add a DB COMMENT marking the table deprecated so anyone inspecting the schema sees the warning.

---

## 🟢 INFO (35)

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

### `R003-missing-symbols` — masd.sec_edgar_filing_events

**actionable: 0 | monitor: 10,183 (delisted+ambiguous) | structural: 100,097 (Form 4 / non-equity)**

EDGAR filings; filer_type + ticker_mapping_status disambiguate Form 4 (insider) from public-company filings.

Total rows: 154,112
NULL ticker_derived: 110,280 (71.6%)
  • Structural   (filer_type=person OR status=non_equity_filer): 100,097 (65.0%)
  • Monitor      (status=delisted_or_unmapped, ambiguous): 10,183 (6.6%)
  • Actionable   (genuine missing-symbol; should have resolved): 0 (0.0%)

- affected rows: **0**

_Recommendation:_ Form 4 / 4-A filings have filer_type=person — the cik refers to an insider, not a tradable entity. Those NULLs are correct. delisted_or_unmapped and ambiguous rows are visible but not active defects. Genuinely actionable rows (status=unknown or filer_type=unknown with NULL ticker) are rare; investigate those individually.

---

### `R008-mef-coverage` — masd.sec_edgar_filing_events

**SEC EDGAR filings: 294/305 MEF stocks (96.4%)**

Expected coverage: broad. 294 of 305 MEF universe stocks present in masd.sec_edgar_filing_events.ticker_derived.

- affected symbols: **11**

_Recommendation:_ Broad sources falling below 50% coverage indicate ingestion or symbol-mapping issues. Compare MASD source row counts to SHDB curated row counts to localise the bottleneck (R009 also covers analyst-grades / price-targets explicitly).

---

### `R003-missing-symbols` — masd.secapi_regulatory_enforcement

**243/597 (40.7%) actionable missing symbol; 282 structurally NULL**

Enforcement targets individuals/private LLCs; only company rows are actionable.

Total rows: 597
NULL symbol: 525 (87.9%)
  • of which structurally correct (individuals / funds / private / agencies / system / other): 282 (47.2%)
  • of which actionable (entity_type=company or unknown): 243 (40.7% of total)

- affected rows: **243**

_Recommendation:_ Investigate whether company_name / CIK fields can be resolved to a ticker. Rows the resolver leaves NULL are explained by entity_type — UDC consumers should filter `entity_type='company' AND symbol IS NOT NULL` for per-symbol equity signals.

---

### `R008-mef-coverage` — masd.secapi_regulatory_enforcement

**SEC enforcement: 5/305 MEF stocks (1.6%)**

Expected coverage: sparse_expected. 5 of 305 MEF universe stocks present in masd.secapi_regulatory_enforcement.symbol.

- affected symbols: **300**

_Recommendation:_ Sparse-expected source: low coverage is by nature, not a quality issue. Only relevant when paired with a real-world event.

---

### `R003-missing-symbols` — masd.secapi_regulatory_penalties

**19/130 (14.6%) actionable missing symbol; 109 structurally NULL**

Penalties target individuals/private LLCs; only company rows are actionable.

Total rows: 130
NULL symbol: 128 (98.5%)
  • of which structurally correct (individuals / funds / private / agencies / system / other): 109 (83.8%)
  • of which actionable (entity_type=company or unknown): 19 (14.6% of total)

- affected rows: **19**

_Recommendation:_ Investigate whether company_name / CIK fields can be resolved to a ticker. Rows the resolver leaves NULL are explained by entity_type — UDC consumers should filter `entity_type='company' AND symbol IS NOT NULL` for per-symbol equity signals.

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

### `R003-missing-symbols` — shdb.sec_enforcement

**117/290 (40.3%) actionable missing symbol; 139 structurally NULL**

Curated enforcement; entity_type filter applied if column present.

Total rows: 290
NULL symbol: 256 (88.3%)
  • of which structurally correct (individuals / funds / private / agencies / system / other): 139 (47.9%)
  • of which actionable (entity_type=company or unknown): 117 (40.3% of total)

- affected rows: **117**

_Recommendation:_ Investigate whether company_name / CIK fields can be resolved to a ticker. Rows the resolver leaves NULL are explained by entity_type — UDC consumers should filter `entity_type='company' AND symbol IS NOT NULL` for per-symbol equity signals.

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
