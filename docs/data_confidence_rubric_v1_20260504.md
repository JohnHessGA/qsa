# Qualitative Data Confidence Rubric — v1 (News/Sentiment Anchor)

*Generated: 2026-05-04. Path B1 deliverable: design the qualitative
data-confidence rubric before drafting the canonical qualitative mart
(Path B2). Anchor source for v1: news/sentiment.*

---

## ⚠ This is **data confidence**, not prediction confidence.

A high-confidence bearish-news signal means we **trust the news
observation itself**: the data is fresh, the article maps to the right
symbol, multiple sources are saying the same thing, and there is no
mapping ambiguity. It does **not** mean the stock will fall.

Prediction confidence comes later, in MEF/RSE/CCW, after qualitative
signals are combined with price, fundamentals, events, and strategy
logic. Keeping the two layers separate is the entire point of B1.

If a sentence in a downstream design starts with *"because confidence
is high, the prediction is..."* — that sentence is wrong by
construction. Confidence is an input weight on the **observation**, not
on the conclusion.

---

## Rubric overview

Every qualitative source publishes a row per (symbol, obs_date) into
SHDB, and now also publishes a confidence row at the same grain. The
confidence row answers four orthogonal questions about the underlying
observation:

1. **How fresh is it?** — `freshness_score`
2. **How much data backs it?** — `coverage_depth_score`
3. **Are we sure it's about this symbol?** — `mapping_certainty_score`
4. **Do independent sources agree?** — `source_count_score` /
   `dispersion_score`

These sub-scores roll up to a single `confidence_score` (0–100) plus a
human-readable `confidence_status` band, plus structured flags
explaining the score. Backtest-safe: every component is computable
using only data that would have been available as of `obs_date`.

The roll-up rule deliberately treats mapping certainty as a **gate**,
not an average — if we're not sure the row is about AAPL, the rest of
the dimensions don't matter. Other sub-scores blend via weighted mean.

---

## Common confidence schema

Every source publishes these columns into its own
`<source>_confidence_1d` table. The mart (B2) will pivot or join these
into a single canonical view.

```sql
CREATE TABLE shdb.news_confidence_1d (
    -- Identity (matches the underlying signal table's grain)
    source_name              TEXT       NOT NULL,    -- e.g. 'news_ticker_sentiment'
    symbol                   TEXT       NOT NULL,
    obs_date                 DATE       NOT NULL,

    -- Backtest-safe provenance
    as_of_date               DATE       NOT NULL,    -- data_available_date; equal to or
                                                     -- later than obs_date for sources
                                                     -- with publication lag
    confidence_version       TEXT       NOT NULL,    -- e.g. 'news.v1.0.0'

    -- Common sub-scores (all 0-100; NULL where not applicable)
    freshness_score          SMALLINT,
    coverage_depth_score     SMALLINT,
    mapping_certainty_score  SMALLINT,
    source_count_score       SMALLINT,
    dispersion_score         SMALLINT,

    -- Roll-up
    confidence_score         SMALLINT   NOT NULL,    -- 0-100
    confidence_status        TEXT       NOT NULL,    -- high|medium|low|insufficient

    -- Structured explanation
    confidence_flags         TEXT[],                  -- e.g. ['stale','single_source']
    confidence_reason        TEXT,                    -- one-line human summary

    -- Source-specific extensions live here as nullable columns;
    -- mart layer picks them up if useful, otherwise ignored.
    article_count            INTEGER,
    distinct_source_count    INTEGER,
    sentiment_dispersion     DOUBLE PRECISION,        -- max - min (sentiment in [-1, 1])
    bullish_share            DOUBLE PRECISION,
    bearish_share            DOUBLE PRECISION,
    neutral_share            DOUBLE PRECISION,

    -- Bookkeeping
    computed_at_utc          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_name, symbol, obs_date)
);
```

Why these columns specifically:

