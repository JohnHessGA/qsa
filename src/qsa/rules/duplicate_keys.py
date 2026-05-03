"""R004 — Duplicate natural keys.

For curated SHDB tables that should have one row per (symbol, date), check
that the natural key is in fact unique. Duplicate rows are a strong signal
that ingestion is double-applying or that a builder lacks an upsert.
"""

from __future__ import annotations

from typing import Any

from qsa.finding import Finding

# (database, schema, table, [key_columns], severity)
TARGETS: list[tuple[str, str, str, list[str], str]] = [
    ("shdb", "shdb", "news_ticker_sentiment_1d",     ["symbol", "obs_date"], "warning"),
    ("shdb", "shdb", "symbol_event_sentiment_1d",    ["symbol", "obs_date"], "warning"),
    ("shdb", "shdb", "news_av_ticker_sentiment",     ["symbol", "obs_date"], "warning"),
    ("shdb", "shdb", "stock_news_1d",                ["symbol", "bar_date"], "info"),
    ("shdb", "shdb", "insider_conviction_signals",   ["symbol", "bar_date"], "warning"),
    ("shdb", "shdb", "insider_mspr_signals",         ["symbol", "bar_date"], "warning"),
    ("shdb", "shdb", "stock_short_interest",         ["symbol", "settlement_date"], "warning"),
    ("shdb", "shdb", "stock_short_volume_1d",        ["symbol", "report_date"], "warning"),
]


def _connection_for(db: str, masd, shdb, mefdb):
    return {"masd": masd, "shdb": shdb, "mefdb": mefdb}[db]


def check(*, masd, shdb, mefdb, app_cfg: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []

    for db, schema, table, keys, severity in TARGETS:
        conn = _connection_for(db, masd, shdb, mefdb)
        key_list = ", ".join(keys)
        sql = f"""
            SELECT COUNT(*) AS dup_groups, COALESCE(SUM(extra), 0) AS extra_rows
            FROM (
              SELECT {key_list}, COUNT(*) - 1 AS extra
              FROM {schema}.{table}
              GROUP BY {key_list}
              HAVING COUNT(*) > 1
            ) g;
        """
        with conn.cursor() as cur:
            cur.execute(sql)
            dup_groups, extra_rows = cur.fetchone()

        if not dup_groups:
            continue

        sample_sql = f"""
            SELECT {key_list}, COUNT(*) AS n
            FROM {schema}.{table}
            GROUP BY {key_list} HAVING COUNT(*) > 1
            ORDER BY n DESC LIMIT 5;
        """
        with conn.cursor() as cur:
            cur.execute(sample_sql)
            rows = cur.fetchall()
            sample = [
                {**{k: str(v) for k, v in zip(keys, r[:-1])}, "rows": r[-1]}
                for r in rows
            ]

        findings.append(Finding(
            rule_id="R004-duplicate-keys",
            severity=severity,
            database=db,
            table=f"{schema}.{table}",
            summary=f"{dup_groups:,} duplicate ({key_list}) groups; {extra_rows:,} extra row(s)",
            detail=(
                f"Natural key ({key_list}) should be unique but {dup_groups:,} groups "
                f"contain duplicates totalling {extra_rows:,} extra row(s)."
            ),
            affected_rows=int(extra_rows),
            sample=sample,
            recommendation=(
                "Confirm the curation builder uses ON CONFLICT DO UPDATE on the natural key; "
                "back-out the dup rows or add a unique index."
            ),
        ))

    return findings
