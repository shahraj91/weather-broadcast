"""
Generates friendly WhatsApp weather messages using the local Llama model.
Each message includes a weather summary and a kid-friendly fun fact.

Falls back to a static template if Llama is unavailable or times out.
"""

import os
import time
import logging
import requests
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

LLAMA_API_URL = os.getenv("LLAMA_API_URL", "http://localhost:11434/api/generate")
LLAMA_MODEL   = os.getenv("LLAMA_MODEL", "llama3")
LLAMA_TIMEOUT = 60   # seconds
MAX_TOKENS    = 400


class FormatterError(Exception):
    """Raised when message generation fails completely."""


SYSTEM_PROMPT = """You are a cheerful weather assistant. Raj is sending a daily WhatsApp message on your behalf to the recipient.
Your audience includes kids and families. Keep language simple, warm, and positive.

Your message MUST have exactly two parts:

PART 1 — Weather summary. Start with a friendly greeting to the recipient by their name
  (provided in the weather data below), then present the weather details in this exact
  format (one item per line):

  🌡️ High: <value>  |  Low: <value>
  🌤️ Condition: <value>
  💨 Wind: <value>
  💧 Humidity: <value>

  End with 1 sentence advising whether to bring a jacket or umbrella.

PART 2 — Fun Fact (one kid-friendly fact loosely related to today's weather,
  season, or nature). Prefix it with exactly: 🌟 Fun Fact:

Rules:
- No scary, violent, or inappropriate content
- Factually accurate
- Total message under 300 words
- Simple enough for a 10-year-old to enjoy
- Do NOT include any preamble, intro line, or meta-commentary (e.g. "Here is...", "Sure!", "Of course!") — start the message directly with the greeting"""


_ACTIVITY_HINTS = {
    "runner": (
        "The recipient is a runner. Add a short note on the best time window to run today "
        "based on temperature and wind, and mention the feels-like temperature if it matters."
    ),
    "cyclist": (
        "The recipient is a cyclist. Add a short note on the best time window to cycle, "
        "wind speed and direction impact, and feels-like temperature."
    ),
    "farmer": (
        "The recipient is a farmer. Add a short note on total expected rainfall today and "
        "any frost risk, and what it means for crops or livestock."
    ),
    "photographer": (
        "The recipient is a photographer. Add a short note on golden hour timing, "
        "cloud cover quality for photography, and visibility conditions."
    ),
    "parent": (
        "The recipient is a parent. Add a short note on morning commute/school-run "
        "conditions and what afternoon pickup conditions will be like."
    ),
    "general": None,   # No extra activity hint — standard morning update
}


def _build_user_prompt(weather: dict, user=None) -> str:
    name = getattr(user, "name", None)
    activity = getattr(user, "activity", None)
    activity_notes = getattr(user, "activity_notes", None)

    recipient = f"  Recipient name:   {name}\n" if name else ""
    base = (
        f"Weather data for today:\n"
        f"{recipient}"
        f"  Temperature high: {weather['temp_max']}{weather['temp_unit']}\n"
        f"  Temperature low:  {weather['temp_min']}{weather['temp_unit']}\n"
        f"  Condition:        {weather['condition']}\n"
        f"  Wind speed:       {weather['wind_speed']} {weather['wind_unit']}\n"
        f"  Humidity:         {weather['humidity']}%\n"
        f"  Unit system:      {weather['unit_system']}\n"
    )

    if activity and activity in _ACTIVITY_HINTS:
        hint = _ACTIVITY_HINTS[activity]
        if hint:   # None for "general" — no extra context added
            if activity_notes:
                hint += f" Note about this user: {activity_notes}"
            base += f"\n  Activity context: {hint}\n"

    return base


def _strip_preamble(text: str) -> str:
    """Remove any LLM preamble lines before the actual message body."""
    import re
    lines = text.splitlines()
    preamble = re.compile(
        r"^\s*(here\s+is|here'?s|sure[!,]?|of course[!,]?|certainly[!,]?|okay[!,]?)",
        re.IGNORECASE,
    )
    while lines and preamble.match(lines[0]):
        lines.pop(0)
    return "\n".join(lines).strip()


def _call_llama(prompt: str) -> Optional[str]:
    """
    Invoke the Ollama HTTP API to generate a weather message.
    """
    if not LLAMA_MODEL:
        logger.warning("LLAMA_MODEL not set — skipping Ollama call")
        return None

    payload = {
        "model":  LLAMA_MODEL,
        "system": SYSTEM_PROMPT,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": MAX_TOKENS,
            "temperature": 0.7,
            "top_p":       0.9,
        },
    }

    try:
        response = requests.post(LLAMA_API_URL, json=payload, timeout=LLAMA_TIMEOUT)
        response.raise_for_status()
        output = response.json().get("response", "").strip()
        if not output:
            logger.warning("Ollama returned empty response")
            return None
        return _strip_preamble(output)

    except requests.Timeout:
        logger.warning("Ollama timed out after %ds", LLAMA_TIMEOUT)
        return None
    except requests.ConnectionError:
        logger.error("Could not connect to Ollama at '%s' — is it running?", LLAMA_API_URL)
        return None
    except requests.HTTPError as e:
        logger.error("Ollama HTTP error: %s", e)
        return None
    except Exception as e:
        logger.error("Ollama call failed: %s", e)
        return None


