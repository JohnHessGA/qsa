# QSA — Build Specification

- **Abbreviation:** QSA
- **Full name:** Qualitative Signal Audit
- **Role:** AFT cross-cutting audit tool (read-only) — peer to MDC/UDC quality
  tooling rather than to the application streams (MEF/CCW/CIA/IRA Guard).

## Purpose

Read-only data-quality audit across MASD (bronze) and SHDB (silver), in three
slices:

- **Qualitative** (R001–R009) — the non-price slice: news, sentiment,
  insider/Form-4 events, congressional trades, SEC filings, CFPB complaints,
  FINRA short interest, etc.
- **Quantitative** (R010) — **OHLC price-bar integrity over the AFT
  investable universe** of stocks and ETFs (`shdb.v_investable_universe_active`).
  This slice is deliberately narrow: QSA checks that curated price bars are
  *possible and plausible* (no dropped-digit lows, no inverted bars); it does
  **not** compute returns/indicators or replicate MDC/UDC freshness dashboards.
- **Identity** (R011) — **ticker-reuse / long-void boundaries** where one
  `security_id` splices two different companies because a delisted issuer's
  ticker was later reused. Reports `shdb.security_ticker_boundary` plus a drift
  cross-check against long price-series voids.

QSA emits a Markdown + CSV findings report grouped by severity. Used as the
gating check before UDC harvest changes, and as the dated-snapshot record of
data quality over time.

## Inputs

- **Read-only DB connections:**
  - `masd` — raw qualitative tables collected by MDC.
  - `shdb` — curated qualitative tables + signals (R001–R009), the mart price
    tables `mart.stock_equity_daily` / `mart.stock_etf_daily` and the AFT
    investable-universe view `shdb.v_investable_universe_active` (R010). Search
    path: `mart, shdb, public`.
  - `mefdb` — universe tables (`mef.universe_stock`) for coverage checks.
- **Configuration:**
  - `config/qsa.yaml` — staleness thresholds per cadence, MEF coverage tiers,
    deprecated-table list with replacement pointers, repos to grep for live
    consumers. Checked into the repo.
  - `config/postgres.secrets.yaml` — DB credentials. Gitignored; see
    `config/postgres.secrets.yaml.example` and
    `~/repos/aft-platform/docs/conventions/secrets-conventions.md`.
- **Filesystem (read-only) for R007 consumer-grep:** `~/repos/{mef, ccw, cia,
  iraguard, rse, das, xpm, udc}` per `consumer_grep_repos` in `qsa.yaml`.

## Outputs

- **Markdown report** — `<artifacts_dir>/YYYY/MM/qsa_audit_YYYYMMDD.md`, where
  `artifacts_dir` is configured in `config/qsa.yaml` (default
  `/mnt/aftdata/qsa/artifacts`) and `YYYY/MM` is taken from the run date.
  Grouped by severity (critical / warning / info), per finding: rule ID,
  database, table, one-line summary, detail block, affected row/symbol counts,
  sample values, recommended action.
- **CSV findings table** (optional, `--csv`) — flat one-row-per-finding format
  suitable for diffing against prior baselines, written alongside the Markdown
  report as `qsa_audit_YYYYMMDD.csv`.
- **Exit code:** `0` if zero critical findings, `1` if any critical present.
  Wired so a CI/cron caller can gate on critical-clean.
- **No DB writes.** All connections are opened with `readonly=True`. QSA never
  emits notifications and does not touch Overwatch.

## Scope

- **Qualitative + narrow quantitative & identity slices.** The qualitative
  rules (R001–R009) cover news/sentiment/event tables. R010 covers **OHLC
  price-bar integrity for the AFT investable universe only**; R011 covers
  **ticker-reuse boundaries**. Returns/indicators, freshness dashboards, and
  the full price/return surface remain UDC's / MDC's / Overwatch's territory —
  QSA only checks that curated bars are possible and plausible.
- **Cross-database.** A single audit run spans MASD, SHDB, and MEFDB so that
  cross-tier issues (orphan curated rows, MEF universe coverage gaps) surface
  in one report.