- `as_of_date` separated from `obs_date` is what makes backtests
  honest. A news article published 2026-04-15 but tagged with
  `obs_date=2026-04-14` (because it covered yesterday's close) would
  have `as_of_date=2026-04-15`. Backtests must filter on
  `as_of_date <= simulation_date`, not on `obs_date`.
- `confidence_version` so a future change in the rubric doesn't
  silently rewrite history. Old rows keep their original score; new
  rows compute under the new version. A migration tagged `v2.0.0`
  signals "old and new are not directly comparable."
- `confidence_flags` (text array) is intentionally finite — a small
  controlled vocabulary. Examples: `stale`, `single_source`,
  `low_article_count`, `mapping_unverified`, `high_dispersion`,
  `partial_coverage`. These flags are what RSE explains *with*, and
  what MEF/CCW gate *on*.

---

## Scoring dimensions — definitions

Each sub-score is on a 0–100 scale. NULL means "the dimension does not
apply to this source" (e.g. `dispersion_score` for a single-source
feed). Scoring functions are **monotonic** in the underlying input —
more freshness → higher freshness_score, no surprises.

### freshness_score

How recent is the observation, measured at `as_of_date`?

- 100 = data available within the source's normal cadence (same day
  for daily sources; within publication-lag window for lagged
  sources like FINRA short-interest)
- 0 = data older than the source's "stale" threshold

Formula (linear decay between two cadence-aware breakpoints):

```
let age = today - as_of_date  (days)
let fresh_threshold  = source.fresh_threshold_days   # 100 below this
let stale_threshold  = source.stale_threshold_days   # 0 above this

if age <= fresh_threshold:        score = 100
elif age >= stale_threshold:      score = 0
else:                             score = 100 * (stale - age) / (stale - fresh)
```

For news/sentiment v1: `fresh_threshold=2`, `stale_threshold=14`. A
day-old aggregate scores 100; an article whose latest data point is
two weeks old scores 0.

### coverage_depth_score

How much underlying data backs the observation?

For news/sentiment, "depth" is article count. For other sources it'd
be transaction count (insider), trade count (Congress), etc. Use a
log-shaped curve so the first article counts a lot, the 50th counts
little:

```
score = clamp(0, 100, 30 * log10(1 + n))
```

Where `n` is the underlying observation count. n=1 → 30, n=3 → 56,
n=10 → 70, n=30 → 96, n>50 → 100.

### mapping_certainty_score

Are we sure this row is about this symbol?

This is the **gate** dimension — if it's low, the roll-up score is
forced low regardless of the others. The rule:

```
if mapping_certainty_score < 50: confidence_status = 'insufficient'
                                  confidence_score   = mapping_certainty_score
                                  confidence_flags  += ['mapping_unverified']
                                  return  # short-circuit, skip the rest
```

For news/sentiment v1: derived from the entity-match score when
available (Marketaux, AlphaVantage), and from `relevance_score` for
ticker-level sentiment rows. Defaults to 100 when the source provides
explicit ticker tagging (e.g. AlphaVantage's per-ticker sentiment with
relevance >= 0.5). Defaults to 0 if the symbol field is NULL.

### source_count_score

How many distinct sources report on this symbol on this date? This is
about corroboration — do we have one publication saying it, or twenty?

```
score = clamp(0, 100, 20 * sqrt(distinct_sources))
```

distinct_sources=1 → 20, =3 → 35, =10 → 63, =25 → 100. The shape is
deliberately steep at the low end so a single source can never produce
a roll-up score above ~75.

For news/sentiment, "source" = distinct news outlet (Reuters,
Bloomberg, AP, etc.) — captured via the source field on each
underlying article.

### dispersion_score

How much do sources agree? Higher = more consensus.

For sentiment in [-1, +1]:

```
range = max_sentiment - min_sentiment           # in [0, 2]
score = clamp(0, 100, 100 * (1 - range / 2))
```

Range=0 (all sources identical) → 100; range=2 (one source +1, another
-1) → 0. Single-source rows have NULL dispersion (cannot compute).

