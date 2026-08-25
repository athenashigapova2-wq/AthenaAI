"""Explicit opt-in live entity-extraction run for the synthetic OCR dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.document_ocr.pipeline import DocumentOCRPipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=BACKEND / "evaluation" / "document_ocr" / "dataset.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not settings.document_ocr_live_eval_enabled:
        raise SystemExit(
            "Set DOCUMENT_OCR_LIVE_EVAL_ENABLED=true explicitly; this run calls the LLM provider."
        )
    cases = json.loads(args.dataset.read_text(encoding="utf-8"))
    pipeline = DocumentOCRPipeline()
    predictions = []
    for case in cases:
        document = pipeline.extract_entities(
            case["ocr_text"],
            locale=case["language"],
        )
        predictions.append(
            {"id": case["id"], "document": document.model_dump(mode="json")}
        )
    args.output.write_text(
        json.dumps(predictions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
