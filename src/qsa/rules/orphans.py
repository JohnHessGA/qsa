"""R005 — Orphan child rows.

Some MASD news sources are split across a parent (article) table and one or
more child (per-ticker, per-topic) tables joined on an article identifier.
Children whose parent is missing are flagged.
"""

from __future__ import annotations

from typing import Any

from qsa.finding import Finding

# (db, schema, child_table, child_key, parent_table, parent_key, severity)
TARGETS: list[tuple[str, str, str, str, str, str, str]] = [
    ("masd", "masd", "alphavantage_news_ticker_sentiment", "article_url_hash",
                    "alphavantage_news_sentiment_1d",      "article_url_hash", "warning"),
    ("masd", "masd", "alphavantage_news_topics",           "article_url_hash",
                    "alphavantage_news_sentiment_1d",      "article_url_hash", "warning"),
    ("masd", "masd", "marketaux_news_entity_sentiment",    "article_uuid",
                    "marketaux_news_articles_1d",          "article_uuid",     "warning"),
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

    for db, schema, child, ckey, parent, pkey, severity in TARGETS:
        conn = _connection_for(db, masd, shdb, mefdb)
        if not _column_exists(conn, schema, child, ckey):
            continue
        if not _column_exists(conn, schema, parent, pkey):
            continue

        sql = f"""
            SELECT COUNT(*) AS orphans, COUNT(*) FILTER (WHERE c.{ckey} IS NULL) AS null_keys
            FROM {schema}.{child} c
            LEFT JOIN {schema}.{parent} p ON p.{pkey} = c.{ckey}
            WHERE p.{pkey} IS NULL;
        """
        with conn.cursor() as cur:
            cur.execute(sql)
            orphans, null_keys = cur.fetchone()

        if not orphans:
            continue

        findings.append(Finding(
            rule_id="R005-orphan-rows",
            severity=severity,
            database=db,
            table=f"{schema}.{child}",
            summary=f"{orphans:,} child row(s) with no matching {schema}.{parent}.{pkey}",
            detail=(
                f"Child table {schema}.{child} ({ckey}) has {orphans:,} rows with no parent "
                f"in {schema}.{parent}.{pkey}. Of these, {null_keys:,} have NULL {ckey}."
            ),
            affected_rows=orphans,
            recommendation=(
                "Confirm the parent and child are ingested in the same transaction, or that "
                "ingestion enforces FK-equivalent referential integrity. Orphans cannot be "
                "joined back to article context and so are unusable for sentiment scoring."
            ),
        ))

    return findings