For non-sentiment sources, dispersion may be NULL or replaced by a
domain-appropriate proxy (e.g. for insider transactions:
`buy_share - 0.5` magnitude as a "directional consensus" measure).

---

## Roll-up rule

```python
def confidence_score(sub: SubScores) -> int:
    # Gate on mapping certainty — no point averaging if the row might
    # not even be about this symbol.
    if sub.mapping_certainty < 50:
        return sub.mapping_certainty

    # Weighted average of the rest. Weights chosen so freshness +
    # coverage carry the most influence on the final score, with
    # corroboration / dispersion as adjustments.
    components = [
        (sub.freshness,       0.35),
        (sub.coverage_depth,  0.30),
        (sub.source_count,    0.20),
        (sub.dispersion,      0.15),
    ]
    weighted = [w * s for s, w in components if s is not None]
    weight_sum = sum(w for s, w in components if s is not None)
    score = sum(weighted) / weight_sum if weight_sum else 0
    return int(round(score))


def confidence_status(score: int, mapping_certainty: int) -> str:
    if mapping_certainty < 50:
        return "insufficient"
    if score >= 80:
        return "high"
    if score >= 50:
        return "medium"
    if score >= 20:
        return "low"
    return "insufficient"
```

The bands are deliberately wide — a 79 vs 81 boundary should not
change MEF/CCW behaviour. Consumers who need finer thresholds work
with the raw `confidence_score` directly.

---

## v1 scoring rules — news/sentiment

Source: `shdb.news_ticker_sentiment_1d` (the unified daily aggregate).
Each row already carries `article_count`, `avg_sentiment`,
`min_sentiment`, `max_sentiment`, `bullish_count`, `bearish_count`,
`neutral_count`, `sentiment_sma_7d`. Derive distinct-source-count
from the underlying article-level rows in
`shdb.news_av_ticker_sentiment` joined to
`shdb.news_av_sentiment_1d.source` (and the equivalent for Marketaux,
Polygon news).

```python
def score_news_row(row, today, distinct_source_count):
    age = (today - row.obs_date).days
    fresh = decay_score(age, fresh=2, stale=14)

    coverage = clamp(0, 100, 30 * log10(1 + row.article_count))

    # AlphaVantage provides per-ticker relevance; use the row's
    # avg_relevance when available, else 100 if symbol is set, else 0.
    if row.avg_relevance is not None:
        mapping = clamp(0, 100, int(row.avg_relevance * 100))
    elif row.symbol:
        mapping = 100
    else:
        mapping = 0

    sources = clamp(0, 100, int(20 * sqrt(distinct_source_count)))

    if row.article_count > 1:
        rng = (row.max_sentiment - row.min_sentiment)
        dispersion = clamp(0, 100, int(100 * (1 - rng / 2)))
    else:
        dispersion = None  # cannot compute on a single article

    return SubScores(fresh, coverage, mapping, sources, dispersion)
```

Flag rules (also in v1):

| Flag | When |
|---|---|
| `stale` | `freshness_score < 50` |
| `low_article_count` | `article_count < 3` |
| `single_source` | `distinct_source_count == 1` |
| `mapping_unverified` | `mapping_certainty_score < 50` |
| `high_dispersion` | `dispersion_score < 30` (sources strongly disagree) |
| `partial_coverage` | `article_count == 0` (the row exists for some other reason — typically a near-symbol mention) |

Reason text is built from the worst sub-score plus any active flags,
e.g.: *"low source_count (1 distinct source); also stale (last article
9 days ago)"*.

---

## Worked examples

These are real-shaped rows from the current SHDB
(`news_ticker_sentiment_1d` filtered to a few illustrative cases).

### Example 1 — high-confidence consensus around a major event

