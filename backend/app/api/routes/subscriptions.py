"""Subscription routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.tables import Manga, Subscription, User

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


class SubscriptionToggle(BaseModel):
    manga_id: uuid.UUID


@router.get("")
async def list_subscriptions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    subs = result.scalars().all()
    return [{"manga_id": s.manga_id, "notify": s.notify} for s in subs]


@router.post("")
async def toggle_subscription(
    body: SubscriptionToggle,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify manga exists
    manga = await db.execute(select(Manga).where(Manga.id == body.manga_id))
    if not manga.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Manga not found")

    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.manga_id == body.manga_id,
        )
    )
    sub = result.scalar_one_or_none()

    if sub:
        await db.delete(sub)
        await db.commit()
        return {"subscribed": False}
    else:
        db.add(Subscription(user_id=user.id, manga_id=body.manga_id))
        await db.commit()
        return {"subscribed": True}
