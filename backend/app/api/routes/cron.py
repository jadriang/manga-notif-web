"""Cron endpoint — scrapes all manga and sends notifications."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import async_session
from app.models.tables import ChapterState, Manga, Subscription, User
from app.scrapers import asura, demonic
from app.services.telegram import send_notification

router = APIRouter(prefix="/cron", tags=["cron"])

log = logging.getLogger(__name__)

SCRAPERS = {"asura": asura, "demonic": demonic}
REQUEST_DELAY = 2  # seconds between scrape requests


def chapter_is_newer(current: str, stored: str) -> bool:
    try:
        return float(current) > float(stored)
    except ValueError:
        return current != stored


@router.post("/check")
async def check_for_updates(authorization: str = Header(...)):
    import hmac
    expected = f"Bearer {settings.cron_secret}"
    if not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")

    async with async_session() as db:
        # Load all manga with their chapter states
        result = await db.execute(
            select(Manga).options(selectinload(Manga.chapter_states))
        )
        all_manga = result.scalars().all()

        updates = []
        first_request = True

        for manga in all_manga:
            slug_map = {}
            if manga.asura_slug:
                slug_map["asura"] = manga.asura_slug
            if manga.demonic_slug:
                slug_map["demonic"] = manga.demonic_slug

            existing_state = {cs.site: cs for cs in manga.chapter_states}
            new_results = []

            for site, slug in slug_map.items():
                scraper = SCRAPERS.get(site)
                if not scraper:
                    continue

                if not first_request:
                    await asyncio.sleep(REQUEST_DELAY)
                first_request = False

                log.info("Checking %s on %s …", manga.title, site)
                scrape_result = await scraper.get_latest_chapter(slug)
                if scrape_result is None:
                    continue

                cs = existing_state.get(site)
                if cs is None:
                    # First time seeing this site — seed state
                    log.info("First seen: %s Ch.%s on %s", manga.title, scrape_result["chapter"], site)
                    db.add(ChapterState(
                        manga_id=manga.id,
                        site=site,
                        latest_chapter=scrape_result["chapter"],
                        chapter_url=scrape_result["url"],
                    ))
                elif chapter_is_newer(scrape_result["chapter"], cs.latest_chapter):
                    log.info("New chapter! %s Ch.%s on %s (was %s)",
                             manga.title, scrape_result["chapter"], site, cs.latest_chapter)
                    cs.latest_chapter = scrape_result["chapter"]
                    cs.chapter_url = scrape_result["url"]
                    new_results.append(scrape_result)
                else:
                    log.info("No update: %s still at Ch.%s on %s", manga.title, cs.latest_chapter, site)

                # Update cover if we got a new one
                if scrape_result.get("cover_url") and not manga.cover_url:
                    manga.cover_url = scrape_result["cover_url"]

            if new_results:
                updates.append({"manga": manga, "results": new_results})

        await db.commit()

        # Send notifications to subscribed users
        notifications_sent = 0
        for update in updates:
            manga = update["manga"]
            results = update["results"]

            # Find users subscribed to this manga with notify=True and a linked Telegram
            sub_result = await db.execute(
                select(User)
                .join(Subscription, Subscription.user_id == User.id)
                .where(
                    Subscription.manga_id == manga.id,
                    Subscription.notify.is_(True),
                    User.telegram_chat_id.isnot(None),
                )
            )
            users = sub_result.scalars().all()

            for u in users:
                await send_notification(u.telegram_chat_id, manga.title, results)
                notifications_sent += 1

    return {
        "manga_checked": len(all_manga),
        "updates_found": len(updates),
        "notifications_sent": notifications_sent,
    }
