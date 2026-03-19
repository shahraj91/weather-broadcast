"""
Weather Broadcast System — Entry Point
Run with: python3 main.py
"""

import os
import sys
import logging
import threading

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
from webhook import app as flask_app
from utils.log import structured_log
from utils.alerting import check_ollama_health, send_admin_alert


def main():
    db_path         = os.getenv("DB_PATH", "./data/weather_broadcast.db")
    webhook_enabled = os.getenv("WEBHOOK_ENABLED", "false").lower() == "true"
    webhook_port    = int(os.getenv("WEBHOOK_PORT", "5000"))

    # Ensure DB and tables exist
    db = Database(db_path)
    db.init()
    timezones = db.get_all_timezones() or []
    db.close()

    logger.info("=" * 60)
    logger.info("  ☀️  Weather Broadcast System starting up")
    logger.info("=" * 60)

    # Structured startup log
    structured_log(
        "startup",
        timezones=sorted(timezones),
        timezone_count=len(timezones),
        webhook_enabled=webhook_enabled,
        safety_check_enabled=os.getenv("SAFETY_CHECK_ENABLED", "true").lower() == "true",
        hallucination_check_enabled=os.getenv("HALLUCINATION_CHECK_ENABLED", "true").lower() == "true",
    )

    # Ollama health check
    if not check_ollama_health():
        structured_log("ollama_unreachable", level="ERROR",
                       detail="Ollama is unreachable at startup — static fallback will be used")
        send_admin_alert(
            "⚠️ System Alert: Ollama is unreachable at startup. "
            "Weather messages will use static fallback until resolved."
        )
    else:
        logger.info("Ollama health check passed")

    if webhook_enabled:
        flask_thread = threading.Thread(
            target=lambda: flask_app.run(host="0.0.0.0", port=webhook_port),
            daemon=True,
        )
        flask_thread.start()
        logger.info("Webhook listening on http://0.0.0.0:%d/webhook", webhook_port)
    else:
        logger.info("Webhook disabled — set WEBHOOK_ENABLED=true to enable")

    scheduler = WeatherScheduler(db_path=db_path, blocking=True)
    scheduler.start()   # Blocks until Ctrl+C


if __name__ == "__main__":
    main()
