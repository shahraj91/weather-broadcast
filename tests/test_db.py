"""
Tests for database/db.py
Uses a temporary SQLite database — fully isolated, no files left behind.
"""

import pytest
import sqlite3
from database.db import Database
from database.models import User, SendLog


class TestDatabaseInit:

    def test_tables_created_on_init(self, test_db):
        """DB-init: users and send_logs tables exist after init()."""
        conn = test_db.connect()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "users" in tables
        assert "send_logs" in tables

    def test_init_is_idempotent(self, tmp_path):
        """Calling init() twice does not raise or duplicate tables."""
        db = Database(str(tmp_path / "test.db"))
        db.init()
        db.init()   # should be a no-op
        db.close()


class TestAddUser:

    def test_db01_add_valid_user(self, test_db, imperial_user):
        """DB-01: New user is persisted and returns an integer id."""
        user_id = test_db.add_user(imperial_user)
        assert isinstance(user_id, int)
        assert user_id > 0

    def test_db02_duplicate_phone_raises(self, test_db, imperial_user):
        """DB-02: Adding the same phone twice raises IntegrityError."""
        test_db.add_user(imperial_user)
        with pytest.raises(sqlite3.IntegrityError):
            test_db.add_user(imperial_user)

    def test_user_is_retrievable_after_add(self, test_db, imperial_user):
        """Added user can be fetched by phone."""
        test_db.add_user(imperial_user)
        fetched = test_db.get_user_by_phone(imperial_user.phone)
        assert fetched is not None
        assert fetched.phone == imperial_user.phone
        assert fetched.timezone == imperial_user.timezone
        assert fetched.unit_system == imperial_user.unit_system
        assert fetched.name == imperial_user.name  # name field round-trips correctly

    def test_name_field_is_optional(self, test_db):
        """User with name=None is stored and retrieved correctly."""
        user = User(
            phone="+19995550001",
            lat=37.7749,
            lon=-122.4194,
            timezone="America/Los_Angeles",
            unit_system="imperial",
        )
        test_db.add_user(user)
        fetched = test_db.get_user_by_phone(user.phone)
        assert fetched is not None
        assert fetched.name is None


class TestGetUsersByTimezone:

    def test_db03_returns_only_matching_active_users(self, seeded_db, imperial_user, metric_user):
        """DB-03: get_users_by_timezone returns only active users in that timezone."""
        la_users = seeded_db.get_users_by_timezone("America/Los_Angeles")
        phones = [u.phone for u in la_users]
        assert imperial_user.phone in phones
        assert metric_user.phone not in phones

    def test_db06_empty_result_for_unknown_timezone(self, test_db):
        """DB-06: Querying an unknown timezone returns empty list."""
        result = test_db.get_users_by_timezone("Nowhere/Atlantis")
        assert result == []

    def test_inactive_users_excluded(self, test_db, imperial_user):
        """Inactive users are not returned by timezone queries."""
        test_db.add_user(imperial_user)
        test_db.deactivate_user(imperial_user.phone)
        result = test_db.get_users_by_timezone(imperial_user.timezone)
        assert result == []


class TestDeactivateUser:

    def test_db04_deactivate_sets_active_false(self, test_db, imperial_user):
        """DB-04: Deactivated user has active=False and is excluded from queries."""
        test_db.add_user(imperial_user)
        success = test_db.deactivate_user(imperial_user.phone)
        assert success is True
        fetched = test_db.get_user_by_phone(imperial_user.phone)
        assert fetched.active is False

    def test_deactivate_nonexistent_returns_false(self, test_db):
        """Deactivating a phone that doesn't exist returns False."""
        result = test_db.deactivate_user("+19999999999")
        assert result is False


class TestGetAllTimezones:

    def test_db05_returns_distinct_timezones(self, seeded_db):
        """DB-05: get_all_timezones returns distinct list of active timezones."""
        timezones = seeded_db.get_all_timezones()
        # Two users in two different timezones
        assert "America/Los_Angeles" in timezones
        assert "Europe/London" in timezones
        # No duplicates
        assert len(timezones) == len(set(timezones))

    def test_db06_empty_db_returns_empty_list(self, test_db):
        """DB-06: Empty database returns empty list from get_all_timezones."""
        result = test_db.get_all_timezones()
        assert result == []


