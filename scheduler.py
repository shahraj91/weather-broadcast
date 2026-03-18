"""
Scheduler — registers one APScheduler cron job per unique timezone.
Each job fires at 07:30 in its local timezone, fetches weather for all
users in that timezone, formats a message via Llama, and broadcasts via Twilio.
"""

import logging
from zoneinfo import ZoneInfo  # stdlib in Python 3.9+

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from database.db import Database
from database.models import SendLog
from weather.fetcher import get_forecast, WeatherFetchError
from messaging.formatter import generate, FormatterError
from messaging import broadcaster
from messaging.broadcaster import BroadcasterError, SandboxOptInError
from conversation.risk_engine import check_risks, format_risk_alert

logger = logging.getLogger(__name__)

SEND_HOUR   = 7
SEND_MINUTE = 30


def _send_to_user(user, db: Database):
    """
    Fetch weather, generate a message, send it, and log the result for a single user.
    All exceptions are caught and logged; nothing is re-raised.
    """
    try:
        weather = get_forecast(
            lat=user.lat,
            lon=user.lon,
            unit_system=user.unit_system,
            timezone=user.timezone,
        )
        message = generate(weather, user=user)
        sid = broadcaster.send_to_user(user, message)
        db.log_send(SendLog(
            user_id=user.id,
            status="success",
            message_sid=sid,
            message_body=message,
        ))
        logger.info("✓ Sent to %s (SID: %s)", user.phone, sid)

        # Risk alert — sent as a separate message after the regular morning message
        risks = check_risks(user, weather)
        if risks:
            try:
                alert = format_risk_alert(user, weather, risks)
                alert_sid = broadcaster.send_to_user(user, alert)
                db.log_send(SendLog(
                    user_id=user.id,
                    status="risk_alert",
                    message_sid=alert_sid,
                    message_body=alert,
                ))
                logger.info("⚠ Risk alert sent to %s (SID: %s)", user.phone, alert_sid)
            except Exception as e:
                logger.error("Risk alert failed for user %s: %s", user.id, e)

    except SandboxOptInError:
        db.log_send(SendLog(
            user_id=user.id,
            status="skipped",
            error="sandbox_opt_in_required",
            retryable=False,
        ))

    except WeatherFetchError as e:
        logger.error("Weather fetch failed for user %s: %s", user.id, e)
        db.log_send(SendLog(
            user_id=user.id,
            status="failed",
            error=f"WeatherFetchError: {e}",
            retryable=True,
        ))

    except FormatterError as e:
        logger.error("Formatter failed for user %s: %s", user.id, e)
        db.log_send(SendLog(
            user_id=user.id,
            status="failed",
            error=f"FormatterError: {e}",
            retryable=True,
        ))

    except BroadcasterError as e:
        logger.error("Broadcast failed for user %s: %s", user.id, e)
        db.log_send(SendLog(
            user_id=user.id,
            status="failed",
            error=f"BroadcasterError: {e}",
            retryable=True,
        ))

    except Exception as e:
        logger.exception("Unexpected error for user %s: %s", user.id, e)
        db.log_send(SendLog(
            user_id=user.id,
            status="failed",
            error=f"UnexpectedError: {e}",
            retryable=False,
        ))


def run_user_job(user, db_path: str):
    """Send a weather message to a single user. Used by send_now.py for name/phone lookups."""
    logger.info("▶ Manual send for user: %s", user.phone)
    db = Database(db_path)
    try:
        _send_to_user(user, db)
    finally:
        db.close()
        logger.info("◀ Manual send complete for user: %s", user.phone)


def run_timezone_job(timezone: str, db_path: str):
    """
    Called by APScheduler at 07:30 for a specific timezone.
    Fetches weather + sends message to every active user in that timezone.
    """
    logger.info("▶ Job started for timezone: %s", timezone)
    db = Database(db_path)

    try:
        users = db.get_users_by_timezone(timezone)
        if not users:
            logger.info("No active users in %s — skipping", timezone)
            return

        logger.info("Processing %d user(s) in %s", len(users), timezone)

        for user in users:
            _send_to_user(user, db)

    finally:
        db.close()
        logger.info("◀ Job complete for timezone: %s", timezone)


class WeatherScheduler:
    """
    Manages APScheduler jobs — one per unique timezone in the database.
    Supports both blocking (production) and background (testing) modes.
    """

    def __init__(self, db_path: str, blocking: bool = True):
        self.db_path  = db_path
        self.blocking = blocking
        self._scheduler = BlockingScheduler() if blocking else BackgroundScheduler()
        self._registered_timezones: set = set()

    def _register_timezone(self, timezone: str):
        """Add a cron job for a timezone if not already registered."""
        if timezone in self._registered_timezones:
            return

        try:
            # Validate timezone
            ZoneInfo(timezone)
        except Exception:
            logger.warning("Invalid timezone '%s' — skipping", timezone)
            return

        job_id = f"weather_{timezone.replace('/', '_')}"

        self._scheduler.add_job(
            func=run_timezone_job,
            trigger=CronTrigger(
                hour=SEND_HOUR,
                minute=SEND_MINUTE,
                timezone=timezone,
            ),
            id=job_id,
            name=f"Weather broadcast — {timezone}",
            kwargs={"timezone": timezone, "db_path": self.db_path},
            replace_existing=True,
            misfire_grace_time=300,   # Allow up to 5 min late if system was sleeping
        )

        self._registered_timezones.add(timezone)
        logger.info("Registered job for timezone: %s (07:%02d local)", timezone, SEND_MINUTE)

    def load_timezones_from_db(self):
        """Read all active timezones from the DB and register jobs."""
        db = Database(self.db_path)
        try:
            timezones = db.get_all_timezones()
        finally:
            db.close()

        if not timezones:
            logger.warning("No active users found in database — no jobs registered")
            return

        for tz in timezones:
            self._register_timezone(tz)

        logger.info(
            "Loaded %d timezone(s): %s",
            len(timezones), ", ".join(sorted(timezones))
        )

    def add_timezone(self, timezone: str):
        """Dynamically register a new timezone job (e.g. when a new user is added)."""
        self._register_timezone(timezone)

    def start(self):
        """Load timezones from DB and start the scheduler."""
        self.load_timezones_from_db()

        job_count = len(self._registered_timezones)
        if job_count == 0:
            logger.error("No jobs to schedule — exiting")
            return

        logger.info(
            "Starting scheduler with %d job(s). "
            "Messages will be sent at %02d:%02d in each local timezone.",
            job_count, SEND_HOUR, SEND_MINUTE
        )

        try:
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped")

    def stop(self):
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    @property
    def registered_timezones(self) -> set:
        return set(self._registered_timezones)
