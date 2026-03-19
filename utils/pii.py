"""PII masking utilities for log-safe phone and user references."""


def mask_phone(phone: str) -> str:
    """
    Mask the middle portion of a phone number for log-safe output.
    Input:  "+18183573973"
    Output: "+1818***3973"
    """
    if len(phone) < 8:
        return "***"
    prefix = phone[:-7]
    suffix = phone[-4:]
    return f"{prefix}***{suffix}"


def mask_user(user) -> str:
    """Returns '{name} ({masked_phone})' for log-safe user reference."""
    name  = getattr(user, "name", None) or "Unknown"
    phone = getattr(user, "phone", "")
    return f"{name} ({mask_phone(phone)})"
