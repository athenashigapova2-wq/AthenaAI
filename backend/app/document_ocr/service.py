"""Observable application service around the pure document pipeline."""

from __future__ import annotations

import json
from time import perf_counter

from app.document_ocr.models import DocumentOCRResult
from app.document_ocr.pipeline import DocumentOCRPipeline
from app.services import agent_traces


class DocumentOCRService:
    def __init__(self, pipeline: DocumentOCRPipeline | None = None) -> None:
        self._pipeline = pipeline or DocumentOCRPipeline()

    def process(
        self,
        *,
        user_id: str,
        content: bytes,
        content_type: str,
        locale: str,
        trace_id: str,
    ) -> DocumentOCRResult:
        started_at = perf_counter()
        run_id = agent_traces.create_agent_run(
            user_id,
            json.dumps(
                {
                    "use_case": "document_ocr",
                    "content_type": content_type,
                    "byte_count": len(content),
                    "locale": locale,
                },
                separators=(",", ":"),
            ),
            run_id=trace_id,
        )
        try:
            result = self._pipeline.process(
                content,
                content_type,
                locale=locale,
                trace_id=run_id,
            )
        except Exception as exc:
            agent_traces.fail_agent_run(
                run_id,
                user_id,
                exc,
                agent_traces.elapsed_ms(started_at),
            )
            raise
        agent_traces.succeed_agent_run(
            run_id,
            user_id,
            route="document_ocr",
            output_text=json.dumps(
                {
                    "status": result.status,
                    "confidence": result.confidence,
                    "page_count": result.page_count,
                    "issue_count": len(result.consistency_issues),
                    "review_reason_count": len(result.review_reasons),
                },
                separators=(",", ":"),
            ),
            latency_ms=agent_traces.elapsed_ms(started_at),
            resolution_mode=(
                "fallback" if result.status == "needs_human_review" else "main_llm"
            ),
        )
        return result
