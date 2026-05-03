"""R002 — Future-dated rows where future dates are impossible.

Insider/congress transaction dates and filing dates cannot be in the future.
News publish timestamps cannot be more than `future_date_tolerance_days`
ahead of now (allows for clock skew on UTC->local conversions).
"""

from __future__ import annotations

from typing import Any

from qsa.finding import Finding

# (database, schema, table, date_col, severity, kind)
TARGETS: list[tuple[str, str, str, str, str, str]] = [
    ("masd", "masd", "fmp_stocks_insider_trades",  "bar_date",         "critical", "date"),
    ("masd", "masd", "fmp_stocks_insider_trades",  "transaction_date", "critical", "date"),
    ("masd", "masd", "finnhub_stocks_insider_txn", "transaction_date", "critical", "date"),
    ("masd", "masd", "finnhub_stocks_insider_txn", "filing_date",      "critical", "date"),
    ("masd", "masd", "fmp_congress_house_trades",  "transaction_date", "warning",  "date"),
    ("masd", "masd", "fmp_congress_senate_trades", "transaction_date", "warning",  "date"),
    ("shdb", "shdb", "insider_trades",             "bar_date",         "critical", "date"),
    ("shdb", "shdb", "congress_trades",            "transaction_date", "warning",  "date"),
]


def _connection_for(db: str, masd, shdb, mefdb):
    return {"masd": masd, "shdb": shdb, "mefdb": mefdb}[db]


def _column_exists(conn, schema: str, table: str, column: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name=%s AND column_name=%s",
            (schema, table, column),
        )
        return cur.fetchone() is not None


def check(*, masd, shdb, mefdb, app_cfg: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    tol_days = app_cfg["future_date_tolerance_days"]

    for db, schema, table, col, severity, _kind in TARGETS:
        conn = _connection_for(db, masd, shdb, mefdb)
        if not _column_exists(conn, schema, table, col):
            continue

        sql = f"""
            SELECT COUNT(*) AS n,
                   MAX({col})::text AS max_d,
                   COUNT(DISTINCT {col}) AS distinct_dates
            FROM {schema}.{table}
            WHERE {col} > CURRENT_DATE + INTERVAL '{int(tol_days)} days';
        """
        with conn.cursor() as cur:
            cur.execute(sql)
            n, max_d, distinct_dates = cur.fetchone()

        if not n:
            continue

        sample_sql = f"""
            SELECT {col}::text AS d, COUNT(*) AS n
            FROM {schema}.{table}
            WHERE {col} > CURRENT_DATE + INTERVAL '{int(tol_days)} days'
            GROUP BY 1 ORDER BY 1 DESC LIMIT 5;
        """
        with conn.cursor() as cur:
            cur.execute(sample_sql)
            sample = [{"date": r[0], "rows": r[1]} for r in cur.fetchall()]

        findings.append(Finding(
            rule_id="R002-future-dates",
            severity=severity,
            database=db,
            table=f"{schema}.{table}",
            summary=f"{n:,} row(s) with future-dated {col} (max={max_d})",
            detail=(
                f"{n:,} rows in {schema}.{table} have {col} more than "
                f"{tol_days} day(s) in the future (across {distinct_dates} distinct date(s))."
            ),
            affected_rows=n,
            sample=sample,
            recommendation=(
                "Add ingest validation rejecting rows with future-dated transaction/filing/bar "
                "columns. Existing bad rows should be quarantined in a later phase."
            ),
        ))

    return findings
