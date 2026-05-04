"""R003 — Missing symbols where a symbol is expected.

Some tables ship rows where the symbol column is NULL/empty. For SEC API
enforcement and penalty tables, that's mostly STRUCTURAL: SEC enforcement
actions are routinely brought against individuals, private LLCs, mutual
funds, and other non-tradable entities — those rows correctly have NULL
symbol because no public ticker exists.

The rule supports three increasingly-aware classifiers and probes the
live schema to pick the most informative one available:

  1. **filer_type / ticker_mapping_status (sec_edgar)**.
     Migration 031 (2026-05-03) added these columns. Form 4 / 4-A
     filings are tagged `filer_type='person'` (the cik refers to an
     insider, not a company). 8-K and SCHEDULE 13D/G filings are tagged
     `public_company` or `subject_company`. Status further classifies
     the NULL ticker reason: `non_equity_filer` (structural),
     `delisted_or_unmapped` and `ambiguous` (monitor), `unknown`
     (genuinely actionable).

  2. **entity_type (sec_api)**.
     Migration 029 (2026-05-03) added this on penalties; enforcement
     already had it. Values: `company` (actionable when symbol NULL),
     `individual` / `fund` / `agency` / `system` / `other` / `private`
     (structural).

  3. **Legacy fallback**.
     Tables without either column report all NULLs as actionable
     (softer severity), with a UDC-follow-up note in the detail.

Output severity is driven by the *actionable* share, not the total NULL
count. A finding fires only when there's at least one actionable row OR
a non-trivial monitor-bucket population worth surfacing.
"""

from __future__ import annotations

from typing import Any

from qsa.finding import Finding


# Entity-type values that are NOT publicly-tradable (SEC API).
NON_MAPPABLE_ENTITY_TYPES = ("individual", "private", "fund", "agency", "system", "other")

# Mapping-status values on sec_edgar that mean "structurally NULL" — no
# action needed; the parser correctly couldn't produce a ticker.
SEC_EDGAR_STRUCTURAL_STATUSES = ("non_equity_filer",)

# Mapping-status values that are noteworthy but not active defects.
SEC_EDGAR_MONITOR_STATUSES = ("delisted_or_unmapped", "ambiguous")


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
     "EDGAR filings; filer_type + ticker_mapping_status disambiguate "
     "Form 4 (insider) from public-company filings."),
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


def _query_filer_type_buckets(conn, schema: str, table: str, col: str):
    """Return (missing_total, actionable, structural, monitor, total).

    Used when the table carries `filer_type` and `ticker_mapping_status`
    (introduced for sec_edgar_filing_events by migration 031).

    Bucketing of NULL-ticker rows:
      - structural : filer_type='person' OR
                     ticker_mapping_status IN structural-set
      - monitor    : ticker_mapping_status IN monitor-set
      - actionable : everything else (filer_type=public/subject/unknown
                     AND status NOT IN structural ∪ monitor)
    """
    structural_set = ", ".join(f"'{s}'" for s in SEC_EDGAR_STRUCTURAL_STATUSES)
    monitor_set = ", ".join(f"'{s}'" for s in SEC_EDGAR_MONITOR_STATUSES)
    sql = f"""
        WITH classified AS (
            SELECT
                {col} AS sym,
                CASE
                    WHEN filer_type = 'person'
                         OR ticker_mapping_status IN ({structural_set})
                        THEN 'structural'
                    WHEN ticker_mapping_status IN ({monitor_set})
                        THEN 'monitor'
                    ELSE 'actionable'
                END AS bucket
            FROM {schema}.{table}
        )
        SELECT
            COUNT(*) FILTER (WHERE sym IS NULL OR sym = '')                                AS missing_total,
            COUNT(*) FILTER (WHERE (sym IS NULL OR sym = '') AND bucket = 'actionable')    AS missing_actionable,
            COUNT(*) FILTER (WHERE (sym IS NULL OR sym = '') AND bucket = 'structural')    AS missing_structural,
            COUNT(*) FILTER (WHERE (sym IS NULL OR sym = '') AND bucket = 'monitor')       AS missing_monitor,
            COUNT(*)                                                                       AS total
        FROM classified;
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()


def _query_entity_type_buckets(conn, schema: str, table: str, col: str):
    """Return (missing_total, actionable, structural, total).

    Used when the table carries `entity_type` (SEC API tables).
    """
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
        return cur.fetchone()


def _query_legacy_buckets(conn, schema: str, table: str, col: str):
    """Return (missing_total, total). All NULLs are treated as actionable."""
    sql = f"""
        SELECT
            COUNT(*) FILTER (WHERE {col} IS NULL OR {col} = '')   AS missing_total,
            COUNT(*)                                              AS total
        FROM {schema}.{table};
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()


def _classifier_for(conn, schema: str, table: str) -> str:
    """Pick the richest classifier the table supports — runtime probe so
    the rule auto-tracks schema changes (UDC catching up to migration
    029, etc.). Order: filer_type > entity_type > legacy."""
    if _has_column(conn, schema, table, "filer_type"):
        return "filer_type"
    if _has_column(conn, schema, table, "entity_type"):
        return "entity_type"
    return "legacy"


