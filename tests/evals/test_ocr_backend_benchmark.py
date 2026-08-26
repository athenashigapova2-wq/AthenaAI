from app.document_ocr.benchmark import (
    OCRComparisonBenchmark,
    OCRVariant,
    character_accuracy,
)
from app.document_ocr.models import ExtractedDocument


class FakeBackend:
    def __init__(self, name: str, text: str) -> None:
        self.engine_name = name
        self.text = text

    def recognize_image(self, image: bytes, *, language: str):
        assert image.startswith(b"\x89PNG")
        return self.text, 0.99


def normalize(text: str, _locale: str) -> ExtractedDocument:
    total = "10.00" if "10.00" in text else "11.00"
    return ExtractedDocument(
        document_kind="receipt",
        issue_date="2026-08-20",
        currency="USD",
        supplier={"name": "EXAMPLE"},
        total=total,
    )


def test_paired_benchmark_compares_quality_latency_and_provider_cost() -> None:
    cases = [
        {
            "id": "en-receipt-test",
            "language": "en",
            "ocr_text": "EXAMPLE\n2026-08-20\nTOTAL 10.00 USD",
            "expected": {
                "document_kind": "receipt",
                "issue_date": "2026-08-20",
                "currency": "USD",
                "supplier": {"name": "EXAMPLE"},
                "total": "10.00",
            },
        }
    ]
    report = OCRComparisonBenchmark(
        variants=[
            OCRVariant("local_tesseract", FakeBackend("local", "TOTAL 11.00"), 0, "cpu"),
            OCRVariant(
                "aws_textract",
                FakeBackend("aws", "EXAMPLE 2026-08-20 TOTAL 10.00 USD"),
                0.0015,
                "api",
            ),
        ],
        normalizer=normalize,
    ).run(cases)
    local, aws = report["variants"]
    assert aws["field_quality"]["micro"]["f1"] > local["field_quality"]["micro"]["f1"]
    assert local["cost"]["ocr_estimated_cost_usd"] == 0
    assert aws["cost"]["ocr_estimated_cost_usd"] == 0.0015
    assert report["tradeoff"]["recommendation"] == "aws_quality_candidate"
    # The routing policy requests the economical tier. In a credential-free CI
    # environment LLM_ROUTER_MODEL is intentionally empty, so model routing may
    # report the configured main model as the effective fallback.
    assert report["normalization_model"]["requested_tier"] == "small"
    assert report["normalization_model"]["tier"] in {"small", "main"}
    assert report["normalization_model"]["is_fallback"] == (
        report["normalization_model"]["tier"] == "main"
    )


def test_character_accuracy_is_normalized_and_bounded() -> None:
    assert character_accuracy(" TOTAL   10 ", "total 10") == 1.0
    assert 0 <= character_accuracy("wrong", "expected") <= 1
