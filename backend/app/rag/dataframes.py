"""Canonical pandas DataFrame schemas used by the future ingestion pipeline."""

from collections.abc import Iterable

import pandas as pd

from app.rag.contracts import ChunkInput, DocumentInput, SourceManifestEntry

SOURCE_COLUMNS = [
    "slug",
    "title",
    "publisher",
    "canonical_url",
    "source_type",
    "domains",
    "languages",
    "rights_status",
    "ingestion_enabled",
    "verification_status",
    "license_notes",
    "selection_notes",
    "metadata",
]
DOCUMENT_COLUMNS = [
    "source_slug",
    "external_id",
    "title",
    "canonical_url",
    "language",
    "source_updated_at",
    "fetched_at",
    "normalized_text",
    "content_hash",
    "metadata",
]
CHUNK_COLUMNS = [
    "document_external_id",
    "chunk_index",
    "section_title",
    "content",
    "content_hash",
    "token_count",
    "embedding_model",
    "metadata",
]


def sources_frame(rows: Iterable[SourceManifestEntry]) -> pd.DataFrame:
    return pd.DataFrame(
        [row.model_dump(mode="json") for row in rows],
        columns=SOURCE_COLUMNS,
    )


def documents_frame(rows: Iterable[DocumentInput]) -> pd.DataFrame:
    return pd.DataFrame(
        [row.model_dump(mode="json") for row in rows],
        columns=DOCUMENT_COLUMNS,
    )


def chunks_frame(rows: Iterable[ChunkInput]) -> pd.DataFrame:
    return pd.DataFrame(
        [row.model_dump(mode="json") for row in rows],
        columns=CHUNK_COLUMNS,
    )
