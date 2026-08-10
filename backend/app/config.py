"""Единая точка чтения настроек. Больше нигде в коде нет os.environ."""

from pathlib import Path

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

    # LLM provider
    llm_provider: str = "gigachat"
    llm_router_model: str = ""
    agent_baseline_version: str = "baseline-v1"

    # GigaChat
    gigachat_auth_key: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat-2"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-latest"

    # Supabase
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwt_audience: str = "authenticated"

    # HTTP API
    api_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    app_env: str = "dev"
    test_user_id: str = "4c58346d-801f-4241-a349-02a2736361f0"

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


settings = Settings()
