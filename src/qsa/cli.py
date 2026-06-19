"""QSA command-line entry point.

Subcommands:

    qsa                     → equivalent to `qsa status`
    qsa status              → last audit timestamp + DB connectivity check
    qsa audit               → run the audit, all rules (read-only)
    qsa ccoption            → consolidated covered-call operations report

The audit is read-only: connections are opened with readonly=True and no
rule issues a write of any kind.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from qsa.audit import run_audit
from qsa.config import artifacts_dir
from qsa.report import render_markdown, write_csv, write_markdown


def _report_path(generated_at: datetime, suffix: str) -> Path:
    """Dated report path under the configured artifacts dir.

    Layout: <artifacts_dir>/YYYY/MM/qsa_audit_YYYYMMDD.<suffix>, with YYYY/MM
    taken from the generated date. Parent dirs are created by the writers.
    """
    base = artifacts_dir() / generated_at.strftime("%Y") / generated_at.strftime("%m")
    return base / f"qsa_audit_{generated_at.strftime('%Y%m%d')}.{suffix}"


def _audit_recency_key(path: Path) -> tuple[str, float]:
    """Sort key for ranking audit reports newest-first.

    Ranks by the YYYYMMDD date embedded in the filename (the audit date),
    not lexicographic filename order — so `qsa_audit_20260527.md` beats
    `qsa_audit_post_tuning_20260503.md`. Files that share a date are broken
    by mtime. A name with no parseable date sorts oldest.
    """
    dates = re.findall(r"(\d{8})", path.stem)
    date_str = dates[-1] if dates else ""
    return (date_str, path.stat().st_mtime)


class _FullHelpArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that prints full help on error.

    Default argparse prints only the usage line plus the error message.
    AFT convention is to print the complete help body so the operator
    immediately sees the supported commands when they mistype. `-h` /
    `--help` behavior is unchanged.
    """

    def error(self, message):  # type: ignore[override]
        self.print_help(sys.stderr)
        sys.stderr.write(f"\nerror: {message}\n")
        sys.exit(2)


def _add_status(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "status",
        help="Show latest audit timestamp + DB connectivity (default).",
    )
    p.set_defaults(func=_run_status)


def _add_audit(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "audit",
        help="Run the QSA audit (all rules) across MASD and SHDB.",
    )
    p.add_argument(
        "--csv",
        action="store_true",
        help="Also emit a CSV findings table alongside the Markdown report "
             "(same artifacts dir, .csv extension).",
    )
    p.add_argument(
        "--rules",
        default=None,
        help="Comma-separated rule IDs to run (default: all). Example: R001,R007",
    )
    p.add_argument(
        "--stdout",
        action="store_true",
        help="Print the report to stdout in addition to writing it.",
    )
    p.set_defaults(func=_run_audit)


def _add_ccoption(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "ccoption",
        help="Refresh (run IRA Guard + cc2) and compile a consolidated "
             "covered-call operations report.",
    )
    p.add_argument(
        "--compile-only",
        action="store_true",
        help="Skip running the tools; compile from the newest artifacts already "
             "on disk (no side effects).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would run and the live process pre-checks, but don't "
             "execute the tools; compiles from on-disk artifacts for preview.",
    )
    p.add_argument(
        "--stdout",
        action="store_true",
        help="Print the report to stdout in addition to writing it.",
    )
    p.set_defaults(func=_run_ccoption)


