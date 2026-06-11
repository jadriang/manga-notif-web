"""Telegram webhook + linking routes."""

from __future__ import annotations

import hmac
import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import async_session, get_db
from app.models.tables import User
from app.services.telegram import send_message

router = APIRouter(prefix="/telegram", tags=["telegram"])

log = logging.getLogger(__name__)


@router.post("/link")
async def generate_link_token(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a one-time token and return a Telegram deep link."""
    token = secrets.token_urlsafe(32)
    user.telegram_link_token = token
    await db.commit()

    # Build bot username from token (set via env or derive at runtime)
    # The user will need to know the bot username — stored in frontend config
    return {"token": token, "telegram_chat_id": user.telegram_chat_id}


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=""),
):
    """Receive updates from Telegram Bot API."""
    # Fail closed: require the secret to be configured, then verify it.
    # Without this, an unset secret would leave the webhook fully open.
    if not settings.telegram_webhook_secret:
        log.error("TELEGRAM_WEBHOOK_SECRET is not configured; rejecting webhook")
        raise HTTPException(status_code=503, detail="Webhook not configured")
    if not hmac.compare_digest(
        x_telegram_bot_api_secret_token, settings.telegram_webhook_secret
    ):
        raise HTTPException(status_code=403, detail="Forbidden")

    data = await request.json()

    message = data.get("message")
    if not message:
        return {"ok": True}

    text = message.get("text", "")
    chat_id = str(message["chat"]["id"])

    if not text.startswith("/start"):
        return {"ok": True}

    # Extract token from /start <token>
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await send_message(chat_id, "Welcome! Please use the link from the web app to connect your account.")
        return {"ok": True}

    link_token = parts[1].strip()

    async with async_session() as db:
        result = await db.execute(
            select(User).where(User.telegram_link_token == link_token)
        )
        user = result.scalar_one_or_none()

        if not user:
            await send_message(chat_id, "❌ Invalid or expired link token. Please generate a new one from the web app.")
            return {"ok": True}

        user.telegram_chat_id = chat_id
        user.telegram_link_token = None  # Consume the token
        await db.commit()

    await send_message(chat_id, "✅ Account linked! You'll receive manga chapter notifications here.")
    return {"ok": True}


@router.delete("/link")
async def unlink_telegram(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unlink Telegram from the user's account."""
    user.telegram_chat_id = None
    user.telegram_link_token = None
    await db.commit()
    return {"ok": True}