```
symbol               JPM
obs_date             2026-03-12      (JPM Q1 earnings)
as_of_date           2026-03-12

article_count                     119
distinct_source_count              31
avg_sentiment                   +0.42
min_sentiment                   -0.05
max_sentiment                   +0.81
avg_relevance                    0.94

freshness_score                   100   (today)
coverage_depth_score              100   (article_count >> 10)
mapping_certainty_score            94   (high relevance)
source_count_score                100   (31 distinct sources)
dispersion_score                   57   (range 0.86 → moderate consensus)

confidence_score                   91   weighted = .35*100 + .30*100 + .20*100 + .15*57
confidence_status                "high"
confidence_flags                  []
confidence_reason                 "broad coverage and consensus across sources"
```

MEF/CCW behaviour: include this signal at full weight. RSE
explanation: *"31 outlets covered JPM earnings on 2026-03-12 with
mostly bullish tone; we trust this observation."*

### Example 2 — single-source mention, otherwise fine

```
symbol               INSM
obs_date             2026-04-30
as_of_date           2026-04-30

article_count                       1
distinct_source_count               1
avg_sentiment                   -0.11
avg_relevance                    0.62

freshness_score                   100
coverage_depth_score               30   (only 1 article)
mapping_certainty_score            62
source_count_score                 20   (only 1 source)
dispersion_score                  NULL  (cannot compute on n=1)

confidence_score                   54   excludes dispersion from weighted avg
confidence_status                "medium"
confidence_flags                  ['low_article_count', 'single_source']
confidence_reason                 "only 1 article from 1 source"
```

MEF behaviour: weight this signal at 0.54 of normal. CCW behaviour:
treat as caution (a single mention isn't enough to skip a covered call
the firm is otherwise comfortable writing). RSE: *"single-source
mention from a low-relevance article; treat with caution."*

### Example 3 — stale + ambiguous mapping → insufficient

```
symbol               ACME            (hypothetical small-cap)
obs_date             2026-02-15
as_of_date           2026-02-15

article_count                       2
distinct_source_count               2
avg_relevance                    0.34   (entity match weak)

freshness_score                    14   (today is 2026-05-04, age 78d → stale)
coverage_depth_score               48
mapping_certainty_score            34   ← gate triggered
source_count_score                 28
dispersion_score                   60

confidence_score                   34   short-circuited at mapping
confidence_status                 "insufficient"
confidence_flags                  ['mapping_unverified', 'stale']
confidence_reason                 "entity match score below threshold; not safe to attribute to ACME"
```

MEF behaviour: drop the signal entirely (gate at confidence < 50). CCW:
ignore. RSE: *"we have a 2-article mention but the entity-match score
suggests it may not actually be about ACME; we're not surfacing this."*

### Example 4 — fresh, well-covered, but split

```
symbol               TSLA
obs_date             2026-04-15
as_of_date           2026-04-15

article_count                      87
distinct_source_count              23
avg_sentiment                   +0.05
min_sentiment                   -0.78
max_sentiment                   +0.91
avg_relevance                    0.92

freshness_score                   100
coverage_depth_score              100
mapping_certainty_score            92
source_count_score                 96
dispersion_score                   16   (range 1.69 → strongly split)

confidence_score                   83   freshness + coverage + sources dominate
confidence_status                 "high"
confidence_flags                  ['high_dispersion']
confidence_reason                 "well-covered but sources strongly disagree on tone"
```

Subtle case: the *observation* (lots of news, conflicting tone) is
high-confidence — we trust that the news landscape on TSLA looks like
this. Whether this should affect a trading decision is a different
question entirely (and lives in MEF, not here). The flag tells RSE to
explain it as "news consensus is split" rather than "we're confident
TSLA is going down."

---

## Consumer patterns

### MEF (forecasting / recommendation) — weight + optional gate

MEF v1 should treat confidence as a multiplicative weight on the
qualitative signal contribution to its ranker. A signal with
`confidence_score = 60` enters the ranker at 0.6× the strength of one
with `confidence_score = 100`.

```python
# MEF ranker, v1
qualitative_contribution = signal_value * (confidence_score / 100.0)
```

