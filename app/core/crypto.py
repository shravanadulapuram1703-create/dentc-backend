"""Symmetric encryption for secrets at rest (EIN, AI-assist client secret).

Uses Fernet (AES-128-CBC + HMAC). The key comes from ``settings.ENCRYPTION_KEY``
if set, otherwise is deterministically derived from ``JWT_SECRET_KEY`` so local
dev works without extra config. Set a dedicated ``ENCRYPTION_KEY`` in production.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


@lru_cache
def _fernet() -> Fernet:
    if settings.ENCRYPTION_KEY:
        return Fernet(settings.ENCRYPTION_KEY.encode())
    digest = hashlib.sha256(settings.JWT_SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str | None) -> str | None:
    if not plaintext:
        return None
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def mask(plaintext: str | None, visible: int = 4) -> str | None:
    """Return a masked form keeping the last ``visible`` chars (e.g. EIN ••••1234)."""
    if not plaintext:
        return None
    s = str(plaintext)
    if len(s) <= visible:
        return "•" * len(s)
    return "•" * (len(s) - visible) + s[-visible:]
