"""Fetch one allowlisted official document and write metadata-only evidence."""

import argparse
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.contracts import DocumentCandidate  # noqa: E402
from app.rag.source_verification import build_evidence  # noqa: E402

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"
CANDIDATES_PATH = KNOWLEDGE_DIR / "document_candidates.json"


def load_candidate(external_id: str) -> DocumentCandidate:
    candidates = [
        DocumentCandidate.model_validate(item)
        for item in json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    ]
    matches = [item for item in candidates if item.external_id == external_id]
    if len(matches) != 1:
        available = ", ".join(sorted(item.external_id for item in candidates))
        raise ValueError(
            f"Unknown or duplicate document candidate {external_id!r}. "
            f"Available candidates: {available}"
        )
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("external_id")
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    try:
        candidate = load_candidate(args.external_id)
    except ValueError as exc:
        raise SystemExit(f"Candidate configuration error: {exc}") from exc
    headers = {"User-Agent": "AthenaAI-RAG-source-verification/0.1 (manual review)"}
    try:
        response = httpx.get(
            str(candidate.canonical_url),
            headers=headers,
            follow_redirects=True,
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise SystemExit(f"Source verification network error: {type(exc).__name__}: {exc}") from exc

    evidence = build_evidence(candidate, response)
    print(evidence.model_dump_json(indent=2))
    if args.write_report:
        reports_dir = KNOWLEDGE_DIR / "verification"
        reports_dir.mkdir(exist_ok=True)
        report_path = reports_dir / f"{candidate.external_id}.json"
        report_path.write_text(evidence.model_dump_json(indent=2), encoding="utf-8")
        print(f"Evidence written to {report_path}")

    if response.status_code != 200 or not evidence.official_host_match:
        raise SystemExit(1)
    print("Identity evidence collected; rights_status remains review_required")


if __name__ == "__main__":
    main()
