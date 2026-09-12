"""HMAC-bound guest claim tokens. Never persist the plaintext token."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from django.conf import settings

_CLAIM_PREFIX = 'guest-claim-v1:'


def generate_claim_token() -> str:
    """Opaque token returned once at guest checkout start."""
    return secrets.token_urlsafe(32)


def hash_claim_token(token: str) -> str:
    """SHA-256 HMAC keyed by SECRET_KEY. Stored on PaymentTransaction."""
    key = str(settings.SECRET_KEY).encode('utf-8')
    message = f'{_CLAIM_PREFIX}{token}'.encode('utf-8')
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def claim_token_matches(stored_hash: str, token: str | None) -> bool:
    """Constant-time compare. Missing hash or token is always a miss."""
    if not stored_hash or not token:
        return False
    digest = hash_claim_token(token)
    return hmac.compare_digest(stored_hash, digest)
