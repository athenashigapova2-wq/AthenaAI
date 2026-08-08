"""Pure helpers for collecting source identity evidence without approving rights."""

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from app.rag.contracts import DocumentCandidate, VerificationEvidence

OFFICIAL_HOSTS = {
    "nih-ods-fact-sheets": {"ods.od.nih.gov"},
}


def official_host_matches(source_slug: str, url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in OFFICIAL_HOSTS.get(source_slug, set())


def build_evidence(
    candidate: DocumentCandidate,
    response: httpx.Response,
) -> VerificationEvidence:
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
    final_url = str(response.url)
    notes: list[str] = []
    if response.status_code != 200:
        notes.append("HTTP response is not 200; source identity is not verified")
    if content_type not in {"text/html", "application/pdf"}:
        notes.append(f"Unexpected content type: {content_type or 'missing'}")
    if not official_host_matches(candidate.source_slug, final_url):
        notes.append("Redirect left the allowlisted official host")
    notes.append("Copyright/licence and robots review must be completed manually")

    return VerificationEvidence(
        source_slug=candidate.source_slug,
        external_id=candidate.external_id,
        requested_url=candidate.canonical_url,
        final_url=final_url,
        verified_at=datetime.now(timezone.utc),
        status_code=response.status_code,
        content_type=content_type,
        content_length=len(response.content),
        content_sha256=hashlib.sha256(response.content).hexdigest(),
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
        official_host_match=official_host_matches(candidate.source_slug, final_url),
        rights_status="review_required",
        notes=notes,
    )

