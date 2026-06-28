"""Acceso a PostgreSQL (+ pgvector) para los artefactos gold y el índice del RAG."""

from __future__ import annotations

from contextlib import contextmanager

import psycopg

from vigia.config import settings


def _dsn() -> str:
    """Convierte el DATABASE_URL al formato que entiende psycopg."""
    return settings.database_url.replace("postgres://", "postgresql://")


@contextmanager
def get_conn():
    """Context manager de conexión psycopg con autocommit."""
    conn = psycopg.connect(_dsn(), autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


def ping() -> bool:
    """Verifica conectividad con la base de datos."""
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001
        return False
