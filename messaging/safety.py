"""
Content safety filter for outgoing WhatsApp messages.

Two-layer check:
  1. Fast keyword filter  — no API call, blocks immediately on known bad terms
  2. Llama age-check      — YES/NO prompt; on timeout defaults to safe (True)
"""

import os
import logging
import requests

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

LLAMA_API_URL  = os.getenv("LLAMA_API_URL", "http://localhost:11434/api/generate")
LLAMA_MODEL    = os.getenv("LLAMA_MODEL", "llama3")
SAFETY_TIMEOUT = 10   # seconds — on timeout, default to safe

BLOCKED_TERMS = [
    # Violence
    "kill", "murder", "shoot", "stab", "bomb", "attack", "terrorist",
    "genocide", "massacre", "torture", "assault", "rape",
    # Self-harm
    "suicide", "self-harm", "cut yourself", "hang yourself", "overdose",
    # Explicit content
    "pornography", "porn", "nude", "naked", "xxx",
    # Hate speech
    "nigger", "faggot", "kike", "spic", "chink", "wetback",
    # Hard drugs
    "heroin", "cocaine", "crystal meth", "fentanyl",
]


def is_safe(text: str) -> bool:
    """
    Two-layer safety check.

    Layer 1: Fast keyword filter — returns False immediately on any blocked term.
    Layer 2: Llama YES/NO check  — returns False if Llama responds with NO.

    On timeout or error in layer 2, defaults to True (never block due to infra failure).
    Returns True if safe, False if unsafe.
    """
    if os.getenv("SAFETY_CHECK_ENABLED", "true").lower() != "true":
        return True

    # Layer 1 — keyword filter (case-insensitive)
    lower = text.lower()
    for term in BLOCKED_TERMS:
        if term in lower:
            logger.warning("Safety layer-1: blocked term detected in outbound message")
            return False

    # Layer 2 — Llama age-appropriateness check
    if not LLAMA_MODEL:
        return True   # No model configured — skip layer 2

    prompt = (
        "Is the following message appropriate for all ages including "
        "children? Reply with only YES or NO.\n\n"
        f"Message: {text}"
    )
    payload = {
        "model":  LLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": 5, "temperature": 0.0},
    }
    try:
        resp = requests.post(LLAMA_API_URL, json=payload, timeout=SAFETY_TIMEOUT)
        resp.raise_for_status()
        answer = resp.json().get("response", "").strip().upper()
        if not answer.startswith("YES"):
            logger.warning("Safety layer-2: Llama flagged message as inappropriate")
            return False
        return True
    except requests.Timeout:
        logger.warning("Safety check timed out — defaulting to safe")
        return True
    except Exception as e:
        logger.warning("Safety check failed (%s) — defaulting to safe", e)
        return True


def apply_safety(text: str, fallback_text: str) -> str:
    """
    Return text unchanged if it passes safety checks.
    If unsafe: log a warning, increment safety_blocks_total, return fallback_text.
    """
    if is_safe(text):
        return text

    logger.warning("Safety: unsafe message replaced with static fallback")
    try:
        from utils.metrics import increment
        increment("safety_blocks_total")
    except Exception:
        pass
    return fallback_text
