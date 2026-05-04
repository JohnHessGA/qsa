# Polygon `short_interest` Investigation — Findings

*Generated: 2026-05-03 — peer to `mdc_masd_review_20260503.md`*

## TL;DR — root cause

**This is NOT** a provider outage, an endpoint move, an entitlement issue, an
auth/parameter change, or an MDC code regression.

**It IS** a publication-lag scheduling bug. Polygon (Massive) is still
publishing FINRA short-interest data exactly as before. Our daily collector
queries `settlement_date = today`, but FINRA publishes short-interest reports
roughly 12 calendar days *after* the settlement date. So same-day queries
always return empty — and nothing in the current schedule re-runs the
collection for those placeholder dates once FINRA finally publishes.

A periodic lag-aware backfill was happening up through 2026-03-11 (when the
2026-02-27 settlement was successfully pulled with a 12-day lag). After that,
whatever was running those catch-ups stopped, and no one noticed because the
daily collector keeps reporting `status=ok`.

**The data is fully recoverable.** I confirmed three FINRA settlement dates
since 2026-02-27 currently return full datasets via the live API:

| Settlement date | API records (right now) | MASD has |
|---|---:|:-:|
| 2026-03-13 | 21,587 | placeholder only |
| 2026-03-31 | 21,678 | placeholder only |
| 2026-04-15 | 21,757 | placeholder only |
| 2026-04-30 | 0 (not yet published — expected ~2026-05-12) | placeholder only |

That's ~65,000 rows of US short-interest waiting to be re-collected and
ingested.

---

## Evidence trail

### 1. Collector code path is unchanged and correct

`src/mdc/providers/massive/massive.py:_collect_short_interest()`

```python
url = f"{self.base_url}/stocks/v1/short-interest"
params = {
    "apiKey": self.api_key,
    "settlement_date": data_date,
    "limit": 1000,
}
results, http_status = self._fetch_paginated_rest(url, params)

if not results and http_status == 200:
    return { "__mdc_no_data__": True, ..., "meta": { "skippedReason": "no_data" }}
```

The docstring even says: *"Most dates return empty — only ~24 settlement
dates per year (bi-monthly FINRA cycle)."* The author knew empties were
normal. What they didn't account for is that FINRA settlement dates *also*
return empty for ~12 days after the settlement, until FINRA publishes.

`git log` for this file shows no relevant change since the dataset was
introduced — the regression isn't from a code edit.

### 2. The placeholder pattern matches every expected FINRA date

Spot-check of the 10 most-likely settlement-date candidates after 2026-02-27:

```
2026-03-13: 230B [no_data]
2026-03-15: 230B [weekend]
2026-03-16: 230B [no_data]
2026-03-30: 230B [no_data]
2026-03-31: 230B [no_data]
2026-04-14: 230B [no_data]
2026-04-15: 230B [no_data]
2026-04-16: 230B [no_data]
2026-04-29: 230B [no_data]
2026-04-30: 230B [no_data]
```

Every one is a 230-byte `__mdc_no_data__` placeholder.

### 3. Direct API tests with the live key prove data exists

Using the production key from `config/providers/massive.secrets.yaml` and
the same endpoint MDC calls:

```
GET /stocks/v1/short-interest?settlement_date=2026-02-27  → 21,576 rows ✓ (matches MASD)
GET /stocks/v1/short-interest?settlement_date=2026-03-13  → 21,587 rows ✓ (MASD missing)
GET /stocks/v1/short-interest?settlement_date=2026-03-31  → 21,678 rows ✓ (MASD missing)
GET /stocks/v1/short-interest?settlement_date=2026-04-15  → 21,757 rows ✓ (MASD missing)
GET /stocks/v1/short-interest?settlement_date=2026-04-30  →      0 rows  (not yet published)
GET /stocks/v1/short-interest?settlement_date=2026-04-16  →      0 rows  (not a settlement date)
```

Endpoint, parameters, auth, and entitlement are all working.

### 4. Historical collection times confirm "publication lag" was always the model

