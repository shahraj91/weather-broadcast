"""
Tests for weather/fetcher.py
HTTP calls to Open-Meteo are mocked — no network required.
"""

import pytest
from unittest.mock import patch, MagicMock
from weather.fetcher import get_forecast, WeatherFetchError, WMO_CODES


def _mock_response(json_data: dict, status_code: int = 200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    if status_code >= 400:
        from requests.exceptions import HTTPError
        mock.raise_for_status.side_effect = HTTPError(response=mock)
    else:
        mock.raise_for_status.return_value = None
    return mock


class TestGetForecastSuccess:

    def test_wf01_metric_response_has_celsius(self, open_meteo_response_metric):
        """WF-01: Metric request returns °C and km/h units."""
        with patch("weather.fetcher.requests.get") as mock_get:
            mock_get.return_value = _mock_response(open_meteo_response_metric)
            result = get_forecast(51.5, -0.1, unit_system="metric", timezone="Europe/London")

        assert result["temp_unit"] == "°C"
        assert result["wind_unit"] == "km/h"
        assert result["unit_system"] == "metric"

    def test_wf02_imperial_response_has_fahrenheit(self, open_meteo_response_imperial):
        """WF-02: Imperial request returns °F and mph units."""
        with patch("weather.fetcher.requests.get") as mock_get:
            mock_get.return_value = _mock_response(open_meteo_response_imperial)
            result = get_forecast(37.7, -122.4, unit_system="imperial", timezone="America/Los_Angeles")

        assert result["temp_unit"] == "°F"
        assert result["wind_unit"] == "mph"
        assert result["unit_system"] == "imperial"

    def test_wf03_all_expected_keys_present(self, open_meteo_response_metric):
        """WF-03: Response dict contains all expected keys."""
        with patch("weather.fetcher.requests.get") as mock_get:
            mock_get.return_value = _mock_response(open_meteo_response_metric)
            result = get_forecast(51.5, -0.1)

        for key in ["temp_max", "temp_min", "condition", "wind_speed", "humidity",
                    "unit_system", "temp_unit", "wind_unit"]:
            assert key in result, f"Missing key: {key}"

    def test_humidity_is_averaged(self, open_meteo_response_metric):
        """Humidity is the average of the 24 hourly values."""
        with patch("weather.fetcher.requests.get") as mock_get:
            mock_get.return_value = _mock_response(open_meteo_response_metric)
            result = get_forecast(51.5, -0.1)

        assert result["humidity"] == 65   # all 24 values are 65

    def test_wf07_wmo_code_maps_to_label(self):
        """WF-07: WMO weather code is translated to a human-readable string."""
        response = {
            "daily": {
                "temperature_2m_max": [20.0],
                "temperature_2m_min": [10.0],
                "weathercode": [61],          # "Slight rain"
                "windspeed_10m_max": [15.0],
            },
            "hourly": {"relativehumidity_2m": [70] * 24},
        }
        with patch("weather.fetcher.requests.get") as mock_get:
            mock_get.return_value = _mock_response(response)
            result = get_forecast(51.5, -0.1)

        assert result["condition"] == "Slight rain"

    def test_unknown_wmo_code_handled(self):
        """Unknown WMO code returns a fallback string instead of raising."""
        response = {
            "daily": {
                "temperature_2m_max": [20.0],
                "temperature_2m_min": [10.0],
                "weathercode": [999],
                "windspeed_10m_max": [5.0],
            },
            "hourly": {"relativehumidity_2m": [50] * 24},
        }
        with patch("weather.fetcher.requests.get") as mock_get:
            mock_get.return_value = _mock_response(response)
            result = get_forecast(0.0, 0.0)

        assert "999" in result["condition"]


class TestGetForecastErrors:

    def test_wf04_http_500_raises_weather_fetch_error(self):
        """WF-04: HTTP 500 response raises WeatherFetchError."""
        with patch("weather.fetcher.requests.get") as mock_get:
            mock_get.return_value = _mock_response({}, status_code=500)
            with pytest.raises(WeatherFetchError):
                get_forecast(51.5, -0.1)

    def test_wf05_timeout_raises_weather_fetch_error(self):
        """WF-05: Network timeout raises WeatherFetchError."""
        from requests.exceptions import Timeout
        with patch("weather.fetcher.requests.get") as mock_get:
            mock_get.side_effect = Timeout()
            with pytest.raises(WeatherFetchError, match="timed out"):
                get_forecast(51.5, -0.1)

    def test_wf06_missing_key_raises_weather_fetch_error(self):
        """WF-06: Partial / malformed response raises WeatherFetchError."""
        bad_response = {"daily": {}}   # missing all required keys
        with patch("weather.fetcher.requests.get") as mock_get:
            mock_get.return_value = _mock_response(bad_response)
            with pytest.raises(WeatherFetchError):
                get_forecast(51.5, -0.1)

    def test_request_exception_raises_weather_fetch_error(self):
        """Generic RequestException is wrapped in WeatherFetchError."""
        from requests.exceptions import RequestException
        with patch("weather.fetcher.requests.get") as mock_get:
            mock_get.side_effect = RequestException("connection refused")
            with pytest.raises(WeatherFetchError):
                get_forecast(51.5, -0.1)


class TestImperialQueryParams:

    def test_imperial_params_sent_to_api(self, open_meteo_response_imperial):
        """Imperial unit_system sends temperature_unit=fahrenheit and wind_speed_unit=mph."""
        with patch("weather.fetcher.requests.get") as mock_get:
            mock_get.return_value = _mock_response(open_meteo_response_imperial)
            get_forecast(37.7, -122.4, unit_system="imperial", timezone="America/New_York")

        call_params = mock_get.call_args[1]["params"]
        assert call_params.get("temperature_unit") == "fahrenheit"
        assert call_params.get("wind_speed_unit") == "mph"

    def test_metric_does_not_send_unit_params(self, open_meteo_response_metric):
        """Metric requests do not include temperature_unit or wind_speed_unit params."""
        with patch("weather.fetcher.requests.get") as mock_get:
            mock_get.return_value = _mock_response(open_meteo_response_metric)
            get_forecast(51.5, -0.1, unit_system="metric")

        call_params = mock_get.call_args[1]["params"]
        assert "temperature_unit" not in call_params
        assert "wind_speed_unit" not in call_params
