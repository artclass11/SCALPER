"""Local SQLite storage. Credentials and raw prompts are never persisted."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from scalper.config import database_path
from scalper.schemas import StrategySpec


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _secure_database_files(path: Path, *, make_parent_private: bool) -> None:
    if os.name == "nt":
        return
    if make_parent_private:
        os.chmod(path.parent, 0o700)
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        if candidate.exists():
            os.chmod(candidate, 0o600)


def _connect() -> sqlite3.Connection:
    path = database_path()
    configured_path = bool(os.getenv("SCALPER_DB_PATH", "").strip())
    parent_existed = path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Only force permissions on SCALPER's own default data directory, or a directory
    # this invocation has just created. Never chmod an arbitrary existing user directory.
    make_parent_private = not configured_path or not parent_existed
    conn = sqlite3.connect(path, timeout=10)
    _secure_database_files(path, make_parent_private=make_parent_private)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS strategies (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, spec_json TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
                last_processed_bar TEXT, last_error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at TEXT NOT NULL,
                action TEXT NOT NULL, strategy_id TEXT, detail_json TEXT NOT NULL DEFAULT '{}'
            )
        """)
        _secure_database_files(
            database_path(),
            make_parent_private=not bool(os.getenv("SCALPER_DB_PATH", "").strip()),
        )


def _public(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "name": row["name"], "spec": json.loads(row["spec_json"]),
        "active": bool(row["active"]), "last_processed_bar": row["last_processed_bar"],
        "last_error": row["last_error"], "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def record_event(action: str, strategy_id: str | None = None, details: dict | None = None) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO audit_events (occurred_at, action, strategy_id, detail_json) VALUES (?, ?, ?, ?)",
            (_now(), action[:80], strategy_id, json.dumps(details or {}, separators=(",", ":"))),
        )


def save_strategy(name: str, spec: StrategySpec) -> dict:
    init_db()
    strategy_id, now = str(uuid.uuid4()), _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO strategies (id, name, spec_json, active, created_at, updated_at) VALUES (?, ?, ?, 0, ?, ?)",
            (strategy_id, name.strip(), spec.model_dump_json(), now, now),
        )
        row = conn.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
    record_event("strategy_saved", strategy_id)
    return _public(row)


def list_strategies(active_only: bool = False) -> list[dict]:
    init_db()
    query = (
        "SELECT * FROM strategies WHERE active = 1 ORDER BY created_at DESC"
        if active_only else "SELECT * FROM strategies ORDER BY created_at DESC"
    )
    with _connect() as conn:
        rows = conn.execute(query).fetchall()
    return [_public(row) for row in rows]


def get_strategy(strategy_id: str) -> dict | None:
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
    return _public(row) if row else None


def set_strategy_active(strategy_id: str, active: bool) -> dict | None:
    init_db()
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE strategies SET active = ?, last_error = NULL, updated_at = ? WHERE id = ?",
            (1 if active else 0, _now(), strategy_id),
        )
        if not cursor.rowcount:
            return None
        row = conn.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
    record_event("strategy_activated" if active else "strategy_deactivated", strategy_id)
    return _public(row)


def delete_strategy(strategy_id: str) -> bool:
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT active FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
        if row is None or row["active"]:
            return False
        conn.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
    record_event("strategy_deleted", strategy_id)
    return True


def update_processed_bar(strategy_id: str, bar_timestamp: str) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "UPDATE strategies SET last_processed_bar = ?, last_error = NULL, updated_at = ? WHERE id = ?",
            (bar_timestamp, _now(), strategy_id),
        )


def update_strategy_error(strategy_id: str, error_code: str) -> None:
    init_db()
    # Avoid flooding the audit log if a worker keeps encountering the same persistent error.
    with _connect() as conn:
        row = conn.execute("SELECT last_error FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
        if row is None or row["last_error"] == error_code[:80]:
            return
        conn.execute(
            "UPDATE strategies SET last_error = ?, updated_at = ? WHERE id = ?",
            (error_code[:80], _now(), strategy_id),
        )
    record_event("worker_error", strategy_id, {"error_code": error_code[:80]})
