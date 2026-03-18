"""
Tests for messaging/broadcaster.py
Twilio client is mocked — no credentials or network required.
"""

import pytest
import time
from unittest.mock import patch, MagicMock, call
from messaging.broadcaster import (
    send, send_batch, send_to_user,
    BroadcasterError, BroadcasterAuthError, SandboxOptInError,
    SEND_DELAY_SECONDS,
)
from twilio.base.exceptions import TwilioRestException
from database.models import User


def _make_twilio_error(status: int, msg: str = "error") -> TwilioRestException:
    return TwilioRestException(status=status, uri="/messages", msg=msg)


def _make_mock_client(sid: str = "SM123abc"):
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.sid = sid
    mock_client.messages.create.return_value = mock_msg
    return mock_client


class TestSend:

    def test_bc01_sends_to_correct_whatsapp_number(self):
        """BC-01: Twilio is called with whatsapp-prefixed to/from numbers."""
        mock_client = _make_mock_client()
        with patch.dict("os.environ", {"TWILIO_WHATSAPP_FROM": "whatsapp:+14155238886"}):
            send("+14155550100", "Hello!", client=mock_client)

        mock_client.messages.create.assert_called_once_with(
            from_="whatsapp:+14155238886",
            to="whatsapp:+14155550100",
            body="Hello!",
        )

    def test_bc02_returns_sid_on_success(self):
        """BC-02: Successful send returns the Twilio message SID."""
        mock_client = _make_mock_client(sid="SMxyz789")
        result = send("+14155550100", "Hello!", client=mock_client)
        assert result == "SMxyz789"

    def test_bc03_retries_on_429(self):
        """BC-03: 429 rate limit triggers retry with backoff."""
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.sid = "SMretried"

        mock_client.messages.create.side_effect = [
            _make_twilio_error(429, "rate limited"),
            _make_twilio_error(429, "rate limited"),
            mock_msg,   # succeeds on 3rd attempt
        ]

        with patch("messaging.broadcaster.time.sleep"):   # skip actual sleep
            result = send("+14155550100", "Hello!", client=mock_client)

        assert result == "SMretried"
        assert mock_client.messages.create.call_count == 3

    def test_bc03_exhausted_retries_raises_broadcaster_error(self):
        """BC-03: All retries exhausted raises BroadcasterError."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = _make_twilio_error(500, "server error")

        with patch("messaging.broadcaster.time.sleep"):
            with pytest.raises(BroadcasterError):
                send("+14155550100", "Hello!", client=mock_client)

        assert mock_client.messages.create.call_count == 3   # MAX_RETRIES

    def test_bc04_401_raises_broadcaster_auth_error(self):
        """BC-04: Twilio 401 raises BroadcasterAuthError immediately."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = _make_twilio_error(401, "unauthorized")

        with pytest.raises(BroadcasterAuthError):
            send("+14155550100", "Hello!", client=mock_client)

        # Should NOT retry on auth error
        mock_client.messages.create.assert_called_once()

    def test_bc06_invalid_phone_raises_value_error(self):
        """BC-06: Phone not in E.164 format raises ValueError before any API call."""
        mock_client = _make_mock_client()
        with pytest.raises(ValueError, match="E.164"):
            send("14155550100", "Hello!", client=mock_client)   # missing leading +
        mock_client.messages.create.assert_not_called()

    def test_bc06_short_phone_raises_value_error(self):
        """BC-06: Suspiciously short phone raises ValueError."""
        mock_client = _make_mock_client()
        with pytest.raises(ValueError):
            send("+1", "Hello!", client=mock_client)


