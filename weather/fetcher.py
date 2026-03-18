"""
Fetches daily weather forecast from Open-Meteo (free, no API key required).
Returns a normalised dict ready to be passed to the message formatter.
"""

import requests
import logging
from typing import Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SECONDS = 10

# WMO Weather Interpretation Codes → human-readable condition
# https://open-meteo.com/en/docs#weathervariables
WMO_CODES = {
    0:  "Clear sky",
    1:  "Mainly clear",
    2:  "Partly cloudy",
    3:  "Overcast",
    45: "Foggy",
    48: "Icy fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    80: "Slight showers",
    81: "Moderate showers",
    82: "Violent showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with heavy hail",
}


class WeatherFetchError(Exception):
    """Raised when the weather API call fails."""


def get_forecast(
    lat: float,
    lon: float,
    unit_system: str = "metric",
    timezone: str = "UTC",
) -> dict:
    """
    Fetch today's weather forecast for the given coordinates.

    Args:
        lat:         Latitude
        lon:         Longitude
        unit_system: 'metric' or 'imperial'
        timezone:    IANA timezone string e.g. 'America/New_York'

    Returns:
        Dict with keys:
            temp_max      (float)  — daily high
            temp_min      (float)  — daily low
            condition     (str)    — human-readable e.g. 'Partly cloudy'
            wind_speed    (float)  — max wind speed for the day
            humidity      (int)    — average relative humidity %
            unit_system   (str)    — 'metric' | 'imperial'
            temp_unit     (str)    — '°C' | '°F'
            wind_unit     (str)    — 'km/h' | 'mph'

    Raises:
        WeatherFetchError: On HTTP errors, timeouts, or missing data.
    """
    params = {
        "latitude":         lat,
        "longitude":        lon,
        "daily":            "temperature_2m_max,temperature_2m_min,weathercode,windspeed_10m_max",
        "hourly":           "relativehumidity_2m",
        "timezone":         timezone,
        "forecast_days":    1,
    }

    if unit_system == "imperial":
        params["temperature_unit"] = "fahrenheit"
        params["wind_speed_unit"]  = "mph"

    try:
        response = requests.get(BASE_URL, params=params, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        raise WeatherFetchError(f"Open-Meteo timed out after {TIMEOUT_SECONDS}s for ({lat}, {lon})")
    except requests.exceptions.RequestException as e:
        raise WeatherFetchError(f"Open-Meteo request failed: {e}")

    try:
        data = response.json()
        daily   = data["daily"]
        hourly  = data["hourly"]

        temp_max   = daily["temperature_2m_max"][0]
        temp_min   = daily["temperature_2m_min"][0]
        wmo_code   = daily["weathercode"][0]
        wind_speed = daily["windspeed_10m_max"][0]

        # Average the first 24 hourly humidity readings for the day
        humidity_values = [h for h in hourly.get("relativehumidity_2m", [])[:24] if h is not None]
        humidity = round(sum(humidity_values) / len(humidity_values)) if humidity_values else 0

        condition = WMO_CODES.get(wmo_code, f"Weather code {wmo_code}")

    except (KeyError, IndexError, TypeError) as e:
        raise WeatherFetchError(f"Unexpected Open-Meteo response structure: {e}")

    temp_unit = "°F" if unit_system == "imperial" else "°C"
    wind_unit = "mph" if unit_system == "imperial" else "km/h"

    logger.info(
        "Weather fetched for (%.4f, %.4f): %s %.1f/%.1f%s wind %.1f%s",
        lat, lon, condition, temp_max, temp_min, temp_unit, wind_speed, wind_unit
    )

    return {
        "temp_max":    temp_max,
        "temp_min":    temp_min,
        "condition":   condition,
        "wind_speed":  wind_speed,
        "humidity":    humidity,
        "unit_system": unit_system,
        "temp_unit":   temp_unit,
        "wind_unit":   wind_unit,
    }
