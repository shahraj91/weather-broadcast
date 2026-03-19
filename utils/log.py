"""Structured JSON logging helper for key system events."""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def structured_log(event: str, level: str = "INFO", **kwargs) -> None:
    """Emit a structured JSON log entry."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": event,
        **kwargs,
    }
    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn(json.dumps(entry))
