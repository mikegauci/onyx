"""Verification of Supabase Auth access tokens against the project's JWKS.

Only asymmetric algorithms are accepted; shared-secret (HS*) and unsigned tokens are rejected.
The issuer, audience, expiry and subject are mandatory. Tokens are never logged.
"""

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import jwt
from jwt import PyJWK, PyJWKClient

ALLOWED_ALGORITHMS = ("ES256", "RS256")
JWKS_CACHE_SECONDS = 600
JWKS_TIMEOUT_SECONDS = 5


class AuthenticationError(Exception):
    """The request's credentials are missing or invalid (HTTP 401)."""


class AuthUnavailableError(Exception):
    """Tokens cannot be verified right now, e.g. the JWKS is unreachable (HTTP 503)."""


class SigningKeyResolver(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> PyJWK: ...


@dataclass(frozen=True)
class VerifiedIdentity:
    subject: uuid.UUID
    email: str | None


class TokenVerifier:
    def __init__(self, *, issuer: str, audience: str, keys: SigningKeyResolver) -> None:
        self._issuer = issuer
        self._audience = audience
        self._keys = keys

    @classmethod
    def for_jwks_url(cls, *, jwks_url: str, issuer: str, audience: str) -> "TokenVerifier":
        client = PyJWKClient(
            jwks_url, cache_keys=True, lifespan=JWKS_CACHE_SECONDS, timeout=JWKS_TIMEOUT_SECONDS
        )
        return cls(issuer=issuer, audience=audience, keys=client)

    def verify(self, token: str) -> VerifiedIdentity:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Malformed token.") from exc
        if header.get("alg") not in ALLOWED_ALGORITHMS:
            raise AuthenticationError("Token algorithm is not allowed.")

        try:
            signing_key = self._keys.get_signing_key_from_jwt(token)
        except jwt.PyJWKClientConnectionError as exc:
            raise AuthUnavailableError("Signing keys are unavailable.") from exc
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Unknown signing key.") from exc

        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=signing_key,
                algorithms=list(ALLOWED_ALGORITHMS),
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
                leeway=30,
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Invalid token.") from exc

        if claims.get("role") != "authenticated" or claims.get("is_anonymous") is True:
            raise AuthenticationError("Token is not for an authenticated user.")
        try:
            subject = uuid.UUID(str(claims["sub"]))
        except ValueError as exc:
            raise AuthenticationError("Invalid subject.") from exc
        email = claims.get("email")
        return VerifiedIdentity(
            subject=subject, email=email if isinstance(email, str) and email else None
        )