MEF may also expose a configurable hard gate per source — e.g. *"don't
let news/sentiment influence the ranker at all if confidence < 40"* —
because some MEF strategies prefer to drop weak inputs entirely rather
than weight them down. The threshold lives in `config/mef.yaml`, not
in the confidence schema, so MEF can tune without QSA/UDC churn:

```yaml
# mef.yaml
qualitative_gates:
  news:               { min_confidence: 40 }
  insider_conviction: { min_confidence: 50 }
  congress_activity:  { min_confidence: 50 }
  short_interest:     { min_confidence: 30 }   # publication-lag tolerated
```

When `confidence_status == 'insufficient'` the row is always dropped,
regardless of MEF's gate threshold. That's a contract of the rubric,
not a configurable choice.

### RSE (research & screening) — explanation

RSE should present the structured `confidence_flags` and
`confidence_reason` directly when answering inquiries. The natural
RSE pattern:

> *"Q: What's the news tone on TSLA today?"*
> *"A: News tone on 2026-04-15 was mixed (avg_sentiment=+0.05, range
> -0.78 to +0.91 across 87 articles from 23 sources). Confidence in
> this observation is **high (83/100)** — well-covered with
> high-relevance entity matching — but the sources disagree
> strongly (`high_dispersion` flag set), so the avg_sentiment number
> is more meaningful as a 'lots of mixed news' signal than as a
> directional reading."*

The flags are the structured handle; the reason is the
human-readable summary.

### CCW (covered-call writing) — caution / risk adjustment

CCW v1 should use confidence as a caution overlay, not a weight on
the option-selection score itself. A held position with a
**high-confidence bearish-news signal** is a stronger caution against
writing a deep ITM call than the same signal at low confidence.

```python
# CCW Friday hold-review, conceptual
if news.bearish_signal and news.confidence_status == 'high':
    flag_caution(symbol, "high-confidence bearish news; review hold")
elif news.bearish_signal and news.confidence_status == 'medium':
    note_for_review(symbol, "medium-confidence bearish news")
# low / insufficient: ignored
```

CCW need not threshold quantitatively — it's a human-in-loop tool, so
the status band is the right granularity.

---

## Backtest semantics

Backtests are the second-most-likely place data confidence gets
silently corrupted (after "prediction confidence vs data confidence"
itself). The rule is one line:

> A backtest at simulation date `D` uses confidence rows where
> `as_of_date <= D`.

Not `obs_date <= D`. The distinction matters whenever a source has
publication lag, because the row "exists" with `obs_date = D` but
isn't visible until `as_of_date = D + lag`. Filtering on `obs_date`
in a backtest is lookahead.

Concrete enforcement:

- Every confidence row carries `as_of_date` populated by the producer.
  For news/sentiment, `as_of_date = obs_date` (articles are published
  same-day). For FINRA short-interest, `as_of_date = settlement_date +
  publication_lag_days`. Producers know their lag; consumers don't
  have to.
- Mart layer (B2) will surface `as_of_date` prominently — the
  recommended pattern for any backtest query is `WHERE as_of_date <=
  :sim_date`, not `WHERE obs_date <= :sim_date`.
- `confidence_version` lets a backtest pin to a specific rubric
  version. If we ship v2 and re-score historical rows, both versions
  coexist; the backtest specifies which it wants.

If a future source has a complex publication pattern (e.g. SEC AAERs
publish irregularly with no fixed lag), `as_of_date` is the actual
date the data first became visible — taken from
`masd.sys_raw_file.collected_at_utc::date` if no source-side date is
available. Worst case is wider than reality, never narrower.

---

## v1 scope and what's NOT in scope

In scope:

- Common confidence schema (the table above).
- Sub-score definitions and roll-up rule.
- v1 scoring functions for news/sentiment.
- Documented consumer patterns (MEF / RSE / CCW).
- Backtest semantics.

Explicitly NOT in scope:

