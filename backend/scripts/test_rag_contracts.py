"""Offline checks for RAG governance, contracts and DataFrame schemas."""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.embeddings import EMBEDDING_DIM, MODEL_NAME  # noqa: E402
from app.rag.contracts import DocumentInput, IngestionBatch, SourceManifestEntry  # noqa: E402
from app.rag.dataframes import documents_frame, sources_frame  # noqa: E402

MANIFEST_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "source_manifest.json"


def main() -> None:
    entries = [
        SourceManifestEntry.model_validate(item)
        for item in json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    ]
    assert len(entries) == 6
    assert all(not entry.ingestion_enabled for entry in entries)
    assert all(entry.rights_status == "review_required" for entry in entries)
    assert sources_frame(entries).shape[0] == 6
    assert EMBEDDING_DIM == 768
    assert MODEL_NAME == "intfloat/multilingual-e5-base"

    text = "Official guidance text"
    document = DocumentInput(
        source_slug=entries[0].slug,
        external_id="test-document",
        title="Test document",
        canonical_url=entries[0].canonical_url,
        fetched_at=datetime.now(timezone.utc),
        normalized_text=text,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
    )
    assert documents_frame([document]).shape[0] == 1

    try:
        IngestionBatch(source=entries[0], documents=[document], chunks=[])
    except ValidationError:
        pass
    else:
        raise AssertionError("unapproved sources must not produce ingestion batches")
    print("RAG contract checks passed")


if __name__ == "__main__":
    main()
