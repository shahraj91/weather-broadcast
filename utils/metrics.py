"""Persistent metrics collector backed by SQLite.

Counters survive process restarts.
Rolling latency windows live in memory (last 100 samples) and their current
average is also flushed to the DB so the last-known value is readable after restart.

The metrics table is stored in the same DB file as the rest of the application
(DB_PATH env var, defaulting to ./data/weather_broadcast.db).
"""

import os
import sqlite3
from collections import deque
from datetime import datetime, timezone
from threading import Lock

_lock = Lock()

# Module-level SQLite connection — reused across calls, protected by _lock.
_conn: sqlite3.Connection = None   # type: ignore[assignment]

# In-memory rolling windows (not persisted between restarts, avg is persisted).
_latency_windows: dict = {
    "llama_latency_ms": deque(maxlen=100),
}

_STANDARD_COUNTERS = [
    "messages_sent_total",
    "messages_failed_total",
    "hallucination_fallbacks_total",
    "safety_blocks_total",
    "webhook_requests_total",
    "webhook_rejected_total",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _init(db_path: str = None) -> None:
    """
    (Re-)initialize the SQLite connection and create the metrics table.

    Called once at module import. Tests call this explicitly with a tmp_path
    so each test run gets an isolated DB.
    """
    global _conn

    if db_path is None:
        db_path = os.getenv("DB_PATH", "./data/weather_broadcast.db")

    # Ensure parent directory exists (mirrors behaviour of database/db.py)
    parent = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(parent, exist_ok=True)

    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass

    _conn = sqlite3.connect(db_path, check_same_thread=False)
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            name       TEXT PRIMARY KEY,
            value      REAL    NOT NULL DEFAULT 0,
            updated_at TEXT    NOT NULL
        )
    """)
    _conn.commit()

    # Seed standard counters with 0 if they don't already exist
    now = _now()
    for name in _STANDARD_COUNTERS:
        _conn.execute(
            "INSERT OR IGNORE INTO metrics (name, value, updated_at) VALUES (?, 0, ?)",
            (name, now),
        )
    _conn.commit()


def increment(metric_name: str) -> None:
    """Increment a named counter by 1 and persist to DB."""
    now = _now()
    with _lock:
        # Ensure row exists (no-op if already present)
        _conn.execute(
            "INSERT OR IGNORE INTO metrics (name, value, updated_at) VALUES (?, 0, ?)",
            (metric_name, now),
        )
        # Atomically add 1
        _conn.execute(
            "UPDATE metrics SET value = value + 1, updated_at = ? WHERE name = ?",
            (now, metric_name),
        )
        _conn.commit()


def record_latency(metric_name: str, ms: float) -> None:
    """
    Append a latency sample to the in-memory rolling window (last 100).
    Also persists the current rolling average to the DB.
    """
    now = _now()
    with _lock:
        if metric_name not in _latency_windows:
            _latency_windows[metric_name] = deque(maxlen=100)
        _latency_windows[metric_name].append(ms)
        avg = round(sum(_latency_windows[metric_name]) / len(_latency_windows[metric_name]), 2)

        _conn.execute(
            "INSERT OR IGNORE INTO metrics (name, value, updated_at) VALUES (?, 0, ?)",
            (metric_name, now),
        )
        _conn.execute(
            "UPDATE metrics SET value = ?, updated_at = ? WHERE name = ?",
            (avg, now, metric_name),
        )
        _conn.commit()


def reset(metric_name: str) -> None:
    """Reset a named counter (or latency average) to 0."""
    now = _now()
    with _lock:
        _conn.execute(
            "INSERT OR IGNORE INTO metrics (name, value, updated_at) VALUES (?, 0, ?)",
            (metric_name, now),
        )
        _conn.execute(
            "UPDATE metrics SET value = 0, updated_at = ? WHERE name = ?",
            (now, metric_name),
        )
        _conn.commit()
        if metric_name in _latency_windows:
            _latency_windows[metric_name].clear()


def get_summary() -> dict:
    """
    Read all counters from the DB and return as a dict.
    For latency metrics, the in-memory rolling average overrides the DB value
    when there are live samples (more accurate than the last-persisted average).
    Computes fallback_rate on the fly.
    """
    with _lock:
        rows = _conn.execute("SELECT name, value FROM metrics").fetchall()
        summary = {name: value for name, value in rows}

        # Override latency keys with live in-memory average when window has samples
        for key, window in _latency_windows.items():
            if window:
                summary[key] = round(sum(window) / len(window), 2)
            else:
                # Fall back to last-persisted average (survives restart)
                summary.setdefault(key, 0.0)

        sent   = summary.get("messages_sent_total", 0)
        failed = summary.get("messages_failed_total", 0)
        summary["fallback_rate"] = round(failed / sent, 4) if sent > 0 else 0.0

    return summary


# ── Initialise on module import ────────────────────────────────────────────
_init()
