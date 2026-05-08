# UDC qualitative harvest preflight — 2026-05-04

Verification round before building any new confidence tables. Goal: confirm
the recently-shipped sec_penalties entity-metadata propagation works through
the **normal** UDC harvest runner (not just direct SQL), and document the
patterns the next builder (`news_confidence_1d`) should follow.

## TL;DR

- sec_penalties works clean through `udc harvest --builder sec_penalties …`
  on the normal path. Telemetry, validation, rebuild-safety all confirmed.
- Mart-builder conventions are stable and well-established. The wide-pivot
  shape on `(symbol, bar_date)` with LATERAL forward-fill from
  different-cadence sources is exactly what migrate-per-source needs.
- UDC's existing test convention is **pure-function unit tests only** —
  no tests invoke `build_*` SQL. End-to-end verification is a manual
  scoped harvest, the same pattern this preflight just exercised.
- **No blockers.** `news_confidence_1d` PR can proceed.
- Migrate-per-source is the right call (matches existing mart pattern;
  forward-allocate would be net-new infrastructure with no precedent).

## 1. sec_penalties through the normal harvest runner

```bash
udc harvest --builder sec_penalties --from 2026-04-15 --to 2026-05-03
```

Result:

```
Phase B: Layer 1 Cleaned
  [OK] sec_penalties: 18 rows
SHDB Harvest complete. Status: ok (0.2s)  [1/1 builders, 18 rows]
```

Telemetry written cleanly:

| Surface          | Result                                                                                  |
| ---------------- | --------------------------------------------------------------------------------------- |
| `ow.udc_run`     | `status=ok`, `exit_code=0`, lifecycle complete                                          |
| `ow.udc_builder` | `builder=sec_penalties`, `phase=B`, `target_table=sec_penalties`, `status=ok`, `rows_upserted=18`, `rows_rejected=0`, `duration_secs=0.043` |
| `ow.udc_event`   | one info-level `unknown_masd_tables` (harvest-startup discovery, unrelated)             |

Entity metadata propagation:

| Column        | Populated of 18 |
| ------------- | --------------: |
| `entity_type` | 16              |
| `entity_role` | 16              |
| `cik`         | 0               |

