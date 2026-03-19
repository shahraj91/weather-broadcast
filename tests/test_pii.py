"""
Tests for utils/pii.py — PII masking for log-safe output.
"""

import pytest
from utils.pii import mask_phone, mask_user
from database.models import User


class TestMaskPhone:

    def test_standard_us_number(self):
        """TP-01: Standard E.164 US number is masked correctly."""
        assert mask_phone("+18183573973") == "+1818***3973"

    def test_short_number_returns_placeholder(self):
        """TP-02: Numbers shorter than 8 chars return '***'."""
        assert mask_phone("+123") == "***"
        assert mask_phone("+1234") == "***"

    def test_eight_char_number(self):
        """TP-03: Exactly 8-char number is masked without error."""
        result = mask_phone("+1234567")   # 8 chars
        assert "***" in result
        assert result.endswith("4567")

    def test_uk_number(self):
        """TP-04: UK E.164 number is masked correctly."""
        result = mask_phone("+447700900100")
        assert "***" in result
        assert result.endswith("0100")

    def test_mask_preserves_leading_plus(self):
        """TP-05: Masked number still starts with the country prefix."""
        result = mask_phone("+18183573973")
        assert result.startswith("+")

    def test_last_four_digits_visible(self):
        """TP-06: Last 4 digits are always visible."""
        assert mask_phone("+18183573973").endswith("3973")


class TestMaskUser:

    def _make_user(self, phone, name=None):
        return User(
            id=1,
            phone=phone,
            lat=37.0,
            lon=-122.0,
            timezone="America/Los_Angeles",
            unit_system="metric",
            name=name,
        )

    def test_mask_user_with_name(self):
        """TP-07: Named user returns 'name (masked_phone)' format."""
        user   = self._make_user("+18183573973", name="Alice")
        result = mask_user(user)
        assert result == "Alice (+1818***3973)"

    def test_mask_user_without_name(self):
        """TP-08: Unnamed user uses 'Unknown' as the name."""
        user   = self._make_user("+18183573973", name=None)
        result = mask_user(user)
        assert result == "Unknown (+1818***3973)"

    def test_mask_user_format(self):
        """TP-09: Result is always 'name (masked)' format."""
        user   = self._make_user("+447700900100", name="Bob")
        result = mask_user(user)
        assert result.startswith("Bob (")
        assert result.endswith(")")
        assert "***" in result
