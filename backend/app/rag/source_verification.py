"""Pure helpers for collecting source identity evidence without approving rights."""

import hashlib
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.parse import urljoin

import httpx

from app.rag.contracts import DocumentCandidate, VerificationEvidence

OFFICIAL_HOSTS = {
    "nih-ods-fact-sheets": {"ods.od.nih.gov"},
    "who-physical-activity-guidelines": {"www.who.int", "who.int", "iris.who.int"},
}

LICENSE_MARKERS = ("creative commons", "cc by", "licence", "license", "copyright")


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


def official_host_matches(source_slug: str, url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in OFFICIAL_HOSTS.get(source_slug, set())


def discover_document_urls(
    source_slug: str,
    final_url: str,
    content_type: str,
    content: bytes,
) -> list[str]:
    if content_type == "application/pdf":
        return [final_url] if official_host_matches(source_slug, final_url) else []
    if content_type != "text/html":
        return []

    parser = _LinkParser()
    parser.feed(content.decode("utf-8", errors="ignore"))
    discovered: set[str] = set()
    for href in parser.links:
        url = urljoin(final_url, href)
        path = urlparse(url).path.lower()
        if official_host_matches(source_slug, url) and (
            path.endswith(".pdf") or "/bitstream" in path or "/bitstreams/" in path
        ):
            discovered.add(url)
    return sorted(discovered)


def build_evidence(
    candidate: DocumentCandidate,
    response: httpx.Response,
) -> VerificationEvidence:
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
    final_url = str(response.url)
    text_lower = response.content.decode("utf-8", errors="ignore").lower()
    discovered_urls = discover_document_urls(
        candidate.source_slug,
        final_url,
        content_type,
        response.content,
    )
    license_markers = [marker for marker in LICENSE_MARKERS if marker in text_lower]
    notes: list[str] = []
    if response.status_code != 200:
        notes.append("HTTP response is not 200; source identity is not verified")
    if content_type not in {"text/html", "application/pdf"}:
        notes.append(f"Unexpected content type: {content_type or 'missing'}")
    pdf_magic_valid = None
    if content_type == "application/pdf":
        pdf_magic_valid = response.content.startswith(b"%PDF-")
        if not pdf_magic_valid:
            notes.append("Content type is PDF but the PDF magic header is missing")
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
        pdf_magic_valid=pdf_magic_valid,
        discovered_document_urls=discovered_urls,
        license_markers=license_markers,
        rights_status="review_required",
        notes=notes,
    )
