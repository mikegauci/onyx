"""Every failure uses the standard error body, with the request id and no internals."""

from collections.abc import Iterator

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import ConflictError
from app.main import create_app


class Body(BaseModel):
    count: int


@pytest.fixture
def errors_client() -> Iterator[TestClient]:
    app = create_app(Settings(_env_file=None, environment="test"))
    router = APIRouter()

    @router.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    @router.get("/conflict")
    async def conflict() -> None:
        raise ConflictError("Already done.")

    @router.post("/validate")
    async def validate(body: Body) -> Body:
        return body

    app.include_router(router)
    with TestClient(app) as client:
        yield client


def _error(response: object) -> dict[str, object]:
    body = response.json()  # type: ignore[attr-defined]
    assert set(body) == {"error"}
    error: dict[str, object] = body["error"]
    assert error["request_id"] == response.headers["X-Request-ID"]  # type: ignore[attr-defined]
    return error


def test_unhandled_exception_is_a_generic_500(errors_client: TestClient) -> None:
    response = errors_client.get("/boom", headers={"X-Request-ID": "trace-1"})
    assert response.status_code == 500
    error = _error(response)
    assert error == {
        "code": "internal_error",
        "message": "Something went wrong.",
        "request_id": "trace-1",
    }
    assert "secret" not in response.text


def test_app_error_keeps_its_code_and_message(errors_client: TestClient) -> None:
    response = errors_client.get("/conflict")
    assert response.status_code == 409
    assert _error(response)["code"] == "conflict"
    assert _error(response)["message"] == "Already done."


def test_validation_error_lists_fields_without_echoing_input(errors_client: TestClient) -> None:
    response = errors_client.post("/validate", json={"count": "not-a-number-SENSITIVE"})
    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "validation_failed"
    details = error["details"]
    assert isinstance(details, list)
    assert details[0]["loc"] == ["body", "count"]
    assert "SENSITIVE" not in response.text


@pytest.mark.parametrize(
    ("method", "path", "status", "code"),
    [
        ("get", "/nope", 404, "not_found"),
        ("delete", "/health", 405, "method_not_allowed"),
        ("get", "/v1/me", 503, "unavailable"),
    ],
)
def test_framework_errors_use_the_standard_shape(
    errors_client: TestClient, method: str, path: str, status: int, code: str
) -> None:
    response = getattr(errors_client, method)(path)
    assert response.status_code == status
    assert _error(response)["code"] == code
