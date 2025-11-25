# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProvenanceStore:
    """Base interface for provenance/memory stores."""

    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id or uuid.uuid4().hex

    def handle_event(self, name: str, payload: dict[str, Any]) -> None:
        """Record an orchestrator event (default: no-op)."""
        return None

    def as_event_hook(self) -> Callable[[str, dict[str, Any]], None]:
        """Return a callable suitable for SwarmOrchestrator event hooks."""

        def _hook(name: str, payload: dict[str, Any] | None) -> None:
            self.handle_event(name, payload or {})

        return _hook

    def close(self) -> None:
        """Close underlying resources (default: nothing)."""
        return None


class NullProvenanceStore(ProvenanceStore):
    """No-op store used when provenance persistence is disabled."""

    def handle_event(self, name: str, payload: dict[str, Any]) -> None:  # noqa: ARG002
        return None


class SQLiteProvenanceStore(ProvenanceStore):
    """SQLite-backed provenance store recording runs and agent events."""

    def __init__(
        self,
        path: str | Path | None,
        *,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(run_id=run_id)
        self._path = None if path in (None, "-", "") else Path(path)
        self._conn: sqlite3.Connection | None = None
        self._metadata = metadata or {}
        self._run_initialized = False

    def _connect(self) -> sqlite3.Connection:
        if self._conn:
            return self._conn
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._path))
        else:
            conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        self._conn = conn
        self._init_schema()
        return conn

    def _init_schema(self) -> None:
        conn = self._conn
        if not conn:
            return
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                started TEXT,
                completed TEXT,
                metadata TEXT,
                status TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                event TEXT NOT NULL,
                agent TEXT,
                created TEXT NOT NULL,
                payload TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
            )
            """
        )
        conn.commit()

    def handle_event(self, name: str, payload: dict[str, Any]) -> None:
        conn = self._connect()
        created = _utc_now()
        agent = payload.get("agent") if isinstance(payload, dict) else None

        if name == "run_started" and not self._run_initialized:
            started = payload.get("started") or created
            conn.execute(
                """
                INSERT INTO runs(run_id, started, metadata)
                VALUES(?, ?, json(?))
                ON CONFLICT(run_id) DO UPDATE SET started=excluded.started, metadata=excluded.metadata
                """,
                (self.run_id, started, json.dumps(self._metadata)),
            )
            self._run_initialized = True

        conn.execute(
            """
            INSERT INTO events(run_id, event, agent, created, payload)
            VALUES(?, ?, ?, ?, json(?))
            """,
            (self.run_id, name, agent, created, json.dumps(payload)),
        )

        if name == "run_completed":
            completed = payload.get("completed") or created
            conn.execute(
                "UPDATE runs SET completed=?, status=json(?) WHERE run_id=?",
                (completed, json.dumps(payload), self.run_id),
            )
        conn.commit()

    def fetch_run(self) -> dict[str, Any] | None:
        conn = self._conn
        if not conn:
            return None
        row = conn.execute(
            "SELECT run_id, started, completed, metadata, status FROM runs WHERE run_id=?",
            (self.run_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "run_id": row["run_id"],
            "started": row["started"],
            "completed": row["completed"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
            "status": json.loads(row["status"]) if row["status"] else {},
        }

    def fetch_events(self) -> list[dict[str, Any]]:
        conn = self._conn
        if not conn:
            return []
        rows = conn.execute(
            "SELECT event, agent, created, payload FROM events WHERE run_id=? ORDER BY id",
            (self.run_id,),
        ).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            events.append(
                {
                    "event": row["event"],
                    "agent": row["agent"],
                    "created": row["created"],
                    "payload": json.loads(row["payload"]) if row["payload"] else {},
                }
            )
        return events

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


def open_provenance_store(
    path: str | Path | None, *, metadata: dict[str, Any] | None = None
) -> ProvenanceStore:
    """Factory returning the appropriate provenance store for the provided path."""
    if path in (None, "", False, "-"):
        return NullProvenanceStore()
    return SQLiteProvenanceStore(path, metadata=metadata)
