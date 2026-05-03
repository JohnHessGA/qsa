"""R003 — Missing symbols where a symbol is expected.

Some tables ship rows where the symbol column is NULL/empty. For
`secapi_regulatory_penalties` this happens because penalty rows aren't being
linked to the entity ticker — the canonical symbol-link bug. Reported per
table with severity tied to whether a symbol is logically required.
"""

from __future__ import annotations

from typing import Any

from qsa.finding import Finding

# (database, schema, table, symbol_col, severity, note)
TARGETS: list[tuple[str, str, str, str, str, str]] = [
    ("masd", "masd", "secapi_regulatory_penalties",   "symbol", "critical",
     "Penalties without a symbol cannot drive per-stock signals."),
    ("masd", "masd", "secapi_regulatory_enforcement", "symbol", "warning",
     "Enforcement rows sometimes target individuals; not always linkable to a ticker."),
    ("shdb", "shdb", "sec_penalties",                 "symbol", "critical",
     "Curated penalties inherit the MASD link gap."),
    ("shdb", "shdb", "sec_enforcement",               "symbol", "warning",
     "Curated enforcement; same as MASD — individuals not linkable."),
    ("masd", "masd", "sec_edgar_filing_events",       "ticker_derived", "warning",
     "Filings without a derived ticker still have a CIK; the curated event_filing layer can resolve."),
]


def _connection_for(db: str, masd, shdb, mefdb):
    return {"masd": masd, "shdb": shdb, "mefdb": mefdb}[db]


def check(*, masd, shdb, mefdb, app_cfg: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []

    for db, schema, table, col, severity, note in TARGETS:
        conn = _connection_for(db, masd, shdb, mefdb)
        sql = f"""
            SELECT
              COUNT(*) FILTER (WHERE {col} IS NULL OR {col} = '')   AS missing,
              COUNT(*)                                              AS total
            FROM {schema}.{table};
        """
        with conn.cursor() as cur:
            cur.execute(sql)
            missing, total = cur.fetchone()

        if not missing:
            continue

        pct = (missing / total * 100.0) if total else 0.0
        # Severity escalates if 100% are missing (the SEC penalties pathology).
        eff_severity = "critical" if pct == 100.0 else severity

        findings.append(Finding(
            rule_id="R003-missing-symbols",
            severity=eff_severity,
            database=db,
            table=f"{schema}.{table}",
            summary=f"{missing:,}/{total:,} ({pct:.1f}%) rows with missing {col}",
            detail=(f"{note}\n\nRows missing {col}: {missing:,} of {total:,} ({pct:.1f}%)."),
            affected_rows=missing,
            recommendation=(
                "Investigate whether company_name / CIK / URL fields in the source can be "
                "resolved to a ticker (via dim_security or symbol_master) and add a "
                "resolution step in MDC or UDC. Until then, mark such rows as unmapped "
                "rather than silently surfacing them as actionable."
            ),
        ))

    return findings
