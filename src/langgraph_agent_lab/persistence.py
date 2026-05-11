"""Checkpointer adapter."""

from __future__ import annotations


from typing import Any


def build_checkpointer(kind: str = "memory", database_url: str | None = None) -> Any | None:  # noqa: ANN401
    """Return a LangGraph checkpointer."""
    if kind == "none":
        return None
    if kind == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
    if kind == "sqlite":
        try:
            import sqlite3

            from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError as exc:
            msg = "SQLite checkpointer requires: pip install langgraph-checkpoint-sqlite"
            raise RuntimeError(msg) from exc
        sqlite_conn = sqlite3.connect(database_url or "checkpoints.db", check_same_thread=False)
        sqlite_conn.execute("PRAGMA journal_mode=WAL;")
        return SqliteSaver(conn=sqlite_conn)
    if kind == "postgres":
        try:
            import psycopg
            from langgraph.checkpoint.postgres import PostgresSaver
        except ImportError as exc:
            msg = (
                "Postgres checkpointer requires: "
                "pip install langgraph-checkpoint-postgres psycopg[binary]"
            )
            raise RuntimeError(msg) from exc
        db_url = database_url or "postgresql://postgres:postgres@localhost:5432/langgraph_lab"
        pg_conn = psycopg.connect(db_url, autocommit=True)
        checkpointer = PostgresSaver(pg_conn)  # type: ignore[arg-type]
        checkpointer.setup()
        return checkpointer
    raise ValueError(f"Unknown checkpointer kind: {kind}")
