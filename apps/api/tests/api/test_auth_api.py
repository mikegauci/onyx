"""Authentication at the HTTP boundary and first-sign-in provisioning."""

import uuid

import jwt
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.api.conftest import As
from tests.auth_tokens import TokenFactory


def test_missing_token_is_401_with_challenge(api: TestClient) -> None:
    response = api.get("/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_token_is_401(api: TestClient) -> None:
    assert api.get("/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_wrong_scheme_is_401(api: TestClient, as_: As) -> None:
    token = as_.seeded("olivia.owner@lumen.example.test")["Authorization"].split()[1]
    assert api.get("/me", headers={"Authorization": f"Basic {token}"}).status_code == 401


def test_unreachable_jwks_is_503(api: TestClient, as_: As, tokens: TokenFactory) -> None:
    headers = as_.seeded("olivia.owner@lumen.example.test")
    tokens.keys.fail = jwt.PyJWKClientConnectionError("timeout")
    try:
        assert api.get("/me", headers=headers).status_code == 503
    finally:
        tokens.keys.fail = None


def test_unconfigured_auth_and_database_are_503(tokens: TokenFactory, as_: As) -> None:
    settings = Settings(_env_file=None, environment="test")
    with TestClient(create_app(settings)) as client:
        assert client.get("/me").status_code == 503
    with TestClient(create_app(settings, token_verifier=tokens.verifier())) as client:
        assert client.get("/me", headers=as_.seeded("a@b.test")).status_code == 503
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200


def test_first_sign_in_creates_a_profile_with_no_workspaces(api: TestClient, as_: As) -> None:
    subject = uuid.uuid4()
    headers = as_.subject(subject, "New.Person@example.test")
    first = api.get("/me", headers=headers)
    assert first.status_code == 200
    body = first.json()
    assert body["user"]["email"] == "New.Person@example.test"
    assert body["user"]["display_name"] == "New.Person"
    assert body["workspaces"] == []
    assert api.get("/me", headers=headers).json()["user"]["id"] == body["user"]["id"]


def test_existing_email_is_never_linked_to_a_new_login(api: TestClient, as_: As) -> None:
    # A new Supabase subject presenting a seeded user's email must not take over the profile.
    response = api.get("/me", headers=as_.subject(uuid.uuid4(), "olivia.owner@lumen.example.test"))
    assert response.status_code == 409


def test_token_without_email_is_403(api: TestClient, as_: As) -> None:
    assert api.get("/me", headers=as_.subject(uuid.uuid4(), None)).status_code == 403
