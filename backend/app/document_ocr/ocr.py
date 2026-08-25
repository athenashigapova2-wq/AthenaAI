"""OCR adapters and safe PDF/image decoding."""

from __future__ import annotations

import io
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.config import settings
from app.document_ocr.models import OCRDocument, OCRPage


class UnsupportedDocumentError(ValueError):
    pass


class OCRBackendError(RuntimeError):
    pass


class OCRBackend(Protocol):
    def recognize_image(self, image: bytes, *, language: str) -> tuple[str, float]: ...


class TesseractCLIBackend:
    """Local adapter; sends no receipt data to an external service."""

    def __init__(self, command: str | None = None) -> None:
        self.command = command or settings.document_ocr_tesseract_command

    def recognize_image(self, image: bytes, *, language: str) -> tuple[str, float]:
        with tempfile.TemporaryDirectory(prefix="athena-ocr-") as directory:
            source = Path(directory) / "page.png"
            source.write_bytes(image)
            try:
                completed = subprocess.run(
                    [self.command, str(source), "stdout", "-l", language, "tsv"],
                    capture_output=True,
                    check=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60,
                )
            except (FileNotFoundError, subprocess.SubprocessError) as exc:
                raise OCRBackendError("Tesseract OCR failed") from exc
        words: list[str] = []
        confidences: list[float] = []
        previous_line: tuple[str, str, str] | None = None
        for row in completed.stdout.splitlines()[1:]:
            columns = row.split("\t", 11)
            if len(columns) != 12 or not columns[11].strip():
                continue
            line = (columns[4], columns[5], columns[6])
            if previous_line is not None and line != previous_line:
                words.append("\n")
            words.append(columns[11].strip())
            previous_line = line
            try:
                confidence = float(columns[10])
            except ValueError:
                continue
            if confidence >= 0:
                confidences.append(confidence / 100.0)
        text = " ".join(words).replace(" \n ", "\n").strip()
        mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return text, mean_confidence


class DocumentTextExtractor:
    def __init__(self, backend: OCRBackend | None = None) -> None:
        self.backend = backend or TesseractCLIBackend()

    def extract(self, content: bytes, content_type: str) -> OCRDocument:
        if content_type == "application/pdf":
            return self._extract_pdf(content)
        if content_type in {
            "image/png",
            "image/jpeg",
            "image/webp",
            "image/tiff",
        }:
            if not _matches_image_signature(content, content_type):
                raise UnsupportedDocumentError("File content does not match its image type")
            text, confidence = self.backend.recognize_image(
                content,
                language=settings.document_ocr_languages,
            )
            return OCRDocument(
                pages=[OCRPage(page_number=1, text=text, confidence=confidence)],
                engine="tesseract",
            )
        raise UnsupportedDocumentError(f"Unsupported content type: {content_type}")

    def _extract_pdf(self, content: bytes) -> OCRDocument:
        if not content.startswith(b"%PDF-"):
            raise UnsupportedDocumentError("File content is not a PDF")
        try:
            reader = PdfReader(io.BytesIO(content))
        except (PdfReadError, ValueError) as exc:
            raise UnsupportedDocumentError("PDF could not be decoded") from exc
        if not reader.pages:
            raise UnsupportedDocumentError("PDF has no pages")
        if len(reader.pages) > settings.document_ocr_max_pdf_pages:
            raise UnsupportedDocumentError("PDF exceeds configured page limit")
        pages: list[OCRPage] = []
        with tempfile.TemporaryDirectory(prefix="athena-pdf-") as directory:
            source = Path(directory) / "source.pdf"
            source.write_bytes(content)
            for index, page in enumerate(reader.pages):
                embedded = (page.extract_text() or "").strip()
                if len(embedded) >= 40:
                    pages.append(
                        OCRPage(page_number=index + 1, text=embedded, confidence=0.99)
                    )
                    continue
                target = Path(directory) / f"page-{index + 1}"
                try:
                    subprocess.run(
                        [
                            "pdftoppm",
                            "-f",
                            str(index + 1),
                            "-singlefile",
                            "-png",
                            "-r",
                            "200",
                            str(source),
                            str(target),
                        ],
                        capture_output=True,
                        check=True,
                        timeout=60,
                    )
                except (FileNotFoundError, subprocess.SubprocessError) as exc:
                    raise OCRBackendError("PDF rendering failed") from exc
                text, confidence = self.backend.recognize_image(
                    target.with_suffix(".png").read_bytes(),
                    language=settings.document_ocr_languages,
                )
                pages.append(
                    OCRPage(page_number=index + 1, text=text, confidence=confidence)
                )
        return OCRDocument(pages=pages, engine="embedded-text+tesseract")


def _matches_image_signature(content: bytes, content_type: str) -> bool:
    signatures = {
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP",
        "image/tiff": content.startswith((b"II*\x00", b"MM\x00*")),
    }
    return signatures[content_type]
