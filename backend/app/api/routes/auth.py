"""Auth routes: invite redemption."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import _decode_with_jwks, _get_jwks
from app.database import get_db
from app.models.tables import InviteCode, User
from app.rate_limit import invite_redeem_limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()


class RedeemInviteBody(BaseModel):
    code: str


async def _verify_clerk_token(credentials: HTTPAuthorizationCredentials) -> dict:
    """Validate Clerk JWT and return payload. Raises 401 on failure."""
    try:
        keys = await _get_jwks()
        return _decode_with_jwks(credentials.credentials, keys)
    except JWTError as e:
        logger.warning("JWT decode failed: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


@router.post("/redeem-invite")
async def redeem_invite(
    body: RedeemInviteBody,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    if not invite_redeem_limiter.check(client_ip):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate_limited")

    payload = await _verify_clerk_token(credentials)
    clerk_id = payload.get("sub")
    email = payload.get("email", "")
    if not clerk_id or not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    result = await db.execute(select(InviteCode).where(InviteCode.code == body.code))
    invite = result.scalar_one_or_none()

    logged_result = "ok"
    try:
        if invite is None:
            logged_result = "invalid"
            raise HTTPException(status_code=400, detail="invalid_code")
        if invite.used_count >= invite.max_uses:
            logged_result = "exhausted"
            raise HTTPException(status_code=400, detail="code_exhausted")

        existing = await db.execute(select(User).where(User.clerk_id == clerk_id))
        if existing.scalar_one_or_none() is not None:
            logged_result = "already_redeemed"
            raise HTTPException(status_code=409, detail="already_redeemed")

        user = User(clerk_id=clerk_id, email=email.lower())
        db.add(user)
        invite.used_count += 1
        await db.commit()
        await db.refresh(user)

        return {"id": str(user.id), "email": user.email, "clerk_id": user.clerk_id}
    finally:
        logger.info(
            "invite_redeem result=%s clerk_id=%s",
            logged_result,
            clerk_id,
        )
