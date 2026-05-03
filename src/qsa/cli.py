"""QSA command-line entry point.

Currently implements one subcommand:

    qsa audit qualitative [--output PATH] [--csv PATH] [--rules R001,R002,...]

The audit is read-only: connections are opened with readonly=true and no rule
issues a write of any kind.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from qsa.audit import run_audit
from qsa.config import repo_root
from qsa.report import render_markdown, write_csv, write_markdown


def _add_audit(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("audit", help="Run a QSA audit.")
    audit_sub = p.add_subparsers(dest="audit_kind", required=True)

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
    parser = argparse.ArgumentParser(prog="qsa", description="Qualitative Signal Audit")
    sub = parser.add_subparsers(dest="cmd", required=True)
    _add_audit(sub)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
