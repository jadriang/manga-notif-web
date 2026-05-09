"""Public auth utilities."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.tables import AllowedEmail

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/check-email")
async def check_email(
    email: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    normalized = email.lower().strip()
    result = await db.execute(select(AllowedEmail).where(AllowedEmail.email == normalized))
    found = result.scalar_one_or_none()
    return {"allowed": found is not None}
