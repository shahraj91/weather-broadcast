"""
Seed the database with test users spread across global timezones and unit systems.
Run with:  python3 database/seed.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from database.db import Database
from database.models import User

TEST_USERS = [
    # (phone, lat, lon, timezone, unit_system, country_code, name, label)
    # Phone numbers use officially reserved / fictional ranges (NANP 555-01xx, UK Ofcom 07700 900xxx, etc.)
    ("+14155550101",  37.7600,  -122.4000, "America/Los_Angeles", "imperial", "US", "Test User 1",  "San Francisco, USA"),
    ("+12125550102",  40.7100,   -74.0000, "America/New_York",    "imperial", "US", "Test User 2",  "New York, USA"),
    ("+447700900101", 51.5000,    -0.1200, "Europe/London",       "metric",   "GB", "Test User 3",  "London, UK"),
    ("+33100000001",  48.8500,    2.3500,  "Europe/Paris",        "metric",   "FR", "Test User 4",  "Paris, France"),
    ("+819000000001", 35.6700,  139.6500,  "Asia/Tokyo",          "metric",   "JP", "Test User 5",  "Tokyo, Japan"),
    ("+610400000001", -33.8700, 151.2000,  "Australia/Sydney",    "metric",   "AU", "Test User 6",  "Sydney, Australia"),
    ("+551100000001", -23.5500,  -46.6300, "America/Sao_Paulo",   "metric",   "BR", "Test User 7",  "São Paulo, Brazil"),
    ("+27100000001",  -33.9200,   18.4200, "Africa/Johannesburg", "metric",   "ZA", "Test User 8",  "Cape Town, South Africa"),
    ("+971500000001",  25.2000,   55.2700, "Asia/Dubai",          "metric",   "AE", "Test User 9",  "Dubai, UAE"),
    ("+911234560001",  28.6100,   77.2100, "Asia/Kolkata",        "metric",   "IN", "Test User 10", "New Delhi, India"),
]


def seed(db_path: str = None):
    path = db_path or os.getenv("DB_PATH", "./data/weather_broadcast.db")
    db = Database(path)
    db.init()

    added = 0
    skipped = 0

    for phone, lat, lon, tz, units, cc, name, label in TEST_USERS:
        existing = db.get_user_by_phone(phone)
        if existing:
            print(f"  SKIP  {label} ({phone}) — already exists")
            skipped += 1
            continue

        user = User(phone=phone, lat=lat, lon=lon, timezone=tz,
                    unit_system=units, country_code=cc, name=name)
        db.add_user(user)
        print(f"  ADD   {label} ({phone}) — {tz} / {units}")
        added += 1

    print(f"\nDone. {added} added, {skipped} skipped.")
    db.close()


if __name__ == "__main__":
    seed()
