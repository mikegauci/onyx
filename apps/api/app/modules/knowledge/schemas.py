"""Knowledge API contracts."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.knowledge.models import FILENAME_MAX_LENGTH, TITLE_MAX_LENGTH, DocumentFormat

# A 5 MB file is about 6.7 million base64 characters.
BASE64_MAX_LENGTH = 7_000_000
QUERY_MAX_LENGTH = 500
EXCERPT_LENGTH = 300


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX_LENGTH)
]
Filename = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=FILENAME_MAX_LENGTH)
]
Content = Annotated[str, StringConstraints(min_length=1, max_length=BASE64_MAX_LENGTH)]


class DocumentUpload(_Input):
    title: Title
    filename: Filename = Field(description="Decides the format: .pdf, .txt or .md")
    content_base64: Content = Field(description="The file, base64-encoded (at most 5 MB)")


class DocumentReplace(_Input):
    filename: Filename
    content_base64: Content
    title: Title | None = Field(default=None, description="A new title; omit to keep it")


class UserRef(BaseModel):
    user_id: uuid.UUID
    display_name: str | None


class DocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    filename: str
    format: DocumentFormat
    size_bytes: int
    version: int
    page_count: int | None
    character_count: int
    chunk_count: int
    created_by: UserRef | None
    updated_by: UserRef | None
    created_at: datetime
    updated_at: datetime


class ChunkPreview(BaseModel):
    ordinal: int
    page: int | None
    excerpt: str = Field(description=f"The first {EXCERPT_LENGTH} characters")


class DocumentDetail(DocumentOut):
    chunks: list[ChunkPreview]


class DocumentList(BaseModel):
    items: list[DocumentOut]


class SearchRequest(_Input):
    query: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=2, max_length=QUERY_MAX_LENGTH)
    ]
    limit: int = Field(default=5, ge=1, le=10)


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    page: int | None
    content: str
    score: float = Field(description="Fused rank score; higher is better")
    matched_by: list[Literal["keyword", "semantic"]]


class SearchOut(BaseModel):
    hits: list[SearchHit]
    mode: Literal["hybrid", "keyword"] = Field(
        description="keyword when semantic search was unavailable for this query"
    )
    abstained: bool = Field(description="True when nothing relevant enough was found")
