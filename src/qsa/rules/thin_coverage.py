"""R009 — Thin source coverage.

Where a table-level distinct-symbol count is unexpectedly small, flag the
table for follow-up. Specifically targets analyst_grades / price_targets
which today cover ~20 symbols total — a known coverage gap.

Compares MASD source row counts against SHDB curated row counts so the user
can see whether SHDB is filtering data out or whether MASD is the bottleneck.
"""

from __future__ import annotations

from typing import Any

from qsa.finding import Finding

# (label, masd_table, shdb_table, masd_sym_col, shdb_sym_col)
PAIRS: list[tuple[str, str, str, str, str]] = [
    ("analyst-grades",       "fmp_stocks_analyst_grades",   "analyst_grades",
                             "symbol", "symbol"),
    ("analyst-price-targets","fmp_stocks_price_targets_1d", "analyst_price_targets_1d",
                             "symbol", "symbol"),
]


def check(*, masd, shdb, mefdb, app_cfg: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []

    for label, m_tbl, s_tbl, m_col, s_col in PAIRS:
        with masd.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*), COUNT(DISTINCT {m_col}) FROM masd.{m_tbl};"
            )
            m_rows, m_syms = cur.fetchone()

        with shdb.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*), COUNT(DISTINCT {s_col}) FROM shdb.{s_tbl};"
            )
            s_rows, s_syms = cur.fetchone()

        # Anything below 100 distinct symbols on a "broad" stream is thin.
        if m_syms >= 100 and s_syms >= 100:
            continue

        delta_rows = m_rows - s_rows
        delta_syms = m_syms - s_syms

        findings.append(Finding(
            rule_id="R009-thin-coverage",
            severity="warning",
            database="shdb",
            table=f"shdb.{s_tbl}",
            summary=f"{label}: thin coverage — MASD {m_syms} sym / SHDB {s_syms} sym",
            detail=(
                f"MASD masd.{m_tbl}: {m_rows:,} rows / {m_syms:,} distinct {m_col}.\n"
                f"SHDB shdb.{s_tbl}: {s_rows:,} rows / {s_syms:,} distinct {s_col}.\n"
                f"Delta: {delta_rows:,} rows, {delta_syms:,} symbols.\n\n"
                "A near-equal MASD↔SHDB count means the bottleneck is upstream (API "
                "entitlement, rate-limited collection). A large drop from MASD to SHDB "
                "means a curation builder is filtering data out."
            ),
            affected_symbols=305 - s_syms,
            recommendation=(
                "Determine whether this is a source limitation (API plan, free-tier cap), "
                "a symbol-mapping issue (curation step rejects rows that don't resolve to "
                "symbol_master), or a date-window issue (refresh cadence too tight). "
                "If source-limited: document and exclude from hard gates until fixed."
            ),
        ))

    return findings