class TestLogSend:

    def test_db07_log_successful_send(self, test_db, imperial_user):
        """DB-07: Successful send log is written with correct fields."""
        user_id = test_db.add_user(imperial_user)
        log = SendLog(user_id=user_id, status="success", message_sid="SM123abc")
        test_db.log_send(log)

        conn = test_db.connect()
        row = conn.execute(
            "SELECT * FROM send_logs WHERE user_id = ?", (user_id,)
        ).fetchone()

        assert row["status"] == "success"
        assert row["message_sid"] == "SM123abc"
        assert row["retryable"] == 0

    def test_db08_log_failed_send(self, test_db, imperial_user):
        """DB-08: Failed send log is written with retryable=True."""
        user_id = test_db.add_user(imperial_user)
        log = SendLog(
            user_id=user_id,
            status="failed",
            error="Network timeout",
            retryable=True,
        )
        test_db.log_send(log)

        conn = test_db.connect()
        row = conn.execute(
            "SELECT * FROM send_logs WHERE user_id = ?", (user_id,)
        ).fetchone()

        assert row["status"] == "failed"
        assert row["error"] == "Network timeout"
        assert row["retryable"] == 1


class TestSandboxOptIn:

    def test_sandbox_opted_in_defaults_to_false(self, test_db, imperial_user):
        """New users have sandbox_opted_in=False by default."""
        test_db.add_user(imperial_user)
        fetched = test_db.get_user_by_phone(imperial_user.phone)
        assert fetched.sandbox_opted_in is False

    def test_set_sandbox_opted_in_marks_user_true(self, test_db, imperial_user):
        """set_sandbox_opted_in() sets sandbox_opted_in=True for the user."""
        test_db.add_user(imperial_user)
        result = test_db.set_sandbox_opted_in(imperial_user.phone)
        assert result is True
        fetched = test_db.get_user_by_phone(imperial_user.phone)
        assert fetched.sandbox_opted_in is True

    def test_set_sandbox_opted_in_nonexistent_returns_false(self, test_db):
        """set_sandbox_opted_in() returns False for an unknown phone."""
        assert test_db.set_sandbox_opted_in("+19999999999") is False

    def test_add_user_with_opted_in_true(self, test_db):
        """User added with sandbox_opted_in=True is persisted correctly."""
        user = User(
            phone="+12125550199",
            lat=40.71,
            lon=-74.00,
            timezone="America/New_York",
            unit_system="imperial",
            sandbox_opted_in=True,
        )
        test_db.add_user(user)
        fetched = test_db.get_user_by_phone(user.phone)
        assert fetched.sandbox_opted_in is True

    def test_get_unapproved_users_returns_not_opted_in(self, test_db, imperial_user, metric_user):
        """get_unapproved_users() returns active users where sandbox_opted_in=False."""
        test_db.add_user(imperial_user)   # sandbox_opted_in=False (default)
        test_db.add_user(metric_user)
        test_db.set_sandbox_opted_in(metric_user.phone)  # metric_user now opted in

        unapproved = test_db.get_unapproved_users()
        phones = [u.phone for u in unapproved]
        assert imperial_user.phone in phones
        assert metric_user.phone not in phones

    def test_get_unapproved_users_excludes_inactive(self, test_db, imperial_user):
        """get_unapproved_users() does not include inactive users."""
        test_db.add_user(imperial_user)
        test_db.deactivate_user(imperial_user.phone)
        assert test_db.get_unapproved_users() == []

    def test_set_opted_in_idempotent(self, test_db, imperial_user):
        """Calling set_sandbox_opted_in() twice does not raise."""
        test_db.add_user(imperial_user)
        test_db.set_sandbox_opted_in(imperial_user.phone)
        test_db.set_sandbox_opted_in(imperial_user.phone)   # second call is safe
        fetched = test_db.get_user_by_phone(imperial_user.phone)
        assert fetched.sandbox_opted_in is True


class TestContextManager:

    def test_context_manager_closes_connection(self, tmp_path):
        """Database works as a context manager and closes cleanly."""
        db_path = str(tmp_path / "ctx.db")
        with Database(db_path) as db:
            db.init()
            assert db._conn is not None
        assert db._conn is None