- **Categorical, not statistical.** R001–R011 are deterministic shape checks
  (NULL keys, future dates, stale streams, missing-symbol joins, impossible
  OHLC bars, ticker-reuse boundaries, etc.), not anomaly detection or
  distribution drift.

## Hard boundaries

1. Read-only. No writes to any DB; no inserts to Overwatch; no notifications.
2. No backtesting, no scoring, no recommendations. Findings are descriptive.
3. No LLM. All rules are deterministic SQL + Python.
4. Quantitative checks are limited to OHLC bar integrity over the AFT
   investable universe. QSA does not compute returns/indicators and does not
   duplicate MDC/UDC freshness dashboards for price-and-return tables.
5. Output goes to `artifacts_dir` (default `/mnt/aftdata/qsa/artifacts`, outside
   the repo). Documentation about QSA goes to `docs/`. Nothing is written under
   the repo tree.

## Schedule

- **Weekly cron** — `Sat 09:00 America/New_York`, via the standard plumbing
  wrapper `scripts/cron_run.sh` (activates the venv and execs `qsa audit "$@"`;
  the wrapper owns the `audit` subcommand, so the crontab line is a bare
  wrapper call with no decision logic). Output and exit code as usual; the
  exit code lets the run gate on critical-clean.
- **Ad-hoc** — operators also run `qsa audit` by hand before/after
  pipeline changes; the dated report lands under
  `<artifacts_dir>/YYYY/MM/qsa_audit_*` either way.

## CLI surface

See `src/qsa/cli.py` and `docs/qsa_cli_reference.md`. The audit subcommand runs
all rules:

```
qsa audit [--csv] [--rules R001,R007,...] [--stdout]
```

A second, **non-audit** subcommand compiles the covered-call operations report
(added 2026-06-18 — see `docs/qsa_cli_reference.md` § `qsa ccoption`):

```
qsa ccoption [--compile-only] [--dry-run] [--stdout]
```

Unlike `audit`, `ccoption` *runs other AFT tools* (IRA Guard + cc2) to refresh
their Markdown artifacts, then slices and recombines those artifacts into one
consolidated covered-call report. QSA still writes no database; the side
effects (Fidelity fetch, yfinance, PHDB/CC2DB writes) belong to the invoked
tools.

## Config

- `config/postgres.secrets.yaml` — credentials for `masd`, `shdb`, `mefdb`
  (gitignored; see `config/postgres.secrets.yaml.example`).
- `config/qsa.yaml` — application knobs:
  - `artifacts_dir` — base directory for generated reports (default
    `/mnt/aftdata/qsa/artifacts`); reports land under its `YYYY/MM` subtree.
  - `min_valid_date`, `future_date_tolerance_days` for R001/R002.
  - `staleness_thresholds_days` per cadence — `daily`, `weekly`, `monthly`,
    `quarterly`, `bi_monthly_lagged` (FINRA short interest, mirrors MDC's
    21/45 no-data rule).
  - `mef_coverage.warn_below_pct` / `critical_below_pct` for R008.
  - `deprecated_tables` — schema/table/replacement/reason triples driving
    R007 plus the consumer-grep across `consumer_grep_repos`.
  - `ohlc_integrity` — R010 scan `targets` (schema.table + `asset_type`) plus
    `low_factor` / `high_factor` / `range_factor` / `max_samples`.

## Databases

### Tables read (inputs)

| Database | Schema(s)              | Purpose                                      |
|----------|------------------------|----------------------------------------------|
| `masd`   | `masd`                 | Raw qualitative tables (news, insider, etc.) |
| `shdb`   | `mart`, `shdb`         | Curated qualitative tables + derived signals (R001–R009); mart price tables + `v_investable_universe_active` (R010) |
| `mefdb`  | `mef`                  | `universe_stock` for R008 MEF coverage tier  |

All connections set `readonly=True` and `autocommit=True`. QSA writes nothing.

### Tables written (outputs)

None. QSA is purely advisory; its outputs are files under `artifacts_dir`
(default `/mnt/aftdata/qsa/artifacts`), never under the repo or any DB.

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
| R010  | ohlc-integrity           | Impossible/implausible OHLC bars (dropped-digit low, inverted bar) in mart price tables, AFT investable universe only — **quantitative** |

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
