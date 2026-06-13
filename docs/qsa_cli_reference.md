# QSA — CLI Reference

QSA exposes one top-level command (`qsa`) with one audit subcommand (`audit`),
which runs all rules. Everything is read-only.

## Install / activate

```bash
cd ~/repos/qsa
source .venv/bin/activate
pip install -e .            # editable install on first use
qsa --help
```

## `qsa audit`

Runs all enabled rules against MASD + SHDB + MEFDB and writes a Markdown
report (and optionally CSV) under the configured `artifacts_dir`.

```
qsa audit
    [--csv]
    [--rules R001,R007,...]
    [--stdout]
```

### Output location

Reports are written to:

```
<artifacts_dir>/YYYY/MM/qsa_audit_YYYYMMDD.md
```

where `artifacts_dir` comes from `config/qsa.yaml` (default
`/mnt/aftdata/qsa/artifacts`) and `YYYY/MM/YYYYMMDD` are taken from the local
run date. The `YYYY/MM` subtree is created on demand. Nothing is written under
the repo. There is no flag to override the path — relocate by editing
`artifacts_dir` in `config/qsa.yaml`.

### Options

- `--csv`
  Also emit a flat CSV findings table (one row per finding, columns
  `rule_id, severity, database, table, summary, affected_rows,
  affected_symbols, recommendation`) next to the Markdown report as
  `qsa_audit_YYYYMMDD.csv`. Useful for diffing against prior baselines.
- `--rules R001,R007,...`
  Comma-separated rule IDs to run. Short codes (`R001`) are accepted and
  resolved by prefix-match against the canonical IDs (`R001-invalid-
  timestamps`, etc.). Default: all rules.
- `--stdout`
  Also print the rendered Markdown to stdout, in addition to writing it.

### Exit codes

- `0` — zero `critical` findings.
- `1` — at least one `critical` finding (or a rule raised an exception, which
  is reported as a critical `(rule-error)` finding rather than aborting).

### Examples

Full audit with default-named report:

```bash
qsa audit
```

Run only the staleness and deprecated-tables rules and dump a CSV alongside:

```bash
qsa audit --rules R006,R007 --csv
```

Quick check piped to a pager:

```bash
qsa audit --stdout > /dev/null  # writes file + prints to stdout
```

## Report layout

Generated reports group findings in this order:

1. **Header** — generated-at timestamp, total counts per severity.
2. **Critical** — must-fix items (invalid timestamps, future dates, exceptions
   raised by rules, etc.).
3. **Warning** — quality issues that don't block but should be tracked
   (staleness, thin coverage, deprecated tables with live consumers).
4. **Info** — informational signals (sparse-expected tables, deprecated tables
   with no live consumers, low-MEF-coverage tier crossings).

Each finding includes:
- Rule ID and severity
- Database + qualified table name
- One-line summary
- Multi-line detail block (counts, sample values, affected symbols)
- Recommendation, when actionable

## Configuration that affects output

All in `config/qsa.yaml`:

- `artifacts_dir` — base directory for generated reports (default
  `/mnt/aftdata/qsa/artifacts`); reports land under its `YYYY/MM` subtree.
- `min_valid_date`, `future_date_tolerance_days` — R001 / R002 thresholds.
- `staleness_thresholds_days` — per-cadence freshness rules for R006,
  including `bi_monthly_lagged: 21` for FINRA short interest (matches MDC's
  21/45 no-data alert window).
- `mef_coverage.warn_below_pct` / `critical_below_pct` — R008 tiers against
  the MEF 305-stock universe.
- `deprecated_tables` — list of `{schema, table, replacement, reason}` triples
  flagged by R007. Each entry triggers a consumer-grep across the repos
  listed in `consumer_grep_repos`.
- `consumer_grep_repos` — paths walked by R007's filesystem grep; no DB
  calls, just textual `schema.table` matches.
- `ohlc_integrity` — R010 OHLC price-bar integrity (quantitative): `targets`
  (mart `schema.table` + `asset_type`), `low_factor` (dropped-digit low,
  critical), `high_factor` / `range_factor` (high spike / wide range,
  warning), `max_samples`. Scoped to `shdb.v_investable_universe_active`.

## Things QSA will NOT do

- Write to any database (connections are `readonly=True`).
- Send notifications (no email, no SMS, no Overwatch event rows).
- Score, rank, or recommend trades. Findings are descriptive only.