The 2 NULL `entity_type` rows are upstream MASD NULLs (pre-resolution rows
the entity classifier didn't tag) — expected. The 16 populated rows split
sensibly: 11 `individual/defendant`, 3 `individual/respondent`, 2
`company/defendant`. **CIK is NULL across the board** because the sec-api
penalties endpoint doesn't always return CIKs; the column is in place and
the upsert refreshes it on re-harvest, so future enrichment can backfill
without a schema change. Not a blocker for this preflight — just a known
upstream gap.

Rebuild-safety: re-running the same harvest over the same source window
produced the same 18 derived rows, with no duplicates, no drift, and no
telemetry breakage. ON CONFLICT DO UPDATE refreshes `entity_type` /
`entity_role` / `cik` on every re-run, so newly-resolved entity values
flow through automatically. The derived rows themselves are
rebuildable from MASD — "idempotent" is a property of raw collection
(don't re-fetch externally), not of derived-table re-runs.

Builder code (`src/udc/builders/shdb/other.py:1362`) follows the canonical
Layer 1 cleaned pattern unchanged: `build_validation_clauses` →
`count_and_log_rejections` → return `int | tuple[int, int]`. No drift.

## 2. UDC mart-builder conventions (for the future qualitative mart)

Read: `src/udc/builders/mart/stock_equity_daily.py` (444 lines, the
heaviest), `stock_etf_daily.py` (191 lines), and the canonical decisions
in `src/udc/CLAUDE.md` ("Core Principles", phase ordering).

Conventions worth committing to memory before writing
`news_confidence_1d`:

1. **One file per mart table** under `src/udc/builders/mart/`.
2. **Module-level SQL constants:** `_SELECT` (or `_STOCK_SELECT`/`_ADR_SELECT`
   for UNION ALL), `_INSERT_COLS`, `_ON_CONFLICT_SET`. Builder function
   is just `INSERT … {_INSERT_COLS} {_SELECT} ON CONFLICT … DO UPDATE SET
   {_ON_CONFLICT_SET}`.
3. **Single SQL pass.** No Python loops, no temp tables. The whole upsert
   is one round-trip inside `shdb_transaction(db_config)`.
4. **Rebuild-safe upsert** on a stable PK (mart's is `(symbol, bar_date)`).
   Re-running the same builder over the same source window produces the
   same derived rows with no duplicates or drift; the table itself is
   rebuildable from upstream at any time.
5. **Forward-fill via LATERAL** when joining different-cadence sources
   (quarterly valuations → daily price, biweekly short interest → daily
   price). The pattern is `LEFT JOIN LATERAL (SELECT … FROM tbl WHERE
   key = p.key AND date <= p.bar_date ORDER BY date DESC LIMIT 1) x ON
   true`. This is the **template the qualitative mart should reuse** for
   news, analyst, insider, congress, etc., since each has its own cadence.
6. **Explicit NULL casts** when a row legitimately has no value
   (`NULL::boolean`, `NULL::date`, …) — keeps UNION ALL + per-segment
   coverage explicit instead of silently inheriting types.
7. **Standard tail columns:** `data_tier='silver'`, `source_provider`,
   `last_built_at = now()` in the SET clause so re-runs refresh the
   visibility timestamp.
8. **Builder signature:** `def build_mart_<name>(db_config, date_from,
   date_to) -> int`. Plain `int` return — mart builders don't run
   ingest validation (their inputs are already validated).
9. **Output line:** `print(f"  {green('[OK]')} mart.<name>: {count:,} rows")`.
10. **WHERE bar_date BETWEEN %s AND %s** scopes the build to the harvest
    window; full rebuild is the same call with a wider window.

Phase E ordering (per CLAUDE.md): mart builders run after Phase C derived,
before Phase D catalog. Catalog runs last so `sys_catalog` reflects mart
freshness. Any new qualitative mart goes in Phase E; the per-source Layer
2 confidence tables (`news_confidence_1d`, …) go in Phase C.

## 3. UDC test convention

UDC has 5 test files, all pure-function unit tests:

| File                  | What it tests                                  |
| --------------------- | ---------------------------------------------- |
| `test_auto_widen.py`  | `compute_widen_decision()` decision logic      |
| `test_bsm.py`         | Black-Scholes pricing + IV roundtrip           |
| `test_occ_parser.py`  | OCC option-symbol parser                       |
| `test_cli.py`         | argparse construction                          |
| `conftest.py`         | dummy `PostgresConfig` fixture (type only)     |

**No test invokes a `build_*` function or hits Postgres.** The convention
is: extract the pure logic into testable Python, leave the SQL plumbing
to be verified end-to-end by a scoped harvest.

For `news_confidence_1d` this means:

- **Pure-function tests** for each sub-score in the rubric (source
  diversity, density, freshness, age decay, mapping certainty gate, etc.)
  with curated input fixtures. These live in `tests/test_news_confidence.py`.
- **End-to-end verification** by running `udc harvest --builder
  news_confidence_1d --from <recent> --to <recent>` against real
  shdb data, then querying:
  - `ow.udc_builder` for status / rows_upserted / rows_rejected / duration
  - `shdb.news_confidence_1d` for distribution sanity (no all-zero, no
    all-100, expected NULL pattern for symbols with no news)
  - re-run the same range to confirm rebuild-safety (same row count, no
    drift) — the derived table is rebuildable from upstream, but a single
    builder's reruns must be deterministic for the same source window

That's the same pattern this preflight just used for sec_penalties.
It's lightweight, doesn't require a test-DB fixture, and is the
already-blessed UDC convention.

## 4. Migrate-per-source vs forward-allocate

User leans migrate-per-source; this preflight confirms it.

The existing mart builders **already use migrate-per-source semantics.**
`mart.stock_equity_daily` joins:

- daily price → daily returns → daily technicals (same cadence; plain LEFT JOIN)
- daily price → quarterly valuation (different cadence; LATERAL forward-fill)
- daily price → biweekly short interest (different cadence; LATERAL forward-fill)
- daily price → quarterly analyst snapshots (different cadence; nested LATERAL)

Every additional source slots in as another LATERAL block on its own
cadence. The qualitative mart roll-up (whether it lives as new columns
on `mart.stock_equity_daily` or a parallel `mart.qualitative_confidence_1d`)
follows the same shape: each `<source>_confidence_1d` table is a Phase C
Layer 2 build at its own native cadence; the mart joins them in.

Forward-allocate (one wide table that gets columns added per source over
time) has no precedent in UDC. Introducing it would be net-new
infrastructure for a tiebreaker question that the existing pattern
already answers cleanly.

The roll-up label should be **data breadth/freshness**, not prediction
trust — same framing carried over from the B1 rubric design (per
`docs/data_confidence_rubric_v1_20260504.md`).

## 5. Changes needed before the `news_confidence_1d` PR

**None blocking.** All preflight criteria pass.

Two optional follow-ups (not gating):

- **CIK backfill on `shdb.sec_penalties`.** Column exists, upsert refreshes
  on every re-harvest, but sec-api doesn't always return a CIK. A small
  ticket to derive CIK from the entity-resolution lookup would close the
  gap; doesn't block any qualitative work that doesn't read CIK.
- **`udc.core.config.load_postgres_config` import path.** Hit during
  prior direct-Python invocation of `build_sec_penalties`. The normal
  CLI entry point uses `udc.core.db.shdb_config_from_env()` and works
  fine; only matters if someone tries to call a builder from a script
  outside the CLI. Document or fix — defer until a real consumer needs it.

## 6. Recommended path to ship `news_confidence_1d`

1. Add `config/datasets/news_confidence_1d.yaml` (Phase C, harvest_window
   matching news Layer 1 tables).
2. Add `build_news_confidence_1d` to `src/udc/builders/shdb/news_events.py`
   (canonical pattern, Layer 2 derived → returns plain `int`).
3. Register the builder in the harvest chain.
4. `tests/test_news_confidence.py` — pure-function tests for each sub-score
   in the rubric.
5. Run `udc harvest --builder news_confidence_1d --from 2026-04-15 --to
   2026-05-03` end-to-end. Verify telemetry + distribution + rebuild-safety
   exactly as this preflight did for sec_penalties.
6. Open PR with the harvest output + telemetry rows in the description.

After that's green: per-source builders for analyst, insider, congress,
… with the same shape; then the mart roll-up as a separate Phase E
addition.

---

**Reference**

- B1 rubric: `docs/data_confidence_rubric_v1_20260504.md`
- B2 mart design: `docs/canonical_qualitative_mart_design_v1_20260504.md`
- Mart-builder examples: `~/repos/udc/src/udc/builders/mart/{stock_equity_daily,stock_etf_daily}.py`
- UDC core principles: `~/repos/udc/CLAUDE.md` § Core Principles
- sec_penalties builder (post-propagation): `~/repos/udc/src/udc/builders/shdb/other.py:1362`
- This preflight harvest's run_id: `udc-harvest-2026-05-04T04-43-30Z`
