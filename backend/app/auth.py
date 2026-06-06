"""Clerk JWT auth dependency for FastAPI."""

from __future__ import annotations

import logging
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

_jwks_cache: Optional[list] = None


async def _get_jwks() -> list:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    async with httpx.AsyncClient() as client:
        resp = await client.get(settings.clerk_jwks_url, timeout=10)
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
                issuer=settings.clerk_issuer,
                options={"verify_aud": False},
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
        keys = await _get_jwks()
        if keys:
            payload = _decode_with_jwks(token, keys)
        else:
            payload = jwt.decode(
                token,
                "",
                algorithms=["RS256"],
                issuer=settings.clerk_issuer,
                options={"verify_aud": False, "verify_signature": False},
            )
    except JWTError as e:
        logger.warning("JWT decode failed: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    clerk_id = payload.get("sub")
    if not clerk_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.clerk_id == clerk_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invite_required")

    return user
