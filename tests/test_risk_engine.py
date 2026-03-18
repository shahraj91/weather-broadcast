"""
Tests for conversation/risk_engine.py
All weather data passed as plain dicts — no external calls.
"""

import pytest
from database.models import User
from conversation.risk_engine import check_risks


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def metric_user():
    return User(
        phone="+14155550100",
        lat=37.7749,
        lon=-122.4194,
        timezone="America/Los_Angeles",
        unit_system="metric",
    )


@pytest.fixture
def imperial_user():
    return User(
        phone="+14155550101",
        lat=37.7749,
        lon=-122.4194,
        timezone="America/Los_Angeles",
        unit_system="imperial",
    )


def _safe_weather(**overrides):
    """Normal conditions that trigger no rules."""
    base = {
        "temp_max":    22.0,
        "temp_min":    13.0,
        "condition":   "Partly cloudy",
        "wind_speed":  16.0,
        "humidity":    65,
        "unit_system": "metric",
        "temp_unit":   "°C",
        "wind_unit":   "km/h",
    }
    base.update(overrides)
    return base


def _imperial_weather(**overrides):
    base = {
        "temp_max":    72.0,
        "temp_min":    55.0,
        "condition":   "Partly cloudy",
        "wind_speed":  10.0,
        "humidity":    65,
        "unit_system": "imperial",
        "temp_unit":   "°F",
        "wind_unit":   "mph",
    }
    base.update(overrides)
    return base


# ── Rule 1: Extreme heat ───────────────────────────────────────────────────

class TestExtremeHeat:

    def test_triggers_above_35c(self, metric_user):
        risks = check_risks(metric_user, _safe_weather(temp_max=35.1))
        assert any("heat" in r.lower() or "35.1" in r for r in risks)

    def test_no_trigger_at_35c(self, metric_user):
        risks = check_risks(metric_user, _safe_weather(temp_max=35.0))
        assert not any("extreme heat" in r.lower() for r in risks)

    def test_triggers_above_95f_imperial(self, imperial_user):
        risks = check_risks(imperial_user, _imperial_weather(temp_max=95.1))
        assert any("heat" in r.lower() or "95.1" in r for r in risks)

    def test_no_trigger_at_95f_imperial(self, imperial_user):
        risks = check_risks(imperial_user, _imperial_weather(temp_max=95.0))
        assert not any("extreme heat" in r.lower() for r in risks)


# ── Rule 2: Dangerous cold ─────────────────────────────────────────────────

class TestDangerousCold:

    def test_triggers_below_minus_10c(self, metric_user):
        risks = check_risks(metric_user, _safe_weather(temp_min=-10.1))
        assert any("cold" in r.lower() or "-10.1" in r for r in risks)

    def test_no_trigger_at_minus_10c(self, metric_user):
        risks = check_risks(metric_user, _safe_weather(temp_min=-10.0))
        assert not any("cold" in r.lower() for r in risks)

    def test_triggers_below_14f_imperial(self, imperial_user):
        risks = check_risks(imperial_user, _imperial_weather(temp_min=13.9))
        assert any("cold" in r.lower() or "13.9" in r for r in risks)

    def test_no_trigger_at_14f_imperial(self, imperial_user):
        risks = check_risks(imperial_user, _imperial_weather(temp_min=14.0))
        assert not any("cold" in r.lower() for r in risks)


# ── Rule 3: Strong winds ───────────────────────────────────────────────────

class TestStrongWinds:

    def test_triggers_above_60kmh(self, metric_user):
        risks = check_risks(metric_user, _safe_weather(wind_speed=60.1))
        assert any("wind" in r.lower() for r in risks)

    def test_no_trigger_at_60kmh(self, metric_user):
        risks = check_risks(metric_user, _safe_weather(wind_speed=60.0))
        assert not any("wind" in r.lower() for r in risks)

    def test_triggers_above_37_3mph_imperial(self, imperial_user):
        risks = check_risks(imperial_user, _imperial_weather(wind_speed=37.4))
        assert any("wind" in r.lower() for r in risks)

    def test_no_trigger_at_37_3mph_imperial(self, imperial_user):
        risks = check_risks(imperial_user, _imperial_weather(wind_speed=37.3))
        assert not any("wind" in r.lower() for r in risks)


