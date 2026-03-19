"""
Shared pytest fixtures for the Weather Broadcast System test suite.
All external dependencies are mocked so tests run offline with no credentials.
"""

import pytest
from unittest.mock import patch, MagicMock
from database.db import Database
from database.models import User


@pytest.fixture(autouse=True)
def _safety_always_passes(request):
    """
    For every test file that is NOT test_safety.py, patch is_safe() to always
    return True. This prevents the safety Llama call from reaching a live Ollama
    instance and breaking unrelated tests.

    Tests inside test_safety.py control their own safety mocks explicitly.
    """
    if "test_safety" in request.fspath.basename:
        yield   # safety tests own their mocks
        return

    with patch("messaging.safety.is_safe", return_value=True):
        yield


# ── Users ──────────────────────────────────────────────────────

@pytest.fixture
def imperial_user():
    return User(
        id=1,
        phone="+14155550100",
        lat=37.7749,
        lon=-122.4194,
        timezone="America/Los_Angeles",
        unit_system="imperial",
        country_code="US",
        name="Test User 1",
    )


@pytest.fixture
def metric_user():
    return User(
        id=2,
        phone="+447700900100",
        lat=51.5074,
        lon=-0.1278,
        timezone="Europe/London",
        unit_system="metric",
        country_code="GB",
        name="Test User 2",
    )


# ── Weather data ───────────────────────────────────────────────

@pytest.fixture
def weather_imperial():
    return {
        "temp_max":    72.0,
        "temp_min":    55.0,
        "condition":   "Partly cloudy",
        "wind_speed":  10.0,
        "humidity":    65,
        "unit_system": "imperial",
        "temp_unit":   "°F",
        "wind_unit":   "mph",
    }


@pytest.fixture
def weather_metric():
    return {
        "temp_max":    22.0,
        "temp_min":    13.0,
        "condition":   "Partly cloudy",
        "wind_speed":  16.0,
        "humidity":    65,
        "unit_system": "metric",
        "temp_unit":   "°C",
        "wind_unit":   "km/h",
    }


@pytest.fixture
def weather_rainy():
    return {
        "temp_max":    15.0,
        "temp_min":    9.0,
        "condition":   "Moderate rain",
        "wind_speed":  25.0,
        "humidity":    88,
        "unit_system": "metric",
        "temp_unit":   "°C",
        "wind_unit":   "km/h",
    }


# ── Database ───────────────────────────────────────────────────

@pytest.fixture
def test_db(tmp_path):
    """In-memory-style SQLite DB in a temp directory — isolated per test."""
    db = Database(str(tmp_path / "test.db"))
    db.init()
    yield db
    db.close()


@pytest.fixture
def seeded_db(test_db, imperial_user, metric_user):
    """DB pre-populated with two users."""
    test_db.add_user(imperial_user)
    test_db.add_user(metric_user)
    return test_db


# ── Open-Meteo API response stub ───────────────────────────────

@pytest.fixture
def open_meteo_response_metric():
    """Minimal valid Open-Meteo JSON response (metric)."""
    return {
        "daily": {
            "temperature_2m_max": [22.0],
            "temperature_2m_min": [13.0],
            "weathercode":        [2],
            "windspeed_10m_max":  [16.0],
        },
        "hourly": {
            "relativehumidity_2m": [65] * 24,
        },
    }


@pytest.fixture
def open_meteo_response_imperial():
    """Minimal valid Open-Meteo JSON response (imperial)."""
    return {
        "daily": {
            "temperature_2m_max": [72.0],
            "temperature_2m_min": [55.0],
            "weathercode":        [2],
            "windspeed_10m_max":  [10.0],
        },
        "hourly": {
            "relativehumidity_2m": [65] * 24,
        },
    }
