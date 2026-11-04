import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings


def test_generates_request_id_when_missing(client: TestClient) -> None:
    response = client.get("/health")

    assert len(response.headers["X-Request-ID"]) == 32


def test_echoes_well_formed_request_id(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "abc-123"})

    assert response.headers["X-Request-ID"] == "abc-123"


def test_replaces_malformed_request_id(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "bad id <script>"})

    assert response.headers["X-Request-ID"] != "bad id <script>"
    assert len(response.headers["X-Request-ID"]) == 32


def test_cors_allows_configured_origin(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "http://localhost:3001"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:3001"


def test_cors_rejects_unlisted_origin(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_settings_parse_comma_separated_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONYX_API_CORS_ORIGINS", "http://a.test, http://b.test")

    assert Settings(_env_file=None).cors_origins == ["http://a.test", "http://b.test"]


def test_settings_reject_wildcard_origin() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=["*"])
