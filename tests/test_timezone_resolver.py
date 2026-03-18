"""
Tests for utils/timezone_resolver.py
All tests are purely local — no network calls (timezonefinder uses local data files).
"""

import pytest
from unittest.mock import patch, MagicMock
from utils.timezone_resolver import resolve_timezone


class TestResolveTimezone:

    def test_tz01_new_york(self):
        """TZ-01: New York coordinates return correct IANA timezone."""
        result = resolve_timezone(40.7128, -74.0060)
        assert result == "America/New_York"

    def test_tz02_london(self):
        """TZ-02: London coordinates return correct IANA timezone."""
        result = resolve_timezone(51.5074, -0.1278)
        assert result == "Europe/London"

    def test_tz03_tokyo(self):
        """TZ-03: Tokyo coordinates return correct IANA timezone."""
        result = resolve_timezone(35.6762, 139.6503)
        assert result == "Asia/Tokyo"

    def test_tz04_sydney(self):
        """TZ-04: Sydney coordinates return correct IANA timezone."""
        result = resolve_timezone(-33.8688, 151.2093)
        assert result == "Australia/Sydney"

    def test_tz05_invalid_latitude(self):
        """TZ-05: Latitude out of range raises ValueError."""
        with pytest.raises(ValueError, match="Latitude"):
            resolve_timezone(999, 0)

    def test_tz05_invalid_longitude(self):
        """TZ-05: Longitude out of range raises ValueError."""
        with pytest.raises(ValueError, match="Longitude"):
            resolve_timezone(0, 999)

    def test_tz05_invalid_both(self):
        """TZ-05: Both out of range raises ValueError."""
        with pytest.raises(ValueError):
            resolve_timezone(999, 999)

    def test_tz06_boundary_coordinate(self):
        """TZ-06: Coordinate on a timezone boundary returns a valid IANA string."""
        # Colorado / Utah border area
        result = resolve_timezone(37.0, -109.05)
        assert result is not None
        assert "/" in result   # All valid IANA tzs contain a slash e.g. 'America/Denver'

    def test_returns_string(self):
        """Return type is always a string."""
        result = resolve_timezone(48.8566, 2.3522)   # Paris
        assert isinstance(result, str)
        assert len(result) > 0

    def test_fallback_when_timezone_at_returns_none(self):
        """Falls back to closest_timezone_at when timezone_at returns None."""
        with patch("utils.timezone_resolver._tf") as mock_tf:
            mock_tf.timezone_at.return_value = None
            mock_tf.closest_timezone_at.return_value = "Pacific/Auckland"
            result = resolve_timezone(-40.0, -175.0)
            assert result == "Pacific/Auckland"
            mock_tf.closest_timezone_at.assert_called_once()

    def test_raises_when_both_lookups_return_none(self):
        """Raises ValueError when both lookups fail."""
        with patch("utils.timezone_resolver._tf") as mock_tf:
            mock_tf.timezone_at.return_value = None
            mock_tf.closest_timezone_at.return_value = None
            with pytest.raises(ValueError, match="Could not determine timezone"):
                resolve_timezone(0.0, 0.0)