def _run_ccoption(args: argparse.Namespace) -> int:
    """Compile the consolidated covered-call operations report.

    Default refreshes inputs by running IRA Guard (run/ccoptions/standing) and
    cc2 (scan) — each gated by a live-process backoff — then compiles. The
    report is always written; on any failure it carries a banner and the
    command exits non-zero.
    """
    from qsa.ccoption import (
        STEPS, build_report, build_report_live, report_path, wait_for_clear,
    )

    def log(msg: str) -> None:
        print(msg, file=sys.stderr)

    generated_at = datetime.now()

    if args.dry_run:
        print("DRY RUN — would run, in order:", file=sys.stderr)
        for step in STEPS:
            running = wait_for_clear(step.precheck, attempts=1)
            state = "BUSY" if running else "clear"
            print(f"  - {step.label} (pre-check {','.join(step.precheck)}: {state})",
                  file=sys.stderr)
        markdown, problems = build_report(generated_at=generated_at)
    elif args.compile_only:
        markdown, problems = build_report(generated_at=generated_at)
    else:
        markdown, problems = build_report_live(generated_at=generated_at, log=log)

    output_path = report_path(artifacts_dir(), generated_at)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown)
    print(f"Wrote {output_path}", file=sys.stderr)

    if problems:
        print(f"INCOMPLETE — {len(problems)} issue(s):", file=sys.stderr)
        for prob in problems:
            print(f"  - {prob}", file=sys.stderr)

    if args.stdout:
        print(markdown)

    # Exit non-zero if the report is not fully fresh/complete.
    return 0 if not problems else 1


def _run_status(args: argparse.Namespace) -> int:
    """Print QSA status: latest audit + DB connectivity."""
    from qsa.db import masd_conn, shdb_conn, mefdb_conn

    print("QSA Status")
    print("==========")

    reports_dir = artifacts_dir()
    audits = (
        sorted(reports_dir.rglob("qsa_audit_*.md"), key=_audit_recency_key, reverse=True)
        if reports_dir.is_dir() else []
    )
    if audits:
        latest = audits[0]
        mtime = datetime.fromtimestamp(latest.stat().st_mtime)
        print(f"Latest audit: {latest.name}")
        print(f"              {mtime.strftime('%Y-%m-%d %H:%M')} ({latest})")
    else:
        print(f"Latest audit: (none — no qsa_audit_*.md under {reports_dir})")

    print()
    print("Database connectivity (readonly):")
    rc = 0
    for name, conn_fn in [("masd", masd_conn), ("shdb", shdb_conn), ("mefdb", mefdb_conn)]:
        try:
            with conn_fn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            print(f"  [OK]   {name}")
        except Exception as exc:
            print(f"  [FAIL] {name}: {exc}")
            rc = 1

    return rc


def _run_audit(args: argparse.Namespace) -> int:
    only_rules: list[str] | None = None
    if args.rules:
        only_rules = []
        for token in args.rules.split(","):
            token = token.strip()
            # Accept short codes like "R001" by prefix-matching the canonical IDs.
            if not token:
                continue
            only_rules.append(token if "-" in token else _resolve_rule_prefix(token))

    print("Running QSA audit (read-only)...", file=sys.stderr)
    findings = run_audit(only_rules=only_rules)
    print(f"Total findings: {len(findings)}", file=sys.stderr)

    generated_at = datetime.now()
    output_path = _report_path(generated_at, "md")
    write_markdown(findings, output_path, generated_at=generated_at)
    print(f"Wrote {output_path}", file=sys.stderr)

    if args.csv:
        csv_path = _report_path(generated_at, "csv")
        write_csv(findings, csv_path)
        print(f"Wrote {csv_path}", file=sys.stderr)

    if args.stdout:
        print(render_markdown(findings, generated_at=generated_at))

    # Exit code: 0 if no critical findings, 1 if any critical present.
    n_critical = sum(1 for f in findings if f.severity == "critical")
    return 0 if n_critical == 0 else 1


def _resolve_rule_prefix(token: str) -> str:
    from qsa.rules import ALL_RULES
    for rid, _ in ALL_RULES:
        if rid.startswith(token):
            return rid
    return token  # let the rule simply not match


def main(argv: list[str] | None = None) -> int:
    parser = _FullHelpArgumentParser(prog="qsa", description="Qualitative Signal Audit")
    sub = parser.add_subparsers(
        dest="cmd",
        required=False,
        parser_class=_FullHelpArgumentParser,
    )
    _add_status(sub)
    _add_audit(sub)
    _add_ccoption(sub)

    args = parser.parse_args(argv)
    if args.cmd is None:
        # Bare `qsa` → `qsa status` (AFT convention).
        args = parser.parse_args(["status"])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
