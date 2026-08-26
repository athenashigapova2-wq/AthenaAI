"""Paired OCR backend experiment with shared LLM entity normalization."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.document_ocr.evaluation import evaluate_dataset_fields
from app.document_ocr.models import ExtractedDocument
from app.document_ocr.ocr import OCRBackend
from app.document_ocr.ocr import OCRBackendError
from app.model_routing import select_model


Normalizer = Callable[[str, str], ExtractedDocument]


@dataclass(frozen=True)
class OCRVariant:
    variant_id: str
    backend: OCRBackend
    price_per_page_usd: float
    cost_scope: str


class OCRComparisonBenchmark:
    """Run every case through every backend to avoid assignment imbalance."""

    experiment_id = "receipt-ocr-backend-v1"

    def __init__(self, *, variants: list[OCRVariant], normalizer: Normalizer) -> None:
        self.variants = variants
        self.normalizer = normalizer

    def run(self, cases: list[dict[str, Any]]) -> dict[str, Any]:
        model = select_model(
            node_name="document_ocr",
            purpose="normalize_entities",
            default_tier="small",
        )
        summaries = []
        for variant in self.variants:
            rows = []
            pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for case in cases:
                image = render_synthetic_document(
                    case["ocr_text"],
                    degraded="low-quality" in case["id"],
                )
                ocr_started = perf_counter()
                error: str | None = None
                billed = False
                try:
                    text, ocr_confidence = variant.backend.recognize_image(
                        image,
                        language=case["language"],
                    )
                    billed = True
                except OCRBackendError as exc:
                    text, ocr_confidence = "", 0.0
                    error = type(exc).__name__
                ocr_latency_ms = _elapsed_ms(ocr_started)
                if error is None:
                    llm_started = perf_counter()
                    try:
                        document = self.normalizer(text, case["language"])
                        prediction = document.model_dump(mode="json")
                    except Exception as exc:
                        prediction = {}
                        error = f"normalization:{type(exc).__name__}"
                    llm_latency_ms = _elapsed_ms(llm_started)
                else:
                    llm_latency_ms = 0
                    prediction = {}
                pairs.append((prediction, case["expected"]))
                rows.append(
                    {
                        "id": case["id"],
                        "language": case["language"],
                        "error": error,
                        "ocr_billed": billed,
                        "ocr_confidence": round(ocr_confidence, 4),
                        "ocr_character_accuracy": round(
                            character_accuracy(text, case["ocr_text"]), 4
                        ),
                        "ocr_latency_ms": ocr_latency_ms,
                        "llm_latency_ms": llm_latency_ms,
                        "end_to_end_latency_ms": ocr_latency_ms + llm_latency_ms,
                        "document": prediction,
                    }
                )
            quality = evaluate_dataset_fields(pairs)
            quality_by_language = {
                language: evaluate_dataset_fields(
                    [
                        pair
                        for pair, row in zip(pairs, rows, strict=True)
                        if row["language"] == language
                    ]
                )
                for language in sorted({row["language"] for row in rows})
            }
            summaries.append(
                _summarize_variant(
                    variant,
                    rows,
                    quality,
                    quality_by_language=quality_by_language,
                )
            )
        report = {
            "experiment_id": self.experiment_id,
            "design": "paired",
            "case_count": len(cases),
            "normalization_model": {
                "provider": model.provider,
                "model": model.model_name,
                "requested_tier": model.requested_model_tier,
                "tier": model.model_tier,
                "routing_rule": model.matched_rule,
                "is_fallback": model.is_fallback,
                "fallback_reason": model.fallback_reason,
            },
            "cost_note": (
                "OCR API cost only. Local compute and common LLM normalization cost are "
                "reported as uncovered and must be supplied from runtime telemetry."
            ),
            "variants": summaries,
        }
        report["tradeoff"] = compare_variants(summaries)
        return report


def compare_variants(summaries: list[dict[str, Any]]) -> dict[str, Any] | None:
    by_id = {summary["variant_id"]: summary for summary in summaries}
    local = by_id.get("local_tesseract")
    aws = by_id.get("aws_textract")
    if local is None or aws is None:
        return None
    local_f1 = float(local["field_quality"]["micro"]["f1"])
    aws_f1 = float(aws["field_quality"]["micro"]["f1"])
    quality_delta = round(aws_f1 - local_f1, 4)
    latency_delta = (
        aws["latency_ms"]["end_to_end_p95"] - local["latency_ms"]["end_to_end_p95"]
    )
    if quality_delta >= 0.03:
        recommendation = "aws_quality_candidate"
    elif quality_delta <= -0.03:
        recommendation = "local_quality_candidate"
    else:
        recommendation = "quality_tie_choose_by_privacy_latency_and_operational_cost"
    languages = sorted(
        set(local["field_quality_by_language"]) | set(aws["field_quality_by_language"])
    )
    return {
        "aws_minus_local_field_f1": quality_delta,
        "aws_minus_local_end_to_end_p95_ms": latency_delta,
        "aws_minus_local_ocr_cost_usd": round(
            aws["cost"]["ocr_estimated_cost_usd"]
            - local["cost"]["ocr_estimated_cost_usd"],
            6,
        ),
        "recommendation": recommendation,
        "field_f1_by_language": {
            language: {
                "local": local["field_quality_by_language"][language]["micro"]["f1"],
                "aws": aws["field_quality_by_language"][language]["micro"]["f1"],
                "aws_minus_local": round(
                    aws["field_quality_by_language"][language]["micro"]["f1"]
                    - local["field_quality_by_language"][language]["micro"]["f1"],
                    4,
                ),
            }
            for language in languages
        },
        "warning": "Validate the decision on an approved real-world corpus, not synthetic data alone.",
    }


def render_synthetic_document(text: str, *, degraded: bool = False) -> bytes:
    """Render identical privacy-safe source pixels for paired OCR experiments."""
    font = _unicode_font(24)
    lines = text.splitlines() or [""]
    width = max(720, max(int(font.getlength(line)) for line in lines) + 80)
    line_height = 34
    image = Image.new("L", (width, len(lines) * line_height + 80), color=255)
    draw = ImageDraw.Draw(image)
    draw.multiline_text((40, 40), text, fill=0, font=font, spacing=8)
    if degraded:
        image = image.rotate(0.8, expand=True, fillcolor=245).filter(
            ImageFilter.GaussianBlur(radius=0.7)
        )
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def character_accuracy(predicted: str, expected: str) -> float:
    left = " ".join(predicted.casefold().split())
    right = " ".join(expected.casefold().split())
    if not right:
        return 1.0 if not left else 0.0
    return max(0.0, 1.0 - _levenshtein(left, right) / len(right))


def _summarize_variant(
    variant: OCRVariant,
    rows: list[dict[str, Any]],
    quality: dict[str, Any],
    *,
    quality_by_language: dict[str, Any],
) -> dict[str, Any]:
    ocr_latencies = [row["ocr_latency_ms"] for row in rows]
    llm_latencies = [row["llm_latency_ms"] for row in rows]
    e2e_latencies = [row["end_to_end_latency_ms"] for row in rows]
    return {
        "variant_id": variant.variant_id,
        "engine": variant.backend.engine_name,
        "field_quality": quality,
        "field_quality_by_language": quality_by_language,
        "error_count": sum(bool(row["error"]) for row in rows),
        "mean_ocr_character_accuracy": round(
            sum(row["ocr_character_accuracy"] for row in rows) / len(rows), 4
        ),
        "latency_ms": {
            "ocr_p50": _percentile(ocr_latencies, 0.50),
            "ocr_p95": _percentile(ocr_latencies, 0.95),
            "llm_p50": _percentile(llm_latencies, 0.50),
            "llm_p95": _percentile(llm_latencies, 0.95),
            "end_to_end_p50": _percentile(e2e_latencies, 0.50),
            "end_to_end_p95": _percentile(e2e_latencies, 0.95),
        },
        "cost": {
            "ocr_price_per_page_usd": variant.price_per_page_usd,
            "ocr_estimated_cost_usd": round(
                variant.price_per_page_usd
                * sum(bool(row["ocr_billed"]) for row in rows),
                6,
            ),
            "scope": variant.cost_scope,
            "llm_cost_usd": None,
            "llm_cost_covered": False,
            "failed_call_billing_unknown_count": sum(
                bool(row["error"]) and not row["ocr_billed"] for row in rows
            ),
        },
        "cases": rows,
    }


def _unicode_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    )
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    raise RuntimeError("A Unicode TrueType font is required for the OCR benchmark")


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1_000))


def _percentile(values: list[int], quantile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def _levenshtein(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_character in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_character != right_character),
                )
            )
        previous = current
    return previous[-1]
