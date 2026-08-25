"""Authenticated receipt/invoice ingestion boundary."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.auth.supabase_jwt import AuthenticatedUser, get_current_user
from app.config import settings
from app.document_ocr import DocumentOCRService
from app.document_ocr.models import DocumentOCRResult
from app.document_ocr.ocr import OCRBackendError, UnsupportedDocumentError


router = APIRouter(prefix="/documents", tags=["documents"])
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/tiff",
}


def get_document_ocr_service() -> DocumentOCRService:
    return DocumentOCRService()


@router.post("/extract", response_model=DocumentOCRResult)
async def extract_document(
    response: Response,
    file: UploadFile = File(...),
    locale: str = Form(default="ru", min_length=2, max_length=5),
    user: AuthenticatedUser = Depends(get_current_user),
    service: DocumentOCRService = Depends(get_document_ocr_service),
) -> DocumentOCRResult:
    """Process a bounded in-memory upload; source bytes are never persisted."""
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Supported types: PDF, PNG, JPEG, WebP and TIFF",
        )
    content = await file.read(settings.document_ocr_max_bytes + 1)
    await file.close()
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded document is empty")
    if len(content) > settings.document_ocr_max_bytes:
        raise HTTPException(status_code=413, detail="Uploaded document is too large")

    trace_id = str(uuid4())
    response.headers["X-Trace-ID"] = trace_id
    try:
        return await run_in_threadpool(
            service.process,
            user_id=user.user_id,
            content=content,
            content_type=content_type,
            locale=locale,
            trace_id=trace_id,
        )
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OCRBackendError as exc:
        raise HTTPException(status_code=503, detail="OCR engine is unavailable") from exc
