"""R003 — Missing symbols where a symbol is expected.

Some tables ship rows where the symbol column is NULL/empty. For SEC API
enforcement and penalty tables, that's mostly STRUCTURAL: SEC enforcement
actions are routinely brought against individuals, private LLCs, mutual
funds, and other non-tradable entities — those rows correctly have NULL
symbol because no public ticker exists.

The rule treats `entity_type` as the disambiguator. When the column is
present (the SEC API tables have it as of migration 029, 2026-05-03 +
reprocess), only rows whose `entity_type` is `company` (or NULL/unknown)
count as "actionable missing-symbol" findings. Rows tagged `individual`,
`fund`, `agency`, `system`, `other`, etc., are intentionally excluded —
they are correct-by-design and shouldn't drive a data-defect alert.

For tables without an `entity_type` column the rule falls back to the
old behaviour (count any NULL symbol), but reports under a softer
severity and labels the finding as a structural-vs-actionable mix that
needs UDC follow-up to surface the entity context.
"""

from __future__ import annotations

from typing import Any

from qsa.finding import Finding


# Entity-type values that are NOT publicly-tradable. Rows tagged this way
# correctly have NULL symbol; the rule does not count them as defects.
NON_MAPPABLE_ENTITY_TYPES = ("individual", "private", "fund", "agency", "system", "other")


# (database, schema, table, symbol_col, severity, note)
TARGETS: list[tuple[str, str, str, str, str, str]] = [
    ("masd", "masd", "secapi_regulatory_penalties",   "symbol", "warning",
     "Penalties target individuals/private LLCs; only company rows are actionable."),
    ("masd", "masd", "secapi_regulatory_enforcement", "symbol", "warning",
     "Enforcement targets individuals/private LLCs; only company rows are actionable."),
    ("shdb", "shdb", "sec_penalties",                 "symbol", "warning",
     "Curated penalties; entity_type filter applied if column present."),
    ("shdb", "shdb", "sec_enforcement",               "symbol", "warning",
     "Curated enforcement; entity_type filter applied if column present."),
    ("masd", "masd", "sec_edgar_filing_events",       "ticker_derived", "warning",
     "Filings without ticker_derived have a CIK; resolver covers ~3K. Most "
     "remaining NULLs are non-equity issuers."),
]


def _connection_for(db: str, masd, shdb, mefdb):
    return {"masd": masd, "shdb": shdb, "mefdb": mefdb}[db]


def _has_column(conn, schema: str, table: str, column: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name=%s AND column_name=%s",
            (schema, table, column),
        )
        return cur.fetchone() is not None


def check(*, masd, shdb, mefdb, app_cfg: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []

    for db, schema, table, col, severity, note in TARGETS:
        conn = _connection_for(db, masd, shdb, mefdb)

        # Decide whether to apply the entity_type filter. Probe the live
        # schema rather than hard-coding which tables have the column —
        # robust to UDC catching up later on `sec_penalties`.
        has_entity_type = _has_column(conn, schema, table, "entity_type")

        if has_entity_type:
            # Count three buckets:
            #   - missing_total   : every row where the symbol column is NULL/empty.
            #   - missing_actionable : a subset where entity_type IS NULL or 'company'.
            #     These are the rows where a symbol should plausibly exist.
            #   - missing_structural : the rest (individuals, private firms, funds,
            #     agencies, etc.) — correctly NULL by design.
            non_mappable_list = ", ".join(f"'{t}'" for t in NON_MAPPABLE_ENTITY_TYPES)
            sql = f"""
                SELECT
                    COUNT(*) FILTER (WHERE {col} IS NULL OR {col} = '')                AS missing_total,
                    COUNT(*) FILTER (WHERE ({col} IS NULL OR {col} = '')
                                       AND (entity_type IS NULL
                                            OR entity_type = 'company'
                                            OR entity_type = ''))                       AS missing_actionable,
                    COUNT(*) FILTER (WHERE ({col} IS NULL OR {col} = '')
                                       AND entity_type IN ({non_mappable_list}))        AS missing_structural,
                    COUNT(*)                                                            AS total
                FROM {schema}.{table};
            """
            with conn.cursor() as cur:
                cur.execute(sql)
                missing_total, missing_actionable, missing_structural, total = cur.fetchone()
        else:
            sql = f"""
                SELECT
                    COUNT(*) FILTER (WHERE {col} IS NULL OR {col} = '')   AS missing_total,
                    COUNT(*)                                              AS total
                FROM {schema}.{table};
            """
            with conn.cursor() as cur:
                cur.execute(sql)
                missing_total, total = cur.fetchone()
            missing_actionable = missing_total
            missing_structural = 0

        # No actionable missing symbols → no finding.
        if not missing_actionable:
            continue

        pct_actionable = (missing_actionable / total * 100.0) if total else 0.0
        # Severity is now driven by the *actionable* share, not the total.
        if pct_actionable == 100.0:
            eff_severity = "critical"
        elif pct_actionable >= 50.0:
            eff_severity = severity
        else:
            eff_severity = "info"

        if has_entity_type:
            detail = (
                f"{note}\n\n"
                f"Total rows: {total:,}\n"
                f"NULL {col}: {missing_total:,} ({(missing_total / total * 100.0 if total else 0):.1f}%)\n"
                f"  • of which structurally correct (individuals / funds / private / "
                f"agencies / system / other): {missing_structural:,}\n"
                f"  • of which actionable (entity_type=company or unknown): "
                f"{missing_actionable:,} ({pct_actionable:.1f}% of total)"
            )
        else:
            detail = (
                f"{note}\n\n"
                f"NULL {col}: {missing_total:,} of {total:,} "
                f"({(missing_total / total * 100.0 if total else 0):.1f}%). "
                f"Table has no `entity_type` column to disambiguate; UDC follow-up needed "
                f"to surface entity context here."
            )

        findings.append(Finding(
            rule_id="R003-missing-symbols",
            severity=eff_severity,
            database=db,
            table=f"{schema}.{table}",
            summary=(
                f"{missing_actionable:,}/{total:,} ({pct_actionable:.1f}%) actionable "
                f"missing {col}"
                + (f"; {missing_structural:,} structurally NULL"
                   if has_entity_type and missing_structural else "")
            ),
            detail=detail,
            affected_rows=missing_actionable,
            recommendation=(
                "Investigate whether company_name / CIK / URL fields can be resolved to "
                "a ticker (via dim_security / symbol_master / CikTickerResolver). For "
                "rows the resolver leaves NULL, the SEC API entity_type tag explains why "
                "(individual, private, fund, etc.) — UDC consumers should filter "
                "`entity_type='company' AND symbol IS NOT NULL` for per-symbol equity signals."
            ),
        ))

    return findings
