"""
Admin alerting utilities.
Checks Ollama health and sends WhatsApp admin alerts via Twilio.
"""

import os
import logging
import requests

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

_LLAMA_API_URL     = os.getenv("LLAMA_API_URL", "http://localhost:11434/api/generate")
_OLLAMA_ORIGIN     = "/".join(_LLAMA_API_URL.split("/")[:3])   # e.g. http://localhost:11434
OLLAMA_HEALTH_URL  = f"{_OLLAMA_ORIGIN}/api/tags"
OLLAMA_HEALTH_TIMEOUT = 5   # seconds


def check_ollama_health() -> bool:
    """GET the Ollama /api/tags endpoint. Returns True if reachable."""
    try:
        resp = requests.get(OLLAMA_HEALTH_URL, timeout=OLLAMA_HEALTH_TIMEOUT)
        return resp.status_code == 200
    except Exception:
        return False


def send_admin_alert(message: str) -> None:
    """
    Send a WhatsApp message to ADMIN_PHONE env var via Twilio.
    Used for system-level alerts to the operator.
    Silently swallows errors so alerts never crash the system.
    """
    admin_phone = os.getenv("ADMIN_PHONE")
    if not admin_phone:
        logger.warning("ADMIN_PHONE not set — cannot send admin alert")
        return

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    if not account_sid or not auth_token:
        logger.warning("Twilio credentials not set — cannot send admin alert")
        return

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        client.messages.create(
            from_=from_number,
            to=f"whatsapp:{admin_phone}",
            body=message,
        )
        logger.info("Admin alert sent to %s", admin_phone)
    except Exception as e:
        logger.error("Failed to send admin alert: %s", e)
