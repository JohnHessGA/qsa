# Finnhub — Retire vs. Re-enable Recommendation

*Generated: 2026-05-03 — peer to `mdc_masd_review_20260503.md`*

## TL;DR

**Recommend Option A: formally retire Finnhub from the qualitative-signal
pipeline.**

Every Finnhub dataset is either fully redundant with a cheaper or already-
running source (news, insider transactions) or marginally additive at a
disproportionate paid-tier cost (insider sentiment / MSPR). Zero
downstream consumers (MEF, CCW, CIA, IRA Guard, RSE, DAS, XPM) read any
`finnhub_*` MASD table or the SHDB `insider_mspr_signals` table built from
it — confirmed by repo-wide grep. The provider has been quietly disabled
for 78 days with no observed gap in any signal that ever shipped to a
running stream.

## Current state

| Dataset | MASD table | Last data | Last collect | Distinct symbols | Status |
|---|---|---|---|---:|:--:|
| company_news | `finnhub_news_articles` (+ `_article_symbols`) | 2026-02-14 | 2026-02-15 | 20 (hardcoded list) | 🔴 disabled |
| insider_transactions | `finnhub_stocks_insider_txn` | 2026-02-15 | 2026-02-15 | 641 | 🔴 disabled |
| insider_sentiment | `finnhub_stocks_insider_mspr_1m` | 2026-02 (Feb) | 2026-02-15 | 597 | 🔴 disabled |

Provider was disabled 2026-02-15 by explicit config decision. Reason
recorded in `config/providers/finnhub_news.yaml`: *"Free tier provides
limited analytical value... Paid sentiment tier costs $3,000/month — not
justified for current use."* Two malformed historical timestamps in
`finnhub_news_articles` are now caught at ingest by the new MDC
timestamp validator (PR `05ef483`), so re-enable is at least no longer a
correctness risk.

## Data value & redundancy

### Company news → fully redundant

| Source | MEF universe coverage | Distinct symbols | Article-level sentiment | Cost |
|---|---:|---:|:-:|---|
| AlphaVantage `news_ticker_sentiment` | **305 / 305** | 8,032 | yes (per-ticker score) | included |
| Polygon `massive_stocks_news_1d` | 267 / 305 | 582 | yes (per-article sentiment) | included |
| Marketaux `entity_sentiment` | 37 / 305 | 671 | yes (per-entity score) | included |
| **Finnhub `company_news`** | **19 / 305** | 20 | **no** (free tier had no scoring) | $3K/mo for sentiment tier |

Finnhub free tier provided no sentiment scores; we already had three
better sources for both raw articles AND scored sentiment. Finnhub adds
nothing.

### Insider transactions → fully redundant

| Source | Distinct symbols | Rows | Date range |
|---|---:|---:|---|
| FMP `insider_trading` | **4,932** | 130,769 | 2002-02-26 → 2026-05-01 |
| SEC EDGAR Form 4 | 42 (ticker_derived populated) | 70,683 | 2025-12-01 → 2026-05-01 |
| **Finnhub `insider_transactions`** | 641 | 59,887 | 2025-02-13 → 2026-02-15 |

FMP gives us 7.7× more distinct symbols and 24 years of history vs Finnhub's
~12 months. SEC EDGAR is the authoritative Form 4 source and benefits from
the new CIK→ticker resolver (PR `7487e78`). Finnhub adds nothing.

### Insider sentiment / MSPR → marginally additive, not unique

This is the only place Finnhub *might* be uniquely contributing.

`shdb.insider_mspr_signals` (built from `finnhub_stocks_insider_mspr_1m`):
| Aspect | MSPR signals | `insider_conviction_signals` (FMP-based, current) |
|---|---|---|
| Cadence | monthly per symbol | daily per symbol |
| Coverage | 586 distinct symbols | **2,579 distinct symbols** |
| Last bar | 2026-02-01 | 2026-05-01 |
| Output type | smooth numeric (`mspr`, `mspr_z_score`) + extreme flags | event-driven (`cluster_buy` / `cluster_sell` flags + 30-day rolling counts) |
| Underlying signal | insider buying pressure | insider buying pressure |

The metrics are *shaped* differently (a continuous monthly Z-score vs
discrete cluster events), but they measure the same underlying behaviour:
how much net insider buying is happening. The conviction signal — which
the CIA application stream consumes by design — covers 4.4× more symbols,
runs daily, and is built from clean Form-4-derived data via the CIA
team's deliberate "strict P/S only, no grants" policy (memory-noted as
the reason for adding `insider_conviction_signals` in the first place).

The MSPR's one unique property is that it is *continuous*: a smooth
monthly score that can sit in regression / scoring models without the
"event vs no event" cliff that conviction signals have. That's a
real-but-narrow analytical benefit. But:

1. No active stream uses it. CIA opted for conviction signals explicitly.
2. MSPR's monthly cadence is too slow for a daily-decision tool.
3. We can derive a smooth proxy from `insider_conviction_signals.buy_sell_ratio` and `net_shares_30d` if a future model wants one — without paying Finnhub.

## Cost / benefit

| Re-enable scenario | Annual cost | Net new signal value |
|---|---:|---|
| Free tier (current) | $0 | 19/305 MEF news with no scoring; insider txn duplicating FMP. Negligible. |
| Paid news + sentiment tier | **~$36,000** | A 4th sentiment source covering ≤20 symbols (paid tier still constrains to a configured list). Still less coverage than AlphaVantage already provides for free. |
| Paid "All-in-One" tier | higher | MSPR + sentiment, but no current consumer asks for either. |

