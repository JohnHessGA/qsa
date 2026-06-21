"""`qsa ccoption` — consolidated covered-call operations report.

First-pass *compiler* only: it reads the most recent on-disk artifacts that
IRA Guard and cc2 already produce, slices out the sections we care about, and
assembles them into a single human-readable Markdown report. It does **not**
run those tools — the orchestration layer (process checks, backoff, quiesce,
freshness assertion, abort/banner) is bolted on top of this later.

Sections consumed (matched by the stable prefix of each `##` header, since the
source tools embed live counts/dates in the header text):

    cc2 phase-2 artifact      → "Funds Available", "Recommendations"
    IRA Guard ccoptions       → "Suggestions"
    IRA Guard standing        → "Open Orders", "Options in Play", "Options Available"

The compiler is deliberately lossless: each extracted section is embedded
verbatim (headers demoted one level so the document hierarchy stays valid),
so we can look at a real sample and tune the layout before re-parsing anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from qsa.config import load_app_config


# --- source artifact specs -------------------------------------------------
#
# Defaults match where IRA Guard and cc2 write today. Each can be overridden
# from a `ccoption:` block in config/qsa.yaml without code changes.

@dataclass(frozen=True)
class SourceSpec:
    key: str          # internal id used by the group layout
    label: str        # human label shown in the Sources table
    tool: str         # short source-tool tag prefixed onto embedded headers
    root: Path        # directory tree to search (recursively)
    glob: str         # filename glob identifying this tool's artifacts


DEFAULT_SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        key="cc2",
        label="cc2 phase 2",
        tool="cc2",
        root=Path("/mnt/aftdata/cc2/artifacts"),
        glob="cc2_phase2_options_*.md",
    ),
    SourceSpec(
        key="iraguard_ccoptions",
        label="IRA Guard ccoptions",
        tool="iraguard",
        root=Path("/mnt/aftdata/iraguard/artifacts/ccoptions"),
        glob="ccoptions-*.md",
    ),
    SourceSpec(
        key="iraguard_standing",
        label="IRA Guard standing",
        tool="iraguard",
        root=Path("/mnt/aftdata/iraguard/artifacts/standing"),
        glob="iraguard-standing-*.md",
    ),
)

# Consolidated layout: ordered (group title, [(source key, section prefix), ...]).
# Section prefix is the invariant leading text of the source `##` header.
GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("Write candidates today", (
        ("cc2", "Recommendations"),
        ("iraguard_ccoptions", "Suggestions"),
    )),
    ("Already in play", (
        ("iraguard_standing", "Options in Play"),
    )),
    ("Writable shares", (
        ("iraguard_standing", "Options Available"),
    )),
    ("Cash available", (
        ("cc2", "Funds Available"),
    )),
    ("Open stock / ETF orders", (
        ("iraguard_standing", "Open Orders"),
    )),
)


def _load_sources() -> tuple[SourceSpec, ...]:
    """Source specs, with optional overrides from config/qsa.yaml `ccoption:`.

    Falls back silently to DEFAULT_SOURCES if the config block is absent or
    malformed — the compiler must not require a config edit to run.
    """
    try:
        cfg = load_app_config().get("ccoption", {}) or {}
    except Exception:
        return DEFAULT_SOURCES
    overrides = cfg.get("sources") or {}
    if not isinstance(overrides, dict):
        return DEFAULT_SOURCES
    out: list[SourceSpec] = []
    for spec in DEFAULT_SOURCES:
        ov = overrides.get(spec.key) or {}
        out.append(SourceSpec(
            key=spec.key,
            label=ov.get("label", spec.label),
            tool=ov.get("tool", spec.tool),
            root=Path(str(ov.get("root", spec.root))).expanduser(),
            glob=ov.get("glob", spec.glob),
        ))
    return tuple(out)


# --- artifact discovery + section slicing ----------------------------------

@dataclass
class LoadedSource:
    spec: SourceSpec
    path: Path | None = None
    mtime: datetime | None = None
    text: str = ""
    problem: str | None = None
    stale: bool = False
    sections: dict[str, str] = field(default_factory=dict)  # prefix -> block


def find_latest_artifact(spec: SourceSpec) -> Path | None:
    """Newest artifact (by mtime) matching the spec, or None if none exist."""
    if not spec.root.is_dir():
        return None
    matches = list(spec.root.rglob(spec.glob))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def extract_section(text: str, prefix: str) -> str | None:
    """Return the `##` section whose header starts with `prefix`, else None.

    The block runs from its `##` header line up to (but not including) the next
    `##` header at the same level, or end of file. The header line is kept.
    """
    lines = text.splitlines()
    start = None
    pat = re.compile(r"^##\s+" + re.escape(prefix))
    for i, line in enumerate(lines):
        if pat.match(line):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s", lines[j]):
            end = j
            break
    block = "\n".join(lines[start:end]).rstrip()
    return block


def _demote(block: str) -> str:
    """Demote every Markdown header in a block by one level (## -> ###)."""
    return "\n".join(
        ("#" + line) if line.startswith("##") else line
        for line in block.splitlines()
    )


def _demote_and_label(block: str, tool: str) -> str:
    """Demote headers one level and tag the section's own header with its
    source tool, so a reader can tell which tool produced it — e.g.
    ``## Recommendations …`` -> ``### cc2 — Recommendations …``.

    Only the section's leading header is tagged; demoted sub-headers are left
    as-is.
    """
    demoted = _demote(block)
    lines = demoted.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(#+\s+)(.*)$", line)
        if m:
            lines[i] = f"{m.group(1)}{tool} — {m.group(2)}"
            break
    return "\n".join(lines)


def load_sources(
    specs: tuple[SourceSpec, ...], *, min_mtime: datetime | None = None
) -> dict[str, LoadedSource]:
    """Locate + read each source's newest artifact and slice needed sections.

    If ``min_mtime`` is given (live mode), an artifact older than that cutoff is
    flagged ``stale`` — its content is still shown, but the Sources row is
    marked and the staleness surfaces in the report banner. This is the
    "is this artifact actually from the run we just triggered?" assertion.
    """
    # Which prefixes each source must yield (from the group layout).
    wanted: dict[str, set[str]] = {}
    for _title, members in GROUPS:
        for key, prefix in members:
            wanted.setdefault(key, set()).add(prefix)

    loaded: dict[str, LoadedSource] = {}
    for spec in specs:
        ls = LoadedSource(spec=spec)
        path = find_latest_artifact(spec)
        if path is None:
            ls.problem = f"no artifact found under {spec.root} matching {spec.glob}"
            loaded[spec.key] = ls
            continue
        ls.path = path
        ls.mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if min_mtime is not None and ls.mtime < min_mtime:
            ls.stale = True
        try:
            ls.text = path.read_text()
        except OSError as exc:
            ls.problem = f"could not read {path}: {exc}"
            loaded[spec.key] = ls
            continue
        for prefix in wanted.get(spec.key, set()):
            block = extract_section(ls.text, prefix)
            if block is not None:
                ls.sections[prefix] = block
        loaded[spec.key] = ls
    return loaded


# --- report assembly -------------------------------------------------------

def render_report(
    loaded: dict[str, LoadedSource],
    *,
    generated_at: datetime,
    run_problems: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Assemble the consolidated Markdown. Returns (markdown, problems).

    ``run_problems`` carries orchestration-level failures (a tool still busy
    after retries, a non-zero exit, a timeout). They are merged with any
    compiler-level problems (missing/stale artifacts or sections) into a single
    banner at the top, so the report always tells the truth about its own
    completeness.
    """
    problems: list[str] = list(run_problems or [])
    body: list[str] = []

    # Sources table.
    body.append("## Sources")
    body.append("")
    body.append("| Tool | Artifact | Generated | Status |")
    body.append("|---|---|---|---|")
    for spec in DEFAULT_SOURCES:
        ls = loaded.get(spec.key)
        if ls is None or ls.path is None:
            problem = (ls.problem if ls else "not loaded") or "missing"
            problems.append(f"{spec.label}: {problem}")
            body.append(f"| {spec.label} | _missing_ | — | 🔴 missing |")
        else:
            ts = ls.mtime.strftime("%Y-%m-%d %H:%M") if ls.mtime else "—"
            if ls.stale:
                problems.append(
                    f"{spec.label}: artifact `{ls.path.name}` is stale "
                    f"(not produced by this run)"
                )
                status = "🟡 STALE"
            else:
                status = "🟢 fresh"
            body.append(f"| {spec.label} | `{ls.path.name}` | {ts} | {status} |")
    body.append("")

    # Grouped sections.
    for title, members in GROUPS:
        body.append(f"## {title}")
        body.append("")
        for key, prefix in members:
            ls = loaded.get(key)
            label = ls.spec.label if ls else key
            if ls is None or ls.problem:
                note = (ls.problem if ls else "source not loaded")
                body.append(f"> ⚠️ `{label}` / **{prefix}** unavailable — {note}")
                body.append("")
                problems.append(f"{label} / {prefix}: {note}")
                continue
            block = ls.sections.get(prefix)
            if block is None:
                body.append(
                    f"> ⚠️ section **{prefix}** not found in `{ls.path.name}`"
                )
                body.append("")
                problems.append(f"{label} / {prefix}: section not found")
                continue
            body.append(_demote_and_label(block, ls.spec.tool))
            body.append("")

    # Title + (optional) failure banner + body.
    head: list[str] = []
    head.append(
        f"# QSA — Covered-Call Operations — {generated_at.strftime('%Y-%m-%d')}"
    )
    head.append("")
    head.append(f"*Generated: {generated_at.isoformat(timespec='seconds')}*")
    head.append("")
    head.append(
        "Consolidated covered-call view compiled from IRA Guard and cc2 "
        "artifacts. **Advisory only — verify every candidate in Fidelity "
        "(live price, bid, liquidity, order preview) before trading.**"
    )
    head.append("")
    if problems:
        head.append(
            f"> 🔴 **INCOMPLETE REPORT** — {len(problems)} issue(s) prevented a "
            "fully fresh compile. The sections below may be stale or missing:"
        )
        for prob in problems:
            head.append(f"> - {prob}")
        head.append("")

    out = head + body
    return "\n".join(out).rstrip() + "\n", problems


def report_path(base: Path, generated_at: datetime) -> Path:
    """Dated output path: <base>/ccoptions/YYYY/MM/ccoption-YYYY-MM-DD-HHMM.md."""
    sub = (
        base / "ccoptions"
        / generated_at.strftime("%Y") / generated_at.strftime("%m")
    )
    name = f"ccoption-{generated_at.strftime('%Y-%m-%d-%H%M')}.md"
    return sub / name


def build_report(
    *, generated_at: datetime | None = None, min_mtime: datetime | None = None,
    run_problems: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Compile from existing on-disk artifacts (no tool execution)."""
    generated_at = generated_at or datetime.now()
    specs = _load_sources()
    loaded = load_sources(specs, min_mtime=min_mtime)
    return render_report(
        loaded, generated_at=generated_at, run_problems=run_problems
    )


# ===========================================================================
# Orchestration layer — run the live tools, then compile.
# ===========================================================================
#
# `qsa ccoption` (no flags) refreshes the inputs by running each tool, then
# compiles the result. Before each tool we look for an already-running instance
# (and, for cc2, a running MDC — cc2 fail-fasts on the MDC lock). If something
# is running we back off and retry; after RETRY_LIMIT attempts we give up,
# write the report with a failure banner, and exit non-zero.

import subprocess  # noqa: E402  (kept with the orchestration block it serves)
import time  # noqa: E402

RETRY_LIMIT = 3
BACKOFF_SECONDS = 30
QUIESCE_SECONDS = 5
TOOL_TIMEOUT_SECONDS = 900

# Process signatures — the venv console-script path each tool runs under. These
# are specific enough that they never collide with QSA itself, and our own
# (sequential, awaited) child processes have exited before the next pre-check.
PROC_PATTERNS: dict[str, str] = {
    "iraguard": "/repos/iraguard/.venv/bin/iraguard",
    "cc2": "/repos/cc2/.venv/bin/cc2",
    "mdc": "/repos/mdc/.venv/bin/mdc",
}

TOOL_BIN: dict[str, Path] = {
    "iraguard": Path("/home/johnh/repos/iraguard/.venv/bin/iraguard"),
    "cc2": Path("/home/johnh/repos/cc2/.venv/bin/cc2"),
}


@dataclass(frozen=True)
class ToolStep:
    label: str            # human label, e.g. "iraguard run"
    tool: str             # key into TOOL_BIN
    args: tuple[str, ...]  # subcommand + flags
    precheck: tuple[str, ...]  # PROC_PATTERNS keys to wait on before launching


STEPS: tuple[ToolStep, ...] = (
    ToolStep("iraguard run", "iraguard", ("run",), ("iraguard",)),
    ToolStep("iraguard ccoptions", "iraguard", ("ccoptions",), ("iraguard",)),
    ToolStep("iraguard standing", "iraguard", ("standing",), ("iraguard",)),
    # cc2 fail-fasts on a live MDC lock, so we wait out MDC too.
    ToolStep("cc2 scan", "cc2", ("scan",), ("cc2", "mdc")),
)


@dataclass
class StepResult:
    label: str
    ok: bool
    error: str | None = None


def _process_running(pattern: str) -> bool:
    """True iff a live process' command line contains `pattern` (via pgrep -f)."""
    try:
        r = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        # If we can't even run pgrep, assume clear rather than wedging forever.
        return False
    return r.returncode == 0 and bool(r.stdout.strip())


def wait_for_clear(
    keys: tuple[str, ...],
    *,
    attempts: int = RETRY_LIMIT,
    backoff: float = BACKOFF_SECONDS,
    is_running=_process_running,
    sleep_fn=time.sleep,
    log=lambda m: None,
) -> str | None:
    """Block until none of `keys` is running. Returns None if clear, else an
    error string after `attempts` exhausted."""
    for attempt in range(1, attempts + 1):
        busy = [k for k in keys if is_running(PROC_PATTERNS[k])]
        if not busy:
            return None
        if attempt < attempts:
            log(
                f"  waiting: {', '.join(busy)} running "
                f"(attempt {attempt}/{attempts}); backing off {backoff:.0f}s"
            )
            sleep_fn(backoff)
    busy = [k for k in keys if is_running(PROC_PATTERNS[k])]
    if not busy:
        return None
    return (
        f"{', '.join(busy)} still running after {attempts} attempts "
        f"({backoff:.0f}s apart)"
    )


def _exec_tool(step: ToolStep) -> StepResult:
    """Run one tool step (precheck already passed). Captures exit status."""
    binary = TOOL_BIN[step.tool]
    cwd = binary.parent.parent.parent  # /home/johnh/repos/<tool>
    try:
        r = subprocess.run(
            [str(binary), *step.args],
            cwd=str(cwd),
            capture_output=True, text=True,
            timeout=TOOL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return StepResult(step.label, False,
                          f"{step.label}: timed out after {TOOL_TIMEOUT_SECONDS}s")
    except OSError as exc:
        return StepResult(step.label, False, f"{step.label}: failed to launch — {exc}")
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-3:]
        detail = " / ".join(tail) if tail else "no output"
        return StepResult(step.label, False,
                          f"{step.label}: exit {r.returncode} — {detail}")
    return StepResult(step.label, True)


def run_pipeline(
    steps: tuple[ToolStep, ...] = STEPS,
    *,
    wait_fn=wait_for_clear,
    exec_fn=_exec_tool,
    log=lambda m: None,
) -> list[StepResult]:
    """Run each step in order: wait for a clear process slot, then execute.

    A step that can't get a clear slot, or that exits non-zero, is recorded as
    a failure but does NOT stop later steps — we still try to refresh whatever
    we can, and the banner reports every failure together.
    """
    results: list[StepResult] = []
    for step in steps:
        log(f"{step.label}: checking for running {', '.join(step.precheck)}…")
        err = wait_fn(step.precheck, log=log)
        if err is not None:
            log(f"  ✗ {err}")
            results.append(StepResult(step.label, False, f"{step.label}: {err}"))
            continue
        log(f"  running {step.label}…")
        res = exec_fn(step)
        log(f"  {'✓' if res.ok else '✗'} {step.label}"
            + ("" if res.ok else f" — {res.error}"))
        results.append(res)
    return results


def build_report_live(
    *,
    generated_at: datetime | None = None,
    pipeline_fn=run_pipeline,
    sleep_fn=time.sleep,
    log=lambda m: None,
) -> tuple[str, list[str]]:
    """Full path: refresh inputs by running the tools, then compile.

    Freshness assertion: artifacts older than the moment we started running are
    treated as stale (the step that should have refreshed them failed silently).
    """
    generated_at = generated_at or datetime.now()
    run_started = datetime.now()
    results = pipeline_fn(log=log)
    run_problems = [r.error for r in results if not r.ok and r.error]

    log(f"quiescing {QUIESCE_SECONDS}s before reading artifacts…")
    sleep_fn(QUIESCE_SECONDS)

    return build_report(
        generated_at=generated_at,
        min_mtime=run_started,
        run_problems=run_problems,
    )
