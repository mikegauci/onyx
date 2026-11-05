"""The committed OpenAPI contract (source of the TS client) matches the running API."""

from pathlib import Path

from app.core.errors import ErrorCode
from app.openapi_export import openapi_document, render

CONTRACT = Path(__file__).resolve().parents[3] / "packages" / "api-client" / "openapi.json"


def test_committed_contract_is_current() -> None:
    assert CONTRACT.read_text(encoding="utf-8") == render(), (
        "OpenAPI contract is stale: run `make api-client` and commit the result."
    )


def test_product_routes_are_versioned() -> None:
    paths = set(openapi_document()["paths"])
    assert paths - {"/health"}
    assert all(p.startswith("/v1/") for p in paths - {"/health"})


def test_operation_ids_are_route_names() -> None:
    ids = {
        op["operationId"] for item in openapi_document()["paths"].values() for op in item.values()
    }
    assert {"me", "read_workspace", "update_workspace", "create_invitation"} <= ids


def test_errors_use_the_standard_schema() -> None:
    doc = openapi_document()
    patch = doc["paths"]["/v1/w/{slug}"]["patch"]["responses"]
    for status in ("401", "403", "404", "422"):
        ref = patch[status]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/ErrorResponse")
    assert set(doc["components"]["schemas"]["ErrorCode"]["enum"]) == {c.value for c in ErrorCode}
