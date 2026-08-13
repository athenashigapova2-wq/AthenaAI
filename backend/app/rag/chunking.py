"""Deterministic text normalization and overlap chunking for ingestion."""

from __future__ import annotations

import hashlib
import re

from app.embeddings import MODEL_NAME
from app.rag.contracts import ChunkInput, DocumentInput

_WHITESPACE = re.compile(r"[ \t]+")
_TOKEN = re.compile(r"\S+")
_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*$")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_text(text: str) -> str:
    """Normalize whitespace while retaining paragraph and heading boundaries."""
    normalized_lines = [_WHITESPACE.sub(" ", line).strip() for line in text.splitlines()]
    paragraphs: list[str] = []
    current: list[str] = []
    for line in normalized_lines:
        if line:
            current.append(line)
        elif current:
            paragraphs.append("\n".join(current))
            current = []
    if current:
        paragraphs.append("\n".join(current))
    return "\n\n".join(paragraphs).strip()


def chunk_document(
    document: DocumentInput,
    *,
    chunk_size: int = 450,
    overlap: int = 70,
    embedding_model: str = MODEL_NAME,
) -> list[ChunkInput]:
    """Split one normalized document into stable word-token windows.

    The chunker deliberately has no model/tokenizer dependency, which keeps dry-runs
    reproducible. ``token_count`` is an ingestion estimate; the embedding model still
    performs its own exact tokenization.
    """
    if chunk_size < 50:
        raise ValueError("chunk_size must be at least 50")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    text = normalize_text(document.normalized_text)
    tokens = _TOKEN.findall(text)
    if not tokens:
        raise ValueError(f"document {document.external_id!r} has no text after normalization")

    sections: list[tuple[str | None, str]] = []
    section_title: str | None = None
    section_parts: list[str] = []
    for line in text.splitlines():
        heading = _MARKDOWN_HEADING.match(line)
        if heading:
            if section_parts:
                sections.append((section_title, "\n\n".join(section_parts)))
                section_parts = []
            section_title = heading.group(1).strip()
        elif line.strip():
            section_parts.append(line.strip())
    if section_parts:
        sections.append((section_title, "\n\n".join(section_parts)))
    if not sections:
        sections = [(section_title, text)]

    chunks: list[ChunkInput] = []
    step = chunk_size - overlap
    for section_title, section_text in sections:
        section_tokens = _TOKEN.findall(section_text)
        for start in range(0, len(section_tokens), step):
            window = section_tokens[start : start + chunk_size]
            if not window:
                break
            content = " ".join(window)
            chunks.append(
                ChunkInput(
                    document_external_id=document.external_id,
                    chunk_index=len(chunks),
                    section_title=section_title,
                    content=content,
                    content_hash=sha256_text(content),
                    token_count=len(window),
                    embedding_model=embedding_model,
                    metadata={"token_count_method": "whitespace", "overlap": overlap},
                )
            )
            if start + chunk_size >= len(section_tokens):
                break
    return chunks
