"""Outbox + inbound store (SQLite, WAL).

- outbox: delivery log for outbound messages (status pending/sent/failed)
- inbound: received messages; body TTL = COMMS_RETENTION_DAYS (default 7),
  metadata (chat, from, ts) kept longer
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..config import get_settings

_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    sent_at TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS inbound (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    from_id TEXT NOT NULL,
    text TEXT NOT NULL,
    received_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox(status, id);
CREATE INDEX IF NOT EXISTS idx_inbound_chat ON inbound(chat_id, id);
"""


def _conn(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(UTC).isoformat()


def enqueue(channel: str, chat_id: str, text: str, db_path: Path | None = None) -> dict[str, Any]:
    with _lock:
        conn = _conn(db_path)
        try:
            cur = conn.execute(
                "INSERT INTO outbox(channel, chat_id, text, status, created_at)"
                " VALUES (?,?,?,'pending',?)",
                (channel, chat_id, text, _now()),
            )
            conn.commit()
            return {
                "id": int(cur.lastrowid or 0),
                "channel": channel,
                "chat_id": chat_id,
                "status": "pending",
                "text": text[:200],
            }
        finally:
            conn.close()


def mark_sent(outbox_id: int, db_path: Path | None = None) -> bool:
    with _lock:
        conn = _conn(db_path)
        try:
            cur = conn.execute(
                "UPDATE outbox SET status='sent', sent_at=? WHERE id=?", (_now(), outbox_id)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def mark_failed(outbox_id: int, error: str, db_path: Path | None = None) -> bool:
    with _lock:
        conn = _conn(db_path)
        try:
            cur = conn.execute(
                "UPDATE outbox SET status='failed', error=?, sent_at=? WHERE id=?",
                (error[:500], _now(), outbox_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def list_outbox(
    status: str = "", limit: int = 25, db_path: Path | None = None
) -> list[dict[str, Any]]:
    conn = _conn(db_path)
    try:
        sql = "SELECT * FROM outbox"
        params: list[Any] = []
        if status:
            sql += " WHERE status=?"
            params.append(status)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 200)))
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def store_inbound(
    channel: str, chat_id: str, from_id: str, text: str, db_path: Path | None = None
) -> int:
    with _lock:
        conn = _conn(db_path)
        try:
            expires = datetime.now(UTC) + timedelta(days=get_settings().retention_days)
            cur = conn.execute(
                "INSERT INTO inbound(channel, chat_id, from_id, text, received_at, expires_at)"
                " VALUES (?,?,?,?,?,?)",
                (channel, chat_id, from_id, text, _now(), expires.isoformat()),
            )
            conn.commit()
            return int(cur.lastrowid or 0)
        finally:
            conn.close()


def list_inbound(
    chat_id: str = "", limit: int = 20, db_path: Path | None = None
) -> list[dict[str, Any]]:
    conn = _conn(db_path)
    try:
        sql = "SELECT * FROM inbound"
        params: list[Any] = []
        if chat_id:
            sql += " WHERE chat_id=?"
            params.append(chat_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 100)))
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def purge_expired(db_path: Path | None = None) -> int:
    """Delete expired inbound bodies (retention TTL)."""
    with _lock:
        conn = _conn(db_path)
        try:
            cur = conn.execute("DELETE FROM inbound WHERE expires_at < ?", (_now(),))
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()


def status_counts(db_path: Path | None = None) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        out = {
            r["status"]: int(r["n"])
            for r in conn.execute(
                "SELECT status, COUNT(*) AS n FROM outbox GROUP BY status"
            ).fetchall()
        }
        inbound_total = int(conn.execute("SELECT COUNT(*) AS n FROM inbound").fetchone()["n"])
        return {"outbox": out, "inbound_total": inbound_total}
    finally:
        conn.close()
