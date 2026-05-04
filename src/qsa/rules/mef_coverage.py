"""R008 — MEF universe coverage.

For tables that should be broad per-symbol streams, count how many of the
305 MEF stock universe are present. Emits warning/critical if coverage
falls below configured thresholds. Tables that are inherently sparse
(enforcement, congress trades, CFPB) are tagged `sparse_expected` and only
get an INFO finding.
"""

from __future__ import annotations

from typing import Any

from qsa.finding import Finding

# (db, schema, table, symbol_col, expected, label)
#   expected = "broad" | "sparse_expected"
TARGETS: list[tuple[str, str, str, str, str, str]] = [
    # MASD
    ("masd", "masd", "alphavantage_news_ticker_sentiment", "ticker", "broad", "AlphaVantage news sentiment"),
    ("masd", "masd", "massive_stocks_news_1d",             "symbol", "broad", "Polygon stock news"),
    ("masd", "masd", "finnhub_news_article_symbols",       "symbol", "broad", "Finnhub news per-symbol"),
    ("masd", "masd", "marketaux_news_entity_sentiment",    "symbol", "broad", "Marketaux entity sentiment"),
    ("masd", "masd", "apewisdom_social_mentions_1d",       "ticker", "broad", "ApeWisdom social mentions"),
    ("masd", "masd", "fmp_analyst_estimates_1d",           "symbol", "broad", "FMP analyst estimates"),
    ("masd", "masd", "yahoo_stocks_analyst_estimates_1d",  "symbol", "broad", "Yahoo analyst estimates"),
    ("masd", "masd", "yahoo_stocks_eps_momentum_1d",       "symbol", "broad", "Yahoo EPS momentum"),
    ("masd", "masd", "fmp_stocks_analyst_grades",          "symbol", "broad", "FMP analyst grades"),
    ("masd", "masd", "fmp_stocks_price_targets_1d",        "symbol", "broad", "FMP price targets"),
    ("masd", "masd", "finnhub_stocks_insider_mspr_1m",     "symbol", "broad", "Finnhub insider MSPR"),
    ("masd", "masd", "finnhub_stocks_insider_txn",         "symbol", "broad", "Finnhub insider txn"),
    ("masd", "masd", "fmp_stocks_insider_trades",          "symbol", "broad", "FMP insider trades"),
    ("masd", "masd", "massive_stocks_short_int",           "ticker", "broad", "Polygon short interest"),
    ("masd", "masd", "massive_stocks_short_vol_1d",        "symbol", "broad", "Polygon short volume"),
    ("masd", "masd", "sec_edgar_filing_events",            "ticker_derived", "broad", "SEC EDGAR filings"),
    ("masd", "masd", "fmp_congress_house_trades",          "symbol", "sparse_expected", "FMP House trades"),
    ("masd", "masd", "fmp_congress_senate_trades",         "symbol", "sparse_expected", "FMP Senate trades"),
    ("masd", "masd", "secapi_regulatory_enforcement",      "symbol", "sparse_expected", "SEC enforcement"),
    ("masd", "masd", "cfpb_regulatory_complaints_1d",      "symbol", "sparse_expected", "CFPB complaints"),
    # SHDB
    ("shdb", "shdb", "news_ticker_sentiment_1d",           "symbol", "broad", "Unified news sentiment"),
    ("shdb", "shdb", "symbol_event_sentiment_1d",          "symbol", "broad", "Symbol event sentiment"),
    ("shdb", "shdb", "event_market_news",                  "symbol", "broad", "Curated market news"),
    ("shdb", "shdb", "news_av_ticker_sentiment",           "symbol", "broad", "Curated AV news sentiment"),
    ("shdb", "shdb", "stock_news_1d",                      "symbol", "broad", "Curated Polygon news"),
    ("shdb", "shdb", "analyst_estimates_1d",               "symbol", "broad", "Curated analyst estimates"),
    ("shdb", "shdb", "eps_momentum_1d",                    "symbol", "broad", "Curated EPS momentum"),
    ("shdb", "shdb", "analyst_grades",                     "symbol", "broad", "Curated analyst grades"),
    ("shdb", "shdb", "analyst_price_targets_1d",           "symbol", "broad", "Curated price targets"),
    ("shdb", "shdb", "insider_trades",                     "symbol", "broad", "Curated insider trades"),
    ("shdb", "shdb", "insider_conviction_signals",         "symbol", "broad", "Insider conviction signals"),
    ("shdb", "shdb", "insider_mspr_signals",               "symbol", "broad", "Insider MSPR signals"),
    ("shdb", "shdb", "stock_short_interest",               "symbol", "broad", "Curated short interest"),
    ("shdb", "shdb", "stock_short_volume_1d",              "symbol", "broad", "Curated short volume"),
    ("shdb", "shdb", "institutional_holders_1q",           "symbol", "broad", "13F institutional holders"),
    ("shdb", "shdb", "institutional_flow_signals",         "symbol", "broad", "13F flow signals"),
    ("shdb", "shdb", "event_filing",                       "symbol", "broad", "SEC filing events (curated)"),
    ("shdb", "shdb", "congress_activity_signals",          "symbol", "sparse_expected", "Congress activity signals"),
    ("shdb", "shdb", "sec_enforcement",                    "symbol", "sparse_expected", "Curated SEC enforcement"),
    ("shdb", "shdb", "sentiment_consumer_complaints_1d",   "symbol", "sparse_expected", "Curated CFPB complaints"),
]


