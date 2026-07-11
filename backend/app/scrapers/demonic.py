"""Scraper for demonicscans.org — ported from manga-notif."""

from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup

from app.scrapers.util import USER_AGENT, looks_like_challenge

BASE_URL = "https://demonicscans.org/manga/{slug}"
CHAPTER_HREF_RE = re.compile(r"chapter=([\d.]+)")

log = logging.getLogger(__name__)


def parse_latest_chapter(html: str) -> dict | None:
    """Parse a fetched DemonicScans page into the latest-chapter dict (no network)."""
    soup = BeautifulSoup(html, "lxml")

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
        if looks_like_challenge(html):
            log.warning(
                "DemonicScans: got a bot/JS challenge page — likely IP/UA "
                "blocked, not a markup change"
            )
        else:
            log.warning(
                "DemonicScans: no chapters found (%d bytes) — markup may have "
                "changed", len(html),
            )
        return None

    m2 = CHAPTER_HREF_RE.search(best_href)
    chapter_str = m2.group(1) if m2 else str(best_chapter)
    chapter_url = best_href if best_href.startswith("http") else f"https://demonicscans.org{best_href}"

    og_image = soup.find("meta", property="og:image")
    cover_url = og_image["content"] if og_image and og_image.get("content") else None

    og_title = soup.find("meta", property="og:title")
    title = og_title["content"].strip() if og_title and og_title.get("content") else None

    return {
        "chapter": chapter_str,
        "url": chapter_url,
        "site": "DemonicScans",
        "site_key": "demonic",
        "cover_url": cover_url,
        "title": title,
    }


async def get_latest_chapter(slug: str) -> dict | None:
    url = BASE_URL.format(slug=slug)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=30,
                follow_redirects=True,
            )
            log.debug("DemonicScans GET %s -> %s", url, resp.status_code)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("DemonicScans request failed for %s: %s", slug, exc)
        return None

    return parse_latest_chapter(resp.text)
