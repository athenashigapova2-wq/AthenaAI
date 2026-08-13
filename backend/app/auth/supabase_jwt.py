"""Validate Supabase access tokens at the FastAPI boundary."""

import logging
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError, PyJWTError

from app.config import settings

bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    email: str | None = None


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    if not settings.supabase_url:
        raise RuntimeError("SUPABASE_URL is required for asymmetric JWT verification")
    return PyJWKClient(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json",
        cache_keys=True,
    )


def decode_access_token(token: str) -> AuthenticatedUser:
    """Verify a legacy HS256 or current JWKS-signed Supabase access token."""
    try:
        algorithm = str(jwt.get_unverified_header(token).get("alg", ""))
        if algorithm == "HS256":
            if not settings.supabase_jwt_secret:
                raise RuntimeError("SUPABASE_JWT_SECRET is required for HS256 tokens")
            signing_key = settings.supabase_jwt_secret
        elif algorithm in {"RS256", "ES256"}:
            signing_key = _jwks_client().get_signing_key_from_jwt(token).key
        else:
            raise InvalidTokenError(f"Unsupported JWT algorithm: {algorithm}")

        payload = jwt.decode(
            token,
            signing_key,
            algorithms=[algorithm],
            audience=settings.supabase_jwt_audience,
            issuer=f"{settings.supabase_url.rstrip('/')}/auth/v1" if settings.supabase_url else None,
            options={"require": ["exp", "sub"]},
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Backend authentication is not configured: {exc}",
        ) from exc
    except PyJWKClientConnectionError as exc:
        logger.warning("Could not download Supabase JWKS: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Не удалось получить ключи подписи Supabase; проверьте SUPABASE_URL и сеть backend",
        ) from exc
    except PyJWKClientError as exc:
        logger.warning("Supabase JWKS rejected access token: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Для access token не найден актуальный ключ подписи Supabase; войдите заново",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except (InvalidTokenError, PyJWTError, ValueError, TypeError) as exc:
        logger.info("Supabase access token validation failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный или истёкший access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return AuthenticatedUser(user_id=str(payload["sub"]), email=payload.get("email"))


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(credentials.credentials)
