"""
Flask webhook server for inbound WhatsApp messages via Twilio.
Run via main.py (with WEBHOOK_ENABLED=true) or directly for development.
"""

import os
import logging
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
from dotenv import load_dotenv
load_dotenv()

from conversation.handler import handle
from utils.pii import mask_phone
from utils.metrics import increment, get_summary, reset as reset_metric
from utils.log import structured_log

logger = logging.getLogger(__name__)

app = Flask(__name__)

WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "5000"))

# ── Rate Limiting ──────────────────────────────────────────────────────────
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=["60 per minute"],
        storage_uri="memory://",
    )
    logger.debug("Flask-Limiter enabled: 60 req/min per IP")
except ImportError:
    limiter = None
    logger.warning("flask-limiter not installed — rate limiting disabled")


# ── Twilio signature validation ────────────────────────────────────────────

def _validate_twilio_signature() -> bool:
    """
    Validate the X-Twilio-Signature header.
    Returns True if valid, or if TWILIO_SIGNATURE_VALIDATION != 'true'.
    """
    if os.getenv("TWILIO_SIGNATURE_VALIDATION", "false").lower() != "true":
        return True

    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    base_url   = os.getenv("WEBHOOK_BASE_URL", "")
    signature  = request.headers.get("X-Twilio-Signature", "")
    url        = f"{base_url.rstrip('/')}/webhook"
    params     = request.form.to_dict()

    try:
        validator = RequestValidator(auth_token)
        return validator.validate(url, params, signature)
    except Exception as e:
        logger.error("Signature validation error: %s", e)
        return False


# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive an inbound WhatsApp message and return a TwiML reply."""
    increment("webhook_requests_total")

    # Signature validation
    if not _validate_twilio_signature():
        sender = request.form.get("From", "unknown")
        phone  = sender.replace("whatsapp:", "").strip()
        increment("webhook_rejected_total")
        logger.warning(
            "Rejected request with invalid Twilio signature from %s",
            mask_phone(phone),
        )
        return jsonify({"error": "Forbidden"}), 403

    try:
        sender = request.form.get("From", "")
        body   = request.form.get("Body", "").strip()
        phone  = sender.replace("whatsapp:", "").strip()

        structured_log(
            "webhook_inbound",
            phone=mask_phone(phone),
            body_length=len(body),
        )

        reply = handle(phone, body)

        structured_log(
            "webhook_reply",
            phone=mask_phone(phone),
            reply_length=len(reply),
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


@app.route("/metrics", methods=["GET"])
def metrics():
    """Return system metrics as JSON. Requires ?api_key=<METRICS_API_KEY>."""
    api_key      = os.getenv("METRICS_API_KEY", "")
    provided_key = request.args.get("api_key", "")
    if not api_key or provided_key != api_key:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(get_summary())


@app.route("/metrics/reset", methods=["POST"])
def metrics_reset():
    """
    Reset a single metric counter to 0.
    Requires ?api_key=<METRICS_API_KEY> and ?name=<metric_name>.
    """
    api_key      = os.getenv("METRICS_API_KEY", "")
    provided_key = request.args.get("api_key", "")
    if not api_key or provided_key != api_key:
        return jsonify({"error": "Unauthorized"}), 401

    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"error": "Missing required parameter: name"}), 400

    reset_metric(name)
    return jsonify({"reset": name, "value": 0})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=WEBHOOK_PORT)
