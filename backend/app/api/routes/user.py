"""User profile route."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.models.tables import User

router = APIRouter(prefix="/me", tags=["user"])


@router.get("")
async def get_profile(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "telegram_chat_id": user.telegram_chat_id,
        "created_at": user.created_at,
    }
