"""
Data models for the Weather Broadcast System.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class User:
    phone: str                          # E.164 format e.g. +14155552671
    lat: float                          # Latitude  -90 to 90
    lon: float                          # Longitude -180 to 180
    timezone: str                       # IANA e.g. America/New_York
    unit_system: str = "metric"         # 'metric' | 'imperial'
    country_code: Optional[str] = None  # ISO 3166-1 alpha-2
    name: Optional[str] = None          # Recipient's display name
    active: bool = True
    sandbox_opted_in: bool = False      # Must be True before Twilio sandbox will deliver messages
    id: Optional[int] = None
    activity: Optional[str] = None      # e.g. "runner", "farmer", "photographer", "parent", "cyclist", "general"
    activity_notes: Optional[str] = None  # free text e.g. "runs every morning at 6am"
    conversation_context: Optional[str] = None  # last few messages as JSON string

    def __post_init__(self):
        if self.unit_system not in ("metric", "imperial"):
            raise ValueError(f"unit_system must be 'metric' or 'imperial', got '{self.unit_system}'")
        if not self.phone.startswith("+"):
            raise ValueError(f"Phone must be in E.164 format (start with +), got '{self.phone}'")


@dataclass
class SendLog:
    user_id: int
    status: str          # 'success' | 'failed' | 'skipped'
    message_sid: Optional[str] = None   # Twilio message SID on success
    error: Optional[str] = None         # Error message on failure
    retryable: bool = False
    message_body: Optional[str] = None  # Full message text that was sent
    id: Optional[int] = None
