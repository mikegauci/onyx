"""Test-only token minting: an in-process ES256 key stands in for Supabase's JWKS."""

import json
import time
import uuid
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from jwt import PyJWK
from jwt.algorithms import ECAlgorithm

from app.core.auth.tokens import TokenVerifier

ISSUER = "https://test-project.supabase.example/auth/v1"
AUDIENCE = "authenticated"


class StaticKeys:
    """A SigningKeyResolver over a fixed set of keys, keyed by ``kid``."""

    def __init__(self, keys: dict[str, PyJWK], *, fail: Exception | None = None) -> None:
        self._keys = keys
        self.fail = fail

    def get_signing_key_from_jwt(self, token: str) -> PyJWK:
        if self.fail is not None:
            raise self.fail
        kid = jwt.get_unverified_header(token).get("kid")
        if kid not in self._keys:
            raise jwt.PyJWKClientError(f"Unable to find a signing key that matches: {kid!r}")
        return self._keys[kid]


class TokenFactory:
    def __init__(self) -> None:
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.kid = "test-key-1"
        public_jwk = json.loads(ECAlgorithm.to_jwk(self.private_key.public_key()))
        public_jwk.update({"kid": self.kid, "alg": "ES256", "use": "sig"})
        self.keys = StaticKeys({self.kid: PyJWK(public_jwk)})

    def verifier(self) -> TokenVerifier:
        return TokenVerifier(issuer=ISSUER, audience=AUDIENCE, keys=self.keys)

    def claims(self, subject: uuid.UUID, email: str | None, **overrides: Any) -> dict[str, Any]:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": str(subject),
            "email": email,
            "role": "authenticated",
            "iat": now,
            "exp": now + 3600,
            "is_anonymous": False,
        }
        claims.update(overrides)
        return {k: v for k, v in claims.items() if v is not None}

    def token(
        self,
        subject: uuid.UUID,
        email: str | None = None,
        *,
        key: Any = None,
        kid: str | None = None,
        **overrides: Any,
    ) -> str:
        return jwt.encode(
            self.claims(subject, email, **overrides),
            key or self.private_key,
            algorithm="ES256",
            headers={"kid": kid or self.kid},
        )
