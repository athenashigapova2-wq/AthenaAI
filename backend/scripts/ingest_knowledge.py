"""Validate, chunk, embed and upsert one approved knowledge JSON bundle."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.ingestion import ingest_batch, load_ingestion_batch  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="JSON file with source and documents")
    parser.add_argument("--dry-run", action="store_true", help="validate/chunk without DB or embeddings")
    parser.add_argument("--force", action="store_true", help="replace unchanged documents and embeddings")
    parser.add_argument("--chunk-size", type=int, default=450)
    parser.add_argument("--overlap", type=int, default=70)
    parser.add_argument("--embedding-batch-size", type=int, default=64)
    args = parser.parse_args()

    batch = load_ingestion_batch(
        args.bundle,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )
    result = ingest_batch(
        batch,
        dry_run=args.dry_run,
        force=args.force,
        batch_size=args.embedding_batch_size,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