def _severity_for(actionable_pct: float, default_severity: str) -> str:
    """Severity is driven by the *actionable* share, never by the total."""
    if actionable_pct >= 100.0:
        return "critical"
    if actionable_pct >= 50.0:
        return default_severity
    return "info"


def check(*, masd, shdb, mefdb, app_cfg: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []

    for db, schema, table, col, severity, note in TARGETS:
        conn = _connection_for(db, masd, shdb, mefdb)
        classifier = _classifier_for(conn, schema, table)

        missing_monitor = 0  # Only filer_type classifier produces a monitor bucket.

        if classifier == "filer_type":
            missing_total, missing_actionable, missing_structural, missing_monitor, total = \
                _query_filer_type_buckets(conn, schema, table, col)
        elif classifier == "entity_type":
            missing_total, missing_actionable, missing_structural, total = \
                _query_entity_type_buckets(conn, schema, table, col)
        else:
            missing_total, total = _query_legacy_buckets(conn, schema, table, col)
            missing_actionable = missing_total
            missing_structural = 0

        # Suppress the finding entirely when there is literally nothing
        # interesting to report. With the filer_type classifier on
        # sec_edgar, the actionable share will commonly be zero — but if
        # there is a non-trivial monitor population we still emit an
        # info-level finding so consumers see the breakdown.
        if not missing_actionable and not (classifier == "filer_type" and missing_monitor):
            continue

        pct_actionable = (missing_actionable / total * 100.0) if total else 0.0
        eff_severity = _severity_for(pct_actionable, severity)

        # When ONLY monitor rows remain (sec_edgar typical post-cleanup),
        # the finding is informational, not actionable.
        if not missing_actionable and missing_monitor:
            eff_severity = "info"

        if classifier == "filer_type":
            pct_struct = (missing_structural / total * 100.0) if total else 0.0
            pct_monitor = (missing_monitor / total * 100.0) if total else 0.0
            detail = (
                f"{note}\n\n"
                f"Total rows: {total:,}\n"
                f"NULL {col}: {missing_total:,} "
                f"({(missing_total / total * 100.0 if total else 0):.1f}%)\n"
                f"  • Structural   (filer_type=person OR status=non_equity_filer): "
                f"{missing_structural:,} ({pct_struct:.1f}%)\n"
                f"  • Monitor      (status=delisted_or_unmapped, ambiguous): "
                f"{missing_monitor:,} ({pct_monitor:.1f}%)\n"
                f"  • Actionable   (genuine missing-symbol; should have resolved): "
                f"{missing_actionable:,} ({pct_actionable:.1f}%)"
            )
            summary = (
                f"actionable: {missing_actionable:,} | "
                f"monitor: {missing_monitor:,} (delisted+ambiguous) | "
                f"structural: {missing_structural:,} (Form 4 / non-equity)"
            )
            recommendation = (
                "Form 4 / 4-A filings have filer_type=person — the cik refers "
                "to an insider, not a tradable entity. Those NULLs are correct. "
                "delisted_or_unmapped and ambiguous rows are visible but not "
                "active defects. Genuinely actionable rows (status=unknown or "
                "filer_type=unknown with NULL ticker) are rare; investigate "
                "those individually."
            )
        elif classifier == "entity_type":
            pct_struct = (missing_structural / total * 100.0) if total else 0.0
            detail = (
                f"{note}\n\n"
                f"Total rows: {total:,}\n"
                f"NULL {col}: {missing_total:,} "
                f"({(missing_total / total * 100.0 if total else 0):.1f}%)\n"
                f"  • of which structurally correct (individuals / funds / private / "
                f"agencies / system / other): {missing_structural:,} ({pct_struct:.1f}%)\n"
                f"  • of which actionable (entity_type=company or unknown): "
                f"{missing_actionable:,} ({pct_actionable:.1f}% of total)"
            )
            summary = (
                f"{missing_actionable:,}/{total:,} ({pct_actionable:.1f}%) actionable "
                f"missing {col}"
                + (f"; {missing_structural:,} structurally NULL"
                   if missing_structural else "")
            )
            recommendation = (
                "Investigate whether company_name / CIK fields can be resolved to "
                "a ticker. Rows the resolver leaves NULL are explained by "
                "entity_type — UDC consumers should filter "
                "`entity_type='company' AND symbol IS NOT NULL` for per-symbol "
                "equity signals."
            )
        else:
            detail = (
                f"{note}\n\n"
                f"NULL {col}: {missing_total:,} of {total:,} "
                f"({(missing_total / total * 100.0 if total else 0):.1f}%). "
                f"Table has no entity_type / filer_type column to disambiguate; "
                f"UDC follow-up needed to surface entity context here."
            )
            summary = (
                f"{missing_actionable:,}/{total:,} ({pct_actionable:.1f}%) actionable "
                f"missing {col}"
            )
            recommendation = (
                "Add an entity_type or filer_type column at the producing layer "
                "(MDC ingest or UDC curation) so this finding can distinguish "
                "structural NULLs from actionable ones. Until then every NULL is "
                "treated as actionable, which inflates this finding."
            )

        findings.append(Finding(
            rule_id="R003-missing-symbols",
            severity=eff_severity,
            database=db,
            table=f"{schema}.{table}",
            summary=summary,
            detail=detail,
            affected_rows=missing_actionable,
            recommendation=recommendation,
        ))

    return findings
