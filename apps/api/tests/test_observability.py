"""Monitoring catches simulated failures, tagged and scrubbed (PR-027). Nothing leaves the
process: a capturing transport stands in for Sentry."""

from collections.abc import Iterator
from typing import Any

import pytest
import sentry_sdk
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

from app.core.config import Settings
from app.core.observability import REDACTED, before_breadcrumb, init_sentry, scrub_text
from app.main import create_app

LEAKY = (
    "failed for clara.borg@seaview.example.test on +356 2100 0001 with "
    "Bearer eyJhbGciOi.payload.sig and re_live_abcdefgh12345"
)
CAPTURED: list[dict[str, Any]] = []


class CapturingTransport(Transport):
    def capture_envelope(self, envelope: Envelope) -> None:
        for item in envelope.items:
            if item.type == "event" and item.payload.json is not None:
                CAPTURED.append(item.payload.json)


@pytest.fixture
def monitored() -> Iterator[TestClient]:
    CAPTURED.clear()
    settings = Settings(
        _env_file=None,
        environment="test",
        sentry_dsn=SecretStr("https://public@o0.ingest.sentry.io/0"),
    )
    assert init_sentry(settings, "api", transport=CapturingTransport)
    app = create_app(settings)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError(LEAKY)

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        sentry_sdk.get_client().flush()
        sentry_sdk.init(dsn=None)  # back to off for the other tests


def test_an_unhandled_error_is_captured_with_ids_and_without_personal_data(
    monitored: TestClient,
) -> None:
    response = monitored.get(
        "/boom",
        headers={
            "X-Request-ID": "req-simulated-1",
            "Authorization": "Bearer secret-token",
            "Cookie": "sb-auth=secret",
        },
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    sentry_sdk.get_client().flush()

    [event] = CAPTURED
    assert event["tags"]["request_id"] == "req-simulated-1"
    assert event["tags"]["component"] == "api"
    assert event["environment"] == "test"
    text = str(event)
    for secret in (
        "clara.borg@seaview.example.test",
        "+356 2100 0001",
        "eyJhbGciOi",
        "re_live_abcdefgh12345",
        "secret-token",
        "sb-auth",
    ):
        assert secret not in text
    assert REDACTED in text
    assert "user" not in event
    assert "server_name" not in event
    request = event.get("request", {})
    assert not {"headers", "cookies", "data", "query_string"} & set(request)
    for exc in event["exception"]["values"]:
        for frame in exc["stacktrace"]["frames"]:
            assert "vars" not in frame


def test_monitoring_is_off_without_a_dsn() -> None:
    assert init_sentry(Settings(_env_file=None, environment="test"), "api") is False


@pytest.mark.parametrize(
    ("raw", "kept"),
    [
        ("Contact mia@lumen.example.test", "Contact "),
        ("Call 79001234 or +356 7900 1234", "Call "),
        ("token whsec_ZTJlLXVudXNlZA and sk_test_1234567890", "token "),
        ("order 42 failed", "order 42 failed"),  # short numbers and ids stay readable
    ],
)
def test_scrubbing(raw: str, kept: str) -> None:
    assert scrub_text(raw).startswith(kept)
    if raw == kept:
        assert scrub_text(raw) == raw


def test_breadcrumbs_keep_only_method_and_status() -> None:
    crumb = before_breadcrumb(
        {
            "category": "httplib",
            "message": "GET https://api.example.test/v1/w/lumen?email=a@b.test",
            "data": {"url": "https://x/?token=1", "method": "GET", "status_code": 500},
        },
        {},
    )
    assert crumb is not None
    assert crumb["data"] == {"method": "GET", "status_code": 500}
    assert "a@b.test" not in crumb["message"]
