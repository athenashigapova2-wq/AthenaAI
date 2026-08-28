"""Единая точка чтения настроек. Больше нигде в коде нет os.environ."""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Absolute path keeps scripts working whether they are launched from the
        # repository root or from backend/.
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM provider. Mock is explicit and intended only for local/test contours.
    llm_provider: Literal["gigachat", "mock"] = "gigachat"
    mock_llm_model: str = "athena-mock-v1"
    mock_llm_latency_ms: int = Field(default=0, ge=0, le=60_000)

    # Capacity-test fast path. This skips LangGraph and Supabase inside the
    # worker while retaining JWT, FastAPI, Redis broker/status, and Celery.
    agent_infrastructure_test_mode: bool = False
    agent_infrastructure_test_latency_ms: int = Field(
        default=0,
        ge=0,
        le=60_000,
    )

    # GigaChat models
    llm_router_model: str = ""
    llm_model_routing_enabled: bool = True
    llm_model_routing_policy: dict[str, Literal["small", "main"]] = Field(
        default_factory=lambda: {
            "router.route_classification": "small",
            "nutrition.food_translation": "small",
            "memory.structured_extraction": "small",
            "meal_estimation.parse_description": "small",
            "meal_estimation.rerank_candidates": "small",
            "habit_insight.generate_suggestion": "small",
            "document_ocr.normalize_entities": "small",
            "ai_task.daily_tip": "small",
            "ai_task.meal_recommendations": "main",
            "ai_task.workout_plan": "main",
            "ai_task.health_macro_adjustment": "main",
            "*": "main",
        }
    )
    agent_baseline_version: str = "baseline-v1"

    # Server-owned evaluation experiments. Clients never select a variant.
    evaluation_experiment_config_file: str = ""
    evaluation_experiment_id: str = ""

    # GigaChat
    gigachat_auth_key: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat-2"
    # Optional PEM bundle for environments whose system trust store does not
    # contain the CA chain used by the provider. TLS verification stays enabled.
    gigachat_ca_bundle_file: str = ""

    # Retries are used only around idempotent LLM and read operations.
    safe_retry_max_attempts: int = Field(default=3, ge=1, le=10)
    safe_retry_base_delay_seconds: float = Field(default=0.5, ge=0.0, le=60.0)
    safe_retry_max_delay_seconds: float = Field(default=4.0, ge=0.0, le=120.0)
    safe_retry_jitter_ratio: float = Field(default=0.25, ge=0.0, le=1.0)

    # Provider throttling needs a slower schedule than ordinary network errors.
    safe_retry_rate_limit_max_attempts: int = Field(default=4, ge=1, le=10)
    safe_retry_rate_limit_base_delay_seconds: float = Field(
        default=2.0,
        ge=0.0,
        le=300.0,
    )
    safe_retry_rate_limit_max_delay_seconds: float = Field(
        default=30.0,
        ge=0.0,
        le=600.0,
    )

    # Shared token-bucket limiter prevents all workers from bursting GigaChat.
    llm_rate_limiter_enabled: bool = True
    llm_rate_limit_requests_per_second: float = Field(
        default=4.0,
        gt=0.0,
        le=1_000.0,
    )
    llm_rate_limit_burst: int = Field(default=4, ge=1, le=10_000)
    llm_rate_limit_acquire_timeout_seconds: float = Field(
        default=30.0,
        ge=0.0,
        le=600.0,
    )
    llm_rate_limit_state_ttl_seconds: int = Field(
        default=3_600,
        ge=60,
        le=86_400,
    )

    # Shared GigaChat circuit breaker state lives in Redis across all workers.
    llm_circuit_breaker_enabled: bool = True
    llm_circuit_breaker_failure_threshold: int = Field(default=5, ge=1, le=100)
    llm_circuit_breaker_recovery_timeout_seconds: float = Field(
        default=30.0,
        ge=1.0,
        le=3_600.0,
    )
    llm_circuit_breaker_half_open_lease_seconds: float = Field(
        default=210.0,
        ge=1.0,
        le=3_600.0,
    )
    llm_circuit_breaker_state_ttl_seconds: int = Field(
        default=3_600,
        ge=60,
        le=86_400,
    )

    # Supabase
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwt_audience: str = "authenticated"

    # HTTP API
    api_cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,https://localhost"
    )

    # Redis-backed background jobs
    redis_url: str = "redis://127.0.0.1:6379/0"
    agent_job_queue: str = "athena-agent"
    agent_job_ttl_seconds: int = 3_600
    write_confirmation_ttl_seconds: int = Field(default=900, ge=60, le=3_600)

    # Layered conversation memory. Model-proposed facts are accepted only after
    # deterministic evidence and confidence checks on the server.
    agent_memory_updates_enabled: bool = True
    agent_memory_recent_message_limit: int = Field(default=8, ge=2, le=20)
    agent_memory_confidence_threshold: float = Field(default=0.9, ge=0.5, le=1.0)
    agent_memory_max_items_per_category: int = Field(default=40, ge=1, le=200)
    agent_memory_summary_max_chars: int = Field(default=1_200, ge=200, le=4_000)

    # Retrieval-augmented generation
    rag_enabled: bool = True
    rag_retrieval_limit: int = 6
    rag_min_similarity: float = 0.55
    rag_context_max_chars: int = 12_000

    app_env: str = "dev"
    test_user_id: str = "4c58346d-801f-4241-a349-02a2736361f0"

    # Content is opt-in. Production-safe structured metadata is always stored;
    # prompt, response and tool values are disabled by default.
    trace_content_mode: Literal["off", "redacted", "full"] = "off"
    trace_raw_payload_retention_days: int = Field(default=7, ge=0, le=30)
    trace_record_retention_days: int = Field(default=90, ge=1, le=3_650)
    trace_payload_max_chars: int = Field(default=4_000, ge=100, le=100_000)
    trace_payload_max_collection_items: int = Field(default=100, ge=1, le=1_000)
    trace_export_max_runs: int = Field(default=1_000, ge=1, le=10_000)

    # Receipt/invoice ingestion. Files are processed in memory and are not
    # persisted by this pipeline; review storage is a separate explicit action.
    document_ocr_max_bytes: int = Field(default=10_000_000, ge=1_024, le=50_000_000)
    document_ocr_max_pdf_pages: int = Field(default=20, ge=1, le=100)
    document_ocr_languages: str = "eng+rus"
    document_ocr_tesseract_command: str = "tesseract"
    document_ocr_human_review_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    document_ocr_live_eval_enabled: bool = False
    document_ocr_backend: Literal["tesseract", "aws_textract"] = "tesseract"
    document_ocr_aws_enabled: bool = False
    document_ocr_aws_region: str = "us-west-2"
    document_ocr_benchmark_enabled: bool = False
    # Pricing snapshot for DetectDocumentText, first 1M pages. Override for the
    # actual benchmark region/date instead of silently assuming a global price.
    document_ocr_aws_price_per_page_usd: float = Field(default=0.0015, ge=0)
    document_ocr_aws_pricing_snapshot: str = "2026-08-26"

    @model_validator(mode="after")
    def prevent_full_trace_content_outside_local_environments(self) -> "Settings":
        environment = self.app_env.strip().lower()
        if self.trace_content_mode == "full" and environment not in {
            "dev",
            "development",
            "local",
            "test",
        }:
            raise ValueError("TRACE_CONTENT_MODE=full is allowed only in local/dev/test")
        return self

    @property
    def is_dev(self) -> bool:
        return self.app_env == "dev"

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.api_cors_origins.split(",")
            if origin.strip()
        ]

    @field_validator("llm_model_routing_policy")
    @classmethod
    def validate_model_routing_policy(
        cls,
        policy: dict[str, Literal["small", "main"]],
    ) -> dict[str, Literal["small", "main"]]:
        """Accept exact or one-segment wildcard rules only."""
        for rule in policy:
            if rule == "*":
                continue
            parts = rule.split(".")
            if len(parts) != 2 or any(not cls._valid_model_route_segment(part) for part in parts):
                raise ValueError(
                    "LLM model route keys must be '*', 'node.purpose', "
                    "'node.*', or '*.purpose'"
                )
        return policy

    @staticmethod
    def _valid_model_route_segment(segment: str) -> bool:
        if segment == "*":
            return True
        normalized = segment.replace("_", "").replace("-", "")
        return bool(normalized) and normalized.isalnum() and segment == segment.lower()


settings = Settings()
