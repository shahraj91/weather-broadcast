"""
Weather Broadcast System — Entry Point
Run with: python3 main.py
"""

import os
import sys
import logging

from dotenv import load_dotenv
load_dotenv()

# ── Logging setup ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("weather_broadcast.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ── Imports ───────────────────────────────────────────────────
from database.db import Database
from scheduler import WeatherScheduler


def main():
    db_path = os.getenv("DB_PATH", "./data/weather_broadcast.db")

    # Ensure DB and tables exist
    db = Database(db_path)
    db.init()
    db.close()

    logger.info("=" * 60)
    logger.info("  ☀️  Weather Broadcast System starting up")
    logger.info("=" * 60)

    scheduler = WeatherScheduler(db_path=db_path, blocking=True)
    scheduler.start()   # Blocks until Ctrl+C


if __name__ == "__main__":
    main()
