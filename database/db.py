"""
SQLite database layer for the Weather Broadcast System.
Schema is Postgres-compatible for easy future migration.
"""

import sqlite3
import logging
from pathlib import Path
from typing import List, Optional

from database.models import User, SendLog

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = "./data/weather_broadcast.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    # ──────────────────────────────────────────
    # Connection management
    # ──────────────────────────────────────────

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")   # Better concurrency
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()

    # ──────────────────────────────────────────
    # Schema initialisation
    # ──────────────────────────────────────────

    def init(self):
        """Create tables if they do not already exist."""
        conn = self.connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                phone        TEXT    UNIQUE NOT NULL,
                lat          REAL    NOT NULL,
                lon          REAL    NOT NULL,
                timezone     TEXT    NOT NULL,
                unit_system  TEXT    NOT NULL DEFAULT 'metric',
                country_code TEXT,
                name         TEXT,
                active       INTEGER NOT NULL DEFAULT 1,
                created_at   TEXT    DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS send_logs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL REFERENCES users(id),
                status       TEXT    NOT NULL,
                message_sid  TEXT,
                error        TEXT,
                retryable    INTEGER NOT NULL DEFAULT 0,
                message_body TEXT,
                sent_at      TEXT    DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_users_timezone ON users (timezone);
            CREATE INDEX IF NOT EXISTS idx_users_active   ON users (active);
            CREATE INDEX IF NOT EXISTS idx_logs_user_id   ON send_logs (user_id);
        """)
        conn.commit()

        # Migration: add name column if it doesn't exist (existing databases)
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "name" not in existing_cols:
            conn.execute("ALTER TABLE users ADD COLUMN name TEXT")
            conn.commit()
            logger.info("Migrated users table: added 'name' column")

        # Migration: add sandbox_opted_in column if it doesn't exist
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "sandbox_opted_in" not in existing_cols:
            conn.execute("ALTER TABLE users ADD COLUMN sandbox_opted_in INTEGER NOT NULL DEFAULT 0")
            conn.commit()
            logger.info("Migrated users table: added 'sandbox_opted_in' column")

        # Migration: add message_body column to send_logs if it doesn't exist
        log_cols = {row[1] for row in conn.execute("PRAGMA table_info(send_logs)").fetchall()}
        if "message_body" not in log_cols:
            conn.execute("ALTER TABLE send_logs ADD COLUMN message_body TEXT")
            conn.commit()
            logger.info("Migrated send_logs table: added 'message_body' column")

        # Migration: add activity columns if they don't exist
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        for col, definition in [
            ("activity",             "ALTER TABLE users ADD COLUMN activity TEXT"),
            ("activity_notes",       "ALTER TABLE users ADD COLUMN activity_notes TEXT"),
            ("conversation_context", "ALTER TABLE users ADD COLUMN conversation_context TEXT"),
        ]:
            if col not in existing_cols:
                conn.execute(definition)
                conn.commit()
                logger.info("Migrated users table: added '%s' column", col)

        logger.info("Database initialised at %s", self.db_path)

    # ──────────────────────────────────────────
    # User CRUD
    # ──────────────────────────────────────────

    def add_user(self, user: User) -> int:
        """Insert a new user. Returns the new row id."""
        conn = self.connect()
        cursor = conn.execute(
            """INSERT INTO users
               (phone, lat, lon, timezone, unit_system, country_code, name, active, sandbox_opted_in,
                activity, activity_notes, conversation_context)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user.phone, user.lat, user.lon, user.timezone, user.unit_system,
             user.country_code, user.name, int(user.active), int(user.sandbox_opted_in),
             user.activity, user.activity_notes, user.conversation_context)
        )
        conn.commit()
        logger.info("Added user phone=%s timezone=%s", user.phone, user.timezone)
        return cursor.lastrowid

    def get_users_by_timezone(self, timezone: str) -> List[User]:
        """Return all active users in the given IANA timezone."""
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM users WHERE timezone = ? AND active = 1", (timezone,)
        ).fetchall()
        return [self._row_to_user(r) for r in rows]

    def get_all_timezones(self) -> List[str]:
        """Return distinct timezones that have at least one active user."""
        conn = self.connect()
        rows = conn.execute(
            "SELECT DISTINCT timezone FROM users WHERE active = 1"
        ).fetchall()
        return [r["timezone"] for r in rows]

    def deactivate_user(self, phone: str) -> bool:
        """Set a user as inactive (unsubscribed). Returns True if found."""
        conn = self.connect()
        cursor = conn.execute(
            "UPDATE users SET active = 0 WHERE phone = ?", (phone,)
        )
        conn.commit()
        return cursor.rowcount > 0

    def get_user_by_phone(self, phone: str) -> Optional[User]:
        conn = self.connect()
        row = conn.execute(
            "SELECT * FROM users WHERE phone = ?", (phone,)
        ).fetchone()
        return self._row_to_user(row) if row else None

    def set_sandbox_opted_in(self, phone: str) -> bool:
        """Mark a user as having sent the sandbox join code. Returns True if found."""
        conn = self.connect()
        cursor = conn.execute(
            "UPDATE users SET sandbox_opted_in = 1 WHERE phone = ?", (phone,)
        )
        conn.commit()
        return cursor.rowcount > 0

    def get_unapproved_users(self) -> List[User]:
        """Return all active users who have not yet opted in to the sandbox."""
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM users WHERE active = 1 AND sandbox_opted_in = 0 ORDER BY id"
        ).fetchall()
        return [self._row_to_user(r) for r in rows]

    # ──────────────────────────────────────────
    # Send logging
    # ──────────────────────────────────────────

    def log_send(self, log: SendLog):
        """Record the result of a send attempt."""
        conn = self.connect()
        conn.execute(
            """INSERT INTO send_logs (user_id, status, message_sid, error, retryable, message_body)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (log.user_id, log.status, log.message_sid, log.error, int(log.retryable), log.message_body)
        )
        conn.commit()

    # ──────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────

    def update_activity(self, phone: str, activity: str, notes: Optional[str] = None) -> bool:
        """Set a user's activity type and optional notes. Returns True if found."""
        conn = self.connect()
        cursor = conn.execute(
            "UPDATE users SET activity = ?, activity_notes = ? WHERE phone = ?",
            (activity, notes, phone)
        )
        conn.commit()
        return cursor.rowcount > 0

    def update_conversation_context(self, phone: str, context_json: str) -> bool:
        """Persist the serialised conversation context for a user. Returns True if found."""
        conn = self.connect()
        cursor = conn.execute(
            "UPDATE users SET conversation_context = ? WHERE phone = ?",
            (context_json, phone)
        )
        conn.commit()
        return cursor.rowcount > 0

    def get_user_conversation_context(self, phone: str) -> dict:
        """Return the conversation context for a user as a parsed dict (empty dict if none)."""
        import json
        user = self.get_user_by_phone(phone)
        if not user or not user.conversation_context:
            return {}
        try:
            return json.loads(user.conversation_context)
        except (json.JSONDecodeError, TypeError):
            return {}

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> User:
        keys = row.keys()
        return User(
            id=row["id"],
            phone=row["phone"],
            lat=row["lat"],
            lon=row["lon"],
            timezone=row["timezone"],
            unit_system=row["unit_system"],
            country_code=row["country_code"],
            name=row["name"],
            active=bool(row["active"]),
            sandbox_opted_in=bool(row["sandbox_opted_in"]) if "sandbox_opted_in" in keys else False,
            activity=row["activity"] if "activity" in keys else None,
            activity_notes=row["activity_notes"] if "activity_notes" in keys else None,
            conversation_context=row["conversation_context"] if "conversation_context" in keys else None,
        )
