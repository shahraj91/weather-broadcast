"""
Tests for conversation/handler.py
Llama HTTP calls, weather fetcher, and DB writes are all mocked.
"""

import pytest
from unittest.mock import patch, MagicMock

from database.models import User
from conversation.handler import handle


# ── Shared fixtures & helpers ──────────────────────────────────────────────

PHONE = "+14155550100"

MOCK_USER = User(
    id=1,
    phone=PHONE,
    lat=37.7749,
    lon=-122.4194,
    timezone="America/Los_Angeles",
    unit_system="metric",
    name="Alex",
)

WEATHER_STUB = {
    "temp_max":    22.0,
    "temp_min":    13.0,
    "condition":   "Partly cloudy",
    "wind_speed":  16.0,
    "humidity":    65,
    "unit_system": "metric",
    "temp_unit":   "°C",
    "wind_unit":   "km/h",
}


def _llama_resp(text: str) -> MagicMock:
    """Build a mock requests.Response returning the given Llama text."""
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {"response": text}
    return mock


def _mock_db(user=MOCK_USER) -> MagicMock:
    """Build a mock Database instance."""
    db = MagicMock()
    db.get_user_by_phone.return_value = user
    db.get_user_conversation_context.return_value = {}
    return db


# ── Tests ──────────────────────────────────────────────────────────────────

class TestHandleUnknownUser:

    def test_unknown_phone_returns_friendly_message(self):
        mock_db = _mock_db(user=None)
        with patch("conversation.handler.Database", return_value=mock_db):
            reply = handle("+19999999999", "Hello")
        assert isinstance(reply, str)
        assert len(reply) > 0
        # Should mention something about not being registered
        lower = reply.lower()
        assert any(word in lower for word in ("recognise", "recognize", "registered", "administrator", "not"))


class TestHandleWeatherQuery:

    def test_weather_query_returns_string_with_info(self):
        mock_db = _mock_db()
        with patch("conversation.handler.Database", return_value=mock_db), \
             patch("conversation.handler.get_forecast", return_value=WEATHER_STUB), \
             patch("conversation.handler.requests.post") as mock_post:
            mock_post.side_effect = [
                _llama_resp("WEATHER_QUERY"),
                _llama_resp("Today will be partly cloudy with a high of 22°C. No rain expected."),
            ]
            reply = handle(PHONE, "Will it rain today?")
        assert isinstance(reply, str)
        assert len(reply) > 0

    def test_weather_query_fetches_forecast(self):
        mock_db = _mock_db()
        with patch("conversation.handler.Database", return_value=mock_db), \
             patch("conversation.handler.get_forecast", return_value=WEATHER_STUB) as mock_fetch, \
             patch("conversation.handler.requests.post") as mock_post:
            mock_post.side_effect = [
                _llama_resp("WEATHER_QUERY"),
                _llama_resp("Partly cloudy, high of 22°C."),
            ]
            handle(PHONE, "What is the forecast?")
        mock_fetch.assert_called_once()


class TestHandleActivityUpdate:

    def test_activity_update_saves_to_db(self):
        mock_db = _mock_db()
        with patch("conversation.handler.Database", return_value=mock_db), \
             patch("conversation.handler.requests.post") as mock_post:
            mock_post.side_effect = [
                _llama_resp("ACTIVITY_UPDATE"),
                _llama_resp('{"activity": "runner", "notes": "runs every morning at 6am"}'),
            ]
            reply = handle(PHONE, "I am a runner who goes out every morning at 6am")

        mock_db.update_activity.assert_called_once_with(PHONE, "runner", "runs every morning at 6am")

    def test_activity_update_returns_confirmation(self):
        mock_db = _mock_db()
        with patch("conversation.handler.Database", return_value=mock_db), \
             patch("conversation.handler.requests.post") as mock_post:
            mock_post.side_effect = [
                _llama_resp("ACTIVITY_UPDATE"),
                _llama_resp('{"activity": "cyclist", "notes": ""}'),
            ]
            reply = handle(PHONE, "I cycle to work every day")

        assert "cyclist" in reply.lower() or "got it" in reply.lower()

    def test_activity_update_uses_test_db(self, test_db):
        """Verify DB state using test_db fixture."""
        test_db.add_user(MOCK_USER)
        # Wrap test_db so close() is a no-op (keeps connection alive for assertions)
        db_wrapper = MagicMock(wraps=test_db)
        db_wrapper.close = MagicMock()

        with patch("conversation.handler.Database", return_value=db_wrapper), \
             patch("conversation.handler.requests.post") as mock_post:
            mock_post.side_effect = [
                _llama_resp("ACTIVITY_UPDATE"),
                _llama_resp('{"activity": "farmer", "notes": "grows wheat"}'),
            ]
            handle(PHONE, "I am a farmer growing wheat")

        user = test_db.get_user_by_phone(PHONE)
        assert user.activity == "farmer"


