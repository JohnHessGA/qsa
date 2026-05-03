"""R007 — Deprecated table usage.

Surfaces tables explicitly marked deprecated in `qsa.yaml`. Always emits one
finding per deprecated table even if the table is empty — the goal is to
make sure no future pipeline accidentally consumes it. Pairs with the
consumer-grep run in audit.py which surfaces live consumers.
"""

from __future__ import annotations

from typing import Any

from qsa.finding import Finding


def _connection_for(db: str, masd, shdb, mefdb):
    return {"masd": masd, "shdb": shdb, "mefdb": mefdb}[db]


def check(*, masd, shdb, mefdb, app_cfg: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []

    for entry in app_cfg["deprecated_tables"]:
        schema = entry["schema"]
        table = entry["table"]
        replacement = entry.get("replacement", "(none)")
        reason = entry.get("reason", "(no reason given)")
        # Decide which connection holds this schema. Default to shdb.
        db = "masd" if schema == "masd" else "shdb"
        conn = _connection_for(db, masd, shdb, mefdb)

        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema=%s AND table_name=%s",
                (schema, table),
            )
            exists = cur.fetchone()[0] > 0

        if not exists:
            findings.append(Finding(
                rule_id="R007-deprecated-tables",
                severity="info",
                database=db,
                table=f"{schema}.{table}",
                summary=f"Deprecated table {schema}.{table} is already removed",
                detail=f"Reason: {reason}\nPreferred source: {replacement}",
            ))
            continue

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {schema}.{table};")
            n = cur.fetchone()[0]

        findings.append(Finding(
            rule_id="R007-deprecated-tables",
            severity="warning",
            database=db,
            table=f"{schema}.{table}",
            summary=f"Deprecated table {schema}.{table} still present ({n:,} rows)",
            detail=(
                f"Reason: {reason}\n"
                f"Preferred source: {replacement}\n\n"
                f"Consumer-grep results are listed in the cross-cutting findings section."
            ),
            affected_rows=n,
            recommendation=(
                "Do not consume this table from new pipelines. Migrate any existing "
                f"consumers to {replacement}. Optionally add a DB COMMENT marking the "
                "table deprecated so anyone inspecting the schema sees the warning."
            ),
        ))

    return findings
