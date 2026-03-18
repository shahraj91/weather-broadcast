"""
Add users to the database — via CLI args or CSV file.

CLI usage:
    python3 add_users.py --phone +<country_code><number> --lat <latitude> --lon <longitude>
    python3 add_users.py --name "<name>" --phone +<country_code><number> --lat <latitude> --lon <longitude>
    python3 add_users.py --csv

CSV format (users_to_add.csv):
    phone,lat,lon,name
    +14155552671,37.7749,-122.4194,Alex
    +447700900123,51.5074,-0.1278,Charlie
"""

import argparse
import csv
import os
import sqlite3
import sys

from dotenv import load_dotenv
load_dotenv()

from database.db import Database
from database.models import User
from utils.timezone_resolver import resolve_timezone
from utils.unit_resolver import resolve_unit_system, resolve_country_code

CSV_FILE = "users_to_add.csv"
DB_PATH  = os.getenv("DB_PATH", "./data/weather_broadcast.db")


def _build_user(
    phone: str,
    lat: float,
    lon: float,
    name: str | None,
    sandbox_opted_in: bool = False,
) -> User:
    """Resolve timezone/units from lat/lon and construct a User."""
    print(f"  Resolving timezone + units for {phone}...")
    timezone     = resolve_timezone(lat, lon)
    unit_system  = resolve_unit_system(lat, lon)
    country_code = resolve_country_code(lat, lon)
    return User(
        phone=phone,
        lat=lat,
        lon=lon,
        timezone=timezone,
        unit_system=unit_system,
        country_code=country_code,
        name=name,
        sandbox_opted_in=sandbox_opted_in,
    )


def _add_user(db: Database, user: User) -> bool:
    """Insert user into DB. Returns True on success, False on duplicate."""
    try:
        uid = db.add_user(user)
        print(f"  ✓ Added {user.phone} (ID {uid}) — {user.timezone} / {user.unit_system}")
        return True
    except sqlite3.IntegrityError:
        print(f"  ✗ {user.phone} already exists — skipped")
        return False


def add_single(
    db: Database,
    phone: str,
    lat: float,
    lon: float,
    name: str | None,
    sandbox_opted_in: bool = False,
):
    user = _build_user(phone, lat, lon, name, sandbox_opted_in=sandbox_opted_in)
    _add_user(db, user)


def add_from_csv(db: Database):
    if not os.path.exists(CSV_FILE):
        print(f"✗ Could not find {CSV_FILE} — make sure it's in the project root")
        sys.exit(1)

    added   = 0
    skipped = 0

    with open(CSV_FILE, newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            phone = row.get("phone", "").strip()
            lat   = row.get("lat",   "").strip()
            lon   = row.get("lon",   "").strip()
            name  = row.get("name",  "").strip() or None

            if not phone or not lat or not lon:
                print(f"✗ Skipped empty row: {row}")
                skipped += 1
                continue

            try:
                user = _build_user(phone, float(lat), float(lon), name)
                if _add_user(db, user):
                    added += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"  ✗ Skipped {phone} — {e}")
                skipped += 1

    print(f"\nDone — {added} added, {skipped} skipped.")


def main():
    parser = argparse.ArgumentParser(
        description="Add users to the Weather Broadcast database.",
        epilog=(
            "Examples:\n"
            '  python3 add_users.py --name "<name>" --phone +<country_code><number> --lat <latitude> --lon <longitude>\n'
            "  python3 add_users.py --phone +<country_code><number> --lat <latitude> --lon <longitude>\n"
            "  python3 add_users.py --csv"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--name",     help="Recipient's display name (optional)")
    parser.add_argument("--phone",    help="Phone number in E.164 format e.g. +<country_code><number>")
    parser.add_argument("--lat",      type=float, help="Latitude as decimal e.g. 47.6148")
    parser.add_argument("--lon",      type=float, help="Longitude as decimal e.g. -122.3470")
    parser.add_argument("--csv",      action="store_true", help=f"Import from {CSV_FILE}")
    parser.add_argument("--opted-in", action="store_true",
                        help="Mark user as already opted in to the Twilio sandbox")

    # Print help when no args are given
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    db = Database(DB_PATH)
    db.init()

    try:
        if args.csv:
            add_from_csv(db)
        else:
            # Validate required CLI fields
            missing = [f for f, v in [("--phone", args.phone), ("--lat", args.lat), ("--lon", args.lon)] if v is None]
            if missing:
                parser.error(f"The following arguments are required for CLI mode: {', '.join(missing)}")
            add_single(db, args.phone, args.lat, args.lon, args.name,
                       sandbox_opted_in=args.opted_in)
    finally:
        db.close()


if __name__ == "__main__":
    main()