"""Manga CRUD routes."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.database import get_db
from app.models.tables import ChapterState, Manga, Subscription, User
from app.scrapers.url_parser import parse_manga_url
from app.scrapers import asura, demonic

router = APIRouter(prefix="/manga", tags=["manga"])


class MangaCreate(BaseModel):
    url: str
    title: Optional[str] = None


class MangaOut(BaseModel):
    id: uuid.UUID
    title: str
    asura_slug: Optional[str]
    demonic_slug: Optional[str]
    cover_url: Optional[str]
    subscribed: bool = False
    latest_chapters: dict[str, str] = {}

    model_config = {"from_attributes": True}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_manga(
    body: MangaCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    parsed = parse_manga_url(body.url)
    if not parsed:
        raise HTTPException(status_code=400, detail="Unsupported URL. Use an AsuraScans or DemonicScans manga page URL.")

    site = parsed["site"]
    slug = parsed["slug"]

    # Check if this slug already exists
    if site == "asura":
        existing = await db.execute(select(Manga).where(Manga.asura_slug == slug))
    else:
        existing = await db.execute(select(Manga).where(Manga.demonic_slug == slug))

    manga = existing.scalar_one_or_none()

    if manga:
        # Manga already tracked — just auto-subscribe the user
        sub_check = await db.execute(
            select(Subscription).where(Subscription.user_id == user.id, Subscription.manga_id == manga.id)
        )
        if not sub_check.scalar_one_or_none():
            db.add(Subscription(user_id=user.id, manga_id=manga.id))
            await db.commit()
        return {"id": manga.id, "title": manga.title, "already_existed": True}

    # Scrape the page to get title and cover
    scraper = asura if site == "asura" else demonic
    result = await scraper.get_latest_chapter(slug)

    title = body.title
    if not title:
        if result:
            # try to get from og:title — for now use slug as fallback
            title = slug.replace("-", " ").replace("75e30c62", "").strip().title()
        else:
            raise HTTPException(status_code=400, detail="Could not scrape this URL. Please provide a title manually.")

    manga = Manga(
        title=title,
        asura_slug=slug if site == "asura" else None,
        demonic_slug=slug if site == "demonic" else None,
        cover_url=result["cover_url"] if result else None,
        added_by=user.id,
    )
    db.add(manga)
    await db.flush()

    # Store initial chapter state if scrape succeeded
    if result:
        db.add(ChapterState(
            manga_id=manga.id,
            site=site,
            latest_chapter=result["chapter"],
            chapter_url=result["url"],
        ))

    # Auto-subscribe creator
    db.add(Subscription(user_id=user.id, manga_id=manga.id))
    await db.commit()

    return {"id": manga.id, "title": manga.title, "already_existed": False}


@router.get("")
async def list_manga(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Manga).options(selectinload(Manga.chapter_states))
    )
    all_manga = result.scalars().all()

    # Get user's subscriptions
    sub_result = await db.execute(
        select(Subscription.manga_id).where(Subscription.user_id == user.id)
    )
    subscribed_ids = {row[0] for row in sub_result.all()}

    output = []
    for m in all_manga:
        chapters = {cs.site: cs.latest_chapter for cs in m.chapter_states}
        output.append(MangaOut(
            id=m.id,
            title=m.title,
            asura_slug=m.asura_slug,
            demonic_slug=m.demonic_slug,
            cover_url=m.cover_url,
            subscribed=m.id in subscribed_ids,
            latest_chapters=chapters,
        ))

    return output


@router.post("/{manga_id}/add-url")
async def add_manga_url(
    manga_id: uuid.UUID,
    body: MangaCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a second site URL to an existing manga."""
    parsed = parse_manga_url(body.url)
    if not parsed:
        raise HTTPException(status_code=400, detail="Unsupported URL.")

    result = await db.execute(select(Manga).where(Manga.id == manga_id))
    manga = result.scalar_one_or_none()
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    site = parsed["site"]
    slug = parsed["slug"]

    if site == "asura":
        manga.asura_slug = slug
    else:
        manga.demonic_slug = slug

    # Scrape to get initial chapter state for the new site
    scraper = asura if site == "asura" else demonic
    scrape_result = await scraper.get_latest_chapter(slug)
    if scrape_result:
        # Update cover if we didn't have one
        if not manga.cover_url and scrape_result.get("cover_url"):
            manga.cover_url = scrape_result["cover_url"]

        # Check if chapter state already exists for this site
        cs_check = await db.execute(
            select(ChapterState).where(ChapterState.manga_id == manga.id, ChapterState.site == site)
        )
        if not cs_check.scalar_one_or_none():
            db.add(ChapterState(
                manga_id=manga.id,
                site=site,
                latest_chapter=scrape_result["chapter"],
                chapter_url=scrape_result["url"],
            ))

    await db.commit()
    return {"ok": True}
