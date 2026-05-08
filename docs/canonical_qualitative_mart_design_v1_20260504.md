# Canonical Qualitative Mart — v1 Design

*Generated: 2026-05-04. Path B2 deliverable: design the canonical daily
symbol-level qualitative mart that consumes the per-source confidence
tables defined in `data_confidence_rubric_v1_20260504.md`. Anchor source
for v1 implementation: news/sentiment.*

---

## Framing

This is **schema design**, not rubric redesign. The data-confidence
rubric (B1) defines per-source tables with sub-scores, roll-ups, status
bands, and flags. The mart pivots those per-source tables into a single
daily row per `(symbol, obs_date)` so downstream consumers (MEF, RSE,
CCW) join once and get everything they need to decide *how much to
trust* and *how much to weight* qualitative inputs for that symbol on
that date.

If a sentence in the mart design says *"we should change how confidence
is computed because..."* — that's a B1 v2 conversation, not a mart
conversation. The mart consumes confidence; it does not produce it.

The other principle to honour, per the user's note: **don't tune this
before it exists.** The v1 rubric is versioned (`confidence_version`
column, B1 design); the mart will be too. If the rubric changes,
historical mart rows keep their original `confidence_version` tag.
That gives us room to improve later without rewriting history.

---

## Goal

One row per `(symbol, obs_date)` containing, for every source family
that has anything to say about that symbol on that date:

1. **The underlying signal value** (avg_sentiment, net_insider_shares,
   etc.) — the thing the consumer would want to act on.
2. **The data-confidence score** for that signal, plus status band
   and flags — how much to trust it.
3. **A roll-up across sources** — a single confidence figure +
   posture for the row as a whole, plus enough audit metadata to
   explain *why the row reads strong / weak / stale / thin /
   conflicted / insufficient*.

Consumers in v1:

- **MEF** — uses confidence as a soft weight on the qualitative
  contribution to its ranker, with optional per-source hard gates
  configured in `mef.yaml`.
- **RSE** — uses confidence and flags directly for explanation and
  source-quality disclosure when answering inquiries.
- **CCW** — uses confidence status as a caution/risk overlay on the
  Friday hold-review.

## Non-goals

- ❌ Re-deriving any sub-score or roll-up rule. Defined in B1.
- ❌ Producing predictive direction (bullish/bearish forecasts). The
  mart can carry signed signal values, but those are *observations*,
  not forecasts.
- ❌ Storing per-article / per-trade detail. Those live in their
  respective SHDB source tables; the mart links via foreign-key-
  equivalent grain `(source_name, symbol, obs_date)`.
- ❌ Backfill of confidence for historical rows beyond what the
  per-source builders produce. The mart inherits whatever those
  produce.
- ❌ MEF/RSE/CCW integration code. The mart is the contract;
  consumers integrate later.

---

## Mart shape

### Layout: wide-pivot, one row per `(symbol, obs_date)`

Wide is the right call here for three reasons:

1. **Matches existing SHDB convention.** `mart.stock_equity_daily`
   and `mart.stock_options_underlying_daily` are both wide tables
   keyed on `(symbol, bar_date)`. Consumers expect this shape.
2. **LLM/AI front-door pattern.** A wide row is self-describing —
   one query, one symbol-date, all qualitative context. RSE in
   particular benefits from being able to ask *"give me the row"*
   instead of *"join across N source tables"*.
3. **Sparse-friendly.** Most cells will be NULL on most days
   (insider events are rare, SEC enforcement is rare). NULLs are
   cheap in Postgres; an extra column is cheaper than an extra row.

Estimated size: ~10K active symbols × ~250 trading days/year
× ~70 columns ≈ ~2.5M rows/year, comparable to existing SHDB marts.
Hypertable on `obs_date` to match the existing pattern.

### Identity columns

```
symbol            TEXT       NOT NULL
obs_date          DATE       NOT NULL
PRIMARY KEY (symbol, obs_date)
```

`obs_date` is what the row is *about* — the trading day the qualitative
signals describe. **Backtest filtering happens via per-source
`as_of_date` columns** (see §Backtest semantics below), not on
`obs_date` alone.

### Per-source column blocks

