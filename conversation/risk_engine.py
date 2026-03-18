"""
Risk engine — evaluates weather conditions against alert thresholds
and formats a WhatsApp-ready alert message for the user.
"""

import os
import logging
import requests
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

LLAMA_API_URL = os.getenv("LLAMA_API_URL", "http://localhost:11434/api/generate")
LLAMA_MODEL   = os.getenv("LLAMA_MODEL", "llama3")
LLAMA_TIMEOUT = int(os.getenv("LLAMA_TIMEOUT", "60"))


# ── Thresholds ─────────────────────────────────────────────────────────────

# Metric
_HEAT_C      = 35.0   # temp_max > this
_COLD_C      = -10.0  # temp_min < this
_WIND_KMH    = 60.0   # wind_speed > this
_HEAT_IDX_C  = 30.0   # temp_max > this AND humidity > _HUMIDITY_IDX

# Imperial equivalents
_HEAT_F      = 95.0   # 35°C
_COLD_F      = 14.0   # -10°C
_WIND_MPH    = 37.3   # ≈ 60 km/h
_HEAT_IDX_F  = 86.0   # 30°C

_HUMIDITY_FOG = 90    # humidity > this AND "fog" in condition
_HUMIDITY_IDX = 70    # humidity > this for heat-index rule


def check_risks(user, weather: dict) -> list[str]:
    """
    Evaluate weather against risk thresholds.

    Args:
        user:    User dataclass (uses unit_system)
        weather: Dict returned by weather.fetcher.get_forecast()

    Returns:
        List of plain-text alert strings (empty if no risks).
    """
    risks: list[str] = []
    unit      = weather.get("unit_system", "metric")
    temp_max  = weather["temp_max"]
    temp_min  = weather["temp_min"]
    wind      = weather["wind_speed"]
    condition = weather.get("condition", "").lower()
    humidity  = weather.get("humidity", 0)
    temp_unit = weather.get("temp_unit", "°C")
    wind_unit = weather.get("wind_unit", "km/h")

    if unit == "imperial":
        heat_thresh     = _HEAT_F
        cold_thresh     = _COLD_F
        wind_thresh     = _WIND_MPH
        heat_idx_thresh = _HEAT_IDX_F
    else:
        heat_thresh     = _HEAT_C
        cold_thresh     = _COLD_C
        wind_thresh     = _WIND_KMH
        heat_idx_thresh = _HEAT_IDX_C

    # Rule 1 — extreme heat
    if temp_max > heat_thresh:
        risks.append(
            f"🌡️ Extreme heat expected! High of {temp_max}{temp_unit} today — "
            f"stay cool, drink plenty of water, and avoid the midday sun."
        )

    # Rule 2 — dangerous cold
    if temp_min < cold_thresh:
        risks.append(
            f"🥶 Dangerously cold overnight! Low of {temp_min}{temp_unit} — "
            f"dress in warm layers and watch for icy surfaces."
        )

    # Rule 3 — strong winds
    if wind > wind_thresh:
        risks.append(
            f"💨 Strong winds expected! Up to {wind} {wind_unit} today — "
            f"secure loose outdoor items and take care if cycling or driving."
        )

    # Rule 4 — thunderstorm
    if "thunderstorm" in condition:
        risks.append(
            "⛈️ Thunderstorms forecast today — stay safe indoors if possible "
            "and avoid open fields or tall trees."
        )

    # Rule 5 — dense fog with high humidity
    if humidity > _HUMIDITY_FOG and "fog" in condition:
        risks.append(
            f"🌫️ Dense fog alert! Humidity at {humidity}% with foggy conditions — "
            f"reduce speed when driving and allow extra travel time."
        )

    # Rule 6 — heat index (hot AND humid)
    if temp_max > heat_idx_thresh and humidity > _HUMIDITY_IDX:
        risks.append(
            f"🥵 High heat index today! {temp_max}{temp_unit} with {humidity}% humidity "
            f"will feel much hotter — stay hydrated and limit outdoor exertion."
        )

    return risks


def format_risk_alert(user, weather: dict, risks: list[str]) -> str:
    """
    Format a WhatsApp-ready risk alert using Llama, with a static fallback.

    Args:
        user:    User dataclass
        weather: Dict returned by weather.fetcher.get_forecast()
        risks:   Non-empty list of risk strings from check_risks()

    Returns:
        Formatted alert message string.
    """
    name      = user.name or "there"
    risk_list = "\n".join(f"• {r}" for r in risks)

    prompt = (
        f"Write a short, friendly WhatsApp weather safety alert for {name}.\n\n"
        f"Weather risks identified today:\n{risk_list}\n\n"
        f"Requirements:\n"
        f"- Start with exactly: ⚠️ Weather Alert\n"
        f"- Keep it under 80 words\n"
        f"- Warm and encouraging tone\n"
        f"- No preamble, no meta-commentary — start the message directly"
    )

    payload = {
        "model":  LLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": 200,
            "temperature": 0.7,
        },
    }

    try:
        response = requests.post(LLAMA_API_URL, json=payload, timeout=LLAMA_TIMEOUT)
        response.raise_for_status()
        output = response.json().get("response", "").strip()
        if output:
            return output
    except requests.Timeout:
        logger.warning("Ollama timed out generating risk alert")
    except requests.ConnectionError:
        logger.error("Could not connect to Ollama for risk alert")
    except Exception as e:
        logger.error("Risk alert Llama call failed: %s", e)

    # Static fallback
    return (
        f"⚠️ Weather Alert\n\n"
        f"Hi {name}! Please be aware of today's conditions:\n\n"
        f"{risk_list}\n\n"
        f"Stay safe and take care! ☀️"
    )
