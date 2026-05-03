"""Smoke tests — config loads, rules importable, finding sorts."""

from __future__ import annotations

from datetime import datetime

from qsa.finding import Finding
from qsa.report import render_markdown


def test_finding_sort_order():
    a = Finding(rule_id="R001", severity="critical", database="masd", table="x", summary="a")
    b = Finding(rule_id="R001", severity="warning",  database="masd", table="x", summary="b")
    c = Finding(rule_id="R001", severity="info",     database="masd", table="x", summary="c")
    sorted_findings = sorted([c, a, b], key=lambda f: f.sort_key())
    assert [f.severity for f in sorted_findings] == ["critical", "warning", "info"]


def test_render_empty_report():
    md = render_markdown([], generated_at=datetime(2026, 5, 3))
    assert "QSA — Qualitative Signal Audit Report" in md
    assert "🔴 Critical: **0**" in md


def test_rules_module_importable():
    from qsa.rules import ALL_RULES
    assert len(ALL_RULES) >= 8
    for rule_id, fn in ALL_RULES:
        assert rule_id.startswith("R0")
        assert callable(fn)