For each source family that emits a confidence row, the mart carries a
predictable namespace of columns. This is the news/sentiment block —
the same shape extends to the other 8 source families with appropriate
substitutions.

```
-- News block
news_data_present              BOOLEAN          -- TRUE if a row exists in
                                                -- shdb.news_confidence_1d for
                                                -- this (symbol, obs_date)
news_avg_sentiment             DOUBLE PRECISION -- from news_ticker_sentiment_1d
news_article_count             INTEGER
news_distinct_source_count     INTEGER
news_sentiment_dispersion      DOUBLE PRECISION -- max - min, in [0, 2]
news_bullish_share             DOUBLE PRECISION
news_bearish_share             DOUBLE PRECISION
news_confidence_score          SMALLINT         -- 0-100, from B1 rubric
news_confidence_status         TEXT             -- high|medium|low|insufficient
news_confidence_flags          TEXT[]           -- e.g. ['stale','single_source']
news_as_of_date                DATE             -- when this data became visible
news_confidence_version        TEXT             -- e.g. 'news.v1.0.0'
```

The `_data_present` boolean is the canonical "do we have anything to
say?" flag. When `FALSE`, the rest of the news block is NULL by
construction. This separates "no signal because no event" from "no
signal because the source is missing" — both common, both meaningful,
both currently confused if NULL is the only signal.

The full set of source families (each with its own block):

| Family | Block prefix | Underlying SHDB sources |
|---|---|---|
| News / sentiment | `news_` | `news_ticker_sentiment_1d`, `news_av_ticker_sentiment` (article-level) |
| Insider activity | `insider_` | `insider_conviction_signals`, `insider_trades` |
| Congressional trades | `congress_` | `congress_activity_signals`, `congress_trades` |
| Short interest | `short_int_` | `stock_short_interest` |
| Short volume | `short_vol_` | `stock_short_volume_1d` |
| Institutional flow | `inst_` | `institutional_flow_signals`, `institutional_holders_1q` |
| SEC enforcement | `sec_enf_` | `sec_enforcement`, `sec_penalties` |
| SEC EDGAR filings | `sec_edgar_` | `event_filing` (filtered to filer_type∈{public,subject}) |
| Social attention | `social_` | `event_social_attention` |
| Analyst | `analyst_` | `analyst_estimates_1d`, `analyst_grades`, `analyst_price_targets_1d` |

(Analyst is special — three sub-streams. v1 mart probably exposes them
as `analyst_estimates_*`, `analyst_grades_*`, `analyst_targets_*`
sub-prefixes inside one block. Refined in B1's "open questions for
analyst data" section.)

### Roll-up columns (across sources)

```
qualitative_confidence_score   SMALLINT   -- 0-100, mean of available source scores
qualitative_confidence_status  TEXT       -- high|medium|low|insufficient
qualitative_data_richness      SMALLINT   -- 0-100, fraction of source families
                                          -- with data_present = TRUE
qualitative_flags              TEXT[]     -- promoted from per-source flags
                                          -- when meaningful at the row level
                                          -- (e.g. ['conflicted','stale_majority'])
qualitative_reason             TEXT       -- one-line human summary
qualitative_version            TEXT       -- mart-roll-up logic version,
                                          -- e.g. 'mart.v1.0.0'

-- Posture column (data-side, not prediction-side):
qualitative_posture            TEXT       -- one of: rich | thin | stale |
                                          -- conflicted | insufficient | quiet
```

The roll-up rules are intentionally simple — and explicitly version-
tagged so they can change later without rewriting history:

```python
def rollup(per_source: dict[str, SourceConfidence]) -> Rollup:
    present = [c for c in per_source.values() if c.data_present]
    if not present:
        return Rollup(score=None, status="quiet", richness=0,
                      flags=[], reason="no qualitative source has data")

    # Roll-up score: arithmetic mean of available source scores.
    # Deliberately NOT weighted by source-importance — that's a
    # consumer concern, not a data-confidence concern.
    score = int(round(mean(c.confidence_score for c in present)))

    # Status band re-uses the B1 rubric's bands.
    status = ("high"         if score >= 80
              else "medium"  if score >= 50
              else "low"     if score >= 20
              else "insufficient")

    richness = int(round(100 * len(present) / TOTAL_SOURCE_FAMILIES))

    flags = collect_promoted_flags(per_source)
    posture = derive_posture(present, flags, status, richness)
    reason = build_reason(present, flags, posture, status)

    return Rollup(score, status, richness, flags, reason, posture)
```

Posture derivation is a small decision tree — easier to read than
formalize:

| Condition | Posture |
|---|---|
| No source has `data_present=TRUE` | `quiet` |
| `qualitative_confidence_status='insufficient'` (or only mapping-gated rows) | `insufficient` |
| ≥2 sources fresh + status≥medium + agreeing on direction (where applicable) | `rich` |
| ≥1 source fresh but only 1 family present | `thin` |
| All sources status≤low because of staleness flags | `stale` |
| Sources fresh but their signal values disagree (e.g. news bullish + insider bearish) | `conflicted` |
| Anything else | falls back to status name |

`qualitative_flags` is a small controlled vocabulary that promotes
notable per-source flags to row-level when they apply broadly. v1 set:
`stale_majority` (≥half of present sources flagged stale), `conflicted`
(directional sources disagree), `single_source_only`, `mapping_partial`
(≥1 source has `mapping_unverified`). Future versions can extend.

### Audit columns

```
mart_built_at_utc              TIMESTAMPTZ NOT NULL DEFAULT now()
mart_builder_version           TEXT        NOT NULL  -- e.g. 'mart_qualitative.v1.0.0'
```

That's it. Everything else (per-source confidence_version,
per-source as_of_date, per-source flags) is already on the row.

