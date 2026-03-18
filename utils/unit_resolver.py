"""
Determines the unit system (imperial or metric) for a given lat/lon.
Only the US, Liberia, and Myanmar use imperial; all other countries use metric.
Uses geopy reverse geocoding to resolve country from coordinates.
"""

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# Only three countries in the world use imperial (Fahrenheit/mph)
IMPERIAL_COUNTRY_CODES = {"US", "LR", "MM"}

_geolocator = Nominatim(user_agent="weather_broadcast_system/1.0")


def resolve_unit_system(lat: float, lon: float) -> str:
    """
    Return 'imperial' or 'metric' based on the country at the given coordinates.

    Args:
        lat: Latitude  (-90 to 90)
        lon: Longitude (-180 to 180)

    Returns:
        'imperial' for US, Liberia, Myanmar. 'metric' for all other countries.
        Defaults to 'metric' if country cannot be determined.
    """
    try:
        location = _geolocator.reverse(
            f"{lat}, {lon}",
            exactly_one=True,
            language="en",
            timeout=10,
        )

        if location is None:
            return "metric"

        address = location.raw.get("address", {})
        country_code = address.get("country_code", "").upper()

        return "imperial" if country_code in IMPERIAL_COUNTRY_CODES else "metric"

    except (GeocoderTimedOut, GeocoderServiceError):
        # Network issue — default to metric (affects only 3 countries negatively)
        return "metric"


def resolve_country_code(lat: float, lon: float) -> str | None:
    """
    Return the ISO 3166-1 alpha-2 country code for the given coordinates.
    Returns None if it cannot be determined.
    """
    try:
        location = _geolocator.reverse(
            f"{lat}, {lon}",
            exactly_one=True,
            language="en",
            timeout=10,
        )
        if location is None:
            return None
        address = location.raw.get("address", {})
        return address.get("country_code", "").upper() or None

    except (GeocoderTimedOut, GeocoderServiceError):
        return None
