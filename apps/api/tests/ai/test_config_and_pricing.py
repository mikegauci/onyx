"""AI configuration, pricing and provider selection. No database, no network."""

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.ai.errors import AIUnavailableError
from app.ai.pricing import TokenPrice, estimate_input_tokens
from app.ai.providers import (
    FAKE_MODEL,
    ModelRef,
    build_model,
    example_from_schema,
    price_for,
    resolve_model,
)
from app.ai.redaction import safe_fields
from app.core.config import AIModelPrice, Settings
from app.openapi_export import render

REPO = Path(__file__).resolve().parents[4]
DEPLOYED: dict[str, Any] = {
    "environment": "preview",
    "cors_origins": ["https://app.preview.example.test"],
}


def _settings(**values: Any) -> Settings:
    return Settings(_env_file=None, **({"environment": "test"} | values))


def _price(inp: str, out: str) -> AIModelPrice:
    return AIModelPrice(input_usd_per_mtok=Decimal(inp), output_usd_per_mtok=Decimal(out))


def test_cost_is_integer_micros_rounded_up() -> None:
    price = TokenPrice.from_config(_price("2.50", "10.00"))
    assert price.cost_micros(1_000_000, 0) == 2_500_000
    assert price.cost_micros(0, 1_000_000) == 10_000_000
    assert price.cost_micros(1, 0) == 3  # 2.5 micro-USD rounds up, never down
    assert price.cost_micros(0, 0) == 0
    assert isinstance(price.cost_micros(123, 456), int)
    with pytest.raises(ValueError, match="negative"):
        price.cost_micros(-1, 0)


def test_price_config_rejects_floats_precision_and_negatives() -> None:
    with pytest.raises(ValidationError):
        _price("-1", "1")
    with pytest.raises(ValidationError):
        _price("0.0000001", "1")


def test_input_estimate_over_counts() -> None:
    assert estimate_input_tokens("") == 500
    assert estimate_input_tokens("abc" * 100) >= 100 + 500


def test_local_default_is_the_fake_model() -> None:
    settings = _settings()
    assert resolve_model(settings, "diagnostic") == FAKE_MODEL
    assert price_for(settings, FAKE_MODEL).cost_micros(1_000_000, 0) == 1_000_000


def test_workload_override_wins() -> None:
    settings = _settings(
        ai_default_model="openai:general", ai_workload_models={"diagnostic": "anthropic:small"}
    )
    assert resolve_model(settings, "diagnostic") == ModelRef("anthropic", "small")
    assert resolve_model(settings, "other") == ModelRef("openai", "general")


def test_deployed_without_a_model_is_unavailable() -> None:
    settings = Settings(_env_file=None, **DEPLOYED)
    with pytest.raises(AIUnavailableError):
        resolve_model(settings, "diagnostic")


def test_deployed_environment_refuses_the_fake_model() -> None:
    with pytest.raises(ValidationError, match="fake AI model"):
        Settings(_env_file=None, ai_default_model="fake:onyx", **DEPLOYED)
    settings = Settings(_env_file=None, **DEPLOYED)
    with pytest.raises(AIUnavailableError):
        build_model(FAKE_MODEL, settings)
    with pytest.raises(AIUnavailableError):
        price_for(settings, FAKE_MODEL)


@pytest.mark.parametrize("ref", ["gpt", "unknown:model", "openai:", ":x"])
def test_malformed_model_references_are_rejected(ref: str) -> None:
    with pytest.raises(ValidationError):
        _settings(ai_default_model=ref)


def test_unpriced_model_is_unavailable() -> None:
    settings = _settings(ai_default_model="openai:general")
    with pytest.raises(AIUnavailableError):
        price_for(settings, ModelRef("openai", "general"))
    priced = _settings(
        ai_default_model="openai:general", ai_model_prices={"openai:general": _price("1", "2")}
    )
    assert price_for(priced, ModelRef("openai", "general")).cost_micros(1_000_000, 0) == 1_000_000


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_missing_key_is_unavailable(provider: str) -> None:
    with pytest.raises(AIUnavailableError):
        build_model(ModelRef(provider, "general"), _settings())


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_configured_key_builds_the_adapter_without_calling_it(provider: str) -> None:
    settings = _settings(
        openai_api_key="sk-test-not-a-real-key", anthropic_api_key="sk-test-not-a-real-key"
    )
    model = build_model(ModelRef(provider, "general"), settings)
    assert model.model_name == "general"


def test_keys_are_secret_in_settings_repr() -> None:
    settings = _settings(openai_api_key="sk-test-not-a-real-key")
    assert "sk-test-not-a-real-key" not in repr(settings)
    assert "sk-test-not-a-real-key" not in str(settings.model_dump())


def test_example_from_schema_builds_valid_values() -> None:
    schema = {
        "type": "object",
        "properties": {
            "status": {"const": "ok"},
            "kind": {"enum": ["a", "b"]},
            "count": {"type": "integer", "minimum": 2},
            "items": {"type": "array"},
            "flag": {"type": "boolean"},
            "note": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        },
    }
    assert example_from_schema(schema) == {
        "status": "ok",
        "kind": "a",
        "count": 2,
        "items": [],
        "flag": False,
        "note": "fake",
    }


def test_log_fields_drop_anything_not_allowlisted() -> None:
    fields = safe_fields(model="m", prompt="secret prompt", reply="secret reply", api_key="k")
    assert fields == {"model": "m"}


def test_contract_exposes_no_provider_secrets() -> None:
    contract = render().lower()
    for word in ("api_key", "apikey", "secret", "openai_api", "anthropic_api"):
        assert word not in contract


def test_browser_apps_never_reference_provider_keys() -> None:
    """Provider keys are API-only settings; no frontend source or env file names them."""
    roots = [REPO / "apps" / "platform", REPO / "apps" / "site", REPO / "packages"]
    suffixes = {".ts", ".tsx", ".js", ".mjs", ".json", ".example"}
    for root in roots:
        for path in root.rglob("*"):
            if "node_modules" in path.parts or ".next" in path.parts or not path.is_file():
                continue
            if path.suffix not in suffixes and not path.name.startswith(".env"):
                continue
            body = path.read_text(encoding="utf-8", errors="ignore")
            for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
                assert name not in body, f"{path} references {name}"