def _increment_metric(name: str) -> None:
    """Increment a metric counter, silently ignoring import errors."""
    try:
        from utils.metrics import increment
        increment(name)
    except Exception:
        pass


def _try_record_latency(name: str, ms: float) -> None:
    """Record a latency sample, silently ignoring import errors."""
    try:
        from utils.metrics import record_latency
        record_latency(name, ms)
    except Exception:
        pass


def validate_output(message: str, weather: dict) -> bool:
    """
    Verify that a Llama-generated message contains the expected weather data.

    Checks:
      - temp_max value appears within ±2 degrees (as an integer)
      - temp_min value appears within ±2 degrees
      - At least one keyword from the condition string appears in the message

    Returns True if valid, False if hallucination detected.
    """
    temp_max  = weather.get("temp_max", 0)
    temp_min  = weather.get("temp_min", 0)
    condition = weather.get("condition", "")

    def temp_present(temp: float) -> bool:
        base = int(round(float(temp)))
        return any(str(base + offset) in message for offset in range(-2, 3))

    if not temp_present(temp_max):
        return False
    if not temp_present(temp_min):
        return False

    stop_words = {"and", "or", "the", "a", "an", "with", "of"}
    keywords = [
        w.lower() for w in condition.split()
        if w.lower() not in stop_words and len(w) > 2
    ]
    if keywords:
        msg_lower = message.lower()
        if not any(kw in msg_lower for kw in keywords):
            return False

    return True


def _static_fallback(weather: dict) -> str:
    """Plain-text fallback when Llama is unavailable."""
    temp_max   = weather["temp_max"]
    temp_min   = weather["temp_min"]
    temp_unit  = weather["temp_unit"]
    condition  = weather["condition"]
    wind_speed = weather["wind_speed"]
    wind_unit  = weather["wind_unit"]
    humidity   = weather["humidity"]

    emoji = "🌤️"
    if "rain" in condition.lower() or "drizzle" in condition.lower() or "shower" in condition.lower():
        emoji = "🌧️"
    elif "snow" in condition.lower():
        emoji = "❄️"
    elif "thunder" in condition.lower():
        emoji = "⛈️"
    elif "clear" in condition.lower():
        emoji = "☀️"
    elif "fog" in condition.lower():
        emoji = "🌫️"

    message = (
        f"Good morning! {emoji}\n\n"
        f"Today's forecast: {condition}. "
        f"Expect a high of {temp_max}{temp_unit} and a low of {temp_min}{temp_unit}. "
        f"Wind speeds up to {wind_speed} {wind_unit} with humidity around {humidity}%.\n\n"
        f"🌟 Fun Fact: Did you know that humidity is the amount of water vapour "
        f"in the air? When it's very high, it can make hot days feel even hotter "
        f"because your sweat can't evaporate as easily!"
    )
    return message


def generate(weather: dict, user=None) -> str:
    """
    Generate a WhatsApp-ready weather message with trivia.

    Args:
        weather: Dict returned by weather.fetcher.get_forecast()
        user:    Optional User dataclass. If provided, name and activity context
                 are used to personalise the message.

    Returns:
        Formatted message string ready to send via WhatsApp.

    Raises:
        FormatterError: If both Llama and fallback fail.
    """
    if not isinstance(weather, dict) or "temp_max" not in weather:
        raise FormatterError("Invalid weather data passed to formatter")

    user_prompt = _build_user_prompt(weather, user)

    _t0 = time.time()
    message = _call_llama(user_prompt)
    _try_record_latency("llama_latency_ms", (time.time() - _t0) * 1000)

    header = "📬 Daily Weather Update from Raj\n\n"

    if message:
        # Basic validation: ensure the Fun Fact section is present
        if "🌟 Fun Fact:" not in message:
            logger.warning("Llama output missing Fun Fact section — appending fallback fact")
            message += (
                "\n\n🌟 Fun Fact: Did you know lightning strikes the Earth "
                "about 100 times every single second? That's over 8 million "
                "flashes every day!"
            )
        word_count = len(message.split())
        if word_count > 300:
            logger.warning("Message exceeds 300 words (%d) — consider tuning the prompt", word_count)

        # Hallucination guard — verify output matches the actual weather data
        if os.getenv("HALLUCINATION_CHECK_ENABLED", "true").lower() == "true":
            if not validate_output(message, weather):
                logger.warning(
                    "Hallucination detected — falling back to static template"
                )
                _increment_metric("hallucination_fallbacks_total")
                message = None

    if message:
        # Safety check — pass through content safety filter
        if os.getenv("SAFETY_CHECK_ENABLED", "true").lower() == "true":
            from messaging.safety import apply_safety
            message = apply_safety(message, _static_fallback(weather))
        return header + message

    logger.info("Using static fallback message")
    return header + _static_fallback(weather)
