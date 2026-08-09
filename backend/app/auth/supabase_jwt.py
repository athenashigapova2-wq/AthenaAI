"""Validate Supabase access tokens at the FastAPI boundary."""

from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError

from app.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    email: str | None = None


def decode_access_token(token: str) -> AuthenticatedUser:
    """Decode a Supabase HS256 access token and extract its trusted user id."""
    if not settings.supabase_jwt_secret:
        raise RuntimeError("SUPABASE_JWT_SECRET должен быть задан для запуска API")

    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.supabase_jwt_audience,
            options={"require": ["exp", "sub"]},
        )
    except InvalidTokenError as exc:
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
