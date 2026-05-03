"""Consumer-grep — find live consumers of deprecated tables across AFT repos.

Walks each repo in `consumer_grep_repos`, runs a recursive grep for the
deprecated table name (only against .py / .sql / .yaml files), and returns
hits as Findings keyed by file path.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from qsa.finding import Finding


_VALID_SUFFIXES = (".py", ".sql", ".yaml", ".yml", ".md")


def _expand(path: str) -> Path:
    return Path(os.path.expanduser(path)).resolve()


def _grep(repo: Path, term: str) -> list[tuple[Path, int, str]]:
    """Return list of (file, line_no, line_text) hits, excluding venvs/.git."""
    if not repo.exists():
        return []
    hits: list[tuple[Path, int, str]] = []
    # Use rg if available; fall back to plain walk + regex.
    try:
        out = subprocess.run(
            ["rg", "--no-heading", "--line-number", "--with-filename",
             "-g", "!.venv", "-g", "!venv", "-g", "!__pycache__",
             "-g", "*.py", "-g", "*.sql", "-g", "*.yaml", "-g", "*.yml", "-g", "*.md",
             "-F", term, str(repo)],
            capture_output=True, text=True, timeout=20,
        )
        if out.returncode in (0, 1):
            for line in out.stdout.splitlines():
                parts = line.split(":", 2)
                if len(parts) == 3:
                    hits.append((Path(parts[0]), int(parts[1]), parts[2]))
            return hits
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: walk the tree manually.
    needle = re.compile(re.escape(term))
    for root, dirs, files in os.walk(repo):
        # Prune unwanted dirs in place.
        dirs[:] = [d for d in dirs if d not in {".git", ".venv", "venv", "__pycache__", "node_modules"}]
        for fname in files:
            if not fname.endswith(_VALID_SUFFIXES):
                continue
            p = Path(root) / fname
            try:
                with p.open("r", errors="ignore") as f:
                    for i, line in enumerate(f, start=1):
                        if needle.search(line):
                            hits.append((p, i, line.rstrip()))
            except OSError:
                continue
    return hits


def find_consumers(app_cfg: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []

    for entry in app_cfg["deprecated_tables"]:
        schema = entry["schema"]
        table = entry["table"]
        replacement = entry.get("replacement", "(none)")
        term = table  # bare table name catches FROM x, JOIN x, "x", etc.

        all_hits: list[tuple[Path, int, str]] = []
        scanned: list[str] = []
        for repo in app_cfg["consumer_grep_repos"]:
            repo_path = _expand(repo)
            scanned.append(str(repo_path))
            all_hits.extend(_grep(repo_path, term))

        # Filter out hits inside the qsa repo itself (self-references in this
        # tool's config don't count as live consumers).
        qsa_root = Path(__file__).resolve().parents[2]
        all_hits = [h for h in all_hits if qsa_root not in h[0].parents]

        if not all_hits:
            findings.append(Finding(
                rule_id="R007-deprecated-tables",
                severity="info",
                database="fs",
                table=f"{schema}.{table}",
                summary=f"No live consumers of deprecated {schema}.{table} found",
                detail=(
                    f"Scanned {len(scanned)} repos: {', '.join(scanned)}.\n"
                    f"Searched for the bare term `{term}` in *.py, *.sql, *.yaml, *.yml, *.md files."
                ),
            ))
            continue

        # Group by file
        by_file: dict[Path, list[tuple[int, str]]] = {}
        for path, lineno, text in all_hits:
            by_file.setdefault(path, []).append((lineno, text))

        sample = []
        for path, lines in sorted(by_file.items()):
            for lineno, text in lines[:3]:
                sample.append({
                    "file": str(path),
                    "line": lineno,
                    "text": text.strip()[:160],
                })

        findings.append(Finding(
            rule_id="R007-deprecated-tables",
            severity="warning",
            database="fs",
            table=f"{schema}.{table}",
            summary=f"{len(all_hits)} reference(s) to deprecated {schema}.{table} in {len(by_file)} file(s)",
            detail=(
                f"Scanned {len(scanned)} repos.\n"
                f"Preferred replacement: {replacement}\n\n"
                "Each match is a literal occurrence of the bare table name. Some hits will be "
                "deprecation notes / READMEs (which is fine); only code/SQL hits are live consumers."
            ),
            affected_rows=len(all_hits),
            sample=sample,
            recommendation=(
                f"Migrate live code/SQL consumers to {replacement}. Comment-only hits "
                "(READMEs, notes, this audit) are not action items."
            ),
        ))

    return findings
