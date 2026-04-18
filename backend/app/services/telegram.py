"""Telegram Bot API helpers — notifications + webhook handling."""

from __future__ import annotations

import logging

import httpx

from app.config import settings

BASE_API = "https://api.telegram.org/bot{token}/{method}"

log = logging.getLogger(__name__)


async def send_photo(chat_id: str, photo_url: str, caption: str) -> bool:
    url = BASE_API.format(token=settings.telegram_bot_token, method="sendPhoto")
    payload = {
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "Markdown",
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=15)
            resp.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        log.error("Telegram sendPhoto failed for chat %s: %s", chat_id, exc)
        return False


async def send_message(chat_id: str, text: str) -> bool:
    url = BASE_API.format(token=settings.telegram_bot_token, method="sendMessage")
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=15)
            resp.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        log.error("Telegram sendMessage failed for chat %s: %s", chat_id, exc)
        return False


async def send_notification(chat_id: str, title: str, results: list[dict]) -> bool:
    caption = format_caption(title, results)
    cover_url = next((r["cover_url"] for r in results if r.get("cover_url")), None)

    if cover_url:
        ok = await send_photo(chat_id, cover_url, caption)
        if ok:
            return True
        log.warning("sendPhoto failed for chat %s, falling back to text", chat_id)

    return await send_message(chat_id, caption)


def format_caption(title: str, results: list[dict]) -> str:
    by_chapter: dict[str, list[dict]] = {}
    for r in results:
        by_chapter.setdefault(r["chapter"], []).append(r)

    lines = [f"📖 *{title}*", ""]
    for chapter, chapter_results in by_chapter.items():
        lines.append(f"🆕 *Chapter {chapter}*")
        for r in chapter_results:
            lines.append(f"  • [{r['site']}]({r['url']})")

    return "\n".join(lines)
