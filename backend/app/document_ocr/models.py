"""Strict schemas for receipt and invoice extraction."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


DocumentKind = Literal["receipt", "invoice", "unknown"]


class OCRPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    text: str
    confidence: float = Field(ge=0.0, le=1.0)


class OCRDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pages: list[OCRPage] = Field(min_length=1)
    engine: str

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages).strip()

    @property
    def confidence(self) -> float:
        populated = [page for page in self.pages if page.text.strip()]
        if not populated:
            return 0.0
        return sum(page.confidence for page in populated) / len(populated)


class DocumentParty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=300)
    tax_id: str | None = Field(default=None, max_length=80)


class DocumentLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=500)
    quantity: Decimal | None = Field(default=None, gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    line_total: Decimal = Field(ge=0)
    tax_rate_percent: Decimal | None = Field(default=None, ge=0, le=100)


class ExtractedDocument(BaseModel):
    """LLM output. Arithmetic is deliberately validated outside this schema."""

    model_config = ConfigDict(extra="forbid")

    document_kind: DocumentKind
    document_number: str | None = Field(default=None, max_length=120)
    issue_date: date | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    supplier: DocumentParty = Field(default_factory=DocumentParty)
    customer: DocumentParty = Field(default_factory=DocumentParty)
    line_items: list[DocumentLineItem] = Field(default_factory=list, max_length=500)
    subtotal: Decimal | None = Field(default=None, ge=0)
    tax_total: Decimal | None = Field(default=None, ge=0)
    total: Decimal | None = Field(default=None, ge=0)
    payment_method: str | None = Field(default=None, max_length=120)
    field_confidence: dict[str, float] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else None

    @field_validator("field_confidence")
    @classmethod
    def validate_confidences(cls, values: dict[str, float]) -> dict[str, float]:
        if any(value < 0 or value > 1 for value in values.values()):
            raise ValueError("field confidence must be between 0 and 1")
        return values


class ConsistencyIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    field: str
    message: str
    severity: Literal["warning", "error"]


class DocumentOCRResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "needs_human_review"]
    document: ExtractedDocument | None
    confidence: float = Field(ge=0.0, le=1.0)
    field_confidence: dict[str, float]
    consistency_issues: list[ConsistencyIssue]
    review_reasons: list[str]
    ocr_engine: str
    page_count: int = Field(ge=1)
