"""
Tests for messaging/safety.py — content safety filter.
All Llama calls are mocked — no model required.
"""

import pytest
import requests as req
from unittest.mock import patch, MagicMock

from messaging.safety import is_safe, apply_safety, BLOCKED_TERMS


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_llama_yes():
    """Return a mock requests.post that says YES."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"response": "YES"}
    return mock_resp


def _mock_llama_no():
    """Return a mock requests.post that says NO."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"response": "NO"}
    return mock_resp


# ── Keyword filter (Layer 1) ─────────────────────────────────────────────────

class TestKeywordFilter:

    def test_blocked_keyword_returns_false(self):
        """TS-01: A message containing a blocked keyword is rejected immediately."""
        # 'kill' is in BLOCKED_TERMS — no Llama call needed
        result = is_safe("You should kill yourself today")
        assert result is False

    def test_case_insensitive_blocking(self):
        """TS-02: Keyword matching is case-insensitive."""
        result = is_safe("You should KILL yourself")
        assert result is False

    def test_clean_message_passes_keyword_layer(self):
        """TS-03: A clean weather message passes the keyword filter."""
        with patch("messaging.safety.requests.post", return_value=_mock_llama_yes()):
            result = is_safe(
                "Good morning! Today will be sunny with a high of 22°C. "
                "🌟 Fun Fact: Clouds are made of water droplets!"
            )
        assert result is True

    def test_blocked_terms_list_not_empty(self):
        """TS-04: BLOCKED_TERMS contains at least some entries."""
        assert len(BLOCKED_TERMS) > 0

    def test_safety_check_disabled_skips_all_layers(self):
        """TS-05: SAFETY_CHECK_ENABLED=false bypasses both layers."""
        with patch.dict("os.environ", {"SAFETY_CHECK_ENABLED": "false"}):
            # Even a string with a blocked term should pass
            result = is_safe("kill murder bomb")
        assert result is True


# ── Llama safety check (Layer 2) ─────────────────────────────────────────────

class TestLlamaSafetyCheck:

    _CLEAN = "Nice weather today! High of 22°C, low of 13°C."

    def test_llama_yes_returns_true(self):
        """TS-06: Llama responding YES means the message is safe."""
        with patch("messaging.safety.requests.post", return_value=_mock_llama_yes()):
            result = is_safe(self._CLEAN)
        assert result is True

    def test_llama_no_returns_false(self):
        """TS-07: Llama responding NO means the message is unsafe."""
        with patch("messaging.safety.requests.post", return_value=_mock_llama_no()):
            result = is_safe(self._CLEAN)
        assert result is False

    def test_llama_timeout_defaults_to_safe(self):
        """TS-08: Timeout on Llama call defaults to True (don't block)."""
        with patch("messaging.safety.requests.post", side_effect=req.Timeout):
            result = is_safe(self._CLEAN)
        assert result is True

    def test_llama_connection_error_defaults_to_safe(self):
        """TS-09: Connection error on Llama defaults to True (don't block)."""
        with patch("messaging.safety.requests.post", side_effect=req.ConnectionError):
            result = is_safe(self._CLEAN)
        assert result is True

    def test_llama_unexpected_response_returns_false(self):
        """TS-10: Unexpected Llama response (not YES) is treated as unsafe."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"response": "MAYBE"}
        with patch("messaging.safety.requests.post", return_value=mock_resp):
            result = is_safe(self._CLEAN)
        assert result is False


# ── apply_safety ─────────────────────────────────────────────────────────────

class TestApplySafety:

    def test_returns_original_when_safe(self):
        """TS-11: apply_safety returns original text when is_safe() is True."""
        with patch("messaging.safety.is_safe", return_value=True):
            result = apply_safety("Hello, sunny day!", "fallback text")
        assert result == "Hello, sunny day!"

    def test_returns_fallback_when_unsafe(self):
        """TS-12: apply_safety returns fallback when is_safe() is False."""
        with patch("messaging.safety.is_safe", return_value=False):
            result = apply_safety("unsafe content", "safe fallback text")
        assert result == "safe fallback text"

    def test_fallback_not_called_when_safe(self):
        """TS-13: Fallback text is irrelevant when message is safe."""
        with patch("messaging.safety.is_safe", return_value=True):
            result = apply_safety("original", "should not appear")
        assert result == "original"
