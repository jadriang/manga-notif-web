"""Clerk JWT auth dependency for FastAPI."""

from __future__ import annotations

import logging
from time import monotonic
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

# Clerk signs session tokens with RS256. Pin the algorithm here rather than
# trusting the token's own (attacker-controlled) `alg` header, which would
# otherwise allow algorithm-confusion attacks.
ALLOWED_ALGORITHMS = ["RS256"]

JWKS_TTL_SECONDS = 3600
_jwks_cache: Optional[list] = None
_jwks_cached_at: float = 0.0


async def _get_jwks() -> list:
    global _jwks_cache, _jwks_cached_at
    if _jwks_cache is not None and (monotonic() - _jwks_cached_at) < JWKS_TTL_SECONDS:
        return _jwks_cache
    async with httpx.AsyncClient() as client:
        resp = await client.get(settings.clerk_jwks_url, timeout=10)
        resp.raise_for_status()
    _jwks_cache = resp.json().get("keys", [])
    _jwks_cached_at = monotonic()
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
                algorithms=ALLOWED_ALGORITHMS,
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

    # Fetch signing keys. A failure here (e.g. CLERK_JWKS_URL unset/unreachable)
    # is a server/config problem, not a bad token — surface it as 503 + a log
    # line rather than leaking an unhandled 500.
    try:
        keys = await _get_jwks()
    except Exception as e:
        logger.error("JWKS fetch failed (check CLERK_JWKS_URL): %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth temporarily unavailable",
        )

    try:
        payload = _decode_with_jwks(token, keys)
    except JWTError as e:
        logger.warning("JWT decode failed: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    clerk_id = payload.get("sub")
    if not clerk_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    try:
        result = await db.execute(select(User).where(User.clerk_id == clerk_id))
        user = result.scalar_one_or_none()
    except Exception as e:
        logger.error("DB lookup failed in get_current_user: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invite_required")

    return user
