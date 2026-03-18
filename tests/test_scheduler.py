"""
Tests for scheduler.py
Uses BackgroundScheduler mode and mocked job execution — no blocking.
"""

import pytest
from unittest.mock import patch, MagicMock, call
from database.models import User
from scheduler import WeatherScheduler, run_timezone_job


class TestWeatherScheduler:

    def test_sc01_three_timezones_create_three_jobs(self, tmp_path):
        """SC-01: 3 users in 3 different timezones produce 3 separate cron jobs."""
        db_path = str(tmp_path / "test.db")

        from database.db import Database
        db = Database(db_path)
        db.init()
        for phone, tz in [
            ("+14155550001", "America/New_York"),
            ("+14155550002", "Europe/London"),
            ("+14155550003", "Asia/Tokyo"),
        ]:
            db.add_user(User(phone=phone, lat=0, lon=0, timezone=tz, unit_system="metric"))
        db.close()

        scheduler = WeatherScheduler(db_path=db_path, blocking=False)
        scheduler.load_timezones_from_db()

        assert len(scheduler.registered_timezones) == 3
        assert "America/New_York" in scheduler.registered_timezones
        assert "Europe/London" in scheduler.registered_timezones
        assert "Asia/Tokyo" in scheduler.registered_timezones

    def test_sc02_five_users_same_timezone_one_job(self, tmp_path):
        """SC-02: 5 users in the same timezone produce exactly 1 cron job."""
        db_path = str(tmp_path / "test.db")

        from database.db import Database
        db = Database(db_path)
        db.init()
        for i in range(5):
            db.add_user(User(
                phone=f"+1415555000{i}",
                lat=0, lon=0,
                timezone="America/Chicago",
                unit_system="metric"
            ))
        db.close()

        scheduler = WeatherScheduler(db_path=db_path, blocking=False)
        scheduler.load_timezones_from_db()

        assert len(scheduler.registered_timezones) == 1
        assert "America/Chicago" in scheduler.registered_timezones

    def test_sc03_add_timezone_registers_new_job(self, tmp_path):
        """SC-03: add_timezone() dynamically registers a new job."""
        db_path = str(tmp_path / "empty.db")
        from database.db import Database
        Database(db_path).init()

        scheduler = WeatherScheduler(db_path=db_path, blocking=False)
        assert len(scheduler.registered_timezones) == 0

        scheduler.add_timezone("Australia/Melbourne")
        assert "Australia/Melbourne" in scheduler.registered_timezones

    def test_sc03_adding_duplicate_timezone_is_idempotent(self, tmp_path):
        """SC-03: Adding the same timezone twice doesn't create duplicate jobs."""
        db_path = str(tmp_path / "empty.db")
        from database.db import Database
        Database(db_path).init()

        scheduler = WeatherScheduler(db_path=db_path, blocking=False)
        scheduler.add_timezone("Europe/Paris")
        scheduler.add_timezone("Europe/Paris")

        assert len(scheduler.registered_timezones) == 1

    def test_invalid_timezone_is_skipped(self, tmp_path):
        """Invalid IANA timezone string is logged and skipped gracefully."""
        db_path = str(tmp_path / "empty.db")
        from database.db import Database
        Database(db_path).init()

        scheduler = WeatherScheduler(db_path=db_path, blocking=False)
        scheduler.add_timezone("Nowhere/Atlantis")

        assert len(scheduler.registered_timezones) == 0

    def test_empty_db_registers_no_jobs(self, tmp_path):
        """Empty database results in zero registered jobs."""
        db_path = str(tmp_path / "empty.db")
        from database.db import Database
        Database(db_path).init()

        scheduler = WeatherScheduler(db_path=db_path, blocking=False)
        scheduler.load_timezones_from_db()

        assert len(scheduler.registered_timezones) == 0


class TestRunTimezoneJob:

    def test_sc04_job_calls_send_for_each_user(self, tmp_path, imperial_user, metric_user):
        """SC-04: Job calls broadcaster.send_to_user once per active opted-in user."""
        db_path = str(tmp_path / "test.db")

        from database.db import Database
        db = Database(db_path)
        db.init()
        # Both users must be opted in for send_to_user to proceed
        opted_in_user1 = User(
            phone=imperial_user.phone,
            lat=imperial_user.lat, lon=imperial_user.lon,
            timezone=imperial_user.timezone,
            unit_system="imperial",
            sandbox_opted_in=True,
        )
        opted_in_user2 = User(
            phone=metric_user.phone,
            lat=metric_user.lat, lon=metric_user.lon,
            timezone=imperial_user.timezone,   # same tz as imperial_user
            unit_system="metric",
            sandbox_opted_in=True,
        )
        db.add_user(opted_in_user1)
        db.add_user(opted_in_user2)
        db.close()

        with patch("scheduler.get_forecast") as mock_weather, \
             patch("scheduler.generate") as mock_gen, \
             patch("scheduler.broadcaster.send_to_user") as mock_send:

            mock_weather.return_value = {
                "temp_max": 72, "temp_min": 55, "condition": "Clear sky",
                "wind_speed": 10, "humidity": 60,
                "unit_system": "imperial", "temp_unit": "°F", "wind_unit": "mph",
            }
            mock_gen.return_value = "Good morning! 🌟 Fun Fact: The sky is blue."
            mock_send.return_value = "SM001"

            run_timezone_job(imperial_user.timezone, db_path)

        assert mock_send.call_count == 2

    def test_sc05_inactive_user_is_skipped(self, tmp_path, imperial_user):
        """SC-05: Deactivated user is not sent a message."""
        db_path = str(tmp_path / "test.db")

        from database.db import Database
        db = Database(db_path)
        db.init()
        db.add_user(imperial_user)
        db.deactivate_user(imperial_user.phone)
        db.close()

        with patch("scheduler.get_forecast") as mock_weather, \
             patch("scheduler.generate") as mock_gen, \
             patch("scheduler.broadcaster.send_to_user") as mock_send:

            run_timezone_job(imperial_user.timezone, db_path)

        mock_send.assert_not_called()

    def test_weather_fetch_error_logs_failure_and_continues(self, tmp_path, imperial_user, metric_user):
        """Weather fetch error for one user doesn't stop processing others."""
        db_path = str(tmp_path / "test.db")

        from database.db import Database
        from weather.fetcher import WeatherFetchError
        db = Database(db_path)
        db.init()
        # Two users in same timezone
        user2 = User(
            phone=metric_user.phone, lat=metric_user.lat, lon=metric_user.lon,
            timezone=imperial_user.timezone, unit_system="metric"
        )
        db.add_user(imperial_user)
        db.add_user(user2)
        db.close()

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise WeatherFetchError("API down")
            return {
                "temp_max": 22, "temp_min": 13, "condition": "Clear sky",
                "wind_speed": 10, "humidity": 60,
                "unit_system": "metric", "temp_unit": "°C", "wind_unit": "km/h",
            }

        with patch("scheduler.get_forecast", side_effect=side_effect), \
             patch("scheduler.generate", return_value="Msg 🌟 Fun Fact: Cool!"), \
             patch("scheduler.broadcaster.send_to_user", return_value="SM001"):

            run_timezone_job(imperial_user.timezone, db_path)

        # Second user should still be sent a message
        assert call_count == 2