- Implementation of the news_confidence_1d table (a UDC builder PR).
- Confidence rubrics for the other 8 source families — those are
  open-questions sections below.
- Canonical qualitative mart design (Path B2) — sequenced after this.
- MEF / RSE / CCW integration code — sequenced after the mart lands.
- Confidence calibration / validation against outcomes — that's a
  prediction-confidence concern, not data-confidence.

---

## Open questions for the other source families

These are the next sources to slot into the framework. For each, the
question is *"what shape do the four common sub-scores take, and what
source-specific extensions make sense?"* I've sketched the rough
answer for each so a future design pass has a starting point.

### Insider activity (insider_conviction_signals)

- **freshness_score**: linear decay over the bar_date age; FINRA Form
  4 publishes T+2, so fresh_threshold=4, stale_threshold=21.
- **coverage_depth_score**: from `unique_buyers_30d` (or the
  buy/sell sum). Single-insider trades score lower than cluster
  trades.
- **mapping_certainty_score**: 100 — the symbol is part of the Form 4
  filing; no ambiguity.
- **source_count_score**: substitute `unique_buyers_30d` /
  `unique_sellers_30d` — corroboration here is across-insiders, not
  across-outlets.
- **dispersion_score**: substitute `cluster_buy` / `cluster_sell`
  flag agreement — mixed buy/sell pattern → low dispersion.
- **Source-specific extensions**: insider_role_quality (officer / 10%
  owner / director), buy_sell_ratio_z_score.

### Congressional trades (congress_activity_signals)

- **freshness_score**: STOCK Act mandates T+45 disclosure but most
  arrive within a few days. fresh_threshold=7, stale_threshold=60.
- **mapping_certainty_score**: 100 — disclosed symbols are explicit.
- **source_count_score**: distinct congresspeople trading the symbol
  in the window.
- **Source-specific extensions**: chamber (House / Senate),
  committee_alignment (does the trader sit on a committee that
  oversees this sector?), trade_size_band.

### Short interest (massive_stocks_short_int)

- **freshness_score**: FINRA bi-monthly + T+8 publication lag (handled
  via `as_of_date`). fresh_threshold=12, stale_threshold=21.
- **coverage_depth_score**: not a count — closer to "is the underlying
  shares outstanding meaningful?" Substitute by float-coverage if
  available, else 100.
- **mapping_certainty_score**: 100.
- **source_count_score**: 1 (single authoritative source, FINRA);
  always at the floor — `confidence_flags += ['single_source']`.
- **Source-specific extensions**: publication_lag_status (within
  expected lag / overdue), days_since_settlement.

### Institutional flow (institutional_flow_signals)

- **freshness_score**: 13F published 45 days after quarter-end.
  fresh_threshold=50, stale_threshold=130.
- **coverage_depth_score**: from holder count / total positions size.
- **mapping_certainty_score**: 100.
- **dispersion_score**: net buying vs net selling holders.
- **Source-specific extensions**: top10_pct_change,
  smart_money_concentration (if such a list exists).

### SEC enforcement / penalties (sec_enforcement, sec_penalties)

- **freshness_score**: depends on event_severity; high-severity
  enforcement decays slowly (still relevant 6+ months later).
- **mapping_certainty_score**: directly from `entity_type` /
  `mapping_status` we already added in MDC migrations 029/031. This
  is the one source family where the mapping certainty is genuinely
  variable — most other families are 100.
- **source_count_score**: 1 (SEC is authoritative); use
  `single_source` flag.
- **dispersion_score**: NULL.
- **Source-specific extensions**: event_severity, agreed_to_settle,
  parallel_actions_count.

### SEC EDGAR filings (event_filing)

