# QSA — CLI Reference

QSA exposes one top-level command (`qsa`) with one subcommand group (`audit`)
and one audit kind (`qualitative`). Everything is read-only.

## Install / activate

```bash
cd ~/repos/qsa
source venv/bin/activate
pip install -e .            # editable install on first use
qsa --help
```

## `qsa audit qualitative`

Runs all enabled rules against MASD + SHDB + MEFDB and writes a Markdown
report (and optionally CSV) to `reports/`.

```
qsa audit qualitative
    [--output PATH]
    [--csv PATH]
    [--rules R001,R007,...]
    [--stdout]
```

### Options

- `--output PATH`, `-o PATH`
  Markdown report path. Default: `reports/qsa_audit_YYYYMMDD.md` under the
  repo root, where `YYYYMMDD` is local-time today.
- `--csv PATH`
  Optional CSV path for a flat findings table (one row per finding, columns
  `rule_id, severity, database, table, summary, affected_rows,
  affected_symbols, recommendation`). Useful for diffing against prior
  baselines.
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
qsa audit qualitative
```

Run only the staleness and deprecated-tables rules and dump a CSV alongside:

```bash
qsa audit qualitative \
    --rules R006,R007 \
    --output reports/qsa_audit_partial_$(date +%Y%m%d).md \
    --csv    reports/qsa_audit_partial_$(date +%Y%m%d).csv
```

Quick check piped to a pager:

```bash
qsa audit qualitative --stdout > /dev/null  # writes file + prints to stdout
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

## Things QSA will NOT do

- Write to any database (connections are `readonly=True`).
- Send notifications (no email, no SMS, no Overwatch event rows).
- Run on cron in v1 — operator-driven, dated reports committed to `reports/`.
- Score, rank, or recommend trades. Findings are descriptive only.
