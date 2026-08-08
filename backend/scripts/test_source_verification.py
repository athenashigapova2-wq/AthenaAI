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
    candidate = DocumentCandidate.model_validate(
        json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))[0]
    )
    response = httpx.Response(
        200,
        content=b"<html><title>Official fact sheet</title></html>",
        headers={"content-type": "text/html; charset=utf-8", "etag": "test-etag"},
        request=httpx.Request("GET", str(candidate.canonical_url)),
    )
    evidence = build_evidence(candidate, response)
    assert evidence.status_code == 200
    assert evidence.official_host_match
    assert evidence.rights_status == "review_required"
    assert len(evidence.content_sha256) == 64
    assert official_host_matches(candidate.source_slug, str(candidate.canonical_url))
    assert not official_host_matches(candidate.source_slug, "https://example.com/fake")
    print("Source verification checks passed")


if __name__ == "__main__":
    main()