- **freshness_score**: same-day publication. fresh_threshold=2.
- **mapping_certainty_score**: directly from `filer_type` /
  `ticker_mapping_status` — `person` filings are gated out (they
  *can't* map by definition).
- **source_count_score**: 1.
- **Source-specific extensions**: form_type weighting (8-K material
  events count more than routine filings).

### Social attention (event_social_attention / apewisdom)

- **freshness_score**: same-day; fresh_threshold=2,
  stale_threshold=7.
- **coverage_depth_score**: from mention_count.
- **mapping_certainty_score**: ApeWisdom uses ticker symbols
  directly; high but not 100 (acronym collisions are real — "ALL"
  could be a sentence word, "GME" is unambiguous).
- **source_count_score**: distinct subreddits / boards mentioning
  the symbol.
- **dispersion_score**: bullish vs bearish ratio if available.
- **Source-specific extensions**: rank_change_24h, retail_attention_z.

### Analyst data (analyst_estimates_1d, analyst_grades, analyst_price_targets_1d)

This is the trickiest family because there are three sub-streams with
different shapes:

- **analyst_estimates_1d** (forward consensus) — `coverage_depth` =
  `num_analysts_eps`; `dispersion` = `eps_high − eps_low` normalised
  to `eps_avg`; `mapping = 100`.
- **analyst_grades** (rating changes) — discrete events; `freshness`
  is bar_date age; `coverage` = `total_grades` (cumulative); `dispersion`
  = mix of upgrades vs downgrades.
- **analyst_price_targets_1d** — same-day snapshot; `dispersion` =
  `target_high − target_low` / `target_consensus`.

Open question: do these collapse into a single `analyst_confidence_1d`
or stay as three separate confidence streams? My current preference
is three streams that the mart pivots together — three different
underlying signals, three different freshness profiles, three
different consumer use cases.

---

## Open questions for the user

These would benefit from your weigh-in before B2 (mart) starts:

1. **Sub-score weights.** I picked `.35 / .30 / .20 / .15` for
   freshness / coverage / source-count / dispersion. Reasonable
   defaults but ultimately a judgment call. Alternative views:
   - Equal weights (.25 each) — simpler.
   - Coverage-heavy (.20 / .40 / .20 / .20) — more
     "depth matters most."
   - Freshness-heavy (.50 / .25 / .15 / .10) — more
     "fresh observations are the ones worth trusting."
   I'd ship with the current weights and tune from MEF backtest
   feedback when the time comes.

2. **Status band thresholds.** I went with 80/50/20 for
   high/medium/low/insufficient. These are exposed to RSE and CCW —
   want to validate they read intuitively before locking them in.

3. **Confidence column placement.** Should the v1 implementation
   land:
   - (a) per-source tables (`shdb.news_confidence_1d`,
     `shdb.insider_confidence_1d`, etc.) — what this doc proposes,
     OR
   - (b) one big `shdb.qualitative_confidence_1d` keyed on
     `(source_name, symbol, obs_date)` — fewer tables, more rows.
   The mart (B2) will probably end up flattening into the latter
   shape regardless. (a) is closer to UDC's existing per-source
   builder pattern; (b) is closer to the consumer's view.

4. **Source-specific extensions location.** The schema above puts
   them as nullable columns on the per-source confidence table. An
   alternative is a JSONB `extensions` column. JSONB is more flexible
   but harder to query. I'd ship with explicit nullable columns.

---

## Reference

- Output of this design phase feeds Path B2: canonical qualitative
  mart design.
- Underlying data layer state (post-cleanup baseline):
  `/mnt/aftdata/qsa/artifacts/2026/05/qualitative_cleanup_completion_20260503.md`.
- Per-source MASD/SHDB conventions (entity_type / filer_type / etc.)
  established by:
  - MDC migration 029 (sec_api penalty entity metadata)
  - MDC migration 031 (sec_edgar filer-type tagging)
  - QSA R003 entity-aware filter
- This rubric's version: **`v1.0.0-news-anchor`**. Insider, Congress,
  short-interest, etc., land under successive minor versions
  (`v1.1`, `v1.2`, …) as they get built.

---

*End of B1 deliverable. Next step is B2 (canonical qualitative mart
design) — but a quick pass on the open questions above first.*
