"""R006 — Stale source data.

For each per-symbol qualitative table, the most-recent observation date
should be within the cadence-appropriate threshold from today. Streams that
have stalled raise a warning (data are still readable but recommendations
should not be built on stale inputs).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from qsa.finding import Finding

# (db, schema, table, date_col, cadence)
TARGETS: list[tuple[str, str, str, str, str]] = [
    # MASD daily news/sentiment
    ("masd", "masd", "alphavantage_news_sentiment_1d",  "obs_date",       "daily"),
    ("masd", "masd", "gdelt_news_sentiment_1d",         "obs_date",       "daily"),
    ("masd", "masd", "gdelt_article_trends_1d",         "obs_date",       "daily"),
    ("masd", "masd", "marketaux_news_articles_1d",      "obs_date",       "daily"),
    ("masd", "masd", "massive_stocks_news_1d",          "bar_date",       "daily"),
    ("masd", "masd", "altme_sentiment_feargreed_1d",    "obs_date",       "daily"),
    ("masd", "masd", "apewisdom_social_mentions_1d",    "obs_date",       "daily"),
    ("masd", "masd", "fmp_analyst_estimates_1d",        "snapshot_date",  "daily"),
    ("masd", "masd", "fmp_stocks_price_targets_1d",     "bar_date",       "daily"),
    ("masd", "masd", "fmp_stocks_analyst_grades",       "bar_date",       "daily"),
    ("masd", "masd", "yahoo_stocks_analyst_estimates_1d", "obs_date",     "daily"),
    ("masd", "masd", "yahoo_stocks_eps_momentum_1d",    "obs_date",       "daily"),
    ("masd", "masd", "massive_stocks_short_vol_1d",     "report_date",    "daily"),
    ("masd", "masd", "sec_edgar_filing_events",         "file_date",      "daily"),
    # MASD weekly / monthly
    ("masd", "masd", "cftc_futures_positioning_1w",     "report_date",    "weekly"),
    ("masd", "masd", "finnhub_stocks_insider_mspr_1m",  None,             "monthly"),
    # SHDB curated
    ("shdb", "shdb", "news_ticker_sentiment_1d",        "obs_date",       "daily"),
    ("shdb", "shdb", "symbol_event_sentiment_1d",       "obs_date",       "daily"),
    ("shdb", "shdb", "event_market_news",               "obs_date",       "daily"),
    ("shdb", "shdb", "stock_news_1d",                   "bar_date",       "daily"),
    ("shdb", "shdb", "factor_news_tone_1d",             "obs_date",       "daily"),
    ("shdb", "shdb", "sentiment_feargreed_1d",          "obs_date",       "daily"),
    ("shdb", "shdb", "sentiment_news_tone_1d",          "obs_date",       "daily"),
    ("shdb", "shdb", "stock_short_interest",            "settlement_date","daily"),
    ("shdb", "shdb", "stock_short_volume_1d",           "report_date",    "daily"),
    ("shdb", "shdb", "insider_conviction_signals",      "bar_date",       "daily"),
    ("shdb", "shdb", "insider_trades",                  "bar_date",       "daily"),
    ("shdb", "shdb", "analyst_grades",                  "bar_date",       "daily"),
    ("shdb", "shdb", "analyst_price_targets_1d",        "bar_date",       "daily"),
    ("shdb", "shdb", "futures_positioning_signals_1w",  "report_date",    "weekly"),
    ("shdb", "shdb", "insider_mspr_signals",            "bar_date",       "monthly"),
]


def _connection_for(db: str, masd, shdb, mefdb):
    return {"masd": masd, "shdb": shdb, "mefdb": mefdb}[db]


def _build_deprecated_set(app_cfg: dict[str, Any]) -> set[tuple[str, str]]:
    """Return the set of (schema, table) tuples flagged as deprecated/retired
    in qsa.yaml. Tables in this set are EXEMPT from R006 staleness — their
    staleness is intentional, not a defect, and reporting it as an active-
    source issue creates noise on every run."""
    out: set[tuple[str, str]] = set()
    for entry in app_cfg.get("deprecated_tables") or []:
        schema = entry.get("schema")
        table = entry.get("table")
        if schema and table:
            out.add((schema, table))
    return out


def check(*, masd, shdb, mefdb, app_cfg: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    thresholds = app_cfg["staleness_thresholds_days"]
    deprecated = _build_deprecated_set(app_cfg)
    today = date.today()

    for db, schema, table, col, cadence in TARGETS:
        # Skip retired/deprecated tables — R007 reports them, not R006.
        if (schema, table) in deprecated:
            continue
        conn = _connection_for(db, masd, shdb, mefdb)
        # Tables without a single date column (e.g. mspr year+month) get a
        # synthesized one. Caller passes None; we synth with make_date.
        if col is None:
            date_expr = "make_date(year, month, 1)"
        else:
            date_expr = col

        with conn.cursor() as cur:
            cur.execute(f"SELECT MAX({date_expr})::date AS max_d, COUNT(*) AS n FROM {schema}.{table};")
            row = cur.fetchone()

        if not row or row[0] is None:
            findings.append(Finding(
                rule_id="R006-staleness",
                severity="warning",
                database=db,
                table=f"{schema}.{table}",
                summary=f"{schema}.{table} is empty",
                detail="Table has zero rows.",
                affected_rows=0,
            ))
            continue

        max_d, n = row
        threshold = thresholds.get(cadence, 30)
        age = (today - max_d).days

        if age <= threshold:
            continue

        severity = "warning" if age <= threshold * 3 else "critical"
        findings.append(Finding(
            rule_id="R006-staleness",
            severity=severity,
            database=db,
            table=f"{schema}.{table}",
            summary=f"{schema}.{table} stale: max({col or 'year+month'})={max_d} ({age}d ago)",
            detail=(
                f"Cadence={cadence}, threshold={threshold}d. "
                f"Most recent observation is {max_d} ({age} days ago). "
                f"{n:,} total rows."
            ),
            affected_rows=n,
            recommendation=(
                "Check the upstream collector/ingest cron and whether the source API is "
                "still returning data. Some streams (Finnhub MSPR, free-tier APIs) may have "
                "expired entitlements rather than pipeline bugs."
            ),
        ))

    return findings
