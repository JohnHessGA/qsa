"""Tests for the `qsa ccoption` compiler + orchestration.

All process/tool execution is injected, so nothing here runs IRA Guard, cc2,
or pgrep for real.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

import pytest

from qsa import ccoption as cc


# --- section slicing -------------------------------------------------------

SAMPLE = """# Title

## Funds Available — as of 2026-06-18

cash table here

## Recommendations (0) — expiring None

_zero recs_

## Symbols attempted

| x |
"""


def test_extract_section_slices_to_next_header():
    block = cc.extract_section(SAMPLE, "Funds Available")
    assert block is not None
    assert block.startswith("## Funds Available")
    assert "cash table here" in block
    assert "Recommendations" not in block  # stopped at next ##


def test_extract_section_missing_returns_none():
    assert cc.extract_section(SAMPLE, "Nonexistent") is None


def test_extract_section_distinguishes_similar_prefixes():
    md = "## Options in Play\n\nA\n\n## Options Available\n\nB\n"
    assert "A" in cc.extract_section(md, "Options in Play")
    assert "Available" not in cc.extract_section(md, "Options in Play")
    assert "B" in cc.extract_section(md, "Options Available")


def test_demote_drops_headers_one_level():
    assert cc._demote("## H\ntext\n### sub") == "### H\ntext\n#### sub"


def test_demote_and_label_tags_only_the_section_header():
    out = cc._demote_and_label("## Recommendations (0) — x\ntext\n### sub", "cc2")
    lines = out.splitlines()
    assert lines[0] == "### cc2 — Recommendations (0) — x"  # demoted + tagged
    assert lines[1] == "text"
    assert lines[2] == "#### sub"                            # demoted, not tagged


# --- process backoff -------------------------------------------------------

def test_wait_for_clear_returns_none_when_clear():
    assert cc.wait_for_clear(("iraguard",), is_running=lambda p: False) is None


def test_wait_for_clear_errors_after_retries_without_real_sleep():
    sleeps: list[float] = []
    err = cc.wait_for_clear(
        ("cc2", "mdc"),
        attempts=3,
        backoff=30,
        is_running=lambda p: True,        # always busy
        sleep_fn=sleeps.append,           # capture instead of sleeping
    )
    assert err is not None
    assert "still running after 3 attempts" in err
    assert sleeps == [30, 30]             # slept between the 3 attempts, not after last


def test_wait_for_clear_recovers_mid_retry():
    calls = {"n": 0}

    def is_running(_pattern: str) -> bool:
        calls["n"] += 1
        return calls["n"] < 2  # busy first check, clear after

    assert cc.wait_for_clear(
        ("iraguard",), is_running=is_running, sleep_fn=lambda s: None
    ) is None


# --- pipeline --------------------------------------------------------------

def test_run_pipeline_records_failure_but_continues():
    ran: list[str] = []

    def exec_fn(step):
        ran.append(step.label)
        ok = step.label != "iraguard ccoptions"
        return cc.StepResult(step.label, ok, None if ok else f"{step.label}: boom")

    results = cc.run_pipeline(
        wait_fn=lambda keys, **kw: None,   # always clear
        exec_fn=exec_fn,
    )
    # All four steps attempted despite the middle failure.
    assert len(ran) == 4
    failed = [r for r in results if not r.ok]
    assert len(failed) == 1 and "boom" in failed[0].error


def test_run_pipeline_busy_step_skips_exec():
    def wait_fn(keys, **kw):
        return "iraguard still running after 3 attempts" if "iraguard" in keys else None

    def exec_fn(step):
        return cc.StepResult(step.label, True)

    results = cc.run_pipeline(wait_fn=wait_fn, exec_fn=exec_fn)
    by_label = {r.label: r for r in results}
    assert not by_label["iraguard run"].ok          # blocked by busy pre-check
    assert by_label["cc2 scan"].ok                   # cc2/mdc clear -> ran


# --- freshness + banner ----------------------------------------------------

def _write_artifact(spec, tmp_root, body, when):
    d = tmp_root / spec.key
    d.mkdir(parents=True, exist_ok=True)
    name = spec.glob.replace("*", "x")
    p = d / name
    p.write_text(body)
    ts = when.timestamp()
    os.utime(p, (ts, ts))
    return p


def test_stale_artifact_is_flagged(tmp_path, monkeypatch):
    spec = cc.DEFAULT_SOURCES[0]  # cc2
    body = "## Funds Available — x\n\ncash\n\n## Recommendations (0) — x\n\nrec\n"
    old = datetime.now() - timedelta(hours=2)
    p = _write_artifact(spec, tmp_path, body, old)

    monkeypatch.setattr(cc, "find_latest_artifact",
                        lambda s: p if s.key == "cc2" else None)

    loaded = cc.load_sources((spec,), min_mtime=datetime.now())
    assert loaded["cc2"].stale is True

    md, problems = cc.render_report(loaded, generated_at=datetime.now())
    assert any("stale" in pr for pr in problems)
    assert "INCOMPLETE REPORT" in md


def test_run_problems_surface_in_banner():
    loaded: dict[str, cc.LoadedSource] = {}
    md, problems = cc.render_report(
        loaded, generated_at=datetime.now(),
        run_problems=["iraguard run: exit 1 — kaboom"],
    )
    assert "INCOMPLETE REPORT" in md
    assert "kaboom" in md
    assert "iraguard run: exit 1 — kaboom" in problems
