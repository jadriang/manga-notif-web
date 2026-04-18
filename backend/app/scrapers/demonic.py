"""Scraper for demonicscans.org — ported from manga-notif."""

from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://demonicscans.org/manga/{slug}"
CHAPTER_HREF_RE = re.compile(r"chapter=([\d.]+)")

log = logging.getLogger(__name__)


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
        log.warning("DemonicScans request failed for %s: %s", slug, exc)
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    best_chapter: float = -1
    best_href: str = ""

    for link in soup.find_all("a", class_="chplinks", href=True):
        href: str = link["href"]
        m = CHAPTER_HREF_RE.search(href)
        if m:
            try:
                num = float(m.group(1))
            except ValueError:
                continue
            if num > best_chapter:
                best_chapter = num
                best_href = href

    if best_chapter < 0:
        log.warning("DemonicScans: no chapters found for %s", slug)
        return None

    m2 = CHAPTER_HREF_RE.search(best_href)
    chapter_str = m2.group(1) if m2 else str(best_chapter)
    chapter_url = best_href if best_href.startswith("http") else f"https://demonicscans.org{best_href}"

    og = soup.find("meta", property="og:image")
    cover_url = og["content"] if og and og.get("content") else None

    return {
        "chapter": chapter_str,
        "url": chapter_url,
        "site": "DemonicScans",
        "site_key": "demonic",
        "cover_url": cover_url,
    }
