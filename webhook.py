"""
Flask webhook server for inbound WhatsApp messages via Twilio.
Run via main.py (with WEBHOOK_ENABLED=true) or directly for development.
"""

import os
import logging
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv
load_dotenv()

from conversation.handler import handle

logger = logging.getLogger(__name__)

app = Flask(__name__)

WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "5000"))


@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive an inbound WhatsApp message and return a TwiML reply."""
    try:
        sender = request.form.get("From", "")
        body   = request.form.get("Body", "").strip()

        # Strip the "whatsapp:" prefix Twilio adds to the From field
        phone = sender.replace("whatsapp:", "").strip()

        logger.info(
            "[%s] Inbound from %s: %s",
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            phone,
            body,
        )

        reply = handle(phone, body)

        logger.info(
            "[%s] Reply to %s: %s",
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            phone,
            reply,
        )

    except Exception as e:
        logger.error("Webhook handler error: %s", e, exc_info=True)
        reply = "Sorry, something went wrong on our end. Please try again shortly. 🙏"

    resp = MessagingResponse()
    resp.message(reply)
    return str(resp), 200, {"Content-Type": "text/xml"}


@app.route("/health", methods=["GET"])
def health():
    """Simple liveness check."""
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=WEBHOOK_PORT)
