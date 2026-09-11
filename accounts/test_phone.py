"""
Iranian mobile number normalization used by register, login, and guest checkout.

Canonical form is `09xxxxxxxxx`. Incoming `+98`, `98`, or `9` prefixes are accepted.
"""

from __future__ import annotations

import pytest
from rest_framework.exceptions import ValidationError

from accounts.phone import normalize_iranian_phone


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('09123456789', '09123456789'),
        ('9123456789', '09123456789'),
        ('+989123456789', '09123456789'),
        ('989123456789', '09123456789'),
        (' 0912 345 6789 ', '09123456789'),
        ('0912-345-6789', '09123456789'),
    ],
)
def test_normalize_iranian_phone_accepts_common_forms(raw, expected):
    assert normalize_iranian_phone(raw) == expected


@pytest.mark.parametrize('raw', ['12345', '02122334455', '0912345678', 'abcd', '', None])
def test_normalize_iranian_phone_rejects_invalid(raw):
    with pytest.raises(ValidationError):
        normalize_iranian_phone(raw)