---

## Backtest semantics

The mart row is a **snapshot** — it's what the qualitative picture
looks like as of `MAX(per_source.as_of_date)` for that `(symbol,
obs_date)`. For most sources, `as_of_date == obs_date` (news,
sentiment, social attention). For lagged sources (FINRA short-interest,
13F, AAERs), `as_of_date` can be days or weeks later.

**For consumers asking "what should we believe today?"**, the mart row
is the answer. Read it directly.

**For backtests asking "what would we have believed on date D?"**,
the mart is *not* the right read — it's a current-day snapshot, and
its values may have changed since D as more sources published. The
correct backtest pattern reconstructs the mart on the fly:

```sql
-- For each source, take the most recent confidence row whose
-- as_of_date <= sim_date. Then aggregate.
WITH news AS (
    SELECT symbol, obs_date, confidence_score, confidence_status, ...
    FROM shdb.news_confidence_1d
    WHERE as_of_date <= :sim_date
    -- DISTINCT ON (symbol, obs_date) … ORDER BY as_of_date DESC
),
insider AS (
    SELECT symbol, obs_date, confidence_score, ...
    FROM shdb.insider_confidence_1d
    WHERE as_of_date <= :sim_date
    -- ...
),
-- ... per source ...
LEFT JOIN news USING (symbol, obs_date)
LEFT JOIN insider USING (symbol, obs_date)
-- compute the same roll-up the mart builder uses
```

This is a JOIN-and-aggregate pattern, expensive but correct. The mart
builder's roll-up logic is exposed as a SQL function (e.g.
`shdb.qualitative_rollup_v1(...)`) so backtests don't have to
re-implement it.

`mart_qualitative_daily` itself doesn't carry an `as_of_date` column at
the row level — the per-source `as_of_date`s tell the consumer
everything they need. A row-level `as_of_date` would be misleading
because different sources publish on different lags; aggregating into
one date hides that.

**Documentation rule for any future doc that uses the mart:** if the
example query is for current behaviour, the mart is fine. If it's for
backtests, the example must filter per-source confidence tables by
`as_of_date <= :sim_date`. Putting this rule in the mart's table
comment + a UDF that produces "the as-of view" of the mart for any
date is the cleanest way to keep this honest in production code.

---

## NULL semantics — a quick reference

The mart packs three different "no value here" cases into NULL today,
which is fine *only because* `<source>_data_present` distinguishes
them:

