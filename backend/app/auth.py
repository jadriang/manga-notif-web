"""Supabase JWT auth dependency for FastAPI."""

from __future__ import annotations

import logging
import uuid
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwk, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.tables import User

logger = logging.getLogger(__name__)
security = HTTPBearer()

# Cached JWKS keys (fetched once on first request)
_jwks_cache: Optional[list] = None


async def _get_jwks() -> list:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    async with httpx.AsyncClient() as client:
        resp = await client.get(jwks_url, timeout=10)
        resp.raise_for_status()
    _jwks_cache = resp.json().get("keys", [])
    return _jwks_cache


def _decode_with_jwks(token: str, keys: list) -> dict:
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")
    for key_data in keys:
        if kid and key_data.get("kid") != kid:
            continue
        public_key = jwk.construct(key_data)
        try:
            return jwt.decode(
                token,
                public_key,
                algorithms=[unverified_header.get("alg", "RS256")],
                audience="authenticated",
            )
        except JWTError:
            continue
    raise JWTError("No matching key found in JWKS")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        # Try RS256 via JWKS first (newer Supabase projects)
        keys = await _get_jwks()
        if keys:
            payload = _decode_with_jwks(token, keys)
        else:
            # Fall back to HS256 with JWT secret (older projects)
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
    except JWTError as e:
        logger.warning("JWT decode failed: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user_id = uuid.UUID(sub)
    email = payload.get("email", "")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(id=user_id, email=email)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user
