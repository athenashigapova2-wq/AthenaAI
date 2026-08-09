"""Offline checks for source identity evidence and redirect allowlisting."""

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.contracts import DocumentCandidate  # noqa: E402
from app.rag.source_verification import build_evidence, official_host_matches  # noqa: E402

CANDIDATES_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "document_candidates.json"


def main() -> None:
    candidates = [
        DocumentCandidate.model_validate(item)
        for item in json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    ]
    candidate = candidates[0]
    response = httpx.Response(
        200,
        content=(
            b"<html><title>Official fact sheet</title>Copyright "
            b"<a href='/document.pdf'>PDF</a></html>"
        ),
        headers={"content-type": "text/html; charset=utf-8", "etag": "test-etag"},
        request=httpx.Request("GET", str(candidate.canonical_url)),
    )
    evidence = build_evidence(candidate, response)
    assert evidence.status_code == 200
    assert evidence.official_host_match
    assert evidence.rights_status == "review_required"
    assert len(evidence.content_sha256) == 64
    assert evidence.license_markers == ["copyright"]
    assert official_host_matches(candidate.source_slug, str(candidate.canonical_url))
    assert not official_host_matches(candidate.source_slug, "https://example.com/fake")
    who = next(item for item in candidates if item.source_slug == "who-physical-activity-guidelines")
    assert official_host_matches(who.source_slug, str(who.canonical_url))
    assert official_host_matches(who.source_slug, "https://iris.who.int/example.pdf")
    assert not official_host_matches(who.source_slug, "https://who.int.example.com/fake")
    who_pdf = next(
        item
        for item in candidates
        if item.external_id == "who-physical-activity-guidelines-2020-pdf"
    )
    assert official_host_matches(who_pdf.source_slug, str(who_pdf.canonical_url))

    who_response = httpx.Response(
        200,
        content=(
            b"<html>Creative Commons "
            b"<a href='https://iris.who.int/server/api/core/bitstreams/test/content'>"
            b"Download</a></html>"
        ),
        headers={"content-type": "text/html"},
        request=httpx.Request("GET", str(who.canonical_url)),
    )
    who_evidence = build_evidence(who, who_response)
    assert len(who_evidence.discovered_document_urls) == 1
    assert "creative commons" in who_evidence.license_markers

    pdf_response = httpx.Response(
        200,
        content=b"%PDF-1.7 test bytes",
        headers={"content-type": "application/pdf"},
        request=httpx.Request("GET", str(who_pdf.canonical_url)),
    )
    pdf_evidence = build_evidence(who_pdf, pdf_response)
    assert [str(url) for url in pdf_evidence.discovered_document_urls] == [
        str(who_pdf.canonical_url)
    ]
    print("Source verification checks passed")


if __name__ == "__main__":
    main()