| `_data_present` | Sub-score / signal columns | Meaning |
|---|---|---|
| `TRUE` | populated | source has data; trust at its confidence_status |
| `FALSE`, no row in source's confidence table | NULL | source has nothing to say (e.g. no insider activity that day) — `quiet` posture |
| `FALSE`, source's confidence table flagged this row `insufficient` | NULL | mapping-gated; the data is there but we don't trust it enough to surface |
| `FALSE`, source is retired/suppressed (per `qsa.yaml deprecated_tables`) | NULL | source is intentionally not contributing |

Consumers should treat NULL signal columns as "absence", never as zero.
`qualitative_data_richness` is the headline number for "how many
sources contributed to this row" — it's the right thing to filter on
if a consumer wants to require breadth.

---

## Worked examples

### Example 1 — news + insider + short-interest all fire on the same day

```
symbol                                AAPL
obs_date                       2026-04-15

news_data_present                    TRUE
news_avg_sentiment                  +0.42
news_article_count                     87
news_distinct_source_count             24
news_confidence_score                  91
news_confidence_status              "high"

insider_data_present                 TRUE
insider_buys_30d                       12
insider_sells_30d                       1
insider_cluster_buy                  TRUE
insider_confidence_score               78
insider_confidence_status         "medium"

short_int_data_present               TRUE
short_int_short_interest_pct         3.4
short_int_days_to_cover              1.8
short_int_confidence_score             95
short_int_confidence_status         "high"
short_int_as_of_date           2026-04-15  -- bi-monthly settlement, just published

(other source blocks all _data_present=FALSE)

qualitative_confidence_score           88   mean of [91, 78, 95]
qualitative_confidence_status       "high"
qualitative_data_richness              30   3 of 10 source families
qualitative_flags                      []
qualitative_posture                "rich"
qualitative_reason             "fresh news + cluster-buying insiders +
                                fresh short-interest, all in agreement"
qualitative_version          "mart.v1.0.0"
```

MEF: weights this row's qualitative contribution at 0.88. RSE:
*"three sources (news, insider, short-interest) all fresh and
high-confidence on AAPL today; cluster-buying insiders + bullish news
+ low short-interest."* CCW: status=high, no caution flag.

### Example 2 — news bullish, insider bearish (conflicted)

```
symbol                                TSLA
obs_date                       2026-04-15

news_data_present                    TRUE
news_avg_sentiment                  +0.31
news_article_count                     61
news_confidence_score                  85
news_confidence_status              "high"

insider_data_present                 TRUE
insider_buys_30d                        2
insider_sells_30d                      18
insider_cluster_sell                 TRUE
insider_confidence_score               72
insider_confidence_status         "medium"

(other source blocks _data_present=FALSE)

qualitative_confidence_score           79   mean of [85, 72]
qualitative_confidence_status     "medium"
qualitative_data_richness              20
qualitative_flags          ['conflicted']
qualitative_posture          "conflicted"
qualitative_reason             "news bullish but insiders selling;
                                signal direction disagrees across sources"
```

MEF: weight at 0.79, but the `conflicted` flag tells the ranker to
treat this as ambivalent rather than directional. RSE: the explanation
includes both sub-signals and the flag. CCW: caution overlay — this
is the kind of row a covered-call writer wants to think about, not
auto-include.

### Example 3 — quiet day, no signals

```
symbol                                ABC          (mid-cap, slow news day)
obs_date                       2026-04-15

(every _data_present is FALSE)

qualitative_confidence_score          NULL
qualitative_confidence_status      "quiet"
qualitative_data_richness               0
qualitative_flags                      []
qualitative_posture                "quiet"
qualitative_reason             "no qualitative source has data for this symbol on this date"
```

MEF: skips the row in the qualitative-contribution path entirely.
RSE: *"no qualitative observations for ABC on 2026-04-15."*  CCW:
neutral, no overlay.

### Example 4 — only social attention has data, and it's a single-source spike

```
symbol                              GAMER
obs_date                       2026-04-15

social_data_present                  TRUE
social_mention_count                  140
social_distinct_subreddit_count         1
social_confidence_score                42
social_confidence_status            "low"
social_confidence_flags    ['single_source']

(everything else _data_present=FALSE)

qualitative_confidence_score           42
qualitative_confidence_status        "low"
qualitative_data_richness              10   only 1 source
qualitative_flags    ['single_source_only']
qualitative_posture                "thin"
qualitative_reason             "social-attention spike from a single
                                source; no corroborating news, insider,
                                or short-interest data"
```

