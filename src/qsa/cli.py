"""QSA command-line entry point.

Subcommands:

    qsa                     → equivalent to `qsa status`
    qsa status              → last audit timestamp + DB connectivity check
    qsa audit qualitative   → run the qualitative audit (read-only)

The audit is read-only: connections are opened with readonly=True and no
rule issues a write of any kind.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from qsa.audit import run_audit
from qsa.config import repo_root
from qsa.report import render_markdown, write_csv, write_markdown


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
    p = sub.add_parser("audit", help="Run a QSA audit.")
    audit_sub = p.add_subparsers(
        dest="audit_kind",
        required=True,
        parser_class=_FullHelpArgumentParser,
    )

    q = audit_sub.add_parser(
        "qualitative",
        help="Audit qualitative/sentiment/event data across MASD and SHDB.",
    )
    q.add_argument(
        "--output", "-o",
        default=None,
        help="Path to write the Markdown report. Default: reports/qsa_audit_YYYYMMDD.md",
    )
    q.add_argument(
        "--csv",
        default=None,
        help="Optional CSV path for a flat findings table.",
    )
    q.add_argument(
        "--rules",
        default=None,
        help="Comma-separated rule IDs to run (default: all). Example: R001,R007",
    )
    q.add_argument(
        "--stdout",
        action="store_true",
        help="Print the report to stdout in addition to writing it.",
    )
    q.set_defaults(func=_run_audit_qualitative)


def _run_status(args: argparse.Namespace) -> int:
    """Print QSA status: latest audit + DB connectivity."""
    from qsa.db import masd_conn, shdb_conn, mefdb_conn

    print("QSA Status")
    print("==========")

    reports_dir = repo_root() / "reports"
    audits = sorted(reports_dir.glob("qsa_audit_*.md"), reverse=True) if reports_dir.is_dir() else []
    if audits:
        latest = audits[0]
        mtime = datetime.fromtimestamp(latest.stat().st_mtime)
        print(f"Latest audit: {latest.name}")
        print(f"              {mtime.strftime('%Y-%m-%d %H:%M')} ({latest})")
    else:
        print("Latest audit: (none — no qsa_audit_*.md in reports/)")

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


def _run_audit_qualitative(args: argparse.Namespace) -> int:
    only_rules: list[str] | None = None
    if args.rules:
        only_rules = []
        for token in args.rules.split(","):
            token = token.strip()
            # Accept short codes like "R001" by prefix-matching the canonical IDs.
            if not token:
                continue
            only_rules.append(token if "-" in token else _resolve_rule_prefix(token))

    print("Running QSA qualitative audit (read-only)...", file=sys.stderr)
    findings = run_audit(only_rules=only_rules)
    print(f"Total findings: {len(findings)}", file=sys.stderr)

    generated_at = datetime.now()
    output_path = Path(args.output) if args.output else (
        repo_root() / "reports" / f"qsa_audit_{generated_at.strftime('%Y%m%d')}.md"
    )
    write_markdown(findings, output_path, generated_at=generated_at)
    print(f"Wrote {output_path}", file=sys.stderr)

    if args.csv:
        csv_path = Path(args.csv)
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

    args = parser.parse_args(argv)
    if args.cmd is None:
        # Bare `qsa` → `qsa status` (AFT convention).
        args = parser.parse_args(["status"])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
