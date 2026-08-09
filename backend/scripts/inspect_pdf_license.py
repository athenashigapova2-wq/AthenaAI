"""Verify an official PDF and extract its licence notice without storing the PDF."""

import argparse
import hashlib
import io
import sys
from pathlib import Path

import httpx
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.pdf_license import detect_license_on_pages  # noqa: E402
from app.rag.source_verification import build_evidence  # noqa: E402
from scripts.verify_knowledge_source import KNOWLEDGE_DIR, load_candidate  # noqa: E402


def read_pdf_bytes(candidate, pdf_file: Path | None) -> tuple[bytes, httpx.Response | None]:
    if pdf_file is not None:
        return pdf_file.read_bytes(), None
    response = httpx.get(
        str(candidate.canonical_url),
        headers={"User-Agent": "AthenaAI-RAG-source-verification/0.1 (manual review)"},
        follow_redirects=True,
        timeout=60,
    )
    return response.content, response


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("external_id")
    parser.add_argument("--pdf-file", type=Path)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    candidate = load_candidate(args.external_id)
    try:
        pdf_bytes, response = read_pdf_bytes(candidate, args.pdf_file)
    except (OSError, httpx.HTTPError) as exc:
        raise SystemExit(f"PDF verification error: {type(exc).__name__}: {exc}") from exc

    if response is not None:
        evidence = build_evidence(candidate, response)
        if response.status_code != 200 or evidence.pdf_magic_valid is not True:
            raise SystemExit(
                f"PDF identity failed: status={response.status_code}, "
                f"content_type={evidence.content_type}, pdf_magic={evidence.pdf_magic_valid}"
            )
    elif not pdf_bytes.startswith(b"%PDF-"):
        raise SystemExit("Local file does not have a PDF magic header")

    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_count = len(reader.pages)
    page_indexes = sorted(
        set(range(min(5, page_count)))
        | set(range(max(0, page_count - 3), page_count))
    )
    page_texts = [
        (index + 1, reader.pages[index].extract_text() or "")
        for index in page_indexes
    ]
    report = detect_license_on_pages(
        source_slug=candidate.source_slug,
        external_id=candidate.external_id,
        document_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        page_count=page_count,
        page_texts=page_texts,
    )
    print(report.model_dump_json(indent=2))

    if args.write_report:
        reports_dir = KNOWLEDGE_DIR / "verification"
        reports_dir.mkdir(exist_ok=True)
        report_path = reports_dir / f"{candidate.external_id}-license.json"
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        print(f"Licence evidence written to {report_path}")

    if report.detected_license_id is None:
        raise SystemExit(1)
    print("Licence identifier extracted; rights_status remains review_required")


if __name__ == "__main__":
    main()
