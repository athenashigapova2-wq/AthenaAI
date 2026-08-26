from decimal import Decimal

from app.document_ocr.models import (
    DocumentLineItem,
    ExtractedDocument,
    OCRDocument,
    OCRPage,
)
from app.document_ocr.pipeline import DocumentOCRPipeline
from app.document_ocr.validation import calculate_confidence, validate_consistency


class StubExtractor:
    def __init__(self, confidence: float = 0.98, text: str = "TOTAL 120.00 USD") -> None:
        self.confidence = confidence
        self.text = text
        self.language = None

    def extract(
        self, _content: bytes, _content_type: str, *, language: str | None = None
    ) -> OCRDocument:
        self.language = language
        return OCRDocument(
            pages=[OCRPage(page_number=1, text=self.text, confidence=self.confidence)],
            engine="stub",
        )


def complete_document() -> ExtractedDocument:
    return ExtractedDocument(
        document_kind="receipt",
        issue_date="2026-08-20",
        currency="USD",
        supplier={"name": "EXAMPLE STORE"},
        line_items=[
            DocumentLineItem(
                description="Item",
                quantity=Decimal("2"),
                unit_price=Decimal("50"),
                line_total=Decimal("100"),
            )
        ],
        subtotal=Decimal("100"),
        tax_total=Decimal("20"),
        total=Decimal("120"),
        field_confidence={
            "issue_date": 0.99,
            "currency": 0.99,
            "total": 0.99,
            "supplier.name": 0.99,
        },
    )


def test_consistent_high_confidence_document_is_accepted() -> None:
    def invoke(**_kwargs):
        return complete_document()

    extractor = StubExtractor()
    pipeline = DocumentOCRPipeline(
        text_extractor=extractor,  # type: ignore[arg-type]
        structured_invoker=invoke,
    )
    result = pipeline.process(b"image", "image/png", trace_id="trace-1")
    assert result.status == "accepted"
    assert result.confidence > 0.95
    assert result.consistency_issues == []
    assert extractor.language == "ru"


def test_arithmetic_mismatch_forces_human_review() -> None:
    document = complete_document().model_copy(update={"total": Decimal("130")})
    issues = validate_consistency(document)
    assert [issue.code for issue in issues] == ["total_mismatch"]
    confidence, _, reasons = calculate_confidence(
        document,
        StubExtractor().extract(b"", ""),
        issues,
    )
    assert confidence < 0.85
    assert reasons == ["consistency:total_mismatch"]


def test_missing_critical_field_forces_human_review() -> None:
    incomplete = complete_document().model_copy(update={"currency": None})

    def invoke(**_kwargs):
        return incomplete

    result = DocumentOCRPipeline(
        text_extractor=StubExtractor(),  # type: ignore[arg-type]
        structured_invoker=invoke,
    ).process(b"image", "image/png")
    assert result.status == "needs_human_review"
    assert "missing_critical_field:currency" in result.review_reasons


def test_line_item_mismatch_is_reported_without_silently_repairing_value() -> None:
    document = complete_document()
    document.line_items[0].line_total = Decimal("99")
    issues = validate_consistency(document)
    assert {issue.code for issue in issues} == {"subtotal_mismatch", "line_total_mismatch"}
    assert document.line_items[0].line_total == Decimal("99")


def test_empty_ocr_text_skips_llm_and_requires_review() -> None:
    def invoke(**_kwargs):
        raise AssertionError("LLM must not run without OCR evidence")

    result = DocumentOCRPipeline(
        text_extractor=StubExtractor(text=""),  # type: ignore[arg-type]
        structured_invoker=invoke,
    ).process(b"image", "image/png")
    assert result.document is None
    assert result.review_reasons == ["ocr_text_empty"]
