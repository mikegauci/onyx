"""Embedding models: turn configured text into vectors for tenant-scoped retrieval.

The embedding model is its own workload (``knowledge_embedding``) and never falls back to the
chat model. ``fake`` is a deterministic local model (hashed words, so overlapping words score
as similar); configuration refuses it in deployed environments, and so does this module.
"""

import hashlib
import math
import re
from collections.abc import Callable, Sequence

from pydantic_ai.embeddings import EmbeddingModel, EmbeddingResult, EmbeddingSettings
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.embeddings.result import EmbedInputType
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RequestUsage

from app.ai.errors import AIUnavailableError
from app.ai.providers import ModelRef
from app.core.config import Settings

EMBEDDING_WORKLOAD = "knowledge_embedding"
# Stored vectors have this many dimensions (migration 0017); every model must return it.
EMBEDDING_DIMENSIONS = 1536
FAKE_EMBEDDING = ModelRef("fake", "onyx-fake-embedding")

# Builds the embedding model for a resolved reference. Tests inject their own.
EmbeddingFactory = Callable[[ModelRef, Settings], EmbeddingModel]

_WORD = re.compile(r"[a-z0-9]+")


def resolve_embedding_model(settings: Settings) -> ModelRef:
    """The embedding model: its workload override, or (locally only) the fake. Never the chat
    default, which is not an embedding model."""
    ref = settings.ai_workload_models.get(EMBEDDING_WORKLOAD)
    if ref is None:
        if settings.is_deployed:
            raise AIUnavailableError
        return FAKE_EMBEDDING
    return ModelRef.parse(ref)


def build_embedding_model(model: ModelRef, settings: Settings) -> EmbeddingModel:
    """The real adapter for ``model``. Missing keys and unsupported providers fail closed."""
    if model.provider == "openai":
        if settings.openai_api_key is None:
            raise AIUnavailableError
        return OpenAIEmbeddingModel(
            model.name,
            provider=OpenAIProvider(api_key=settings.openai_api_key.get_secret_value()),
        )
    if model.provider == "fake" and not settings.is_deployed:
        return FakeEmbeddingModel(model.name)
    raise AIUnavailableError


def fake_vector(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Hashed bag of words, L2-normalised. Texts sharing words point the same way."""
    vector = [0.0] * dimensions
    for word in _WORD.findall(text.lower()):
        digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0 if digest[4] & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        vector[0] = 1.0  # a zero vector has no cosine distance
        return vector
    return [v / norm for v in vector]


class FakeEmbeddingModel(EmbeddingModel):
    __test__ = False

    def __init__(self, name: str = FAKE_EMBEDDING.name) -> None:
        self._name = name
        super().__init__()

    @property
    def model_name(self) -> str:
        return self._name

    @property
    def system(self) -> str:
        return "fake"

    async def embed(
        self,
        inputs: str | Sequence[str],
        *,
        input_type: EmbedInputType,
        settings: EmbeddingSettings | None = None,
    ) -> EmbeddingResult:
        inputs, settings = self.prepare_embed(inputs, settings)
        dimensions = settings.get("dimensions") or EMBEDDING_DIMENSIONS
        return EmbeddingResult(
            embeddings=[fake_vector(text, dimensions) for text in inputs],
            inputs=inputs,
            input_type=input_type,
            usage=RequestUsage(input_tokens=sum(len(t) // 4 + 1 for t in inputs)),
            model_name=self.model_name,
            provider_name=self.system,
        )
