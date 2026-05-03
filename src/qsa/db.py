"""Read-only DB connection helpers for QSA.

QSA touches three databases — MASD (raw), SHDB (curated), and MEFDB (universe
read for coverage checks). All connections are opened with readonly=True.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg2
from psycopg2.extensions import connection as PGConnection
from psycopg2.extras import RealDictCursor

from qsa.config import load_postgres_config


def _connect(section: dict[str, Any]) -> PGConnection:
    conn = psycopg2.connect(
        host=section["host"],
        port=section["port"],
        database=section["database"],
        user=section["user"],
        password=section["password"],
        connect_timeout=section.get("connect_timeout", 10),
        application_name=section.get("application_name", "qsa"),
    )
    conn.set_session(readonly=True, autocommit=True)
    return conn


@contextmanager
def masd_conn() -> Iterator[PGConnection]:
    cfg = load_postgres_config()
    conn = _connect(cfg["masd"])
    schema = cfg["masd"].get("schema", "masd")
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {schema}, public")
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def shdb_conn() -> Iterator[PGConnection]:
    cfg = load_postgres_config()
    conn = _connect(cfg["shdb"])
    with conn.cursor() as cur:
        cur.execute("SET search_path TO mart, shdb, public")
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def mefdb_conn() -> Iterator[PGConnection]:
    cfg = load_postgres_config()
    conn = _connect(cfg["mefdb"])
    schema = cfg["mefdb"].get("schema", "mef")
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {schema}, public")
    try:
        yield conn
    finally:
        conn.close()


def fetch_dicts(conn: PGConnection, sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def fetch_one(conn: PGConnection, sql: str, params: tuple | None = None) -> tuple | None:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def fetch_all(conn: PGConnection, sql: str, params: tuple | None = None) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())