Collection-time vs settlement-date for the last working files:

| Settlement | Collected at | Days lag |
|---|---|---:|
| 2026-02-27 | 2026-03-11 09:01 | 12 |
| 2026-01-30 | 2026-02-13 09:01 | 14 |
| 2026-01-15 | 2026-02-12 01:06 | 28 *(part of mass backfill)* |
| 2025-12-31 | 2026-02-12 01:06 | 43 *(mass backfill)* |
| ... | ... | ... |

Note the consistent ~12-14-day lag on the **organic** runs (2026-02-13 and
2026-03-11). That's the FINRA publication window. The earlier December rows
were all swept up in the 2026-02-12 one-off mass backfill.

After 2026-03-11, no more lag-aware collections happened. Recent runs all
have 1–4-day "lag" (i.e., the daily cron firing for `settlement_date=today`
with a 1-day shift) — far too early for FINRA.

```
2026-04-15 (settlement) | 2026-04-19 06:12 (collected, 4d lag) | empty — too early
2026-04-19 06:12 also pulled 2026-04-14, -16, -17, -18 in one batch | all empty
```

So *something* tried to backfill 5 days on 2026-04-19, but caught the
wrong 5-day window for catching the 2026-04-15 settlement (FINRA wouldn't
publish until ~2026-04-27).

### 5. Cron does run a daily backfill at 03:00 ET, but it doesn't retry placeholders

`/etc/cron`:

```
0 4 * * *    daily-collect.sh      # 4 AM — runs collectors for today
0 3 * * *    daily-backfill.sh     # 3 AM — runs `mdc backfill` for pending chunks
0 14 * * *   daily-ingest.sh       # 2 PM — ingests new files
```

`daily-backfill.sh` calls `mdc backfill`, which (per `docs/cli-reference.md`)
processes pending chunks from the backfill plan. The plan is built by
`mdc backfill plan`. Currently nothing in that plan re-targets recent
short_interest placeholders.

There's no provider-level "retry placeholders that may now have data" pass.

---

## Why I did not implement a fix in this PR

The user instruction was: *"Implement only if the fix is obvious. If the
endpoint or parameter changed and the correction is small, update the MDC
collector/config and rerun the dataset."*

This isn't a one-line edit:

- The endpoint and parameters are unchanged.
- The collector code is correct in isolation (empty `data_date` returns
  empty — not wrong).
- The fix needs to live in **scheduling**, not in the per-call code path:
  scan recent placeholders, identify those whose settlement_date is now far
  enough back that FINRA should have published, retry the API, replace the
  placeholder if non-empty, re-ingest.
- That's a small but real new code path with a new CLI surface
  (`mdc backfill --retry-placeholders` or similar) and behaviour worth
  reviewing in its own PR.

In addition, MDC's own CLAUDE.md says *"Pause ingest before parser changes.
Daily ingest runs at 2 PM ET."* — even a one-off backfill would race against
the 2 PM ingest window today. Better to schedule deliberately.

So this round produces the diagnosis only. The next PR (already on the user's
list as item 2: "MDC ingest validators") can stay focused; the short_interest
recovery is a separate, clean follow-up.

---

## Recommended actions

### Immediate (one-off recovery)

Backfill the three confirmed-missing settlement dates by running:

```bash
cd ~/repos/mdc && source .venv/bin/activate
mdc collect --provider massive --dataset short_interest --data-date 2026-03-13
mdc collect --provider massive --dataset short_interest --data-date 2026-03-31
mdc collect --provider massive --dataset short_interest --data-date 2026-04-15
mdc ingest --provider massive --dataset short_interest --since 2026-03-13
```

Each should produce a real ~3.5 MB file (~21.5K rows) and replace the
existing 230-byte placeholder. After ingest, MASD's `max(settlement_date)`
should jump from 2026-02-27 → 2026-04-15.

(Verify behaviour before running: confirm `mdc collect` for an existing
`__mdc_no_data__` date overwrites the placeholder rather than skipping —
the deterministic-output convention and the `__mdc_deterministic__: True`
flag in the placeholder suggest overwrite is intended, but worth confirming
with one date before the others.)

