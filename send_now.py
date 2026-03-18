"""
Manually trigger a weather broadcast for a specific timezone, phone, or name.
Useful for testing without waiting for the 7:30 AM scheduler.

Usage:
    python3 send_now.py                          # sends for all active timezones
    python3 send_now.py <name>                   # sends for a user by name
    python3 send_now.py +<country_code><number>  # sends for a specific phone number
    python3 send_now.py America/Los_Angeles      # sends for a specific timezone
"""

import os
import sys

from dotenv import load_dotenv
load_dotenv()

from database.db import Database
from scheduler import run_timezone_job, run_user_job

DB_PATH = os.getenv("DB_PATH", "./data/weather_broadcast.db")


def _print_sandbox_reminder(unapproved_users: list):
    """Print a reminder for any users who have not yet opted in to the sandbox."""
    if not unapproved_users:
        return

    sandbox_from    = os.getenv("TWILIO_WHATSAPP_FROM", "")
    sandbox_number  = sandbox_from.replace("whatsapp:", "")
    sandbox_keyword = os.getenv("TWILIO_SANDBOX_KEYWORD", "<your_sandbox_keyword>")

    print("\n⚠️  Sandbox opt-in required for the following user(s):")
    for u in unapproved_users:
        label = f"{u.name} ({u.phone})" if u.name else u.phone
        print(f"   • {label}")

    print(
        f"\n   Each user must send this WhatsApp message to {sandbox_number or '<TWILIO_WHATSAPP_FROM>'}:"
        f"\n\n       join {sandbox_keyword}"
        f"\n\n   Once they've sent it, run:"
        f"\n       python3 opt_in_user.py <name or phone>"
        f"\n   to mark them as opted in.\n"
    )


def send_for_timezone(timezone: str):
    print(f"\n▶ Triggering send for timezone: {timezone}")
    run_timezone_job(timezone, DB_PATH)


def send_for_phone(phone: str):
    db = Database(DB_PATH)
    db.init()
    user = db.get_user_by_phone(phone)
    unapproved = [u for u in db.get_unapproved_users() if u.phone == phone]
    db.close()

    if not user:
        print(f"✗ No user found with phone {phone}")
        sys.exit(1)

    print(f"  Found user — timezone: {user.timezone}, units: {user.unit_system}")
    run_user_job(user, DB_PATH)
    _print_sandbox_reminder(unapproved)


def send_for_name(name: str):
    db = Database(DB_PATH)
    db.init()
    conn = db.connect()
    row = conn.execute(
        "SELECT * FROM users WHERE LOWER(name) = LOWER(?) AND active = 1", (name,)
    ).fetchone()

    if not row:
        db.close()
        print(f"✗ No active user found with name '{name}'")
        print("  Tip: check the name matches exactly what's in the database")
        sys.exit(1)

    from database.db import Database as DB
    user = DB._row_to_user(row)
    unapproved = [u for u in db.get_unapproved_users() if u.phone == user.phone]
    db.close()

    print(f"  Found {user.name} ({user.phone}) — {user.timezone} / {user.unit_system}")
    run_user_job(user, DB_PATH)
    _print_sandbox_reminder(unapproved)


def send_for_all():
    db = Database(DB_PATH)
    db.init()
    timezones  = db.get_all_timezones()
    unapproved = db.get_unapproved_users()
    db.close()

    if not timezones:
        print("✗ No active users in database")
        sys.exit(1)

    print(f"  Found {len(timezones)} active timezone(s): {', '.join(timezones)}")
    for tz in timezones:
        send_for_timezone(tz)

    _print_sandbox_reminder(unapproved)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        send_for_all()
    elif sys.argv[1].startswith("+"):
        send_for_phone(sys.argv[1])
    elif "/" in sys.argv[1]:
        send_for_timezone(sys.argv[1])
    else:
        send_for_name(sys.argv[1])
