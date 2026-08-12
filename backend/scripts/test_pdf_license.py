"""Offline checks for exact WHO-style PDF licence classification."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.pdf_license import detect_license_on_pages  # noqa: E402


def main() -> None:
    report = detect_license_on_pages(
        source_slug="who-physical-activity-guidelines",
        external_id="who-pdf",
        document_sha256="a" * 64,
        page_count=100,
        page_texts=[
            (1, "Title page"),
            (
                2,
                "Some rights reserved. This work is available under the Creative Commons "
                "Attribution-NonCommercial-ShareAlike 3.0 IGO licence "
                "(CC BY-NC-SA 3.0 IGO).",
            ),
            (100, "Back cover"),
        ],
    )
    assert report.detected_license_id == "CC BY-NC-SA 3.0 IGO"
    assert report.attribution_required is True
    assert report.commercial_use_allowed is False
    assert report.adaptations_allowed is True
    assert report.share_alike_required is True
    assert report.matched_page == 2
    assert report.rights_status == "review_required"
    print("PDF licence checks passed")


if __name__ == "__main__":
    main()
