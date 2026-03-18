"""
Mark a user as having opted in to the Twilio WhatsApp sandbox.

The Twilio sandbox requires every recipient to send a join code before
messages can be delivered. Run this script after a user has sent their
join code to mark them as opted in.

Usage:
    python3 opt_in_user.py <name>                # mark opted in by name
    python3 opt_in_user.py +<country_code><number>  # mark opted in by phone
    python3 opt_in_user.py --list                # show all users and opt-in status
"""

import os
import sys

from dotenv import load_dotenv
load_dotenv()

from database.db import Database

DB_PATH = os.getenv("DB_PATH", "./data/weather_broadcast.db")


def _opt_in_by_phone(db: Database, phone: str):
    user = db.get_user_by_phone(phone)
    if not user:
        print(f"✗ No user found with phone {phone}")
        sys.exit(1)

    if user.sandbox_opted_in:
        label = f"{user.name} ({user.phone})" if user.name else user.phone
        print(f"  {label} is already marked as opted in.")
        return

    success = db.set_sandbox_opted_in(phone)
    if success:
        label = f"{user.name} ({user.phone})" if user.name else user.phone
        print(f"  ✓ {label} — sandbox_opted_in set to True")
        print(f"    Timezone: {user.timezone}  |  Units: {user.unit_system}")
    else:
        print(f"✗ Update failed for {phone}")
        sys.exit(1)


def _opt_in_by_name(db: Database, name: str):
    conn = db.connect()
    rows = conn.execute(
        "SELECT * FROM users WHERE LOWER(name) = LOWER(?) AND active = 1", (name,)
    ).fetchall()

    if not rows:
        print(f"✗ No active user found with name '{name}'")
        sys.exit(1)

    if len(rows) > 1:
        print(f"  Multiple users match '{name}'. Use phone number to be specific:")
        for r in rows:
            print(f"   • {r['phone']}")
        sys.exit(1)

    from database.db import Database as DB
    user = DB._row_to_user(rows[0])
    _opt_in_by_phone(db, user.phone)


def _list_all(db: Database):
    conn = db.connect()
    rows = conn.execute("SELECT * FROM users ORDER BY sandbox_opted_in ASC, id ASC").fetchall()

    if not rows:
        print("  No users in database.")
        return

    opted_in    = [r for r in rows if r["sandbox_opted_in"]]
    not_opted   = [r for r in rows if not r["sandbox_opted_in"]]

    print(f"\n── Sandbox opt-in status ({len(rows)} user(s)) ──\n")

    if not_opted:
        print("  ⚠️  NOT OPTED IN:")
        for r in not_opted:
            status = "active" if r["active"] else "inactive"
            label  = r["name"] or "—"
            print(f"   ✗  {label:<20} {r['phone']:<20} [{status}]")

    if opted_in:
        print("\n  ✓  OPTED IN:")
        for r in opted_in:
            status = "active" if r["active"] else "inactive"
            label  = r["name"] or "—"
            print(f"   ✓  {label:<20} {r['phone']:<20} [{status}]")

    sandbox_from    = os.getenv("TWILIO_WHATSAPP_FROM", "").replace("whatsapp:", "")
    sandbox_keyword = os.getenv("TWILIO_SANDBOX_KEYWORD", "<your_sandbox_keyword>")

    if not_opted:
        print(
            f"\n  To opt in, each user must send this WhatsApp message"
            f" to {sandbox_from or '<TWILIO_WHATSAPP_FROM>'}:"
            f"\n\n      join {sandbox_keyword}\n"
        )


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    db = Database(DB_PATH)
    db.init()

    try:
        arg = sys.argv[1]
        if arg == "--list":
            _list_all(db)
        elif arg.startswith("+"):
            _opt_in_by_phone(db, arg)
        else:
            _opt_in_by_name(db, arg)
    finally:
        db.close()


if __name__ == "__main__":
    main()
