"""Invitation tokens: random, single-use, stored only as a SHA-256 hash."""

import hashlib
import secrets
from datetime import timedelta

INVITATION_TTL = timedelta(days=7)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
