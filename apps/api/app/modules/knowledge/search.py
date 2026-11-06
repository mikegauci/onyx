"""Hybrid retrieval: PostgreSQL full-text search and pgvector similarity, fused by rank.

Every query filters by the bound tenant explicitly; row-level security (gated by the
``knowledge`` module) applies as well. Results below the relevance bar are dropped, and when
nothing clears it the search abstains instead of returning weak matches.
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Literal

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import Float, bindparam, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import Function

from app.ai.embeddings import EMBEDDING_DIMENSIONS
from app.ai.errors import AIBudgetExceededError, AIProviderError, AIUnavailableError
from app.ai.gateway import AIGateway
from app.modules.knowledge.models import Chunk, Document

logger = logging.getLogger("onyx.knowledge")

CANDIDATES = 20  # per method, before fusion
RRF_K = 60  # reciprocal-rank fusion constant
# Cosine similarity a semantic-only match needs. Keyword matches always qualify.
MIN_SIMILARITY = 0.35
TEXT_SEARCH_CONFIG = "english"

MatchKind = Literal["keyword", "semantic"]


@dataclass
class Hit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    page: int | None
    content: str
    score: float = 0.0
    matched_by: list[MatchKind] = field(default_factory=list)


@dataclass(frozen=True)
class SearchResult:
    hits: list[Hit]
    mode: Literal["hybrid", "keyword"]

    @property
    def abstained(self) -> bool:
        return not self.hits


def tsvector(content: str) -> Function[str]:
    """The full-text vector stored with each chunk (same configuration as queries)."""
    return func.to_tsvector(TEXT_SEARCH_CONFIG, content)


async def search(
    db: AsyncSession,
    organization_id: uuid.UUID,
    gateway: AIGateway | None,
    query: str,
    *,
    limit: int = 5,
    actor_user_id: uuid.UUID | None = None,
) -> SearchResult:
    ranked: dict[uuid.UUID, Hit] = {}

    tsquery = func.websearch_to_tsquery(TEXT_SEARCH_CONFIG, query)
    keyword_rows = await db.execute(
        select(Chunk.id, Chunk.document_id, Document.title, Chunk.page, Chunk.content)
        .join(
            Document,
            (Document.organization_id == Chunk.organization_id)
            & (Document.id == Chunk.document_id),
        )
        .where(Chunk.organization_id == organization_id, Chunk.search.op("@@")(tsquery))
        .order_by(func.ts_rank_cd(Chunk.search, tsquery).desc(), Chunk.id)
        .limit(CANDIDATES)
    )
    for rank, row in enumerate(keyword_rows.all()):
        hit = ranked.setdefault(
            row.id, Hit(row.id, row.document_id, row.title, row.page, row.content)
        )
        hit.score += 1 / (RRF_K + rank + 1)
        hit.matched_by.append("keyword")

    vector = await _query_vector(gateway, organization_id, query, actor_user_id)
    if vector is not None:
        query_vector = bindparam("query_vector", vector, type_=VECTOR(EMBEDDING_DIMENSIONS))
        distance = Chunk.embedding.op("<=>", return_type=Float)(query_vector)
        semantic_rows = await db.execute(
            select(
                Chunk.id,
                Chunk.document_id,
                Document.title,
                Chunk.page,
                Chunk.content,
                distance.label("distance"),
            )
            .join(
                Document,
                (Document.organization_id == Chunk.organization_id)
                & (Document.id == Chunk.document_id),
            )
            .where(Chunk.organization_id == organization_id)
            .order_by(distance, Chunk.id)
            .limit(CANDIDATES)
        )
        for rank, row in enumerate(semantic_rows.all()):
            if 1 - float(row.distance) < MIN_SIMILARITY:
                continue
            hit = ranked.setdefault(
                row.id, Hit(row.id, row.document_id, row.title, row.page, row.content)
            )
            hit.score += 1 / (RRF_K + rank + 1)
            hit.matched_by.append("semantic")

    hits = sorted(ranked.values(), key=lambda h: (-h.score, str(h.chunk_id)))[:limit]
    return SearchResult(hits=hits, mode="hybrid" if vector is not None else "keyword")


async def _query_vector(
    gateway: AIGateway | None,
    organization_id: uuid.UUID,
    query: str,
    actor_user_id: uuid.UUID | None,
) -> list[float] | None:
    """The query's embedding, or None (keyword search only) when embeddings are unavailable."""
    if gateway is None:
        return None
    try:
        batch = await gateway.embed(
            organization_id=organization_id,
            texts=[query],
            input_type="query",
            actor_user_id=actor_user_id,
        )
    except (AIUnavailableError, AIProviderError, AIBudgetExceededError) as exc:
        logger.warning(
            "knowledge search fell back to keywords",
            extra={
                "fields": {"organization_id": str(organization_id), "reason": type(exc).__name__}
            },
        )
        return None
    return batch.vectors[0]
