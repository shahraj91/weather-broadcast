"""
Migration: add activity, activity_notes, and conversation_context columns to users table.

Safe to run multiple times — checks whether each column already exists before
attempting the ALTER TABLE.

Usage:
    python3 migrate_activity.py
"""

import os
import sys
import sqlite3

from dotenv import load_dotenv
load_dotenv()

DB_PATH = os.getenv("DB_PATH", "./data/weather_broadcast.db")

NEW_COLUMNS = [
    ("activity",             "ALTER TABLE users ADD COLUMN activity TEXT"),
    ("activity_notes",       "ALTER TABLE users ADD COLUMN activity_notes TEXT"),
    ("conversation_context", "ALTER TABLE users ADD COLUMN conversation_context TEXT"),
]


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

        added = 0
        for col, sql in NEW_COLUMNS:
            if col in existing_cols:
                print(f"✓ Column '{col}' already exists — skipping.")
            else:
                conn.execute(sql)
                conn.commit()
                print(f"✓ Added column '{col}'.")
                added += 1

        if added:
            print(f"\n{added} column(s) added successfully.")
            print("Users will have NULL for new fields until updated via WhatsApp or CLI.")
        else:
            print("\nAll columns already present — nothing to do.")

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()