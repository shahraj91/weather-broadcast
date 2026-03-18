"""
Tests for messaging/formatter.py
Llama subprocess calls are mocked — no model required.
"""

import pytest
from unittest.mock import patch, MagicMock
from messaging.formatter import generate, FormatterError, _static_fallback
from database.models import User


class TestGenerateWithLlama:

    def test_mf01_metric_message_contains_celsius(self, weather_metric):
        """MF-01: Metric weather data produces a message mentioning °C."""
        with patch("messaging.formatter._call_llama") as mock_llama:
            mock_llama.return_value = (
                "Good morning! Expect a mild day with highs of 22°C and lows of 13°C. "
                "Partly cloudy skies with light winds at 16 km/h. A light jacket would be handy! 🌤️\n\n"
                "🌟 Fun Fact: Clouds are made of tiny water droplets so small that "
                "millions of them fit on a pinhead!"
            )
            result = generate(weather_metric)

        assert "°C" in result or "22" in result

    def test_mf02_imperial_message_contains_fahrenheit(self, weather_imperial):
        """MF-02: Imperial weather data produces a message mentioning °F."""
        with patch("messaging.formatter._call_llama") as mock_llama:
            mock_llama.return_value = (
                "Good morning! A warm day ahead with highs of 72°F and lows of 55°F. "
                "Partly cloudy with a pleasant breeze at 10 mph. ☀️\n\n"
                "🌟 Fun Fact: The sun's light takes about 8 minutes to reach Earth — "
                "so the sunshine you feel is actually 8 minutes old!"
            )
            result = generate(weather_imperial)

        assert "°F" in result or "72" in result

    def test_mf03_llama_response_returned_as_message(self, weather_metric):
        """MF-03: Non-empty Llama response is returned directly (with header prepended)."""
        llama_output = (
            "Great day today! 🌤️ Highs of 22°C, lows of 13°C.\n\n"
            "🌟 Fun Fact: Water can exist as solid, liquid, and gas all at the same time!"
        )
        expected = "📬 Daily Weather Update from Raj\n\n" + llama_output
        with patch("messaging.formatter._call_llama") as mock_llama:
            mock_llama.return_value = llama_output
            result = generate(weather_metric)

        assert result == expected

    def test_mf04_fun_fact_present_in_output(self, weather_metric):
        """MF-04: Output contains the '🌟 Fun Fact:' prefix."""
        with patch("messaging.formatter._call_llama") as mock_llama:
            mock_llama.return_value = (
                "Nice weather today! 🌤️\n\n"
                "🌟 Fun Fact: Raindrops are shaped like hamburger buns, not teardrops!"
            )
            result = generate(weather_metric)

        assert "🌟 Fun Fact:" in result

    def test_mf04_missing_fun_fact_is_appended(self, weather_metric):
        """MF-04: If Llama omits Fun Fact, one is appended automatically."""
        with patch("messaging.formatter._call_llama") as mock_llama:
            mock_llama.return_value = "Just a weather summary with no trivia."
            result = generate(weather_metric)

        assert "🌟 Fun Fact:" in result

    def test_mf05_empty_llama_response_uses_fallback(self, weather_metric):
        """MF-05: Empty Llama string triggers static fallback (not an exception)."""
        with patch("messaging.formatter._call_llama") as mock_llama:
            mock_llama.return_value = None
            result = generate(weather_metric)

        assert len(result) > 0
        assert "🌟 Fun Fact:" in result

    def test_mf06_llama_timeout_uses_fallback(self, weather_metric):
        """MF-06: Llama timeout returns static fallback message."""
        with patch("messaging.formatter._call_llama") as mock_llama:
            mock_llama.return_value = None   # timeout returns None
            result = generate(weather_metric)

        assert isinstance(result, str)
        assert len(result) > 50

    def test_mf08_invalid_weather_data_raises(self):
        """MF-08: Invalid weather dict raises FormatterError."""
        with pytest.raises(FormatterError):
            generate({})

    def test_mf08_none_input_raises(self):
        """MF-08: None input raises FormatterError."""
        with pytest.raises(FormatterError):
            generate(None)


class TestStaticFallback:

    def test_fallback_metric_contains_celsius(self, weather_metric):
        """Fallback message for metric weather contains °C."""
        result = _static_fallback(weather_metric)
        assert "°C" in result

    def test_fallback_imperial_contains_fahrenheit(self, weather_imperial):
        """Fallback message for imperial weather contains °F."""
        result = _static_fallback(weather_imperial)
        assert "°F" in result

    def test_fallback_contains_fun_fact(self, weather_metric):
        """Fallback message always contains a Fun Fact."""
        result = _static_fallback(weather_metric)
        assert "🌟 Fun Fact:" in result

    def test_fallback_rain_emoji(self, weather_rainy):
        """Rainy condition picks a rain emoji."""
        result = _static_fallback(weather_rainy)
        assert "🌧️" in result

    def test_fallback_returns_string(self, weather_metric):
        """Fallback always returns a non-empty string."""
        result = _static_fallback(weather_metric)
        assert isinstance(result, str)
        assert len(result) > 0


class TestActivityHints:
    """Verify activity-specific context is injected into the Llama prompt."""

    _LLAMA_REPLY = (
        "Good morning! Partly cloudy day ahead. 🌤️\n\n"
        "🌟 Fun Fact: Raindrops are shaped like hamburger buns, not teardrops!"
    )

    def _make_user(self, activity: str) -> User:
        return User(
            id=1,
            phone="+14155550100",
            lat=37.7749,
            lon=-122.4194,
            timezone="America/Los_Angeles",
            unit_system="metric",
            name="Test",
            activity=activity,
        )

    def _captured_prompt(self, weather, user) -> str:
        """Run generate() and return the prompt that was passed to _call_llama."""
        with patch("messaging.formatter._call_llama") as mock_llama:
            mock_llama.return_value = self._LLAMA_REPLY
            generate(weather, user=user)
            return mock_llama.call_args[0][0]

    def test_runner_activity_in_prompt(self, weather_metric):
        prompt = self._captured_prompt(weather_metric, self._make_user("runner"))
        assert "runner" in prompt.lower()
        assert "Activity context:" in prompt

    def test_cyclist_activity_in_prompt(self, weather_metric):
        prompt = self._captured_prompt(weather_metric, self._make_user("cyclist"))
        assert "cyclist" in prompt.lower()
        assert "Activity context:" in prompt

    def test_farmer_activity_in_prompt(self, weather_metric):
        prompt = self._captured_prompt(weather_metric, self._make_user("farmer"))
        assert "farmer" in prompt.lower()
        assert "Activity context:" in prompt

    def test_photographer_activity_in_prompt(self, weather_metric):
        prompt = self._captured_prompt(weather_metric, self._make_user("photographer"))
        assert "photographer" in prompt.lower()
        assert "Activity context:" in prompt

    def test_parent_activity_in_prompt(self, weather_metric):
        prompt = self._captured_prompt(weather_metric, self._make_user("parent"))
        assert "parent" in prompt.lower()
        assert "Activity context:" in prompt

    def test_general_activity_no_extra_hint(self, weather_metric):
        prompt = self._captured_prompt(weather_metric, self._make_user("general"))
        assert "Activity context:" not in prompt
