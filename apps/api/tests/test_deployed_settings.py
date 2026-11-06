"""Environment validation for hosted (preview/production) deployments."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import MissingDatabaseUrlError, Settings
from app.main import create_app

APP_ORIGIN = "https://app-preview.example.test"


def deployed(environment: str = "preview", **overrides: object) -> Settings:
    values: dict[str, object] = {"environment": environment, "cors_origins": [APP_ORIGIN]}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.mark.parametrize("environment", ["preview", "production"])
def test_deployed_settings_accept_https_origins(environment: str) -> None:
    assert deployed(environment).cors_origins == [APP_ORIGIN]


@pytest.mark.parametrize(
    "origins",
    [
        [],
        ["http://app.example.test"],
        ["https://localhost:3001"],
        ["https://127.0.0.1"],
        ["https://dev.localhost"],
        ["https://app.example.test/path"],
        ["not-a-url"],
    ],
)
@pytest.mark.parametrize("environment", ["preview", "production"])
def test_deployed_settings_reject_unsafe_origins(environment: str, origins: list[str]) -> None:
    with pytest.raises(ValidationError):
        deployed(environment, cors_origins=origins)


def test_deployed_settings_reject_default_local_origin() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="preview")


def test_local_settings_allow_localhost() -> None:
    assert Settings(_env_file=None, environment="local").cors_origins == ["http://localhost:3001"]


def test_unknown_environment_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="staging")


@pytest.fixture
def preview_client() -> TestClient:
    return TestClient(create_app(deployed()))


def test_preflight_allows_configured_origin(preview_client: TestClient) -> None:
    response = preview_client.options(
        "/health",
        headers={"Origin": APP_ORIGIN, "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == APP_ORIGIN


def test_preflight_rejects_unlisted_origin(preview_client: TestClient) -> None:
    response = preview_client.options(
        "/health",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_health_reports_environment(preview_client: TestClient) -> None:
    assert preview_client.get("/health").json()["environment"] == "preview"


def test_blank_database_urls_are_treated_as_unset() -> None:
    settings = Settings(_env_file=None, database_url="", migration_database_url="  ")
    assert settings.database_url is None
    assert settings.migration_database_url is None


def test_database_url_is_required_when_used() -> None:
    with pytest.raises(MissingDatabaseUrlError):
        Settings(_env_file=None).require_database_url()


def test_migration_url_falls_back_locally_only() -> None:
    url = "postgresql+psycopg://u:p@db.example.com/onyx"
    assert Settings(_env_file=None, database_url=url).require_migration_database_url() == url
    deployed = Settings(
        _env_file=None,
        environment="preview",
        cors_origins=["https://app.example.com"],
        database_url=url,
    )
    with pytest.raises(MissingDatabaseUrlError):
        deployed.require_migration_database_url()


def test_database_urls_are_not_exposed_in_repr() -> None:
    settings = Settings(_env_file=None, database_url="postgresql+psycopg://u:hunter2@h/db")
    assert "hunter2" not in repr(settings)


@pytest.mark.parametrize("environment", ["preview", "production"])
def test_fake_email_provider_is_refused_when_deployed(environment: str) -> None:
    with pytest.raises(ValidationError):
        deployed(environment, email_provider="fake")


def test_fake_email_provider_is_allowed_locally() -> None:
    assert Settings(_env_file=None, environment="test", email_provider="fake").email_provider == (
        "fake"
    )
