"""Typed ingestion boundary between source acquisition and PostgreSQL."""

import hashlib
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

KnowledgeDomain = Literal["nutrition", "workout", "recovery", "safety", "product"]
SourceType = Literal["html", "pdf", "api", "manual"]
RightsStatus = Literal["review_required", "approved", "rejected"]


class SourceManifestEntry(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    title: str
    publisher: str
    canonical_url: HttpUrl
    source_type: SourceType
    domains: list[KnowledgeDomain]
    languages: list[str] = Field(default_factory=lambda: ["en"])
    rights_status: RightsStatus = "review_required"
    ingestion_enabled: bool = False
    verification_status: Literal["pending", "verified", "failed"] = "pending"
    license_notes: str
    selection_notes: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("domains", "languages")
    @classmethod
    def require_non_empty_list(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("must not be empty")
        return value


class DocumentCandidate(BaseModel):
    external_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    source_slug: str
    title: str
    canonical_url: HttpUrl
    language: str = "en"
    domains: list[KnowledgeDomain]
    selection_notes: str


class VerificationEvidence(BaseModel):
    source_slug: str
    external_id: str
    requested_url: HttpUrl
    final_url: HttpUrl
    verified_at: datetime
    status_code: int
    content_type: str
    content_length: int = Field(ge=0)
    content_sha256: str = Field(min_length=64, max_length=64)
    etag: str | None = None
    last_modified: str | None = None
    official_host_match: bool
    pdf_magic_valid: bool | None = None
    discovered_document_urls: list[HttpUrl] = Field(default_factory=list)
    license_markers: list[str] = Field(default_factory=list)
    rights_status: RightsStatus = "review_required"
    notes: list[str] = Field(default_factory=list)


class LicenseEvidence(BaseModel):
    source_slug: str
    external_id: str
    document_sha256: str = Field(min_length=64, max_length=64)
    page_count: int = Field(gt=0)
    inspected_pages: list[int]
    matched_page: int | None = Field(default=None, gt=0)
    detected_license_id: str | None = None
    exact_notice: str | None = None
    attribution_required: bool | None = None
    commercial_use_allowed: bool | None = None
    adaptations_allowed: bool | None = None
    share_alike_required: bool | None = None
    rights_status: RightsStatus = "review_required"
    notes: list[str] = Field(default_factory=list)


class DocumentInput(BaseModel):
    source_slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    external_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    title: str
    canonical_url: HttpUrl
    language: str = "en"
    source_updated_at: datetime | None = None
    fetched_at: datetime
    normalized_text: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def content_hash_matches_text(self) -> "DocumentInput":
        actual = hashlib.sha256(self.normalized_text.encode("utf-8")).hexdigest()
        if self.content_hash != actual:
            raise ValueError("document content_hash does not match normalized_text")
        return self


class ChunkInput(BaseModel):
    document_external_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    chunk_index: int = Field(ge=0)
    section_title: str | None = None
    content: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)
    token_count: int = Field(gt=0)
    embedding_model: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def content_hash_matches_text(self) -> "ChunkInput":
        actual = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        if self.content_hash != actual:
            raise ValueError("chunk content_hash does not match content")
        return self


class IngestionBatch(BaseModel):
    source: SourceManifestEntry
    documents: list[DocumentInput] = Field(min_length=1)
    chunks: list[ChunkInput] = Field(min_length=1)

    @field_validator("documents")
    @classmethod
    def documents_require_approved_source(
        cls,
        value: list[DocumentInput],
        info,
    ) -> list[DocumentInput]:
        source = info.data.get("source")
        if (
            value
            and source
            and (source.rights_status != "approved" or not source.ingestion_enabled)
        ):
            raise ValueError("documents require an approved and enabled source")
        return value

    @model_validator(mode="after")
    def require_consistent_document_chunk_keys(self) -> "IngestionBatch":
        document_ids = [document.external_id for document in self.documents]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("document external_id values must be unique within a batch")

        known_documents = set(document_ids)
        mismatched_sources = {
            document.source_slug
            for document in self.documents
            if document.source_slug != self.source.slug
        }
        if mismatched_sources:
            raise ValueError("every document source_slug must match the batch source slug")
        chunk_keys: set[tuple[str, int]] = set()
        for chunk in self.chunks:
            if chunk.document_external_id not in known_documents:
                raise ValueError(
                    f"chunk references unknown document {chunk.document_external_id!r}"
                )
            key = (chunk.document_external_id, chunk.chunk_index)
            if key in chunk_keys:
                raise ValueError(f"duplicate chunk key: {key!r}")
            chunk_keys.add(key)
        return self


class RetrievedChunk(BaseModel):
    """Citation-ready result returned by the PostgreSQL vector search RPC."""

    chunk_id: str
    document_id: str
    source_slug: str
    document_title: str
    canonical_url: HttpUrl
    section_title: str | None = None
    content: str
    language: str
    similarity: float
