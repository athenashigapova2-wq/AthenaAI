import pytest

from app.document_ocr.ocr import TextractOCRBackend, UnsupportedOCRLanguageError


class FakeTextractClient:
    def __init__(self) -> None:
        self.document = None

    def detect_document_text(self, *, Document):
        self.document = Document
        return {
            "Blocks": [
                {"BlockType": "PAGE", "Confidence": 100},
                {"BlockType": "LINE", "Text": "EXAMPLE STORE", "Confidence": 98.0},
                {"BlockType": "WORD", "Text": "ignored", "Confidence": 99.0},
                {"BlockType": "LINE", "Text": "TOTAL 10.00 USD", "Confidence": 96.0},
            ]
        }


def test_textract_adapter_uses_line_blocks_and_mean_confidence() -> None:
    client = FakeTextractClient()
    text, confidence = TextractOCRBackend(client=client).recognize_image(
        b"private-image-bytes",
        language="en",
    )
    assert client.document == {"Bytes": b"private-image-bytes"}
    assert text == "EXAMPLE STORE\nTOTAL 10.00 USD"
    assert confidence == 0.97


def test_textract_rejects_unsupported_russian_without_spending_a_request() -> None:
    client = FakeTextractClient()
    with pytest.raises(UnsupportedOCRLanguageError):
        TextractOCRBackend(client=client).recognize_image(b"image", language="ru")
    assert client.document is None