def _load_mef_universe(mefdb_conn) -> list[str]:
    with mefdb_conn.cursor() as cur:
        cur.execute("SELECT symbol FROM mef.universe_stock ORDER BY symbol;")
        return [r[0] for r in cur.fetchall()]


def _connection_for(db: str, masd, shdb, mefdb):
    return {"masd": masd, "shdb": shdb, "mefdb": mefdb}[db]


def _build_deprecated_set(app_cfg: dict[str, Any]) -> set[tuple[str, str]]:
    """(schema, table) tuples flagged retired/deprecated in qsa.yaml. R008
    skips them — coverage stats on a retired source aren't useful, and they
    create noise in the critical-coverage bucket."""
    out: set[tuple[str, str]] = set()
    for entry in app_cfg.get("deprecated_tables") or []:
        schema = entry.get("schema")
        table = entry.get("table")
        if schema and table:
            out.add((schema, table))
    return out


def check(*, masd, shdb, mefdb, app_cfg: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    deprecated = _build_deprecated_set(app_cfg)
    universe = _load_mef_universe(mefdb)
    universe_n = len(universe)
    cov_cfg = app_cfg["mef_coverage"]
    warn_pct = cov_cfg["warn_below_pct"]
    crit_pct = cov_cfg["critical_below_pct"]

    # Build per-database lookup table of MEF symbols (read into a temp table
    # under the read-only session by using a parameterised IN-list instead).
    sym_array = "{" + ",".join(s.replace("\\", "\\\\").replace(",", "\\,") for s in universe) + "}"

    for db, schema, table, col, expected, label in TARGETS:
        # Skip retired/deprecated tables — coverage on a retired source is
        # not actionable and inflates the critical bucket.
        if (schema, table) in deprecated:
            continue
        conn = _connection_for(db, masd, shdb, mefdb)
        sql = f"""
            SELECT COUNT(DISTINCT {col})
            FROM {schema}.{table}
            WHERE {col} = ANY (%s::text[]);
        """
        with conn.cursor() as cur:
            cur.execute(sql, (sym_array,))
            covered = cur.fetchone()[0]

        pct = (covered / universe_n * 100.0) if universe_n else 0.0

        # Severity
        if expected == "sparse_expected":
            severity = "info"
        elif pct < crit_pct:
            severity = "critical"
        elif pct < warn_pct:
            severity = "warning"
        else:
            severity = "info"

        missing = universe_n - covered
        # Sample of missing symbols (only when broad and below warn threshold)
        sample: list[Any] = []
        if expected == "broad" and pct < warn_pct and missing:
            missing_sql = f"""
                SELECT s FROM unnest(%s::text[]) AS s
                EXCEPT
                SELECT {col} FROM {schema}.{table} WHERE {col} = ANY (%s::text[])
                ORDER BY 1 LIMIT 20;
            """
            with conn.cursor() as cur:
                cur.execute(missing_sql, (sym_array, sym_array))
                sample = [{"missing_symbol": r[0]} for r in cur.fetchall()]

        if expected == "broad":
            recommendation = (
                "Broad sources falling below 50% coverage indicate ingestion or symbol-"
                "mapping issues. Compare MASD source row counts to SHDB curated row "
                "counts to localise the bottleneck (R009 also covers analyst-grades / "
                "price-targets explicitly)."
            )
        else:
            recommendation = (
                "Sparse-expected source: low coverage is by nature, not a quality issue. "
                "Only relevant when paired with a real-world event."
            )

        findings.append(Finding(
            rule_id="R008-mef-coverage",
            severity=severity,
            database=db,
            table=f"{schema}.{table}",
            summary=f"{label}: {covered}/{universe_n} MEF stocks ({pct:.1f}%)",
            detail=(
                f"Expected coverage: {expected}. "
                f"{covered} of {universe_n} MEF universe stocks present in {schema}.{table}.{col}."
            ),
            affected_symbols=missing,
            sample=sample,
            recommendation=recommendation,
        ))

    return findings
