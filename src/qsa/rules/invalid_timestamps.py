"""R001 — Invalid / impossible timestamps.

Targets timestamp columns on news/article tables. Anything before
`min_valid_date` (default 2000-01-01) or NULL where the column is the only
date evidence is flagged. The Finnhub `0001-12-31 BC` case is the canonical
example.

Detection uses EXTRACT(year FROM ...) so the bad row never has to be
materialised as a Python datetime (psycopg2 chokes on BC dates).
"""

from __future__ import annotations

from typing import Any

from qsa.finding import Finding

# (database, schema, table, ts_column, severity)
TARGETS: list[tuple[str, str, str, str, str]] = [
    ("masd",  "masd",  "finnhub_news_articles",            "published_at_utc", "critical"),
    ("masd",  "masd",  "alphavantage_news_sentiment_1d",   "time_published",   "warning"),
    ("masd",  "masd",  "marketaux_news_articles_1d",       "published_at",     "warning"),
    ("masd",  "masd",  "massive_stocks_news_1d",           "published_utc",    "warning"),
    ("shdb",  "shdb",  "news_av_sentiment_1d",             "time_published",   "warning"),
    ("shdb",  "shdb",  "news_mx_articles_1d",              "published_at",     "warning"),
]


def _connection_for(db: str, masd, shdb, mefdb):
    return {"masd": masd, "shdb": shdb, "mefdb": mefdb}[db]


def check(*, masd, shdb, mefdb, app_cfg: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    min_valid = app_cfg["min_valid_date"]

    for db, schema, table, col, severity in TARGETS:
        conn = _connection_for(db, masd, shdb, mefdb)
        # EXTRACT(year ...) avoids BC datetime materialisation.
        sql = f"""
            SELECT
              COUNT(*) FILTER (WHERE {col} IS NULL) AS null_count,
              COUNT(*) FILTER (
                WHERE {col} IS NOT NULL
                  AND EXTRACT(year FROM {col}) < EXTRACT(year FROM DATE %s)
              ) AS pre_min_count,
              COUNT(*) AS total_rows
            FROM {schema}.{table};
        """
        with conn.cursor() as cur:
            cur.execute(sql, (min_valid,))
            null_count, pre_min, total = cur.fetchone()

        if pre_min == 0 and null_count == 0:
            continue

        bad = (pre_min or 0) + (null_count or 0)
        sample_sql = f"""
            SELECT EXTRACT(year FROM {col})::int AS yr, COUNT(*) AS n
            FROM {schema}.{table}
            WHERE {col} IS NOT NULL
              AND EXTRACT(year FROM {col}) < EXTRACT(year FROM DATE %s)
            GROUP BY 1 ORDER BY 1 LIMIT 5;
        """
        with conn.cursor() as cur:
            cur.execute(sample_sql, (min_valid,))
            sample = [{"year": r[0], "rows": r[1]} for r in cur.fetchall()]

        findings.append(Finding(
            rule_id="R001-invalid-timestamps",
            severity=severity,
            database=db,
            table=f"{schema}.{table}",
            summary=f"{bad:,} row(s) with invalid/impossible {col} (NULL or before {min_valid})",
            detail=(
                f"NULL {col}: {null_count:,} rows | "
                f"{col} before {min_valid}: {pre_min:,} rows | "
                f"total rows: {total:,}"
            ),
            affected_rows=bad,
            sample=sample,
            recommendation=(
                f"Add ingest validation rejecting/quarantining rows with {col} "
                f"before {min_valid} or NULL. Forward-only fix is fine for first pass; "
                f"backfill quarantine in a later phase."
            ),
        ))

    return findings
