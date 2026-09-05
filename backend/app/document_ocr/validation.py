"""Deterministic cross-field consistency and confidence policy."""

from __future__ import annotations

from decimal import Decimal

from app.document_ocr.models import ConsistencyIssue, ExtractedDocument, OCRDocument


MONEY_TOLERANCE = Decimal("0.02")
CRITICAL_FIELDS = ("issue_date", "currency", "total", "supplier.name")


def validate_consistency(document: ExtractedDocument) -> list[ConsistencyIssue]:
    issues: list[ConsistencyIssue] = []
    item_sum = sum((item.line_total for item in document.line_items), Decimal("0"))
    if document.subtotal is not None and document.line_items:
        _compare(issues, "subtotal_mismatch", "subtotal", item_sum, document.subtotal)
    if document.total is not None and document.subtotal is not None:
        expected = document.subtotal + (document.tax_total or Decimal("0"))
        _compare(issues, "total_mismatch", "total", expected, document.total)
    for index, item in enumerate(document.line_items):
        if item.quantity is not None and item.unit_price is not None:
            _compare(
                issues,
                "line_total_mismatch",
                f"line_items.{index}.line_total",
                item.quantity * item.unit_price,
                item.line_total,
                severity="warning",
            )
    return issues


def calculate_confidence(
    document: ExtractedDocument,
    ocr: OCRDocument,
    issues: list[ConsistencyIssue],
) -> tuple[float, dict[str, float], list[str]]:
    field_confidence = dict(document.field_confidence)
    for field in CRITICAL_FIELDS:
        field_confidence.setdefault(field, ocr.confidence if _has_field(document, field) else 0.0)
        field_confidence[field] = min(field_confidence[field], ocr.confidence)
    critical_score = sum(field_confidence[field] for field in CRITICAL_FIELDS) / len(
        CRITICAL_FIELDS
    )
    consistency_penalty = sum(0.20 if issue.severity == "error" else 0.05 for issue in issues)
    confidence = max(
        0.0, min(1.0, 0.45 * ocr.confidence + 0.55 * critical_score - consistency_penalty)
    )
    reasons = [
        f"missing_critical_field:{field}"
        for field in CRITICAL_FIELDS
        if not _has_field(document, field)
    ]
    reasons.extend(f"consistency:{issue.code}" for issue in issues if issue.severity == "error")
    return round(confidence, 4), field_confidence, reasons


def _has_field(document: ExtractedDocument, path: str) -> bool:
    value: object = document
    for part in path.split("."):
        value = getattr(value, part, None)
    return value is not None and value != ""


def _compare(
    issues: list[ConsistencyIssue],
    code: str,
    field: str,
    expected: Decimal,
    actual: Decimal,
    *,
    severity: str = "error",
) -> None:
    tolerance = max(MONEY_TOLERANCE, abs(actual) * Decimal("0.005"))
    if abs(expected - actual) > tolerance:
        issues.append(
            ConsistencyIssue(
                code=code,
                field=field,
                message=f"expected {expected.quantize(MONEY_TOLERANCE)}, got {actual}",
                severity=severity,
            )
        )