class TestHandleWeatherNow:

    def test_weather_now_returns_current_conditions(self):
        mock_db = _mock_db()
        with patch("conversation.handler.Database", return_value=mock_db), \
             patch("conversation.handler.get_forecast", return_value=WEATHER_STUB), \
             patch("conversation.handler.requests.post") as mock_post:
            mock_post.return_value = _llama_resp("WEATHER_NOW")
            reply = handle(PHONE, "What is the weather right now?")

        assert isinstance(reply, str)
        assert len(reply) > 0
        # Should mention the condition or temperature
        assert any(word in reply for word in ("Partly cloudy", "22", "°C", "16"))


class TestHandleUnsubscribe:

    def test_unsubscribe_deactivates_user_in_db(self):
        mock_db = _mock_db()
        with patch("conversation.handler.Database", return_value=mock_db), \
             patch("conversation.handler.requests.post") as mock_post:
            mock_post.return_value = _llama_resp("UNSUBSCRIBE")
            handle(PHONE, "stop")

        mock_db.deactivate_user.assert_called_once_with(PHONE)

    def test_unsubscribe_returns_confirmation(self):
        mock_db = _mock_db()
        with patch("conversation.handler.Database", return_value=mock_db), \
             patch("conversation.handler.requests.post") as mock_post:
            mock_post.return_value = _llama_resp("UNSUBSCRIBE")
            reply = handle(PHONE, "unsubscribe")

        assert "unsubscribed" in reply.lower()

    def test_unsubscribe_uses_test_db(self, test_db):
        """Verify user is actually deactivated in test_db."""
        test_db.add_user(MOCK_USER)
        db_wrapper = MagicMock(wraps=test_db)
        db_wrapper.close = MagicMock()

        with patch("conversation.handler.Database", return_value=db_wrapper), \
             patch("conversation.handler.requests.post") as mock_post:
            mock_post.return_value = _llama_resp("UNSUBSCRIBE")
            handle(PHONE, "cancel")

        user = test_db.get_user_by_phone(PHONE)
        assert not user.active


class TestHandleGeneral:

    def test_general_returns_non_empty_string(self):
        mock_db = _mock_db()
        with patch("conversation.handler.Database", return_value=mock_db), \
             patch("conversation.handler.requests.post") as mock_post:
            mock_post.side_effect = [
                _llama_resp("GENERAL"),
                _llama_resp("That's a great question! The sky looks beautiful today."),
            ]
            reply = handle(PHONE, "Tell me something interesting")

        assert isinstance(reply, str)
        assert len(reply) > 0

    def test_general_llama_failure_returns_fallback(self):
        mock_db = _mock_db()
        with patch("conversation.handler.Database", return_value=mock_db), \
             patch("conversation.handler.requests.post") as mock_post:
            mock_post.side_effect = [
                _llama_resp("GENERAL"),
                _llama_resp(""),   # empty → fallback
            ]
            reply = handle(PHONE, "Hello there")

        assert isinstance(reply, str)
        assert len(reply) > 0


class TestConversationContext:

    def test_context_saved_after_exchange(self):
        mock_db = _mock_db()
        with patch("conversation.handler.Database", return_value=mock_db), \
             patch("conversation.handler.requests.post") as mock_post:
            mock_post.return_value = _llama_resp("UNSUBSCRIBE")
            handle(PHONE, "stop")

        mock_db.update_conversation_context.assert_called_once()
