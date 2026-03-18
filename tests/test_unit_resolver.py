"""
Tests for utils/unit_resolver.py
Geopy calls are mocked — no network required.
"""

import pytest
from unittest.mock import patch, MagicMock
from utils.unit_resolver import resolve_unit_system, resolve_country_code


def _make_location(country_code: str):
    """Build a minimal mock geopy Location object."""
    mock_loc = MagicMock()
    mock_loc.raw = {"address": {"country_code": country_code.lower()}}
    return mock_loc


class TestResolveUnitSystem:

    def test_ur01_us_returns_imperial(self):
        """UR-01: US coordinates return 'imperial'."""
        with patch("utils.unit_resolver._geolocator") as mock_geo:
            mock_geo.reverse.return_value = _make_location("US")
            assert resolve_unit_system(37.77, -122.41) == "imperial"

    def test_ur02_france_returns_metric(self):
        """UR-02: France coordinates return 'metric'."""
        with patch("utils.unit_resolver._geolocator") as mock_geo:
            mock_geo.reverse.return_value = _make_location("FR")
            assert resolve_unit_system(48.85, 2.35) == "metric"

    def test_ur03_liberia_returns_imperial(self):
        """UR-03: Liberia coordinates return 'imperial'."""
        with patch("utils.unit_resolver._geolocator") as mock_geo:
            mock_geo.reverse.return_value = _make_location("LR")
            assert resolve_unit_system(6.30, -10.80) == "imperial"

    def test_ur04_myanmar_returns_imperial(self):
        """UR-04: Myanmar coordinates return 'imperial'."""
        with patch("utils.unit_resolver._geolocator") as mock_geo:
            mock_geo.reverse.return_value = _make_location("MM")
            assert resolve_unit_system(16.87, 96.19) == "imperial"

    def test_ur05_japan_returns_metric(self):
        """UR-05: Japan coordinates return 'metric'."""
        with patch("utils.unit_resolver._geolocator") as mock_geo:
            mock_geo.reverse.return_value = _make_location("JP")
            assert resolve_unit_system(35.68, 139.69) == "metric"

    def test_ur06_geocoder_returns_none_defaults_metric(self):
        """UR-06: If geocoder returns None, default to 'metric'."""
        with patch("utils.unit_resolver._geolocator") as mock_geo:
            mock_geo.reverse.return_value = None
            assert resolve_unit_system(0.0, 0.0) == "metric"

    def test_geocoder_timeout_defaults_metric(self):
        """Network timeout gracefully defaults to 'metric'."""
        from geopy.exc import GeocoderTimedOut
        with patch("utils.unit_resolver._geolocator") as mock_geo:
            mock_geo.reverse.side_effect = GeocoderTimedOut()
            assert resolve_unit_system(37.77, -122.41) == "metric"

    def test_geocoder_service_error_defaults_metric(self):
        """Geocoder service error gracefully defaults to 'metric'."""
        from geopy.exc import GeocoderServiceError
        with patch("utils.unit_resolver._geolocator") as mock_geo:
            mock_geo.reverse.side_effect = GeocoderServiceError()
            assert resolve_unit_system(51.50, -0.12) == "metric"

    def test_returns_string(self):
        """Return value is always 'metric' or 'imperial'."""
        with patch("utils.unit_resolver._geolocator") as mock_geo:
            mock_geo.reverse.return_value = _make_location("DE")
            result = resolve_unit_system(52.52, 13.40)
            assert result in ("metric", "imperial")


class TestResolveCountryCode:

    def test_returns_uppercase_code(self):
        """Country code is returned in uppercase."""
        with patch("utils.unit_resolver._geolocator") as mock_geo:
            mock_geo.reverse.return_value = _make_location("gb")
            result = resolve_country_code(51.50, -0.12)
            assert result == "GB"

    def test_returns_none_when_geocoder_fails(self):
        """Returns None on geocoder failure."""
        from geopy.exc import GeocoderTimedOut
        with patch("utils.unit_resolver._geolocator") as mock_geo:
            mock_geo.reverse.side_effect = GeocoderTimedOut()
            assert resolve_country_code(0.0, 0.0) is None

    def test_returns_none_when_location_is_none(self):
        """Returns None when location lookup returns nothing."""
        with patch("utils.unit_resolver._geolocator") as mock_geo:
            mock_geo.reverse.return_value = None
            assert resolve_country_code(0.0, 0.0) is None
