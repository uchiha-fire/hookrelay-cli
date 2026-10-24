"""
SQLite persistence store for hookrelay-cli webhooks and events.
"""
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import List, Optional
from hookrelay.models import WebhookSession, WebhookEvent


DEFAULT_DB_DIR = Path.home() / ".hookrelay"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "data.db"


class HookRelayStore:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
            self.db_path = str(DEFAULT_DB_PATH)
        else:
            self.db_path = db_path
            if db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return self._conn

    def _init_db(self) -> None:
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS webhooks (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        public_url TEXT NOT NULL,
                        local_target TEXT NOT NULL,
                        local_port INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        created_at REAL NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS events (
                        id TEXT PRIMARY KEY,
                        webhook_id TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        method TEXT NOT NULL,
                        path TEXT NOT NULL,
                        headers_json TEXT NOT NULL,
                        payload_raw TEXT NOT NULL,
                        fwd_status INTEGER,
                        fwd_latency_ms REAL,
                        fwd_response_raw TEXT,
                        FOREIGN KEY(webhook_id) REFERENCES webhooks(id)
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_webhook_id ON events(webhook_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC)")
                conn.commit()

    def save_webhook(self, session: WebhookSession) -> None:
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO webhooks (id, name, public_url, local_target, local_port, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        public_url = excluded.public_url,
                        local_target = excluded.local_target,
                        local_port = excluded.local_port,
                        status = excluded.status
                """, (
                    session.id,
                    session.name,
                    session.public_url,
                    session.local_target,
                    session.local_port,
                    session.status,
                    session.created_at,
                ))
                conn.commit()

    def get_webhook(self, webhook_id: str) -> Optional[WebhookSession]:
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT * FROM webhooks WHERE id = ?", (webhook_id,))
                row = cur.fetchone()
                if row:
                    return WebhookSession(
                        id=row["id"],
                        name=row["name"],
                        public_url=row["public_url"],
                        local_target=row["local_target"],
                        local_port=row["local_port"],
                        status=row["status"],
                        created_at=row["created_at"],
                    )
        return None

    def find_webhook(self, query: str) -> Optional[WebhookSession]:
        """Find webhook by ID or name."""
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute(
                    "SELECT * FROM webhooks WHERE id = ? OR name = ? ORDER BY created_at DESC LIMIT 1",
                    (query, query),
                )
                row = cur.fetchone()
                if row:
                    return WebhookSession(
                        id=row["id"],
                        name=row["name"],
                        public_url=row["public_url"],
                        local_target=row["local_target"],
                        local_port=row["local_port"],
                        status=row["status"],
                        created_at=row["created_at"],
                    )
        return None

    def list_webhooks(self, include_terminated: bool = False) -> List[WebhookSession]:
        query = "SELECT * FROM webhooks"
        params = ()
        if not include_terminated:
            query += " WHERE status != 'TERMINATED'"
        query += " ORDER BY created_at DESC"

        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute(query, params)
                rows = cur.fetchall()
                return [
                    WebhookSession(
                        id=r["id"],
                        name=r["name"],
                        public_url=r["public_url"],
                        local_target=r["local_target"],
                        local_port=r["local_port"],
                        status=r["status"],
                        created_at=r["created_at"],
                    )
                    for r in rows
                ]

    def update_webhook_status(self, webhook_id: str, status: str) -> bool:
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute(
                    "UPDATE webhooks SET status = ? WHERE id = ?",
                    (status, webhook_id),
                )
                conn.commit()
                return cur.rowcount > 0

    def terminate_webhook(self, webhook_id: str) -> bool:
        return self.update_webhook_status(webhook_id, "TERMINATED")

    def delete_webhook(self, webhook_id: str) -> bool:
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM events WHERE webhook_id = ?", (webhook_id,))
                cur = conn.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
                conn.commit()
                return cur.rowcount > 0

    def save_event(self, event: WebhookEvent) -> None:
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO events (
                        id, webhook_id, timestamp, method, path, headers_json,
                        payload_raw, fwd_status, fwd_latency_ms, fwd_response_raw
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        fwd_status = excluded.fwd_status,
                        fwd_latency_ms = excluded.fwd_latency_ms,
                        fwd_response_raw = excluded.fwd_response_raw
                """, (
                    event.id,
                    event.webhook_id,
                    event.timestamp,
                    event.method,
                    event.path,
                    json.dumps(event.headers),
                    event.payload,
                    event.fwd_status,
                    event.fwd_latency_ms,
                    event.fwd_response,
                ))
                conn.commit()

    def get_event(self, event_id: str) -> Optional[WebhookEvent]:
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,))
                row = cur.fetchone()
                if row:
                    return self._row_to_event(row)
        return None

    def list_events(self, webhook_id: Optional[str] = None, limit: int = 50) -> List[WebhookEvent]:
        query = "SELECT * FROM events"
        params: List[Any] = []
        if webhook_id:
            query += " WHERE webhook_id = ?"
            params.append(webhook_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute(query, tuple(params))
                rows = cur.fetchall()
                return [self._row_to_event(r) for r in rows]

    def count_events(self, webhook_id: str) -> int:
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT COUNT(*) FROM events WHERE webhook_id = ?", (webhook_id,))
                return cur.fetchone()[0]

    def _row_to_event(self, row: sqlite3.Row) -> WebhookEvent:
        headers = {}
        try:
            headers = json.loads(row["headers_json"])
        except Exception:
            pass

        return WebhookEvent(
            id=row["id"],
            webhook_id=row["webhook_id"],
            timestamp=row["timestamp"],
            method=row["method"],
            path=row["path"],
            headers=headers,
            payload=row["payload_raw"],
            fwd_status=row["fwd_status"],
            fwd_latency_ms=row["fwd_latency_ms"],
            fwd_response=row["fwd_response_raw"],
        )
