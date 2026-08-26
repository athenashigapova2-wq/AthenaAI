"""Receipt/invoice OCR → extraction → validation → review decision."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ValidationError

from app.ai_execution import ai_execution_service
from app.config import settings
from app.document_ocr.models import DocumentOCRResult, ExtractedDocument
from app.document_ocr.ocr import DocumentTextExtractor
from app.document_ocr.validation import calculate_confidence, validate_consistency


StructuredInvoker = Callable[..., BaseModel]


class DocumentOCRPipeline:
    def __init__(
        self,
        *,
        text_extractor: DocumentTextExtractor | None = None,
        structured_invoker: StructuredInvoker = ai_execution_service.invoke_structured,
    ) -> None:
        self._text_extractor = text_extractor or DocumentTextExtractor()
        self._invoke_structured = structured_invoker

    def process(
        self,
        content: bytes,
        content_type: str,
        *,
        locale: str = "ru",
        trace_id: str | None = None,
    ) -> DocumentOCRResult:
        ocr = self._text_extractor.extract(content, content_type, language=locale)
        if not ocr.text:
            return self._review_without_document(ocr.engine, len(ocr.pages), "ocr_text_empty")
        try:
            extracted = self.normalize_entities(ocr.text, locale=locale, trace_id=trace_id)
        except ValidationError:
            return self._review_without_document(
                ocr.engine,
                len(ocr.pages),
                "schema_validation_failed",
            )
        issues = validate_consistency(extracted)
        confidence, field_confidence, reasons = calculate_confidence(extracted, ocr, issues)
        if confidence < settings.document_ocr_human_review_threshold:
            reasons.append("confidence_below_threshold")
        needs_review = bool(reasons) or any(issue.severity == "error" for issue in issues)
        return DocumentOCRResult(
            status="needs_human_review" if needs_review else "accepted",
            document=extracted,
            confidence=confidence,
            field_confidence=field_confidence,
            consistency_issues=issues,
            review_reasons=list(dict.fromkeys(reasons)),
            ocr_engine=ocr.engine,
            page_count=len(ocr.pages),
        )

    def normalize_entities(
        self,
        ocr_text: str,
        *,
        locale: str,
        trace_id: str | None = None,
    ) -> ExtractedDocument:
        return ExtractedDocument.model_validate(
            self._invoke_structured(
                response_model=ExtractedDocument,
                node_name="document_ocr",
                purpose="normalize_entities",
                system_prompt=(
                    "Extract receipt or invoice entities only when supported by OCR text. "
                    "Never repair arithmetic or invent missing values. Use ISO date and ISO "
                    "4217 currency. Return per-field confidence for observed fields using "
                    "dot paths; low OCR certainty must lower field confidence."
                ),
                input_payload={"locale": locale, "ocr_text": ocr_text},
                run_id=trace_id,
            )
        )

    def extract_entities(
        self,
        ocr_text: str,
        *,
        locale: str,
        trace_id: str | None = None,
    ) -> ExtractedDocument:
        """Compatibility alias for the canonical normalization stage."""
        return self.normalize_entities(ocr_text, locale=locale, trace_id=trace_id)

    @staticmethod
    def _review_without_document(
        engine: str,
        page_count: int,
        reason: str,
    ) -> DocumentOCRResult:
        return DocumentOCRResult(
            status="needs_human_review",
            document=None,
            confidence=0.0,
            field_confidence={},
            consistency_issues=[],
            review_reasons=[reason],
            ocr_engine=engine,
            page_count=page_count,
        )
