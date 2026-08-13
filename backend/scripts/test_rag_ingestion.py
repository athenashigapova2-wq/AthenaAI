"""Offline ingestion/upsert tests with fake embeddings and Supabase."""

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.chunking import chunk_document  # noqa: E402
from app.rag.contracts import DocumentInput, IngestionBatch, SourceManifestEntry  # noqa: E402
from app.rag.ingestion import (  # noqa: E402
    SourceIdentityMismatchError,
    SourceNotApprovedError,
    ingest_batch,
)


class FakeEmbeddings:
    def __init__(self) -> None:
        self.document_calls: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_calls.append(texts)
        return [[float(index)] * 768 for index, _ in enumerate(texts, start=1)]


class FakeQuery:
    def __init__(self, client: "FakeSupabase", table: str) -> None:
        self.client = client
        self.table = table
        self.action = ""
        self.payload = None

    def select(self, *_args, **_kwargs):
        self.action = "select"
        return self

    def insert(self, payload, **_kwargs):
        self.action = "insert"
        self.payload = payload
        return self

    def update(self, payload, **_kwargs):
        self.action = "update"
        self.payload = payload
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self.table == "knowledge_sources" and self.action == "select":
            return SimpleNamespace(data=[self.client.source] if self.client.source else [])
        if self.table == "knowledge_sources" and self.action == "insert":
            self.client.registered_source = self.payload
            return SimpleNamespace(data=[{"id": "source-id", **self.payload}])
        if self.table == "knowledge_sources" and self.action == "update":
            self.client.source_update = self.payload
            return SimpleNamespace(data=[self.payload])
        if self.table == "knowledge_ingestion_runs" and self.action == "insert":
            self.client.run_insert = self.payload
            return SimpleNamespace(data=[{"id": "run-id"}])
        if self.table == "knowledge_ingestion_runs" and self.action == "update":
            self.client.run_updates.append(self.payload)
            return SimpleNamespace(data=[self.payload])
        raise AssertionError(f"unexpected table operation: {self.table} {self.action}")


class FakeRPC:
    def __init__(self, client: "FakeSupabase", params: dict) -> None:
        self.client = client
        self.params = params

    def execute(self):
        self.client.rpc_calls.append(self.params)
        return SimpleNamespace(
            data={
                "status": "inserted",
                "document_id": "document-id",
                "chunks_written": len(self.params["p_chunks"]),
            }
        )


class FakeSupabase:
    def __init__(self, *, approved: bool = True) -> None:
        self.source = {
            "id": "source-id",
            "slug": "approved-source",
            "title": "Approved source",
            "publisher": "Publisher",
            "canonical_url": "https://example.com/source",
            "source_type": "manual",
            "domains": ["workout", "safety"],
            "languages": ["en"],
            "rights_status": "approved" if approved else "review_required",
            "ingestion_enabled": approved,
        }
        self.source_update = None
        self.registered_source = None
        self.run_insert = None
        self.run_updates: list[dict] = []
        self.rpc_calls: list[dict] = []

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)

    def rpc(self, name: str, params: dict) -> FakeRPC:
        assert name == "upsert_knowledge_document"
        return FakeRPC(self, params)


def build_batch() -> IngestionBatch:
    source = SourceManifestEntry(
        slug="approved-source",
        title="Approved source",
        publisher="Publisher",
        canonical_url="https://example.com/source",
        source_type="manual",
        domains=["workout", "safety"],
        rights_status="approved",
        ingestion_enabled=True,
        verification_status="verified",
        license_notes="Approved for this test",
        selection_notes="Offline fixture",
    )
    text = " ".join(f"word-{index}" for index in range(120))
    document = DocumentInput(
        source_slug=source.slug,
        external_id="document-one",
        title="Document one",
        canonical_url="https://example.com/document-one",
        fetched_at=datetime.now(timezone.utc),
        normalized_text=text,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
    )
    return IngestionBatch(
        source=source,
        documents=[document],
        chunks=chunk_document(document, chunk_size=50, overlap=10),
    )


def main() -> None:
    batch = build_batch()
    dry_run = ingest_batch(batch, dry_run=True)
    assert dry_run.status == "dry_run"
    assert dry_run.documents_seen == 1

    client = FakeSupabase()
    embeddings = FakeEmbeddings()
    result = ingest_batch(batch, supabase=client, embeddings=embeddings, batch_size=2)
    assert result.status == "succeeded"
    assert result.documents_written == 1
    assert result.chunks_written == len(batch.chunks)
    assert len(embeddings.document_calls) == 2
    assert client.run_updates[-1]["status"] == "succeeded"
    assert "normalized_text" not in client.rpc_calls[0]["p_document"]
    assert len(client.rpc_calls[0]["p_chunks"][0]["embedding"]) == 768
    assert client.source_update is None

    try:
        ingest_batch(batch, supabase=FakeSupabase(approved=False), embeddings=embeddings)
    except SourceNotApprovedError:
        pass
    else:
        raise AssertionError("database governance must block an unapproved source")

    mismatched_source = FakeSupabase()
    mismatched_source.source["canonical_url"] = "https://example.com/different"
    try:
        ingest_batch(batch, supabase=mismatched_source, embeddings=embeddings)
    except SourceIdentityMismatchError:
        pass
    else:
        raise AssertionError("a bundle must not mutate approved source identity")

    missing_source = FakeSupabase()
    missing_source.source = None
    try:
        ingest_batch(batch, supabase=missing_source, embeddings=embeddings)
    except SourceNotApprovedError:
        assert missing_source.registered_source["rights_status"] == "review_required"
        assert missing_source.registered_source["ingestion_enabled"] is False
    else:
        raise AssertionError("new sources must be registered disabled")
    print("RAG ingestion checks passed")


if __name__ == "__main__":
    main()