MEF: weight at 0.42 — the ranker sees the spike but discounts it.
RSE: *"social-attention spike on GAMER but no other qualitative
source has fresh data; treat as thin."* CCW: don't act on a single-
source social spike.

### Example 5 — mapping-gated, confidence insufficient

```
symbol                                ACME
obs_date                       2026-02-15  (mid-Feb)

news_data_present                    TRUE
news_avg_sentiment                  -0.14
news_article_count                      2
news_confidence_score                  34
news_confidence_status      "insufficient"
news_confidence_flags  ['mapping_unverified', 'stale']

(other source blocks _data_present=FALSE)

qualitative_confidence_score           34
qualitative_confidence_status   "insufficient"
qualitative_data_richness              10
qualitative_flags    ['mapping_partial']
qualitative_posture          "insufficient"
qualitative_reason             "single news source with weak entity match;
                                not safe to attribute to ACME"
```

MEF: drops this row (confidence_status=insufficient is a hard skip per
the B1 contract). RSE: *"we have a 2-article mention but the entity-
match score suggests it may not actually be about ACME."* CCW:
ignore.

---

## Consumer patterns

### MEF — soft weight + per-source gates

```python
# MEF qualitative-contribution to ranker, v1
if mart_row.qualitative_confidence_status == "insufficient":
    qualitative_contribution = 0   # hard contract — never propagate
else:
    weight = mart_row.qualitative_confidence_score / 100.0
    qualitative_contribution = qualitative_signal(mart_row) * weight
```

Per-source gates configured in `mef.yaml` (this is just the example
again from B1; keeping the same shape):

```yaml
qualitative_gates:
  news:               { min_confidence: 40 }
  insider_conviction: { min_confidence: 50 }
  short_interest:     { min_confidence: 30 }
```

A source gate of 0 (or missing entry) means "include unconditionally"
— the row-level `qualitative_confidence_status` still applies.

### RSE — explanation surface

The mart row is a complete RSE answer in one read. Pattern:

> *"Q: What does the qualitative picture look like for AAPL on
> 2026-04-15?"*
> *"A: Three sources fired on AAPL that day — news, insider activity,
> and short-interest. Roll-up confidence is **high (88/100)** with
> posture `rich`: news from 24 sources averaging +0.42 sentiment;
> insider cluster-buying (12 buys vs 1 sell over 30 days); short-
> interest 3.4% with low days-to-cover. All three sources fresh and
> in agreement."*

The RSE response is a direct projection of the mart row + per-source
flags into prose. No JOIN to per-source detail tables needed for the
top-level answer.

### CCW — caution overlay on hold-review

CCW Friday hold-review uses the row-level `qualitative_confidence_status`
+ the directional posture:

```python
# CCW Friday hold-review, conceptual
match (mart_row.qualitative_posture, mart_row.qualitative_confidence_status):
    case ("rich", "high")    if directional_bearish(mart_row):
        flag_caution(symbol, "high-confidence bearish qualitative posture")
    case ("conflicted", _):
        note_for_review(symbol, "qualitative sources disagree; review hold")
    case ("thin" | "stale", _):
        note_for_review(symbol, "qualitative coverage is weak; rely on price")
    case ("quiet" | "insufficient", _):
        pass  # don't surface; pure quantitative call
```

CCW thresholds on status, not score — its reviewer is human-in-the-
loop, so the band granularity is right.

---

## v1 implementation scope

The mart **schema** is designed for all 10 source families (the
column blocks above). The v1 **builder implementation** covers only
the source families that have shipped a confidence table — at design
time, that's news/sentiment alone (B1 anchor). Implementation phases:

1. **v1.0** — news block only. The other 9 blocks are NULL columns
   (data_present=FALSE always). Rollup is just the news row's score.
   Ships once a `udc.builders.shdb.news_confidence` builder lands
   producing `shdb.news_confidence_1d`.
2. **v1.1+** — each subsequent source family adds its block. New
   `<source>_confidence_1d` builder + extends `mart_qualitative_daily`
   builder to JOIN it. Schema is forward-allocated so adding a source
   doesn't bump `qualitative_version`.
