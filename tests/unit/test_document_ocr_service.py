import json

from app.document_ocr.models import DocumentOCRResult
from app.document_ocr.service import DocumentOCRService


class FakePipeline:
    def process(self, content, content_type, *, locale, trace_id):
        assert content == b"SECRET RECEIPT CONTENT"
        return DocumentOCRResult(
            status="accepted",
            document=None,
            confidence=0.99,
            field_confidence={},
            consistency_issues=[],
            review_reasons=[],
            ocr_engine="stub",
            page_count=1,
        )


def test_service_traces_metadata_without_document_content(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def create(user_id, input_text, **kwargs):
        captured["input"] = json.loads(input_text)
        captured["run_id"] = kwargs["run_id"]
        return kwargs["run_id"]

    def succeed(run_id, user_id, **kwargs):
        captured["output"] = json.loads(kwargs["output_text"])
        captured["route"] = kwargs["route"]

    monkeypatch.setattr("app.document_ocr.service.agent_traces.create_agent_run", create)
    monkeypatch.setattr("app.document_ocr.service.agent_traces.succeed_agent_run", succeed)
    result = DocumentOCRService(FakePipeline()).process(  # type: ignore[arg-type]
        user_id="owner-1",
        content=b"SECRET RECEIPT CONTENT",
        content_type="image/png",
        locale="en",
        trace_id="trace-1",
    )
    assert result.status == "accepted"
    assert captured["input"] == {
        "use_case": "document_ocr",
        "content_type": "image/png",
        "byte_count": 22,
        "locale": "en",
    }
    assert "SECRET" not in json.dumps(captured)
    assert captured["route"] == "document_ocr"
