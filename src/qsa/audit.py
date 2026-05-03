"""Audit orchestrator — opens connections, runs rules, returns Findings."""

from __future__ import annotations

import sys
from typing import Any

from qsa.config import load_app_config
from qsa.consumers import find_consumers
from qsa.db import masd_conn, mefdb_conn, shdb_conn
from qsa.finding import Finding
from qsa.rules import ALL_RULES


def run_audit(*, only_rules: list[str] | None = None) -> list[Finding]:
    app_cfg = load_app_config()
    findings: list[Finding] = []

    with masd_conn() as masd, shdb_conn() as shdb, mefdb_conn() as mefdb:
        for rule_id, rule_fn in ALL_RULES:
            if only_rules and rule_id not in only_rules:
                continue
            try:
                rule_findings = rule_fn(masd=masd, shdb=shdb, mefdb=mefdb, app_cfg=app_cfg)
                findings.extend(rule_findings)
                print(f"  [{rule_id}] produced {len(rule_findings)} finding(s)", file=sys.stderr)
            except Exception as exc:
                # Surface the rule failure as a critical finding rather than aborting.
                findings.append(Finding(
                    rule_id=rule_id,
                    severity="critical",
                    database="qsa",
                    table="(rule-error)",
                    summary=f"Rule {rule_id} raised an exception",
                    detail=f"{type(exc).__name__}: {exc}",
                ))
                print(f"  [{rule_id}] ERROR: {exc}", file=sys.stderr)

    # Cross-cutting: deprecated-table consumer grep (filesystem only).
    if not only_rules or "R007-deprecated-tables" in only_rules:
        try:
            findings.extend(find_consumers(app_cfg))
        except Exception as exc:
            findings.append(Finding(
                rule_id="R007-deprecated-tables",
                severity="critical",
                database="fs",
                table="(consumer-grep-error)",
                summary=f"Consumer-grep failed: {exc}",
                detail=str(exc),
            ))

    return findings
