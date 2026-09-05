"""Validated, idempotent knowledge ingestion backed by Supabase/PostgreSQL."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.embeddings import Embeddings

from app.embeddings import EMBEDDING_DIM, MODEL_NAME, get_embeddings
from app.rag.chunking import chunk_document, normalize_text, sha256_text
from app.rag.contracts import (
    ChunkInput,
    DocumentInput,
    IngestionBatch,
    SourceManifestEntry,
)
from app.rag.dataframes import chunks_frame, documents_frame, sources_frame
from app.services.supabase import get_supabase


class SourceNotApprovedError(RuntimeError):
    """Raised when database governance has not enabled a source for ingestion."""


class SourceIdentityMismatchError(RuntimeError):
    """Raised when bundle identity differs from the approved database record."""


@dataclass(frozen=True)
class IngestionResult:
    source_slug: str
    run_id: str | None
    status: str
    documents_seen: int
    documents_written: int
    documents_unchanged: int
    chunks_written: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_ingestion_batch(
    path: str | Path,
    *,
    chunk_size: int = 450,
    overlap: int = 70,
) -> IngestionBatch:
    """Load a JSON bundle and fill deterministic hashes/chunks when omitted."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    source = SourceManifestEntry.model_validate(payload["source"])
    now = datetime.now(timezone.utc)
    documents: list[DocumentInput] = []
    for raw_document in payload.get("documents", []):
        item = dict(raw_document)
        item.setdefault("source_slug", source.slug)
        item.setdefault("fetched_at", now.isoformat())
        item["normalized_text"] = normalize_text(item["normalized_text"])
        item.setdefault("content_hash", sha256_text(item["normalized_text"]))
        documents.append(DocumentInput.model_validate(item))

    raw_chunks = payload.get("chunks")
    if raw_chunks:
        chunks = [ChunkInput.model_validate(item) for item in raw_chunks]
    else:
        chunks = [
            chunk
            for document in documents
            for chunk in chunk_document(
                document,
                chunk_size=chunk_size,
                overlap=overlap,
            )
        ]
    return IngestionBatch(source=source, documents=documents, chunks=chunks)


