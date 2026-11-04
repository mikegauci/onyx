"""Supabase access-token verification (no network, no database)."""

import time
import uuid
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.auth.tokens import AuthenticationError, AuthUnavailableError
from tests.auth_tokens import TokenFactory

SUBJECT = uuid.uuid4()


@pytest.fixture(scope="module")
def tokens() -> TokenFactory:
    return TokenFactory()


def test_valid_token_yields_identity(tokens: TokenFactory) -> None:
    identity = tokens.verifier().verify(tokens.token(SUBJECT, "a@example.test"))
    assert identity.subject == SUBJECT
    assert identity.email == "a@example.test"


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://evil.example/auth/v1"},
        {"aud": "anon"},
        {"exp": int(time.time()) - 3600},
        {"role": "anon"},
        {"role": "service_role"},
        {"is_anonymous": True},
        {"sub": "not-a-uuid"},
    ],
    ids=["issuer", "audience", "expired", "anon-role", "service-role", "anonymous", "subject"],
)
def test_invalid_claims_are_rejected(tokens: TokenFactory, overrides: dict[str, Any]) -> None:
    with pytest.raises(AuthenticationError):
        tokens.verifier().verify(tokens.token(SUBJECT, "a@example.test", **overrides))


def test_missing_expiry_is_rejected(tokens: TokenFactory) -> None:
    claims = tokens.claims(SUBJECT, "a@example.test")
    del claims["exp"]
    token = jwt.encode(claims, tokens.private_key, algorithm="ES256", headers={"kid": tokens.kid})
    with pytest.raises(AuthenticationError):
        tokens.verifier().verify(token)


def test_shared_secret_token_is_rejected(tokens: TokenFactory) -> None:
    token = jwt.encode(
        tokens.claims(SUBJECT, "a@example.test"),
        "a-shared-secret-of-at-least-32-bytes!!",
        algorithm="HS256",
        headers={"kid": tokens.kid},
    )
    with pytest.raises(AuthenticationError, match="algorithm"):
        tokens.verifier().verify(token)


def test_unsigned_token_is_rejected(tokens: TokenFactory) -> None:
    token = jwt.encode(tokens.claims(SUBJECT, "a@example.test"), "", algorithm="none")
    with pytest.raises(AuthenticationError):
        tokens.verifier().verify(token)


def test_token_signed_by_another_key_is_rejected(tokens: TokenFactory) -> None:
    other = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(AuthenticationError):
        tokens.verifier().verify(tokens.token(SUBJECT, "a@example.test", key=other))


def test_unknown_key_id_is_rejected(tokens: TokenFactory) -> None:
    with pytest.raises(AuthenticationError, match="signing key"):
        tokens.verifier().verify(tokens.token(SUBJECT, "a@example.test", kid="rotated-away"))


def test_malformed_token_is_rejected(tokens: TokenFactory) -> None:
    with pytest.raises(AuthenticationError):
        tokens.verifier().verify("not.a.jwt")


def test_unreachable_jwks_is_unavailable_not_unauthenticated() -> None:
    tokens = TokenFactory()
    tokens.keys.fail = jwt.PyJWKClientConnectionError("timeout")
    with pytest.raises(AuthUnavailableError):
        tokens.verifier().verify(tokens.token(SUBJECT, "a@example.test"))
