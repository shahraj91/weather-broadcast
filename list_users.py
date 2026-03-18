"""
View users in the database.

Usage:
    python3 list_users.py              # list all active users
    python3 list_users.py --all        # include inactive users
    python3 list_users.py Raj          # search by name
    python3 list_users.py +18183573973 # search by phone
"""

import os
import sys

from dotenv import load_dotenv
load_dotenv()

from database.db import Database

DB_PATH = os.getenv("DB_PATH", "./data/weather_broadcast.db")


def print_user(row):
    name     = row["name"]   or "—"
    active   = "✓ active" if row["active"] else "✗ inactive"
    keys     = row.keys()
    opted_in = row["sandbox_opted_in"] if "sandbox_opted_in" in keys else None
    if opted_in is None:
        opted_in_str = "—"
    else:
        opted_in_str = "✓ opted in" if opted_in else "✗ not opted in"
    activity       = row["activity"]       if "activity"       in keys else None
    activity_notes = row["activity_notes"] if "activity_notes" in keys else None
    print(f"""
  ID:             {row['id']}
  Name:           {name}
  Phone:          {row['phone']}
  Location:       {row['lat']}, {row['lon']}
  Timezone:       {row['timezone']}
  Units:          {row['unit_system']}
  Country:        {row['country_code'] or '—'}
  Status:         {active}
  Sandbox opt-in: {opted_in_str}
  Activity:       {activity or '—'}
  Notes:          {activity_notes or '—'}
  Added:          {row['created_at']}""")
    print("  " + "─" * 40)


def main():
    db = Database(DB_PATH)
    db.init()
    conn = db.connect()

    arg = sys.argv[1] if len(sys.argv) > 1 else None

    if arg == "--all":
        rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
        label = "all users"
    elif arg and arg.startswith("+"):
        rows = conn.execute(
            "SELECT * FROM users WHERE phone = ?", (arg,)
        ).fetchall()
        label = f"phone = {arg}"
    elif arg:
        rows = conn.execute(
            "SELECT * FROM users WHERE LOWER(name) = LOWER(?)", (arg,)
        ).fetchall()
        label = f"name = {arg}"
    else:
        rows = conn.execute(
            "SELECT * FROM users WHERE active = 1 ORDER BY id"
        ).fetchall()
        label = "active users"

    db.close()

    print(f"\n── {label} ({len(rows)} found) ──")

    if not rows:
        print("  No users found.")
        return

    for row in rows:
        print_user(row)

    print(f"\nTotal: {len(rows)} user(s)")


if __name__ == "__main__":
    main()