def _source_payload(source: SourceManifestEntry) -> dict[str, Any]:
    return {
        "slug": source.slug,
        "title": source.title,
        "publisher": source.publisher,
        "canonical_url": str(source.canonical_url),
        "source_type": source.source_type,
        "domains": source.domains,
        "languages": source.languages,
        "metadata": {
            **source.metadata,
            "license_notes": source.license_notes,
            "selection_notes": source.selection_notes,
            "verification_status": source.verification_status,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _ensure_registered_approved_source(supabase, source: SourceManifestEntry) -> dict[str, Any]:
    """Require database-approved source identity; bundles cannot mutate governance."""
    response = (
        supabase.table("knowledge_sources")
        .select(
            "id,slug,title,publisher,canonical_url,source_type,domains,languages,"
            "rights_status,ingestion_enabled"
        )
        .eq("slug", source.slug)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        registration = {
            **_source_payload(source),
            "rights_status": "review_required",
            "ingestion_enabled": False,
        }
        supabase.table("knowledge_sources").insert(registration).execute()
        raise SourceNotApprovedError(
            f"source {source.slug!r} was registered as review_required; "
            "approve and enable it in the database before ingestion"
        )

    current = rows[0]
    if current.get("rights_status") != "approved" or not current.get("ingestion_enabled"):
        raise SourceNotApprovedError(
            f"source {source.slug!r} is not approved and enabled in the database"
        )
    mismatches: list[str] = []
    scalar_fields = {
        "title": source.title,
        "publisher": source.publisher,
        "source_type": source.source_type,
    }
    for field, expected in scalar_fields.items():
        if current.get(field) != expected:
            mismatches.append(field)
    if str(current.get("canonical_url", "")).rstrip("/") != str(source.canonical_url).rstrip("/"):
        mismatches.append("canonical_url")
    if set(current.get("domains") or []) != set(source.domains):
        mismatches.append("domains")
    if set(current.get("languages") or []) != set(source.languages):
        mismatches.append("languages")
    if mismatches:
        raise SourceIdentityMismatchError(
            f"source {source.slug!r} differs from its approved database record: "
            f"{', '.join(mismatches)}"
        )
    return current


def _embed_chunks(
    chunks: list[ChunkInput],
    embeddings: Embeddings,
    *,
    batch_size: int,
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(chunks), batch_size):
        texts = [chunk.content for chunk in chunks[start : start + batch_size]]
        vectors.extend(embeddings.embed_documents(texts))
    if len(vectors) != len(chunks):
        raise RuntimeError("embedding provider returned an unexpected vector count")
    for vector in vectors:
        if len(vector) != EMBEDDING_DIM:
            raise RuntimeError(
                f"embedding dimension mismatch: expected {EMBEDDING_DIM}, got {len(vector)}"
            )
        if not all(math.isfinite(value) for value in vector):
            raise RuntimeError("embedding provider returned a non-finite value")
    return vectors


def ingest_batch(
    batch: IngestionBatch,
    *,
    dry_run: bool = False,
    force: bool = False,
    batch_size: int = 64,
    supabase=None,
    embeddings: Embeddings | None = None,
) -> IngestionResult:
    """Embed and atomically upsert each document in a validated batch.

    PostgreSQL function ``upsert_knowledge_document`` owns each document/chunk
    transaction. Re-running the same content is therefore safe and returns
    ``unchanged`` without rewriting vectors.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    # Materialize the documented boundary even in dry-run mode. This also catches
    # accidental schema drift before any database writes.
    sources_frame([batch.source])
    documents_frame(batch.documents)
    chunks_frame(batch.chunks)

    chunks_by_document: dict[str, list[ChunkInput]] = {
        document.external_id: [] for document in batch.documents
    }
    for chunk in batch.chunks:
        chunks_by_document[chunk.document_external_id].append(chunk)
    for document_id, chunks in chunks_by_document.items():
        if not chunks:
            raise ValueError(f"document {document_id!r} has no chunks")
        chunks.sort(key=lambda item: item.chunk_index)
    unexpected_models = {
        chunk.embedding_model for chunk in batch.chunks if chunk.embedding_model != MODEL_NAME
    }
    if unexpected_models:
        raise ValueError(
            f"chunks must use the configured embedding model {MODEL_NAME!r}; "
            f"received {sorted(unexpected_models)!r}"
        )

    if dry_run:
        return IngestionResult(
            source_slug=batch.source.slug,
            run_id=None,
            status="dry_run",
            documents_seen=len(batch.documents),
            documents_written=0,
            documents_unchanged=0,
            chunks_written=0,
        )

    client = supabase or get_supabase()
    database_source = _ensure_registered_approved_source(client, batch.source)
    run_response = (
        client.table("knowledge_ingestion_runs")
        .insert(
            {
                "source_id": database_source["id"],
                "status": "started",
                "documents_seen": len(batch.documents),
                "metadata": {"force": force},
            }
        )
        .execute()
    )
    run_id = str(run_response.data[0]["id"])

    documents_written = 0
    documents_unchanged = 0
    chunks_written = 0
    try:
        embedder = embeddings or get_embeddings()
        for document in batch.documents:
            document_chunks = chunks_by_document[document.external_id]
            vectors = _embed_chunks(document_chunks, embedder, batch_size=batch_size)
            document_payload = document.model_dump(mode="json", exclude={"normalized_text"})
            chunk_payloads = []
            for chunk, vector in zip(document_chunks, vectors, strict=True):
                chunk_payload = chunk.model_dump(mode="json")
                chunk_payload["embedding"] = vector
                chunk_payloads.append(chunk_payload)
            response = client.rpc(
                "upsert_knowledge_document",
                {
                    "p_source_slug": batch.source.slug,
                    "p_document": document_payload,
                    "p_chunks": chunk_payloads,
                    "p_force": force,
                },
            ).execute()
            result = response.data or {}
            if isinstance(result, list):
                result = result[0] if result else {}
            upsert_status = result.get("status")
            if upsert_status not in {"inserted", "updated", "unchanged"}:
                raise RuntimeError(
                    f"upsert_knowledge_document returned invalid status {upsert_status!r}"
                )
            if upsert_status == "unchanged":
                documents_unchanged += 1
            else:
                documents_written += 1
                chunks_written += int(result.get("chunks_written", len(chunk_payloads)))

        client.table("knowledge_ingestion_runs").update(
            {
                "status": "succeeded",
                "documents_written": documents_written,
                "chunks_written": chunks_written,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "metadata": {"force": force, "documents_unchanged": documents_unchanged},
            }
        ).eq("id", run_id).execute()
    except Exception as exc:
        client.table("knowledge_ingestion_runs").update(
            {
                "status": "failed",
                "documents_written": documents_written,
                "chunks_written": chunks_written,
                "error_message": f"{type(exc).__name__}: {exc}"[:2000],
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", run_id).execute()
        raise

    return IngestionResult(
        source_slug=batch.source.slug,
        run_id=run_id,
        status="succeeded",
        documents_seen=len(batch.documents),
        documents_written=documents_written,
        documents_unchanged=documents_unchanged,
        chunks_written=chunks_written,
    )
