"""Markdown + CSV report writers."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from qsa.finding import Finding, SEVERITY_ORDER


SEVERITY_BADGE = {
    "critical": "🔴 CRITICAL",
    "warning":  "🟡 WARNING",
    "info":     "🟢 INFO",
}

# Categorical buckets — orthogonal to severity. Built so the user can scan
# the summary and see "what needs attention vs what's just a known structural
# property of the data."
#
#   active     — likely a real data defect (invalid rows, missing data,
#                duplicate keys, future dates). Action recommended.
#   monitor    — staleness or thin-coverage; data is fine but worth watching.
#   retired    — table marked deprecated/retired in qsa.yaml. Reported once
#                so the listing is visible, but should not be treated as an
#                active failure.
#   structural — known by-design NULLs (e.g. SEC API rows for individuals).
#                Reported under INFO severity now that R003 honours
#                entity_type — kept in the report so consumers can see the
#                shape of the data, not because it's broken.
#   coverage   — R008/R009 — population stats per table against the MEF
#                universe. Mostly informational.
CATEGORIES = ("active", "monitor", "retired", "structural", "coverage")


def _category_for(finding) -> str:
    """Derive the categorical bucket from rule + severity."""
    rule = finding.rule_id
    sev = finding.severity
    if rule == "R007-deprecated-tables":
        return "retired"
    if rule == "R008-mef-coverage":
        return "coverage"
    if rule == "R009-thin-coverage":
        return "coverage"
    if rule == "R006-staleness":
        return "monitor"
    if rule == "R003-missing-symbols" and sev == "info":
        # info-severity R003 means the entity_type filter explained most
        # of the NULLs as structural.
        return "structural"
    if sev in ("critical", "warning"):
        return "active"
    return "structural"


def _format_sample(sample: list) -> str:
    if not sample:
        return ""
    if all(isinstance(s, dict) for s in sample):
        keys = list(sample[0].keys())
        rows = ["| " + " | ".join(keys) + " |",
                "|" + "|".join(["---"] * len(keys)) + "|"]
        for row in sample[:10]:
            rows.append("| " + " | ".join(str(row.get(k, "")) for k in keys) + " |")
        return "\n".join(rows)
    return "```\n" + json.dumps(sample[:10], default=str, indent=2) + "\n```"


def render_markdown(findings: list[Finding], *, generated_at: datetime) -> str:
    findings = sorted(findings, key=lambda f: f.sort_key())
    counts = Counter(f.severity for f in findings)
    by_rule: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        by_rule[f.rule_id].append(f)

    lines: list[str] = []
    lines.append("# QSA — Qualitative Signal Audit Report")
    lines.append("")
    lines.append(f"*Generated: {generated_at.isoformat(timespec='seconds')}*")
    lines.append("")
    lines.append("Read-only audit of qualitative / sentiment / event data across MASD and SHDB.")
    lines.append("This report identifies data-quality issues; it does not modify any database.")
    lines.append("")

    # Severity summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- 🔴 Critical: **{counts.get('critical', 0)}**")
    lines.append(f"- 🟡 Warning:  **{counts.get('warning', 0)}**")
    lines.append(f"- 🟢 Info:     **{counts.get('info', 0)}**")
    lines.append(f"- Total:      **{len(findings)}**")
    lines.append("")

    # Categorical summary — orthogonal to severity. Lets the reader see
    # "active defects vs monitoring vs retired noise vs coverage stats"
    # at a glance.
    cat_counts: Counter = Counter(_category_for(f) for f in findings)
    cat_labels = {
        "active":     "🛠  **Active defects**     — likely real issues, action recommended",
        "monitor":    "👀 **Monitoring**           — staleness / thin coverage; watch but not broken",
        "retired":    "🗄  **Retired sources**     — formally retired; tracked here for visibility",
        "structural": "📐 **Structural / by-design** — known correct NULLs (e.g. individual defendants)",
        "coverage":   "📊 **Coverage info**         — population stats vs the MEF universe",
    }
    lines.append("### By category")
    lines.append("")
    for cat in CATEGORIES:
        n = cat_counts.get(cat, 0)
        if n == 0 and cat in ("active", "monitor"):
            lines.append(f"- {cat_labels[cat]}: **{n}** ✅")
        else:
            lines.append(f"- {cat_labels[cat]}: **{n}**")
    lines.append("")

    # By rule
    lines.append("## Findings by Rule")
    lines.append("")
    lines.append("| Rule | Severity counts | Description |")
    lines.append("|---|---|---|")
    rule_names = {
        "R001-invalid-timestamps": "Invalid / impossible timestamps in news tables",
        "R002-future-dates":       "Future-dated rows where the column should be historical",
        "R003-missing-symbols":    "Rows missing a symbol where one is required",
        "R004-duplicate-keys":     "Duplicate natural keys in curated SHDB tables",
        "R005-orphan-rows":        "Child rows with no matching parent article",
        "R006-staleness":          "Streams whose most-recent observation is past threshold",
        "R007-deprecated-tables":  "Tables marked deprecated; live consumers across AFT",
        "R008-mef-coverage":       "MEF universe coverage per qualitative table",
        "R009-thin-coverage":      "Tables with unexpectedly low distinct-symbol counts",
    }
    for rule_id, rule_findings in sorted(by_rule.items()):
        cnt = Counter(f.severity for f in rule_findings)
        cnt_str = " ".join(f"{SEVERITY_BADGE[s].split(' ')[0]} {cnt[s]}" for s in ("critical", "warning", "info") if cnt[s])
        lines.append(f"| `{rule_id}` | {cnt_str or '—'} | {rule_names.get(rule_id, '')} |")
    lines.append("")

    # Detail sections grouped by severity
    for severity in ("critical", "warning", "info"):
        sev_findings = [f for f in findings if f.severity == severity]
        if not sev_findings:
            continue
        lines.append(f"## {SEVERITY_BADGE[severity]} ({len(sev_findings)})")
        lines.append("")
        for f in sev_findings:
            lines.append(f"### `{f.rule_id}` — {f.table or '(cross-table)'}")
            lines.append("")
            lines.append(f"**{f.summary}**")
            lines.append("")
            if f.detail:
                lines.append(f.detail)
                lines.append("")
            meta_bits: list[str] = []
            if f.affected_rows is not None:
                meta_bits.append(f"affected rows: **{f.affected_rows:,}**")
            if f.affected_symbols is not None:
                meta_bits.append(f"affected symbols: **{f.affected_symbols:,}**")
            if meta_bits:
                lines.append("- " + " · ".join(meta_bits))
                lines.append("")
            if f.sample:
                lines.append("**Sample:**")
                lines.append("")
                lines.append(_format_sample(f.sample))
                lines.append("")
            if f.recommendation:
                lines.append(f"_Recommendation:_ {f.recommendation}")
                lines.append("")
            lines.append("---")
            lines.append("")

    # Footer
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "This report was generated by **QSA** (Qualitative Signal Audit), a read-only "
        "audit tool that opens MASD, SHDB, and MEFDB connections in `readonly=true` mode "
        "and runs a fixed set of validation rules. No table is modified. To re-run:"
    )
    lines.append("")
    lines.append("```")
    lines.append("cd ~/repos/qsa && source .venv/bin/activate")
    lines.append("qsa audit qualitative")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def write_markdown(findings: list[Finding], path: Path, *, generated_at: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(findings, generated_at=generated_at))


def write_csv(findings: list[Finding], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rule_id", "severity", "database", "table", "summary",
                    "affected_rows", "affected_symbols", "recommendation"])
        for fi in sorted(findings, key=lambda x: x.sort_key()):
            w.writerow([fi.rule_id, fi.severity, fi.database, fi.table, fi.summary,
                        fi.affected_rows or "", fi.affected_symbols or "", fi.recommendation])
