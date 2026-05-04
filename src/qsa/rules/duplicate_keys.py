"""R004 — Duplicate natural keys for daily-aggregate tables.

Checks the *conceptual* daily-aggregate invariant: tables that are intended
to hold one row per (symbol, date) should not have multiple rows for the
same pair. A violation is a strong signal that the curation builder is
double-applying or missing an upsert.

⚠️  This rule is for tables whose conceptual key is per-day-per-symbol —
    daily aggregates / signals / 1d snapshots. **Article-level tables
    must NOT appear in TARGETS** because their natural key is
    per-article, and (symbol, obs_date) duplicates are *expected* — N
    articles per symbol per day. Adding such a table here generates a
    false-positive equal to (article_rows − distinct_pairs).

Article-level tables to keep OUT of TARGETS (verified 2026-05-03):
  - shdb.news_av_ticker_sentiment    PK (article_url_hash, symbol)
  - shdb.stock_news_1d               PK (security_id, article_id)
  - masd.alphavantage_news_ticker_sentiment, similar shape

For each daily-aggregate table the configured `key_columns` should match
the table's conceptual key, which is usually but not always the database
PK. The security_id-keyed tables below are an example: the DB PK is
(security_id, settlement_date), but the *conceptual* invariant we want
to test is "one symbol → one row per day," so we check (symbol, …).
That correctly catches the case where two security_ids ever resolve to
the same current symbol on the same day.
"""

from __future__ import annotations

from typing import Any

from qsa.finding import Finding

# (database, schema, table, [key_columns], severity)
TARGETS: list[tuple[str, str, str, list[str], str]] = [
    # Daily news/event sentiment aggregates.
    ("shdb", "shdb", "news_ticker_sentiment_1d",     ["symbol", "obs_date"], "warning"),
    ("shdb", "shdb", "symbol_event_sentiment_1d",    ["symbol", "obs_date"], "warning"),
    # Daily insider signal aggregates.
    ("shdb", "shdb", "insider_conviction_signals",   ["symbol", "bar_date"], "warning"),
    ("shdb", "shdb", "insider_mspr_signals",         ["symbol", "bar_date"], "warning"),
    # Daily short-interest / short-volume snapshots. PK uses security_id;
    # we still check the (symbol, date) projection because that's the
    # conceptual invariant for downstream per-symbol consumers.
    ("shdb", "shdb", "stock_short_interest",         ["symbol", "settlement_date"], "warning"),
    ("shdb", "shdb", "stock_short_volume_1d",        ["symbol", "report_date"], "warning"),

    # NOTE: news_av_ticker_sentiment and stock_news_1d are INTENTIONALLY
    # absent — both are article-level tables whose actual PKs include an
    # article identifier. (symbol, obs_date) is correctly non-unique on
    # them and represents article volume, not duplication. The daily
    # aggregate of news_av_ticker_sentiment is news_ticker_sentiment_1d
    # (already in TARGETS above).
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
