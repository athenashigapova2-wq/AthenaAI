"""FastAPI application entry point for the Athena backend."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent import router as agent_router
from app.config import settings

app = FastAPI(
    title="Athena AI API",
    version="0.1.0",
    docs_url="/docs" if settings.is_dev else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(agent_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["system"])
def readiness() -> dict[str, str | list[str]]:
    """Report missing server settings without exposing their values."""
    required_settings = {
        "SUPABASE_URL": settings.supabase_url,
        "SUPABASE_SERVICE_ROLE_KEY": settings.supabase_service_role_key,
        "SUPABASE_JWT_SECRET": settings.supabase_jwt_secret,
    }
    if settings.llm_provider.lower() == "anthropic":
        required_settings["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
    else:
        required_settings["GIGACHAT_AUTH_KEY"] = settings.gigachat_auth_key
    missing = [name for name, value in required_settings.items() if not value]
    return {"status": "ready" if not missing else "not_ready", "missing": missing}
