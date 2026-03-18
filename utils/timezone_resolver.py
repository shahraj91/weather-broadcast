"""
Resolves an IANA timezone string from a latitude/longitude coordinate pair.
Uses the timezonefinder library — no network call required, purely local lookup.
"""

from timezonefinder import TimezoneFinder

_tf = TimezoneFinder()


def resolve_timezone(lat: float, lon: float) -> str:
    """
    Return the IANA timezone string for the given coordinates.

    Args:
        lat: Latitude  (-90 to 90)
        lon: Longitude (-180 to 180)

    Returns:
        IANA timezone string e.g. 'America/New_York', 'Europe/London'

    Raises:
        ValueError: If coordinates are out of range or timezone cannot be determined.
    """
    if not (-90 <= lat <= 90):
        raise ValueError(f"Latitude {lat} is out of range (-90 to 90)")
    if not (-180 <= lon <= 180):
        raise ValueError(f"Longitude {lon} is out of range (-180 to 180)")

    tz = _tf.timezone_at(lat=lat, lng=lon)

    if tz is None:
        # Fallback: try the closest timezone (handles edge cases near ocean/poles)
        tz = _tf.closest_timezone_at(lat=lat, lng=lon)

    if tz is None:
        raise ValueError(
            f"Could not determine timezone for coordinates ({lat}, {lon}). "
            "Try using the nearest land coordinate."
        )

    return tz
