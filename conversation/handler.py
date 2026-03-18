"""
Inbound WhatsApp conversation handler.
Classifies intent via Llama and routes each message to the right action.
"""

import os
import json
import logging
import requests

from dotenv import load_dotenv
load_dotenv()

from database.db import Database
from weather.fetcher import get_forecast

logger = logging.getLogger(__name__)

DB_PATH       = os.getenv("DB_PATH", "./data/weather_broadcast.db")
LLAMA_API_URL = os.getenv("LLAMA_API_URL", "http://localhost:11434/api/generate")
LLAMA_MODEL   = os.getenv("LLAMA_MODEL", "llama3")
LLAMA_TIMEOUT = int(os.getenv("LLAMA_TIMEOUT", "60"))

INTENTS = ("WEATHER_QUERY", "ACTIVITY_UPDATE", "WEATHER_NOW", "UNSUBSCRIBE", "GENERAL")

VALID_ACTIVITIES = {"runner", "cyclist", "farmer", "photographer", "parent", "general"}


# ── Llama helpers ──────────────────────────────────────────────────────────

def _llama(prompt: str, max_tokens: int = 150, temperature: float = 0.7) -> str:
    """Call Ollama and return the response text, or empty string on failure."""
    payload = {
        "model":  LLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": temperature},
    }
    try:
        resp = requests.post(LLAMA_API_URL, json=payload, timeout=LLAMA_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        logger.warning("Llama call failed: %s", e)
        return ""


def _detect_intent(message_text: str) -> str:
    """Return one of the 5 INTENTS for the given user message."""
    prompt = (
        "Classify this WhatsApp message into exactly one of these categories:\n\n"
        "WEATHER_QUERY    — asking about weather conditions (e.g. 'Will it rain?', 'Hot tomorrow?')\n"
        "ACTIVITY_UPDATE  — telling us about their lifestyle (e.g. 'I am a runner', 'I like cycling')\n"
        "WEATHER_NOW      — wants current conditions right now (e.g. 'Weather now?', 'What is it like?')\n"
        "UNSUBSCRIBE      — wants to stop messages (e.g. 'stop', 'unsubscribe', 'cancel')\n"
        "GENERAL          — anything else\n\n"
        f"Message: {message_text}\n\n"
        "Reply with ONLY the category name, nothing else."
    )
    result = _llama(prompt, max_tokens=20, temperature=0.1).upper()
    for intent in INTENTS:
        if intent in result:
            return intent
    return "GENERAL"


def _extract_activity(message_text: str) -> tuple[str, str]:
    """
    Ask Llama to extract activity type and notes from the user message.
    Returns (activity, notes) — activity is always a valid VALID_ACTIVITIES member.
    """
    prompt = (
        "Extract the user's activity type and any notes from this message.\n\n"
        f"Message: {message_text}\n\n"
        "Activity must be one of: runner, cyclist, farmer, photographer, parent, general\n"
        'Reply in JSON only: {"activity": "<type>", "notes": "<notes or empty string>"}'
    )
    raw = _llama(prompt, max_tokens=80, temperature=0.1)
    try:
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data     = json.loads(match.group())
            activity = data.get("activity", "general").lower().strip()
            notes    = data.get("notes", "").strip()
            if activity not in VALID_ACTIVITIES:
                activity = "general"
            return activity, notes
    except Exception as e:
        logger.warning("Activity extraction parse failed: %s", e)
    return "general", message_text


def _answer_weather_query(user, weather: dict, question: str) -> str:
    """Use Llama to answer a specific weather question. Falls back to a summary."""
    prompt = (
        f'The user asked: "{question}"\n\n'
        f"Today's weather data:\n"
        f"  High: {weather['temp_max']}{weather['temp_unit']}\n"
        f"  Low:  {weather['temp_min']}{weather['temp_unit']}\n"
        f"  Condition: {weather['condition']}\n"
        f"  Wind: {weather['wind_speed']} {weather['wind_unit']}\n"
        f"  Humidity: {weather['humidity']}%\n\n"
        f"Answer in 2-3 friendly sentences. Do not add preamble."
    )
    answer = _llama(prompt, max_tokens=150)
    if answer:
        return answer
    return (
        f"Today: {weather['condition']}. "
        f"High of {weather['temp_max']}{weather['temp_unit']}, "
        f"low of {weather['temp_min']}{weather['temp_unit']}. "
        f"Wind: {weather['wind_speed']} {weather['wind_unit']}, humidity {weather['humidity']}%."
    )


def _general_response(user, message_text: str) -> str:
    """Use Llama to give a helpful general reply. Falls back to a static message."""
    name = user.name or "there"
    prompt = (
        f"You are a friendly weather assistant. The user's name is {name}.\n"
        f"User message: {message_text}\n\n"
        f"Respond helpfully in 2-3 sentences. Stay on topics of weather, nature, or daily planning. "
        f"Do not add preamble."
    )
    answer = _llama(prompt, max_tokens=150)
    return answer or "I'm here to help with weather and daily planning! Feel free to ask about today's forecast. ☀️"


def _save_context(db: Database, phone: str, user_msg: str, bot_reply: str):
    """Append this exchange to the user's conversation context, keeping last 3 pairs."""
    ctx      = db.get_user_conversation_context(phone)
    messages = ctx.get("messages", [])
    messages.append({"role": "user",      "content": user_msg})
    messages.append({"role": "assistant", "content": bot_reply})
    # Keep last 3 exchanges = 6 messages
    if len(messages) > 6:
        messages = messages[-6:]
    db.update_conversation_context(phone, json.dumps({"messages": messages}))


# ── Public entry point ─────────────────────────────────────────────────────

def handle(phone: str, message_text: str) -> str:
    """
    Process an inbound WhatsApp message and return the reply string.

    Args:
        phone:        E.164 phone number (whatsapp: prefix already stripped)
        message_text: Raw message body from the user

    Returns:
        Reply string ready to send back via Twilio.
    """
    db = Database(DB_PATH)
    try:
        user = db.get_user_by_phone(phone)
        if not user:
            return (
                "Sorry, I don't recognise your number. "
                "Please contact your administrator to be added to the system. ☀️"
            )

        intent = _detect_intent(message_text)
        logger.info("Intent for %s: %s", phone, intent)

        if intent == "WEATHER_QUERY":
            weather = get_forecast(
                lat=user.lat, lon=user.lon,
                unit_system=user.unit_system, timezone=user.timezone,
            )
            reply = _answer_weather_query(user, weather, message_text)

        elif intent == "ACTIVITY_UPDATE":
            activity, notes = _extract_activity(message_text)
            db.update_activity(phone, activity, notes or None)
            name  = user.name or "there"
            reply = f"Got it {name}! I'll tailor your morning updates for {activity}. 🌤️"

        elif intent == "WEATHER_NOW":
            weather = get_forecast(
                lat=user.lat, lon=user.lon,
                unit_system=user.unit_system, timezone=user.timezone,
            )
            reply = (
                f"Right now in your area: {weather['condition']}. "
                f"High of {weather['temp_max']}{weather['temp_unit']}, "
                f"low of {weather['temp_min']}{weather['temp_unit']}. "
                f"Wind: {weather['wind_speed']} {weather['wind_unit']}, "
                f"humidity {weather['humidity']}%. 🌤️"
            )

        elif intent == "UNSUBSCRIBE":
            db.deactivate_user(phone)
            reply = "You've been unsubscribed. Stay safe! ☀️"

        else:  # GENERAL
            reply = _general_response(user, message_text)

        _save_context(db, phone, message_text, reply)
        return reply

    finally:
        db.close()
