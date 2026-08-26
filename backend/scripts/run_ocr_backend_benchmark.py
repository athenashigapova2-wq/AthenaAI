"""Explicit opt-in paired Tesseract versus AWS Textract experiment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.document_ocr.benchmark import (  # noqa: E402
    OCRComparisonBenchmark,
    OCRVariant,
)
from app.document_ocr.ocr import TesseractCLIBackend, TextractOCRBackend  # noqa: E402
from app.document_ocr.pipeline import DocumentOCRPipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=BACKEND / "evaluation" / "document_ocr" / "dataset.json",
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    if not settings.document_ocr_benchmark_enabled:
        raise SystemExit(
            "Set DOCUMENT_OCR_BENCHMARK_ENABLED=true explicitly; this benchmark calls paid services."
        )
    if not settings.document_ocr_aws_enabled:
        raise SystemExit("Set DOCUMENT_OCR_AWS_ENABLED=true to call AWS Textract.")

    cases = json.loads(args.dataset.read_text(encoding="utf-8"))
    pipeline = DocumentOCRPipeline()
    benchmark = OCRComparisonBenchmark(
        variants=[
            OCRVariant(
                variant_id="local_tesseract",
                backend=TesseractCLIBackend(),
                price_per_page_usd=0.0,
                cost_scope="API fee only; local CPU/RAM/operations excluded",
            ),
            OCRVariant(
                variant_id="aws_textract",
                backend=TextractOCRBackend(),
                price_per_page_usd=settings.document_ocr_aws_price_per_page_usd,
                cost_scope=(
                    "DetectDocumentText API fee snapshot "
                    f"{settings.document_ocr_aws_pricing_snapshot}; transfer/storage excluded"
                ),
            ),
        ],
        normalizer=lambda text, locale: pipeline.normalize_entities(text, locale=locale),
    )
    report = benchmark.run(cases)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    args.output_markdown.write_text(_markdown(report), encoding="utf-8")


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# OCR backend experiment",
        "",
        f"Experiment: `{report['experiment_id']}` ({report['design']}, {report['case_count']} cases)",
        "",
        "| Variant | Field F1 | OCR char accuracy | OCR p95 | E2E p95 | OCR cost |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for variant in report["variants"]:
        lines.append(
            "| {variant_id} | {f1:.4f} | {accuracy:.4f} | {ocr_p95} ms | "
            "{e2e_p95} ms | ${cost:.6f} |".format(
                variant_id=variant["variant_id"],
                f1=variant["field_quality"]["micro"]["f1"],
                accuracy=variant["mean_ocr_character_accuracy"],
                ocr_p95=variant["latency_ms"]["ocr_p95"],
                e2e_p95=variant["latency_ms"]["end_to_end_p95"],
                cost=variant["cost"]["ocr_estimated_cost_usd"],
            )
        )
    lines.extend(
        [
            "",
            "## Engineering trade-off",
            "",
            f"```json\n{json.dumps(report['tradeoff'], ensure_ascii=False, indent=2)}\n```",
            "",
            report["cost_note"],
        ]
    )
    lines.extend(["", "## Field F1 by language", "", "| Variant | Language | F1 |", "|---|---|---:|"])
    for variant in report["variants"]:
        for language, quality in variant["field_quality_by_language"].items():
            lines.append(
                f"| {variant['variant_id']} | {language} | {quality['micro']['f1']:.4f} |"
            )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
