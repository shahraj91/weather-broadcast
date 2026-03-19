"""
Scheduler — registers one APScheduler cron job per unique timezone.
Each job fires at 06:30 in its local timezone, fetches weather for all
users in that timezone, formats a message via Llama, and broadcasts via Twilio.
"""

import logging
import time
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
from utils.pii import mask_phone
from utils.log import structured_log
from utils.metrics import increment

logger = logging.getLogger(__name__)

SEND_HOUR   = 6
SEND_MINUTE = 30

WEATHER_FETCH_RETRIES    = 3   # total attempts (1 initial + 2 retries)
WEATHER_FETCH_RETRY_DELAY = 30  # seconds between attempts


def _fetch_with_retry(user) -> dict:
    """
    Call get_forecast() with up to WEATHER_FETCH_RETRIES attempts.
    Sleeps WEATHER_FETCH_RETRY_DELAY seconds between attempts.
    Re-raises WeatherFetchError if all attempts fail.
    """
    last_error = None
    for attempt in range(1, WEATHER_FETCH_RETRIES + 1):
        try:
            return get_forecast(
                lat=user.lat,
                lon=user.lon,
                unit_system=user.unit_system,
                timezone=user.timezone,
            )
        except WeatherFetchError as e:
            last_error = e
            if attempt < WEATHER_FETCH_RETRIES:
                logger.warning(
                    "Weather fetch failed (attempt %d/%d) for user %s: %s — retrying in %ds",
                    attempt, WEATHER_FETCH_RETRIES, user.id, e, WEATHER_FETCH_RETRY_DELAY,
                )
                time.sleep(WEATHER_FETCH_RETRY_DELAY)
            else:
                logger.error(
                    "Weather fetch failed (attempt %d/%d) for user %s: %s — giving up",
                    attempt, WEATHER_FETCH_RETRIES, user.id, e,
                )
    raise last_error


def _send_to_user(user, db: Database) -> str:
    """
    Fetch weather, generate a message, send it, and log the result for a single user.
    All exceptions are caught and logged; nothing is re-raised.
    Returns 'success', 'failed', or 'skipped'.
    """
    try:
        weather = _fetch_with_retry(user)
        message = generate(weather, user=user)
        sid = broadcaster.send_to_user(user, message)
        db.log_send(SendLog(
            user_id=user.id,
            status="success",
            message_sid=sid,
            message_body=message,
        ))
        increment("messages_sent_total")
        structured_log(
            "message_sent",
            user=mask_phone(user.phone),
            timezone=getattr(user, "timezone", ""),
            status="success",
            sid=sid,
        )
        logger.info("✓ Sent to %s (SID: %s)", mask_phone(user.phone), sid)

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
                logger.info("⚠ Risk alert sent to %s (SID: %s)", mask_phone(user.phone), alert_sid)
            except Exception as e:
                logger.error("Risk alert failed for user %s: %s", user.id, e)

        return "success"

    except SandboxOptInError:
        db.log_send(SendLog(
            user_id=user.id,
            status="skipped",
            error="sandbox_opt_in_required",
            retryable=False,
        ))
        return "skipped"

    except WeatherFetchError as e:
        logger.error("Weather fetch failed for user %s: %s", user.id, e)
        db.log_send(SendLog(
            user_id=user.id,
            status="failed",
            error=f"WeatherFetchError: {e}",
            retryable=True,
        ))
        increment("messages_failed_total")
        return "failed"

    except FormatterError as e:
        logger.error("Formatter failed for user %s: %s", user.id, e)
        db.log_send(SendLog(
            user_id=user.id,
            status="failed",
            error=f"FormatterError: {e}",
            retryable=True,
        ))
        increment("messages_failed_total")
        return "failed"

    except BroadcasterError as e:
        logger.error("Broadcast failed for user %s: %s", user.id, e)
        db.log_send(SendLog(
            user_id=user.id,
            status="failed",
            error=f"BroadcasterError: {e}",
            retryable=True,
        ))
        increment("messages_failed_total")
        return "failed"

    except Exception as e:
        logger.exception("Unexpected error for user %s: %s", user.id, e)
        db.log_send(SendLog(
            user_id=user.id,
            status="failed",
            error=f"UnexpectedError: {e}",
            retryable=False,
        ))
        increment("messages_failed_total")
        return "failed"


def run_user_job(user, db_path: str):
    """Send a weather message to a single user. Used by send_now.py for name/phone lookups."""
    logger.info("▶ Manual send for user: %s", mask_phone(user.phone))
    db = Database(db_path)
    try:
        _send_to_user(user, db)
    finally:
        db.close()
        logger.info("◀ Manual send complete for user: %s", mask_phone(user.phone))


def run_timezone_job(timezone: str, db_path: str):
    """
    Called by APScheduler at 06:30 for a specific timezone.
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

        success_count      = 0
        failed_count       = 0
        consecutive_fails  = 0

        for user in users:
            status = _send_to_user(user, db)
            if status == "success":
                success_count += 1
                consecutive_fails = 0
            elif status == "failed":
                failed_count += 1
                consecutive_fails += 1
            # skipped does not reset or increment consecutive_fails

        total = success_count + failed_count

        # Alert: too many consecutive failures in this run
        if consecutive_fails > 3:
            try:
                from utils.alerting import send_admin_alert
                send_admin_alert(
                    f"⚠️ System Alert: {consecutive_fails} consecutive send failures "
                    f"for timezone {timezone}. Check Twilio credentials and connectivity."
                )
            except Exception as e:
                logger.error("Failed to send consecutive-failure alert: %s", e)

        # Alert: fallback rate > 50% in this job run
        if total > 0 and (failed_count / total) > 0.5:
            try:
                from utils.alerting import send_admin_alert
                send_admin_alert(
                    f"⚠️ System Alert: High failure rate for {timezone} — "
                    f"{failed_count}/{total} sends failed this run."
                )
            except Exception as e:
                logger.error("Failed to send fallback-rate alert: %s", e)

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
        logger.info("Registered job for timezone: %s (06:%02d local)", timezone, SEND_MINUTE)

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
