"""Provider adapters: turn a configured ``<provider>:<model>`` into a Pydantic AI model.

OpenAI and Anthropic are the production providers. ``fake`` is a deterministic local model for
development and tests; configuration refuses it in deployed environments, and so does this
module. Keys are read from settings here and nowhere else.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RequestUsage

from app.ai.errors import AIUnavailableError
from app.ai.pricing import FAKE_PRICE, TokenPrice
from app.core.config import Settings


@dataclass(frozen=True)
class ModelRef:
    provider: str
    name: str

    @classmethod
    def parse(cls, ref: str) -> "ModelRef":
        provider, _, name = ref.partition(":")
        return cls(provider=provider, name=name)

    @property
    def ref(self) -> str:
        return f"{self.provider}:{self.name}"


# Builds the Pydantic AI model for a resolved reference. Tests inject their own.
ModelFactory = Callable[[ModelRef, Settings], Model]

FAKE_MODEL = ModelRef("fake", "onyx-fake")


def resolve_model(settings: Settings, workload: str) -> ModelRef:
    """The model for ``workload``: its override, the default, or (locally only) the fake."""
    ref = settings.ai_workload_models.get(workload) or settings.ai_default_model
    if ref is None:
        if settings.is_deployed:
            raise AIUnavailableError
        return FAKE_MODEL
    return ModelRef.parse(ref)


def price_for(settings: Settings, model: ModelRef) -> TokenPrice:
    """The configured price. An unpriced model is refused, so spend is always computable."""
    if model.provider == "fake" and not settings.is_deployed:
        return TokenPrice.from_config(settings.ai_model_prices.get(model.ref, FAKE_PRICE))
    price = settings.ai_model_prices.get(model.ref)
    if price is None:
        raise AIUnavailableError
    return TokenPrice.from_config(price)


def build_model(model: ModelRef, settings: Settings) -> Model:
    """The real adapter for ``model``. Missing keys fail closed."""
    if model.provider == "openai":
        if settings.openai_api_key is None:
            raise AIUnavailableError
        return OpenAIChatModel(
            model.name,
            provider=OpenAIProvider(api_key=settings.openai_api_key.get_secret_value()),
        )
    if model.provider == "anthropic":
        if settings.anthropic_api_key is None:
            raise AIUnavailableError
        return AnthropicModel(
            model.name,
            provider=AnthropicProvider(api_key=settings.anthropic_api_key.get_secret_value()),
        )
    if model.provider == "fake" and not settings.is_deployed:
        return fake_model(model.name)
    raise AIUnavailableError


# --- the fake model ------------------------------------------------------------------------


def example_from_schema(schema: dict[str, Any], defs: dict[str, Any] | None = None) -> Any:
    """A minimal value that satisfies a simple JSON schema (enough for local development)."""
    defs = defs if defs is not None else schema.get("$defs", {})
    if "$ref" in schema:
        return example_from_schema(defs.get(schema["$ref"].rsplit("/", 1)[-1], {}), defs)
    if "const" in schema:
        return schema["const"]
    if schema.get("enum"):
        return schema["enum"][0]
    for key in ("anyOf", "oneOf", "allOf"):
        if schema.get(key):
            return example_from_schema(schema[key][0], defs)
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        properties: dict[str, Any] = schema.get("properties", {})
        return {name: example_from_schema(sub, defs) for name, sub in properties.items()}
    if kind == "array":
        return []
    if kind == "integer":
        return int(schema.get("minimum", 0))
    if kind == "number":
        return schema.get("minimum", 0)
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    return "fake"


def _fake_reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    characters = sum(len(str(m)) for m in messages)
    usage = RequestUsage(input_tokens=characters // 4 + 1, output_tokens=16)
    if info.output_tools:
        tool = info.output_tools[0]
        args = example_from_schema(tool.parameters_json_schema)
        return ModelResponse(parts=[ToolCallPart(tool.name, args)], usage=usage)
    return ModelResponse(parts=[TextPart("fake")], usage=usage)


def fake_model(name: str = FAKE_MODEL.name) -> FunctionModel:
    return FunctionModel(_fake_reply, model_name=name)