3. **v2** — only if the rollup logic itself changes (different
   averaging rule, new posture types, etc.). At that point all
   historical mart rows keep their `qualitative_version='mart.v1.0.0'`
   tag; new rows are tagged `'mart.v2.0.0'`.

The mart's per-source columns are NULL-tolerant by construction —
adding a source in v1.1 doesn't break v1.0 consumers because they
were already reading NULL on those columns.

Estimated UDC harvest cost for the v1.0 mart (news only):

- Build over the same date window as `news_confidence_1d` (UDC
  daily harvest default 14 days).
- ~10K active symbols × 14 days = 140K rows / harvest.
- Single SELECT-with-LEFT-JOINs from per-source confidence tables
  + roll-up CTE → INSERT ... ON CONFLICT.
- Estimated runtime: 5–15 seconds, comparable to other Phase E mart
  builders.

---

## Versioning + configurability

Per the user's note: *"avoid tuning this too much before it exists.
The v1 rubric is defensible; the important thing now is to make it
versioned so we can improve it later without rewriting history."*

The mart honours that with three explicit version columns:

| Column | Versions what | Bumps when |
|---|---|---|
| `<source>_confidence_version` | per-source rubric (B1) | source's confidence formula or weights change |
| `qualitative_version` | mart roll-up logic (B2) | the cross-source averaging / posture / flags rules change |
| `mart_builder_version` | the builder code itself | builder bug-fixes that don't change semantics |

A row built today is tagged with whichever versions are in effect.
Re-building a date range under a new version emits new rows tagged
with the new version. Old rows stay (different `confidence_version`).
Backtests pin to a version when they want stable history; everything
else reads `WHERE *_version = 'latest'` (or just the latest column
values, which the mart always exposes for the most recent build).

Configurability lives in YAML, not in the schema:

- `udc/config/confidence.yaml` (new) — sub-score weights, status-band
  cutpoints, fresh/stale thresholds per source. Reading the
  config-version into `confidence_version` automatically would be a
  nice property — bump the config, get a new version tag.
- `udc/config/qualitative_mart.yaml` (new) — roll-up weights (if any),
  posture decision-tree thresholds (e.g. how many fresh sources
  qualify for `rich`), the mart builder's `qualitative_version`.

These configs are gitignored only for sensitive credentials; the
confidence/mart configs themselves are intended to be in source
control so the version history of tuning decisions is visible.

---

## v1 minimal SQL sketch

For reference, this is what a v1.0 builder INSERT looks like (news
block only — extend per source). Real implementation lives in UDC.

```sql
INSERT INTO shdb.mart_qualitative_daily (
    symbol, obs_date,
    -- news block
    news_data_present, news_avg_sentiment, news_article_count,
    news_distinct_source_count, news_sentiment_dispersion,
    news_bullish_share, news_bearish_share,
    news_confidence_score, news_confidence_status,
    news_confidence_flags, news_as_of_date, news_confidence_version,
    -- roll-up (trivially equals news block when only news has data)
    qualitative_confidence_score, qualitative_confidence_status,
    qualitative_data_richness, qualitative_flags, qualitative_reason,
    qualitative_posture, qualitative_version,
    -- audit
    mart_builder_version
)
SELECT
    n.symbol, n.obs_date,
    TRUE,
    nts.avg_sentiment, nts.article_count, n.distinct_source_count,
    nts.max_sentiment - nts.min_sentiment,
    nts.bullish_count::DOUBLE PRECISION / NULLIF(nts.article_count, 0),
    nts.bearish_count::DOUBLE PRECISION / NULLIF(nts.article_count, 0),
    n.confidence_score, n.confidence_status,
    n.confidence_flags, n.as_of_date, n.confidence_version,
    n.confidence_score, n.confidence_status,
    10,                                    -- 1 of 10 source families
    CASE
        WHEN 'mapping_unverified' = ANY(n.confidence_flags)
            THEN ARRAY['mapping_partial']
        ELSE ARRAY[]::TEXT[]
    END,
    -- reason text omitted for brevity
    NULL,
    CASE n.confidence_status
        WHEN 'high'         THEN 'thin'      -- only 1 source family present
        WHEN 'medium'       THEN 'thin'
        WHEN 'low'          THEN 'thin'
        WHEN 'insufficient' THEN 'insufficient'
    END,
    'mart.v1.0.0',
    'mart_qualitative.v1.0.0'
FROM shdb.news_confidence_1d n
JOIN shdb.news_ticker_sentiment_1d nts
    ON nts.symbol = n.symbol AND nts.obs_date = n.obs_date
WHERE n.obs_date BETWEEN :date_from AND :date_to
ON CONFLICT (symbol, obs_date) DO UPDATE SET
    news_data_present                = EXCLUDED.news_data_present,
    -- ... all news_* columns
    qualitative_confidence_score     = EXCLUDED.qualitative_confidence_score,
    qualitative_confidence_status    = EXCLUDED.qualitative_confidence_status,
    qualitative_data_richness        = EXCLUDED.qualitative_data_richness,
    qualitative_flags                = EXCLUDED.qualitative_flags,
    qualitative_posture              = EXCLUDED.qualitative_posture,
    qualitative_version              = EXCLUDED.qualitative_version,
    mart_built_at_utc                = now(),
    mart_builder_version             = EXCLUDED.mart_builder_version;
```

