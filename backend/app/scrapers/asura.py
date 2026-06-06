"""Scraper for asurascans.com — ported from manga-notif."""

from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://asurascans.com/comics/{slug}"
CHAPTER_URL_RE = re.compile(r"/chapter/([\d.]+)$")

log = logging.getLogger(__name__)


def parse_latest_chapter(html: str, slug: str) -> dict | None:
    """Parse a fetched AsuraScans page into the latest-chapter dict (no network)."""
    soup = BeautifulSoup(html, "lxml")

    chapter_prefix = f"/comics/{slug}/chapter/"
    best_chapter: float = -1
    best_href: str = ""

    for link in soup.find_all("a", href=True):
        href: str = link["href"]
        if chapter_prefix not in href:
            continue
        m = CHAPTER_URL_RE.search(href)
        if m:
            try:
                num = float(m.group(1))
            except ValueError:
                continue
            if num > best_chapter:
                best_chapter = num
                best_href = href

    if best_chapter < 0:
        log.warning("AsuraScans: no chapters found for %s", slug)
        return None

    m2 = CHAPTER_URL_RE.search(best_href)
    chapter_str = m2.group(1) if m2 else str(best_chapter)
    chapter_url = best_href if best_href.startswith("http") else f"https://asurascans.com{best_href}"

    og_image = soup.find("meta", property="og:image")
    cover_url = og_image["content"] if og_image and og_image.get("content") else None

    og_title = soup.find("meta", property="og:title")
    title = og_title["content"].strip() if og_title and og_title.get("content") else None

    return {
        "chapter": chapter_str,
        "url": chapter_url,
        "site": "AsuraScans",
        "site_key": "asura",
        "cover_url": cover_url,
        "title": title,
    }


async def get_latest_chapter(slug: str) -> dict | None:
    url = BASE_URL.format(slug=slug)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "MangaNotif/1.0 (+https://github.com)"},
                timeout=30,
                follow_redirects=True,
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("AsuraScans request failed for %s: %s", slug, exc)
        return None

    return parse_latest_chapter(resp.text, slug)