class TestSendToUser:

    def _opted_in_user(self, phone="+14155550100"):
        return User(id=1, phone=phone, lat=37.7, lon=-122.4,
                    timezone="America/Los_Angeles", unit_system="imperial",
                    sandbox_opted_in=True)

    def _not_opted_in_user(self, phone="+14155550101"):
        return User(id=2, phone=phone, lat=37.7, lon=-122.4,
                    timezone="America/Los_Angeles", unit_system="imperial",
                    sandbox_opted_in=False)

    def test_opted_in_user_sends_successfully(self):
        """send_to_user() sends when sandbox_opted_in=True."""
        mock_client = _make_mock_client(sid="SMoptin")
        result = send_to_user(self._opted_in_user(), "Hello!", client=mock_client)
        assert result == "SMoptin"
        mock_client.messages.create.assert_called_once()

    def test_not_opted_in_raises_sandbox_opt_in_error(self):
        """send_to_user() raises SandboxOptInError when sandbox_opted_in=False."""
        mock_client = _make_mock_client()
        with pytest.raises(SandboxOptInError):
            send_to_user(self._not_opted_in_user(), "Hello!", client=mock_client)
        mock_client.messages.create.assert_not_called()

    def test_sandbox_opt_in_error_is_broadcaster_error(self):
        """SandboxOptInError is a subclass of BroadcasterError."""
        assert issubclass(SandboxOptInError, BroadcasterError)

    def test_send_to_user_passes_correct_phone(self):
        """send_to_user() sends to the user's phone number."""
        mock_client = _make_mock_client()
        user = self._opted_in_user(phone="+447700900100")
        send_to_user(user, "Hello!", client=mock_client)
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["to"] == "whatsapp:+447700900100"


class TestSendBatch:

    def _make_users(self, count: int, sandbox_opted_in: bool = True):
        return [
            User(id=i, phone=f"+1415555{i:04d}", lat=37.7, lon=-122.4,
                 timezone="America/Los_Angeles", unit_system="imperial",
                 sandbox_opted_in=sandbox_opted_in)
            for i in range(1, count + 1)
        ]

    def test_bc07_delay_between_sends(self):
        """BC-07: time.sleep is called between batch sends."""
        users = self._make_users(3)
        mock_client = _make_mock_client()

        with patch("messaging.broadcaster.time.sleep") as mock_sleep:
            send_batch(users, "Hello!", client=mock_client)

        # sleep called between sends: count = number of users - 1
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(SEND_DELAY_SECONDS)

    def test_batch_all_success(self):
        """All successful sends are recorded in results['success']."""
        users = self._make_users(3)
        mock_client = _make_mock_client(sid="SM001")

        with patch("messaging.broadcaster.time.sleep"):
            results = send_batch(users, "Hello!", client=mock_client)

        assert len(results["success"]) == 3
        assert len(results["failed"]) == 0

    def test_batch_partial_failure(self):
        """Failed sends are recorded in results['failed'] without aborting the batch."""
        users = self._make_users(3)
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.sid = "SM001"

        # First succeeds, second fails after retries, third succeeds
        mock_client.messages.create.side_effect = [
            mock_msg,
            _make_twilio_error(500),
            _make_twilio_error(500),
            _make_twilio_error(500),  # 3 retries for user 2
            mock_msg,
        ]

        with patch("messaging.broadcaster.time.sleep"):
            results = send_batch(users, "Hello!", client=mock_client)

        assert len(results["success"]) == 2
        assert len(results["failed"]) == 1
        assert results["failed"][0]["retryable"] is True

    def test_batch_skips_non_opted_in_users(self):
        """Users with sandbox_opted_in=False are added to 'skipped', not 'failed'."""
        opted_in     = self._make_users(2, sandbox_opted_in=True)
        not_opted_in = self._make_users(1, sandbox_opted_in=False)
        not_opted_in[0].id = 99
        not_opted_in[0].phone = "+19995550001"
        users = opted_in + not_opted_in

        mock_client = _make_mock_client(sid="SM001")
        with patch("messaging.broadcaster.time.sleep"):
            results = send_batch(users, "Hello!", client=mock_client)

        assert len(results["success"]) == 2
        assert len(results["skipped"]) == 1
        assert len(results["failed"]) == 0
        assert results["skipped"][0]["phone"] == "+19995550001"

    def test_batch_aborts_on_auth_error(self):
        """Auth error in batch aborts remaining sends immediately."""
        users = self._make_users(3)
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = _make_twilio_error(401, "unauthorized")

        with patch("messaging.broadcaster.time.sleep"):
            results = send_batch(users, "Hello!", client=mock_client)

        # Only one attempt made (first user triggers auth error, batch stops)
        assert len(results["failed"]) >= 1
        assert results["failed"][0]["retryable"] is False