### Permanent (next dedicated PR)

Add a "retry recent placeholders" pass to MDC's daily backfill flow. Two
reasonable shapes — pick the one that fits the existing backfill model:

- **Option A — placeholder retry pass.** New `mdc backfill --retry-placeholders --provider massive --dataset short_interest --window 21d` step. Walks `masd.sys_raw_file` for recent placeholder rows, re-runs the per-date collector, replaces the file (and emits a new ingest event) if results are now non-empty. Generic across providers if any other dataset has the same publication-lag shape.
- **Option B — scheduled lag query.** Change the short_interest daily call to query `settlement_date = today − 14 days` instead of `settlement_date = today`. Simpler but couples the file naming convention (`short_interest-YYYY-MM-DD.json`) to either the collection-day or the settlement-day in a way that disagrees with how every other dataset is named. Option A is cleaner.

### Future no-data alert (also on the user's list as item 6)

This is the canonical case the alert rule needs to cover:

> If a provider/dataset has produced N consecutive `__mdc_no_data__`
> placeholder files for >K days, and the dataset's expected publication
> cadence implies fresh data should be available, raise an Overwatch
> warning.

For short_interest specifically: 30+ consecutive placeholder days should
have raised a warning by mid-March. We hit 65 days because nothing was
watching for the gap.

---

## Source recoverability and retire/replace decision

| Question | Answer |
|---|---|
| Is Polygon still publishing short-interest? | **Yes.** Confirmed live with current API key. |
| Did the endpoint move? | **No.** `/stocks/v1/short-interest` works as before. |
| Did request URL, auth, parameters, or entitlement change? | **No.** Same key, same params, same response shape. |
| Provider/API issue, plan/entitlement issue, or MDC bug? | **MDC scheduling bug** — daily query timing vs FINRA publication lag. |
| Are weekend placeholders expected? | **Yes** — `_collect_short_interest()` skips weekends explicitly (`is_weekend(data_date) → __mdc_no_data__`). |
| Are weekday `no_data` placeholders expected? | **Partially.** Most weekdays are not FINRA settlement dates and correctly return empty. The defect is that *settlement dates queried before publication* also produce a permanent `no_data` file. |
| Should the source be retired or replaced? | **No.** The data is valuable and recoverable; the bug is on our side. Keep, fix scheduling. |

---

## Code/config changes made

**None.** This PR is investigation only, per the user's "implement only if
obvious" instruction. The fix belongs in a separate scheduling PR.

---

## Should this trigger a future no-data alert rule?

**Yes — this is exactly the use case for item 6 on the user's roadmap
("MDC no-data placeholder alerting"). When that PR lands, the rule
parameters informed by this case:

- Threshold to alert: 21 consecutive calendar days of `__mdc_no_data__`
  placeholders for a dataset whose expected cadence is at most weekly.
  Alert severity: warning.
- Threshold to escalate: 45 consecutive days → critical.
- Suppress for datasets explicitly tagged "sparse" (e.g. `cftc_cot`'s
  futures positioning weekend gaps, `sec_api/aaers` low-frequency releases).
- Surface via Overwatch (`ow.alert_event`) and route through the existing
  notify.py path used by `ow infra-check`.

The 2026-02-27 → 2026-05-03 = 65-day silent failure on short_interest
should have been the canonical first alert this rule fires on, in
hindsight.

---

## Open follow-ups (for the user, after reviewing this report)

1. Confirm the immediate one-off recovery procedure (does `mdc collect` on
   a placeholder date overwrite cleanly?) and run it.
2. Decide between Option A (placeholder-retry pass) and Option B (scheduled
   lag query) for the permanent fix; that PR is best done after the ingest-
   validators PR (user's roadmap item 2) so the validator + retry logic
   share the same review window.
3. Re-run QSA after recovery to confirm `R006-staleness` no longer flags
   `shdb.stock_short_interest`.