**Even at the lowest paid tier the cost-to-uniqueness ratio is bad.**
$3,000/month for a fourth news source covering fewer symbols than the
three free ones we already use is hard to justify.

## Live-consumer audit

Repo-wide grep across the AFT application repos:

```
~/repos/mef     0 references to finnhub_* tables or insider_mspr_signals
~/repos/ccw     0 references
~/repos/cia     0 references (deliberately uses insider_conviction_signals)
~/repos/iraguard 0 references
~/repos/rse     0 references
~/repos/das     0 references
~/repos/xpm     0 references
```

The only references are in QSA's own audit rules (which inspect every
qualitative table by design). UDC still builds `insider_mspr_signals`
from the frozen MASD MSPR data, but nothing reads the result. Retirement
has zero blast radius on running streams.

## Recommendation

**Option A: Formally retire Finnhub from the qualitative-signal pipeline.**

### Reasoning

1. **News**: redundant. AlphaVantage already gives us 305/305 MEF coverage with sentiment scoring at no marginal cost.
2. **Insider transactions**: redundant. FMP provides 7.7× more distinct symbols and 24 years of history; SEC EDGAR is authoritative for Form 4.
3. **Insider sentiment / MSPR**: marginally additive (smooth monthly score) but no consumer wants it; CIA explicitly chose the conviction-signal alternative; we can synthesise a smooth proxy from existing data if needed.
4. **Cost**: paid tiers are out of proportion to the unique signal Finnhub would deliver. $36K/year minimum for what is at best a fourth news feed and at worst a duplicate.
5. **Risk**: zero downstream consumers. Retirement does not break any running stream.

### Follow-up cleanup tasks (Option A — retire)

These are **not** part of this recommendation deliverable; the user's
existing rules say no MDC/UDC/SHDB/QSA changes in this PR. List below
for the eventual retirement PR(s):

| # | Repo | Change | Why |
|--:|---|---|---|
| 1 | mdc | `config/providers/finnhub_news.yaml`: keep `enabled: false` (already true) and add a clear `# RETIRED 2026-MM-DD — see ~/repos/qsa/reports/finnhub_retire_recommendation_20260503.md` header. | Make retirement explicit, not just disabled-by-default. |
| 2 | mdc | Remove the cron entry for `finnhub_news` if any. (Verified: not in current crontab.) | No-op. |
| 3 | udc | Stop building `insider_mspr_signals`. Mark `insider_mspr_1m` and `insider_mspr_signals` as deprecated in `config/table_meta/` similar to how `insider_activity_signals` is being handled. | Source is frozen; producing rows from frozen input is wasted. |
| 4 | qsa | Adjust `R006-staleness` to **suppress** stale findings on tables tagged `retired_source: finnhub`. Same suppression for the `R008-mef-coverage` finding on the three Finnhub tables. (Suppression rather than deletion — historical data still earns its rule check during the deprecation grace window.) | Stop reporting Finnhub staleness as broken; it's intentional. |
| 5 | qsa | Add an `R007`-style entry to mark `finnhub_news_articles`, `finnhub_news_article_symbols`, `finnhub_stocks_insider_txn`, `finnhub_stocks_insider_mspr_1m` as `deprecated_tables` in `config/qsa.yaml`, replacement = explicit "retired — superseded by AlphaVantage / FMP / insider_conviction_signals". | Preserves the deprecation-tracking convention QSA already has for `insider_activity_signals`. |
| 6 | shdb | After ≥ 1 quarter of zero consumer reads in production, drop `shdb.insider_mspr_signals` and `shdb.insider_mspr_1m`. | Storage hygiene; the tables are static. Defer until clear they're truly unused. |
| 7 | data | Keep the existing MASD finnhub_* rows untouched. They're fixed-size historical data, ≈ 1 MB each, and provide lineage for any past inquiry that referenced them. | Per the user's "preserve raw source data" rule. |

### What we are *not* recommending

- **Not deleting** any historical MASD or SHDB row.
- **Not removing** the parser code, since the provider could conceivably be re-enabled by a future paid-tier decision; leaving the code dormant has a near-zero maintenance cost.
- **Not** modifying any consumer (MEF / CCW / CIA / IRA Guard / RSE) — none consume Finnhub data.

## When would re-enable make sense?

Re-evaluate only if **all three** become true:

1. We add a quantitative signal-confidence model that wants a smooth (continuous, not event-flag) insider-pressure score AND
2. The smooth proxy synthesised from existing FMP-based `insider_conviction_signals` is empirically inferior to MSPR for that model AND
3. The Finnhub paid plan is reduced or repackaged so the marginal cost is justifiable (i.e. <$5K/year).

Until then, retirement is the right call.

---

## Open questions for the user (none blocking)

- Confirm the table-deprecation cleanup (tasks 1, 4, 5) is what you want to schedule next, or whether SEC API enforcement metadata cleanup (item 7 on the original roadmap) takes priority.
- Whether the eventual retirement PR should batch tasks 1, 4, 5 (small, mechanical) into a single commit, or split mdc / qsa.

This recommendation is the deliverable; no code changes were made.