This is the v1.0 single-source mart. v1.1 adds insider, v1.2 adds
short-interest, etc. Each phase is a UDC PR + (optionally) a mart
schema migration if the new source family introduces a column the
forward-allocated schema didn't anticipate.

---

## Open questions for the user

These would benefit from a quick read before any implementation PR
starts. None of them blocks design completion.

1. **Source-family count for v1 schema.** I forward-allocated 10
   blocks. Did I miss any? Sources I considered and **excluded** for
   v1: macro tone (gdelt — not symbol-specific), Fear & Greed (not
   symbol-specific), CFTC COT (futures contracts, not equity
   symbols). All three could feed an MEF macro-overlay later but
   don't belong in a *symbol-level* qualitative mart.

2. **Posture vocabulary.** I went with
   `rich / thin / stale / conflicted / insufficient / quiet`. Wider
   than needed? Or do we want `bullish-tilted / bearish-tilted /
   mixed` as posture words too? My read: keep posture as
   *data-shape* labels (the user emphasized "data confidence, not
   prediction confidence" — bullish-tilted is borderline prediction
   talk), and let MEF/CCW infer direction from per-source signal
   values. Confirm?

3. **Roll-up weighting.** The arithmetic-mean rule treats every
   present source equally. Reasonable v1 default, but easy to
   imagine wanting source-importance weights down the road (e.g.
   *"news matters more than social attention, weight 1.0 vs 0.5"*).
   v1 keeps it simple; v2 can add weights via the
   `qualitative_mart.yaml` config and bump `qualitative_version`.
   Confirm v1 = unweighted mean?

4. **Backtest-helper SQL function.** Should the rubric ship with a
   UDF like `shdb.qualitative_mart_as_of(:sim_date)` that returns
   the correctly-reconstructed mart for a backtest's simulation
   date? My instinct: yes, ship the helper at the same time as
   v1.0 — without it, every consumer will write their own and some
   will get it wrong. If yes, add it to the v1.0 implementation
   scope.

Defaults if you say *"your call"* on any: keep all 10 blocks, keep
posture vocabulary as-is, v1 unweighted mean, ship the
`qualitative_mart_as_of` UDF in v1.0.

---

## Reference

- B1 design (rubric): `data_confidence_rubric_v1_20260504.md`.
- Underlying data state (post-cleanup baseline):
  `qualitative_cleanup_completion_20260503.md`.
- Existing SHDB mart conventions:
  `~/repos/udc/docs/mart-layer-guide.md`.

This document's version: **`mart.v1.0.0`**. Subsequent versions
(`v1.1`, `v1.2`, …) extend the per-source coverage as builders ship.
Major version bumps (`v2.0.0`+) happen only if the roll-up logic
itself changes.

---

*End of B2 deliverable. The mart is ready to implement once the four
open questions above resolve. Implementation order: news_confidence_1d
builder (UDC PR) → mart_qualitative_daily v1.0 builder (UDC PR) → MEF
integration → second source family (insider) → repeat.*
