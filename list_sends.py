"""
View send history from the database.

Usage:
    python3 list_sends.py              # last 20 sends
    python3 list_sends.py --all        # full history
    python3 list_sends.py Raj          # sends for a specific user by name
    python3 list_sends.py +18183573973 # sends for a specific user by phone
    python3 list_sends.py --failed     # only failed sends
"""

import os
import sys

from dotenv import load_dotenv
load_dotenv()

from database.db import Database

DB_PATH = os.getenv("DB_PATH", "./data/weather_broadcast.db")


def print_log(row):
    s = row["status"]
    if s == "success":
        status = "✓ success"
    elif s == "skipped":
        status = "— skipped (sandbox opt-in)"
    else:
        status = "✗ failed"
    sid     = row["message_sid"] or "—"
    error   = row["error"]       or "—"
    retry   = "yes" if row["retryable"] else "no"

    print(f"""
  Log ID:      {row['id']}
  User:        {row['name'] or '—'} ({row['phone']})
  Status:      {status}
  Sent at:     {row['sent_at']}
  Message SID: {sid}
  Error:       {error}
  Retryable:   {retry}""")
    print("  " + "─" * 40)


def main():
    db = Database(DB_PATH)
    db.init()
    conn = db.connect()

    arg = sys.argv[1] if len(sys.argv) > 1 else None

    base_query = """
        SELECT s.*, u.phone, u.name
        FROM send_logs s
        JOIN users u ON s.user_id = u.id
    """

    if arg == "--failed":
        rows = conn.execute(
            base_query + " WHERE s.status = 'failed' ORDER BY s.sent_at DESC"
        ).fetchall()
        label = "failed sends"

    elif arg == "--all":
        rows = conn.execute(
            base_query + " ORDER BY s.sent_at DESC"
        ).fetchall()
        label = "all sends"

    elif arg and arg.startswith("+"):
        rows = conn.execute(
            base_query + " WHERE u.phone = ? ORDER BY s.sent_at DESC", (arg,)
        ).fetchall()
        label = f"sends for {arg}"

    elif arg:
        rows = conn.execute(
            base_query + " WHERE LOWER(u.name) = LOWER(?) ORDER BY s.sent_at DESC", (arg,)
        ).fetchall()
        label = f"sends for {arg}"

    else:
        rows = conn.execute(
            base_query + " ORDER BY s.sent_at DESC LIMIT 20"
        ).fetchall()
        label = "last 20 sends"

    db.close()

    print(f"\n── {label} ({len(rows)} found) ──")

    if not rows:
        print("  No send history found.")
        return

    for row in rows:
        print_log(row)

    # Summary stats
    total   = len(rows)
    success = sum(1 for r in rows if r["status"] == "success")
    skipped = sum(1 for r in rows if r["status"] == "skipped")
    failed  = total - success - skipped

    print(f"\nSummary: {total} total — {success} succeeded, {failed} failed, {skipped} skipped")


if __name__ == "__main__":
    main()