# ── Rule 4: Thunderstorm ───────────────────────────────────────────────────

class TestThunderstorm:

    def test_triggers_on_thunderstorm(self, metric_user):
        risks = check_risks(metric_user, _safe_weather(condition="Thunderstorm"))
        assert any("thunder" in r.lower() for r in risks)

    def test_triggers_on_thunderstorm_with_hail(self, metric_user):
        risks = check_risks(metric_user, _safe_weather(condition="Thunderstorm with hail"))
        assert any("thunder" in r.lower() for r in risks)

    def test_no_trigger_on_rain(self, metric_user):
        risks = check_risks(metric_user, _safe_weather(condition="Moderate rain"))
        assert not any("thunder" in r.lower() for r in risks)


# ── Rule 5: Dense fog + high humidity ─────────────────────────────────────

class TestFogHumidity:

    def test_triggers_humidity_91_and_fog(self, metric_user):
        risks = check_risks(metric_user, _safe_weather(humidity=91, condition="Foggy"))
        assert any("fog" in r.lower() for r in risks)

    def test_no_trigger_at_humidity_90_with_fog(self, metric_user):
        risks = check_risks(metric_user, _safe_weather(humidity=90, condition="Foggy"))
        assert not any("fog" in r.lower() for r in risks)

    def test_no_trigger_high_humidity_no_fog(self, metric_user):
        risks = check_risks(metric_user, _safe_weather(humidity=95, condition="Overcast"))
        assert not any("fog" in r.lower() for r in risks)


# ── Rule 6: Heat index ─────────────────────────────────────────────────────

class TestHeatIndex:

    def test_triggers_temp_above_30c_humidity_above_70(self, metric_user):
        risks = check_risks(metric_user, _safe_weather(temp_max=30.1, humidity=71))
        assert any("heat index" in r.lower() for r in risks)

    def test_no_trigger_at_boundary_temp(self, metric_user):
        # temp_max exactly 30.0 — does NOT trigger (rule requires > 30)
        risks = check_risks(metric_user, _safe_weather(temp_max=30.0, humidity=75))
        assert not any("heat index" in r.lower() for r in risks)

    def test_no_trigger_at_boundary_humidity(self, metric_user):
        # humidity exactly 70 — does NOT trigger (rule requires > 70)
        risks = check_risks(metric_user, _safe_weather(temp_max=32.0, humidity=70))
        assert not any("heat index" in r.lower() for r in risks)

    def test_triggers_above_86f_humidity_above_70_imperial(self, imperial_user):
        risks = check_risks(imperial_user, _imperial_weather(temp_max=86.1, humidity=71))
        assert any("heat index" in r.lower() for r in risks)

    def test_no_trigger_at_86f_imperial(self, imperial_user):
        risks = check_risks(imperial_user, _imperial_weather(temp_max=86.0, humidity=75))
        assert not any("heat index" in r.lower() for r in risks)


# ── Normal conditions ──────────────────────────────────────────────────────

class TestNormalConditions:

    def test_safe_weather_returns_empty(self, metric_user):
        risks = check_risks(metric_user, _safe_weather())
        assert risks == []

    def test_safe_imperial_weather_returns_empty(self, imperial_user):
        risks = check_risks(imperial_user, _imperial_weather())
        assert risks == []


# ── Multiple risks ─────────────────────────────────────────────────────────

class TestMultipleRisks:

    def test_two_risks_returned_simultaneously(self, metric_user):
        """Thunderstorm + high wind should both appear."""
        risks = check_risks(
            metric_user,
            _safe_weather(condition="Thunderstorm", wind_speed=65.0),
        )
        assert len(risks) >= 2
        assert any("thunder" in r.lower() for r in risks)
        assert any("wind" in r.lower() for r in risks)

    def test_heat_and_heat_index_both_trigger(self, metric_user):
        """Extreme heat + heat index can both apply on a very hot, humid day."""
        risks = check_risks(
            metric_user,
            _safe_weather(temp_max=36.0, humidity=75),
        )
        assert len(risks) >= 2
