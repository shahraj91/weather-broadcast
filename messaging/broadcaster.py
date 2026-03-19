"""
Sends WhatsApp messages via the Twilio API.
Includes rate limiting (0.5s between sends) and exponential backoff retry (x3).
"""

import os
import time
import logging
from typing import Optional

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from dotenv import load_dotenv
load_dotenv()

from utils.pii import mask_phone

logger = logging.getLogger(__name__)

SEND_DELAY_SECONDS = 0.5    # Pause between each send (Twilio free tier: ~1 msg/sec)
MAX_RETRIES        = 3
RETRY_BASE_DELAY   = 2      # seconds — doubles on each retry (2, 4, 8)


class BroadcasterError(Exception):
    """Raised when a message send fails after all retries."""

class BroadcasterAuthError(BroadcasterError):
    """Raised on Twilio authentication failure (don't retry)."""

class SandboxOptInError(BroadcasterError):
    """Raised when a user has not yet sent the Twilio sandbox join code."""


def _get_client() -> Client:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        raise BroadcasterAuthError(
            "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set in .env"
        )
    return Client(account_sid, auth_token)


def _validate_phone(phone: str):
    """Ensure phone is in E.164 format."""
    if not phone.startswith("+"):
        raise ValueError(f"Phone must be E.164 format (start with +), got: '{phone}'")
    if len(phone) < 8 or len(phone) > 16:
        raise ValueError(f"Phone length out of range: '{phone}'")


def send(phone: str, message: str, client: Optional[Client] = None) -> str:
    """
    Send a WhatsApp message to a single phone number.

    Args:
        phone:   Recipient phone in E.164 format e.g. '+14155552671'
        message: Message body string
        client:  Optional pre-built Twilio client (useful for testing)

    Returns:
        Twilio message SID string on success.

    Raises:
        ValueError:            If phone format is invalid.
        BroadcasterAuthError:  On Twilio 401 authentication error.
        BroadcasterError:      If send fails after all retries.
    """
    _validate_phone(phone)

    whatsapp_to   = f"whatsapp:{phone}"
    whatsapp_from = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    if client is None:
        client = _get_client()

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            msg = client.messages.create(
                from_=whatsapp_from,
                to=whatsapp_to,
                body=message,
            )
            logger.info("Sent to %s — SID: %s", mask_phone(phone), msg.sid)
            return msg.sid

        except TwilioRestException as e:
            if e.status == 401:
                raise BroadcasterAuthError(f"Twilio authentication failed: {e.msg}")

            last_error = e
            backoff = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                "Send failed (attempt %d/%d) to %s: %s — retrying in %ds",
                attempt, MAX_RETRIES, mask_phone(phone), e.msg, backoff
            )
            if attempt < MAX_RETRIES:
                time.sleep(backoff)

        except Exception as e:
            last_error = e
            logger.error("Unexpected error sending to %s: %s", mask_phone(phone), e)
            break

    raise BroadcasterError(
        f"Failed to send to {mask_phone(phone)} after {MAX_RETRIES} attempts: {last_error}"
    )


def send_to_user(user, message: str, client: Optional[Client] = None) -> str:
    """
    Send a WhatsApp message to a User object, enforcing sandbox opt-in check.

    Args:
        user:    User dataclass instance (must have .phone and .sandbox_opted_in)
        message: Message body string
        client:  Optional pre-built Twilio client

    Returns:
        Twilio message SID string on success.

    Raises:
        SandboxOptInError: If user.sandbox_opted_in is False.
        ValueError:        If phone format is invalid.
        BroadcasterAuthError: On Twilio 401 authentication error.
        BroadcasterError:  If send fails after all retries.
    """
    if not user.sandbox_opted_in:
        logger.warning("Skipping %s — sandbox opt-in required", mask_phone(user.phone))
        raise SandboxOptInError(
            f"Skipping {mask_phone(user.phone)} — sandbox opt-in required"
        )
    return send(user.phone, message, client=client)


def send_batch(recipients: list, message: str, client: Optional[Client] = None) -> dict:
    """
    Send the same message to a list of User objects.
    Respects SEND_DELAY_SECONDS between each send.
    Users without sandbox opt-in are skipped (not counted as failures).

    Args:
        recipients: List of User objects (must have .phone, .id, .sandbox_opted_in)
        message:    Message body string
        client:     Optional pre-built Twilio client

    Returns:
        Dict with 'success', 'failed', and 'skipped' lists.
    """
    if client is None:
        client = _get_client()

    results = {"success": [], "failed": [], "skipped": []}

    sent_count = 0
    for user in recipients:
        try:
            if sent_count > 0:
                time.sleep(SEND_DELAY_SECONDS)
            sid = send_to_user(user, message, client=client)
            results["success"].append({"user_id": user.id, "phone": user.phone, "sid": sid})
            sent_count += 1
        except SandboxOptInError:
            results["skipped"].append({"user_id": user.id, "phone": user.phone})
        except BroadcasterAuthError:
            # Auth errors are fatal — no point continuing the batch
            logger.error("Auth error — aborting batch send")
            results["failed"].append({
                "user_id": user.id, "phone": user.phone,
                "error": "Auth failure", "retryable": False
            })
            break
        except BroadcasterError as e:
            results["failed"].append({
                "user_id": user.id, "phone": user.phone,
                "error": str(e), "retryable": True
            })

    logger.info(
        "Batch complete: %d sent, %d failed, %d skipped (sandbox opt-in)",
        len(results["success"]), len(results["failed"]), len(results["skipped"])
    )
    return results
