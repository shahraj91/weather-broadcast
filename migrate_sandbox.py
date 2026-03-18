"""
Migration: add sandbox_opted_in column to the users table.

Safe to run multiple times — checks whether the column already exists
before attempting the ALTER TABLE.

Usage:
    python3 migrate_sandbox.py
"""

import os
import sys
import sqlite3

from dotenv import load_dotenv
load_dotenv()

DB_PATH = os.getenv("DB_PATH", "./data/weather_broadcast.db")


def migrate(db_path: str = DB_PATH):
    if not os.path.exists(db_path):
        print(f"✗ Database not found at {db_path}")
        print("  Run 'python3 database/seed.py' or start the app first to create it.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    try:
        existing_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }

        if "sandbox_opted_in" in existing_cols:
            print("✓ Column 'sandbox_opted_in' already exists — nothing to do.")
            return

        conn.execute(
            "ALTER TABLE users ADD COLUMN sandbox_opted_in INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()
        print("✓ Added 'sandbox_opted_in' column (all existing users set to 0 / not opted in).")

        count = conn.execute("SELECT COUNT(*) FROM users WHERE active = 1").fetchone()[0]
        print(f"  {count} active user(s) now require opt-in before messages will be delivered.")
        print("  Run 'python3 opt_in_user.py --list' to see opt-in status for all users.")

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
