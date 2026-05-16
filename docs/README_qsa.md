# QSA — Build Specification

- **Abbreviation:** QSA
- **Full name:** Qualitative Signal Audit
- **Role:** AFT cross-cutting audit tool (read-only) — peer to MDC/UDC quality
  tooling rather than to the application streams (MEF/CCW/CIA/IRA Guard).

## Purpose

Read-only audit of qualitative/sentiment/event data across MASD (bronze) and
SHDB (silver). QSA scans the non-price slice — news, sentiment, insider/Form-4
events, congressional trades, SEC filings, CFPB complaints, FINRA short
interest, etc. — and emits a Markdown + CSV findings report grouped by
severity. Used as the gating check before UDC harvest changes that touch
qualitative inputs, and as the dated-snapshot record of qualitative data
quality over time.

## Inputs

- **Read-only DB connections:**
  - `masd` — raw qualitative tables collected by MDC.
  - `shdb` — curated qualitative tables and signals derived by UDC (search
    path: `mart, shdb, public`).
  - `mefdb` — universe tables (`mef.universe_stock`) for coverage checks.
- **Configuration:**
  - `config/qsa.yaml` — staleness thresholds per cadence, MEF coverage tiers,
    deprecated-table list with replacement pointers, repos to grep for live
    consumers. Checked into the repo.
  - `config/postgres.secrets.yaml` — DB credentials. Gitignored; see
    `config/postgres.secrets.yaml.example` and
    `~/repos/notes/secrets-conventions.md`.
- **Filesystem (read-only) for R007 consumer-grep:** `~/repos/{mef, ccw, cia,
  iraguard, rse, das, xpm, udc}` per `consumer_grep_repos` in `qsa.yaml`.

## Outputs

- **Markdown report** — `reports/qsa_audit_YYYYMMDD.md` by default, grouped by
  severity (critical / warning / info), per finding: rule ID, database, table,
  one-line summary, detail block, affected row/symbol counts, sample values,
  recommended action.
- **CSV findings table** (optional, `--csv PATH`) — flat one-row-per-finding
  format suitable for diffing against prior baselines.
- **Exit code:** `0` if zero critical findings, `1` if any critical present.
  Wired so a CI/cron caller can gate on critical-clean.
- **No DB writes.** All connections are opened with `readonly=True`. QSA never
  emits notifications and does not touch Overwatch.

## Scope

- **Qualitative-only.** Price/return/technical tables are out of scope —
  those are covered by UDC's own validation, MDC's no-data alerting, and
  Overwatch's freshness dashboards.
- **Cross-database.** A single audit run spans MASD, SHDB, and MEFDB so that
  cross-tier issues (orphan curated rows, MEF universe coverage gaps) surface
  in one report.
- **Categorical, not statistical.** R001–R009 are deterministic shape checks
  (NULL keys, future dates, stale streams, missing-symbol joins, etc.), not
  anomaly detection or distribution drift.

## Hard boundaries

1. Read-only. No writes to any DB; no inserts to Overwatch; no notifications.
2. No backtesting, no scoring, no recommendations. Findings are descriptive.
3. No LLM. All rules are deterministic SQL + Python.
4. Qualitative slice only. Does not duplicate MDC/UDC freshness dashboards
   for price-and-return tables.
5. Output goes to `reports/`. Documentation about QSA goes to `docs/`.

## Schedule

- **Ad-hoc** (default). Operator runs `qsa audit qualitative` before/after
  qualitative-pipeline changes and commits the resulting report under
  `reports/qsa_audit_*` as a dated baseline.
- No cron entry in v1. If cadence is added later, the cron should call the
  CLI directly (`qsa audit qualitative ...`) per the global standard — no
  wrapper script with logic.

## CLI surface

See `src/qsa/cli.py` and `docs/qsa_cli_reference.md`. v1 implements one
subcommand:

```
qsa audit qualitative [--output PATH] [--csv PATH] [--rules R001,R007,...] [--stdout]
```

## Config

- `config/postgres.secrets.yaml` — credentials for `masd`, `shdb`, `mefdb`
  (gitignored; see `config/postgres.secrets.yaml.example`).
- `config/qsa.yaml` — application knobs:
  - `min_valid_date`, `future_date_tolerance_days` for R001/R002.
  - `staleness_thresholds_days` per cadence — `daily`, `weekly`, `monthly`,
    `quarterly`, `bi_monthly_lagged` (FINRA short interest, mirrors MDC's
    21/45 no-data rule).
  - `mef_coverage.warn_below_pct` / `critical_below_pct` for R008.
  - `deprecated_tables` — schema/table/replacement/reason triples driving
    R007 plus the consumer-grep across `consumer_grep_repos`.

## Databases

### Tables read (inputs)

| Database | Schema(s)              | Purpose                                      |
|----------|------------------------|----------------------------------------------|
| `masd`   | `masd`                 | Raw qualitative tables (news, insider, etc.) |
| `shdb`   | `mart`, `shdb`         | Curated qualitative tables + derived signals |
| `mefdb`  | `mef`                  | `universe_stock` for R008 MEF coverage tier  |

All connections set `readonly=True` and `autocommit=True`. QSA writes nothing.

### Tables written (outputs)

None. QSA is purely advisory; its outputs are files in `reports/`.

## Rule catalog (summary)

Full descriptions live in `docs/qsa_rules.md`.

| Rule  | ID                       | What it flags                                         |
|------:|--------------------------|-------------------------------------------------------|
| R001  | invalid-timestamps       | Dates < `min_valid_date` (e.g. `0001-12-31 BC`)       |
| R002  | future-dates             | Dates > today + `future_date_tolerance_days`          |
| R003  | missing-symbols          | Rows whose symbol does not resolve via `symbol_master` (sec_edgar uses `filer_type` / `ticker_mapping_status`) |
| R004  | duplicate-keys           | Duplicate natural keys in qualitative tables          |
| R005  | orphan-rows              | Curated rows whose parent reference is gone           |
| R006  | staleness                | Streams past their cadence threshold (incl. `bi_monthly_lagged` for FINRA short interest) |
| R007  | deprecated-tables        | Listed-deprecated tables + grep across AFT repos for live consumers |
| R008  | mef-coverage             | Coverage of MEF's 305-stock universe per tier (`sparse_expected` tables get INFO only) |
| R009  | thin-coverage            | Tables with very low row/symbol counts vs. expectation |

## Operational notes

- **Read-only.** Connections are opened with `readonly=True`; running QSA
  during UDC harvest or MDC ingest is safe.
- **Rule failures don't abort the run.** A rule that raises emits a single
  `critical` finding (`rule_id=Rxxx`, `table=(rule-error)`) and the audit
  continues.
- **R007 consumer-grep is filesystem-only.** It walks the repos listed in
  `qsa.yaml::consumer_grep_repos` looking for textual references to
  deprecated `schema.table` strings; no DB calls.
- **Rebuild-safe.** Every run produces a fresh report; no QSA state is kept
  across runs other than the dated artefacts the operator commits.
