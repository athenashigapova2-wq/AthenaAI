from fastapi.testclient import TestClient

from app.api.documents import get_document_ocr_service
from app.auth.supabase_jwt import AuthenticatedUser, get_current_user
from app.document_ocr.models import DocumentOCRResult
from app.main import app


class FakePipeline:
    def __init__(self) -> None:
        self.call: dict[str, object] = {}

    def process(self, *, user_id, content, content_type, locale, trace_id):
        self.call = {
            "user_id": user_id,
            "content": content,
            "content_type": content_type,
            "locale": locale,
            "trace_id": trace_id,
        }
        return DocumentOCRResult(
            status="needs_human_review",
            document=None,
            confidence=0,
            field_confidence={},
            consistency_issues=[],
            review_reasons=["ocr_text_empty"],
            ocr_engine="stub",
            page_count=1,
        )


def test_authenticated_upload_returns_trace_and_structured_review_decision() -> None:
    pipeline = FakePipeline()
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser("owner-1")
    app.dependency_overrides[get_document_ocr_service] = lambda: pipeline
    try:
        response = TestClient(app).post(
            "/api/v1/documents/extract",
            files={"file": ("receipt.png", b"fake-png", "image/png")},
            data={"locale": "en"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.headers["x-trace-id"] == pipeline.call["trace_id"]
    assert pipeline.call["locale"] == "en"
    assert pipeline.call["user_id"] == "owner-1"
    assert response.json()["status"] == "needs_human_review"


def test_upload_rejects_unsupported_content_type_before_pipeline() -> None:
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser("owner-1")
    try:
        response = TestClient(app).post(
            "/api/v1/documents/extract",
            files={"file": ("receipt.txt", b"text", "text/plain")},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 415


def test_upload_requires_authentication() -> None:
    response = TestClient(app).post(
        "/api/v1/documents/extract",
        files={"file": ("receipt.png", b"fake-png", "image/png")},
    )
    assert response.status_code == 401


def test_upload_rejects_locale_without_an_installed_ocr_language_pack() -> None:
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser("owner-1")
    try:
        response = TestClient(app).post(
            "/api/v1/documents/extract",
            files={"file": ("receipt.png", b"fake-png", "image/png")},
            data={"locale": "de"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422
