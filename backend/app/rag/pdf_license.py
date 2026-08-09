"""Extract a narrow, auditable licence decision from PDF text."""

import re

from app.rag.contracts import LicenseEvidence

LICENSE_PATTERNS = [
    (
        "CC BY-NC-SA 3.0 IGO",
        re.compile(r"CC\s+BY[- ]NC[- ]SA\s+3\.0\s+IGO", re.IGNORECASE),
        {
            "attribution_required": True,
            "commercial_use_allowed": False,
            "adaptations_allowed": True,
            "share_alike_required": True,
        },
    ),
    (
        "CC BY 3.0 IGO",
        re.compile(r"CC\s+BY\s+3\.0\s+IGO", re.IGNORECASE),
        {
            "attribution_required": True,
            "commercial_use_allowed": True,
            "adaptations_allowed": True,
            "share_alike_required": False,
        },
    ),
]


def normalize_pdf_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def detect_license(
    *,
    source_slug: str,
    external_id: str,
    document_sha256: str,
    page_count: int,
    inspected_pages: list[int],
    text: str,
    matched_page: int | None = None,
) -> LicenseEvidence:
    normalized = normalize_pdf_text(text)
    for license_id, pattern, permissions in LICENSE_PATTERNS:
        match = pattern.search(normalized)
        if not match:
            continue
        start = max(0, match.start() - 220)
        end = min(len(normalized), match.end() + 320)
        return LicenseEvidence(
            source_slug=source_slug,
            external_id=external_id,
            document_sha256=document_sha256,
            page_count=page_count,
            inspected_pages=inspected_pages,
            matched_page=matched_page,
            detected_license_id=license_id,
            exact_notice=normalized[start:end],
            **permissions,
            notes=[
                "Automated extraction must be confirmed against the rendered PDF page",
                "Non-commercial restrictions require legal/product review before production ingestion",
            ],
        )

    return LicenseEvidence(
        source_slug=source_slug,
        external_id=external_id,
        document_sha256=document_sha256,
        page_count=page_count,
        inspected_pages=inspected_pages,
        notes=["No supported licence identifier found in the inspected PDF pages"],
    )


def detect_license_on_pages(
    *,
    source_slug: str,
    external_id: str,
    document_sha256: str,
    page_count: int,
    page_texts: list[tuple[int, str]],
) -> LicenseEvidence:
    """Inspect page text in order and retain the one-based page containing the notice."""
    inspected_pages = [page_number for page_number, _ in page_texts]
    for page_number, text in page_texts:
        report = detect_license(
            source_slug=source_slug,
            external_id=external_id,
            document_sha256=document_sha256,
            page_count=page_count,
            inspected_pages=inspected_pages,
            text=text,
            matched_page=page_number,
        )
        if report.detected_license_id:
            return report

    return detect_license(
        source_slug=source_slug,
        external_id=external_id,
        document_sha256=document_sha256,
        page_count=page_count,
        inspected_pages=inspected_pages,
        text="",
    )
