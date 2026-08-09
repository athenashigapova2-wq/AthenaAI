"""Validate candidate RAG sources and show ingestion DataFrame contracts."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.contracts import SourceManifestEntry  # noqa: E402
from app.rag.dataframes import CHUNK_COLUMNS, DOCUMENT_COLUMNS, sources_frame  # noqa: E402

MANIFEST_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "source_manifest.json"


def main() -> None:
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    sources = [SourceManifestEntry.model_validate(item) for item in raw]
    frame = sources_frame(sources)

    assert frame["slug"].is_unique, "source slugs must be unique"
    assert not frame["ingestion_enabled"].any(), (
        "candidate manifest must not enable ingestion before rights review"
    )
    print(f"Knowledge source manifest valid: {len(frame)} candidates")
    print("Sources frame:", list(frame.columns))
    print("Documents frame:", DOCUMENT_COLUMNS)
    print("Chunks frame:", CHUNK_COLUMNS)
    print("No content downloaded; all candidates remain disabled")


if __name__ == "__main__":
    main()
