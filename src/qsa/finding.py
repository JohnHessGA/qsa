"""Finding dataclass — the unit of audit output.

Every rule produces zero or more Findings. The reporter groups them by
severity and renders them to Markdown / CSV.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str            # "critical" | "warning" | "info"
    database: str            # "masd" | "shdb" | "mefdb" | "fs"
    table: str               # e.g. "shdb.insider_activity_signals" or "" for cross-table
    summary: str             # one-line title
    detail: str = ""         # multi-line description / sample values
    affected_rows: int | None = None
    affected_symbols: int | None = None
    sample: list[Any] = field(default_factory=list)
    recommendation: str = ""

    def sort_key(self) -> tuple:
        return (SEVERITY_ORDER.get(self.severity, 9), self.database, self.table, self.rule_id)
