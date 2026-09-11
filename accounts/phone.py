"""
Iranian mobile numbers as the account identifier.

Canonical storage form is `09xxxxxxxxx`. Register, login, and guest checkout
all funnel through `normalize_iranian_phone` so `+98` / `98` / `9` variants
cannot create duplicate users.
"""

from __future__ import annotations

import re

from rest_framework.exceptions import ValidationError

# Optional 0 / 98 / +98 prefix, then the 10-digit 9xxxxxxxxx subscriber number.
_IRAN_MOBILE = re.compile(r'^(?:0|\+98|98)?9\d{9}$')


def normalize_iranian_phone(value: str | None) -> str:
    """
    Return `09xxxxxxxxx` or raise ValidationError.

    Spaces and dashes are stripped so pasted numbers from WhatsApp still work.
    """
    if value is None:
        raise ValidationError('شماره موبایل وارد شده معتبر نیست.')
    cleaned = re.sub(r'[\s\-]', '', str(value).strip())
    if not _IRAN_MOBILE.match(cleaned):
        raise ValidationError('شماره موبایل وارد شده معتبر نیست.')
    if cleaned.startswith('+98'):
        return '0' + cleaned[3:]
    if cleaned.startswith('98'):
        return '0' + cleaned[2:]
    if not cleaned.startswith('0'):
        return '0' + cleaned
    return cleaned
