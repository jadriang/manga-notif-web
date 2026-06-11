"""Cron endpoint — scrapes all manga and sends notifications."""

from __future__ import annotations

import asyncio
import hmac
import logging
import uuid
from dataclasses import dataclass
from typing import Optional

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


@dataclass
class MangaSnapshot:
    id: uuid.UUID
    title: str
    cover_url: Optional[str]
    slugs: dict[str, str]  # site -> slug
    states: dict[str, str]  # site -> current latest_chapter


def chapter_is_newer(current: str, stored: str) -> bool:
    try:
        return float(current) > float(stored)
    except ValueError:
        return current != stored


async def load_snapshots() -> list[MangaSnapshot]:
    """Phase 1: read all manga into plain dicts, then release the DB."""
    async with async_session() as db:
        result = await db.execute(
            select(Manga).options(selectinload(Manga.chapter_states))
        )
        snapshots = []
        for m in result.scalars().all():
            slugs = {}
            if m.asura_slug:
                slugs["asura"] = m.asura_slug
            if m.demonic_slug:
                slugs["demonic"] = m.demonic_slug
            states = {cs.site: cs.latest_chapter for cs in m.chapter_states}
            snapshots.append(MangaSnapshot(
                id=m.id, title=m.title, cover_url=m.cover_url,
                slugs=slugs, states=states,
            ))
        return snapshots


async def scrape_all(snapshots: list[MangaSnapshot]) -> dict[uuid.UUID, dict[str, dict]]:
    """Phase 2: scrape every (manga, site) with no DB connection held."""
    results: dict[uuid.UUID, dict[str, dict]] = {}
    first_request = True
    for snap in snapshots:
        per_site: dict[str, dict] = {}
        for site, slug in snap.slugs.items():
            scraper = SCRAPERS.get(site)
            if not scraper:
                continue
            if not first_request:
                await asyncio.sleep(REQUEST_DELAY)
            first_request = False

            log.info("Checking %s on %s …", snap.title, site)
            scrape_result = await scraper.get_latest_chapter(slug)
            if scrape_result is not None:
                per_site[site] = scrape_result
        if per_site:
            results[snap.id] = per_site
    return results


async def persist_updates(
    snapshots: list[MangaSnapshot],
    scraped: dict[uuid.UUID, dict[str, dict]],
) -> tuple[int, list[tuple[str, list[dict], list[str]]]]:
    """Phase 3: apply diffs and fetch notification targets in one short session.

    Returns (count_of_manga_with_new_chapters, notify_payload) where
    notify_payload is a list of (manga_title, results, telegram_chat_ids).
    """
    snap_by_id = {s.id: s for s in snapshots}
    updated_manga_ids: list[uuid.UUID] = []
    new_results_by_manga: dict[uuid.UUID, list[dict]] = {}

    if not scraped:
        return 0, []

    async with async_session() as db:
        # Re-fetch only the manga we actually scraped, with their states.

        result = await db.execute(
            select(Manga)
            .options(selectinload(Manga.chapter_states))
            .where(Manga.id.in_(scraped.keys()))
        )
        manga_rows = {m.id: m for m in result.scalars().all()}

        for manga_id, per_site in scraped.items():
            manga = manga_rows.get(manga_id)
            snap = snap_by_id.get(manga_id)
            if manga is None or snap is None:
                continue

            existing_state = {cs.site: cs for cs in manga.chapter_states}
            new_results: list[dict] = []

            for site, scrape_result in per_site.items():
                cs = existing_state.get(site)
                if cs is None:
                    log.info("First seen: %s Ch.%s on %s",
                             snap.title, scrape_result["chapter"], site)
                    db.add(ChapterState(
                        manga_id=manga.id,
                        site=site,
                        latest_chapter=scrape_result["chapter"],
                        chapter_url=scrape_result["url"],
                    ))
                elif chapter_is_newer(scrape_result["chapter"], cs.latest_chapter):
                    log.info("New chapter! %s Ch.%s on %s (was %s)",
                             snap.title, scrape_result["chapter"], site, cs.latest_chapter)
                    cs.latest_chapter = scrape_result["chapter"]
                    cs.chapter_url = scrape_result["url"]
                    new_results.append(scrape_result)
                else:
                    log.info("No update: %s still at Ch.%s on %s",
                             snap.title, cs.latest_chapter, site)

                if scrape_result.get("cover_url") and not manga.cover_url:
                    manga.cover_url = scrape_result["cover_url"]

            if new_results:
                updated_manga_ids.append(manga.id)
                new_results_by_manga[manga.id] = new_results

        # Fetch all notification targets in a single query before commit.
        notify_payload: list[tuple[str, list[dict], list[str]]] = []
        if updated_manga_ids:
            sub_result = await db.execute(
                select(Subscription.manga_id, User.telegram_chat_id)
                .join(User, User.id == Subscription.user_id)
                .where(
                    Subscription.manga_id.in_(updated_manga_ids),
                    Subscription.notify.is_(True),
                    User.telegram_chat_id.isnot(None),
                )
            )
            targets_by_manga: dict[uuid.UUID, list[str]] = {}
            for manga_id, chat_id in sub_result.all():
                targets_by_manga.setdefault(manga_id, []).append(chat_id)

            for manga_id in updated_manga_ids:
                chat_ids = targets_by_manga.get(manga_id, [])
                if not chat_ids:
                    continue
                title = snap_by_id[manga_id].title
                notify_payload.append((title, new_results_by_manga[manga_id], chat_ids))

        await db.commit()

    return len(updated_manga_ids), notify_payload


@router.post("/check")
async def check_for_updates(authorization: str = Header(...)):
    # Fail closed: an unset secret must never authorize anyone (otherwise
    # "Bearer " would match an empty CRON_SECRET).
    if not settings.cron_secret:
        log.error("CRON_SECRET is not configured; refusing cron request")
        raise HTTPException(status_code=503, detail="Cron not configured")
    expected = f"Bearer {settings.cron_secret}"
    if not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Phase 1: short DB read.
    snapshots = await load_snapshots()

    # Phase 2: slow scraping with no DB connection held.
    scraped = await scrape_all(snapshots)

    # Phase 3: short DB write + fetch notification targets.
    updates_found, notify_payload = await persist_updates(snapshots, scraped)

    # Phase 4: send Telegram notifications with no DB connection held.
    notifications_sent = 0
    for title, results, chat_ids in notify_payload:
        for chat_id in chat_ids:
            await send_notification(chat_id, title, results)
            notifications_sent += 1

    return {
        "manga_checked": len(snapshots),
        "updates_found": updates_found,
        "notifications_sent": notifications_sent,
    }
