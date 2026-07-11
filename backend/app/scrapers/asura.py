"""Scraper for asurascans.com — ported from manga-notif.

AsuraScans rebuilt the site (Astro) and rotates a random hash suffix on every
comic slug, e.g. ``nano-machine-a80d257e``. A stored slug carrying an *old*
hash now 404s outright, while the *bare* slug (``nano-machine``) 302-redirects
to whatever the current canonical slug is. So we always fetch the bare slug,
follow the redirect, and filter chapter links by the canonical slug the page
declares about itself (``<link rel="canonical">`` / ``og:url``) rather than by
the slug we happened to request.
"""

from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup

from app.scrapers.util import USER_AGENT, looks_like_challenge

BASE_URL = "https://asurascans.com/comics/{slug}"
CHAPTER_URL_RE = re.compile(r"/chapter/([\d.]+)$")
# A trailing "-<6+ hex chars>" is Asura's rotating cache-buster, not part of
# the human-readable slug. Strip it so the bare slug can 302 to the current one.
HASH_SUFFIX_RE = re.compile(r"-[0-9a-f]{6,}$")
# Pull the slug out of any /comics/<slug>[/...] URL.
CANONICAL_SLUG_RE = re.compile(r"/comics/([^/?#]+)")

log = logging.getLogger(__name__)


def base_slug(slug: str) -> str:
    """Drop the rotating ``-<hash>`` suffix so the bare slug can redirect."""
    return HASH_SUFFIX_RE.sub("", slug)


def canonical_slug_from_html(html: str, fallback: str) -> str:
    """The slug the page declares for itself, so we survive hash rotation."""
    soup = BeautifulSoup(html, "lxml")

    canonical = soup.find("link", rel="canonical")
    href = canonical.get("href") if canonical else None
    if not href:
        og_url = soup.find("meta", property="og:url")
        href = og_url.get("content") if og_url else None

    if href:
        m = CANONICAL_SLUG_RE.search(href)
        if m:
            return m.group(1)
    return fallback


def parse_latest_chapter(html: str, slug: str) -> dict | None:
    """Parse a fetched AsuraScans page into the latest-chapter dict (no network).

    ``slug`` is a fallback; the canonical slug declared by the page wins so a
    rotated hash suffix still resolves correctly.
    """
    soup = BeautifulSoup(html, "lxml")

    canonical = canonical_slug_from_html(html, slug)
    chapter_prefix = f"/comics/{canonical}/chapter/"
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
        if looks_like_challenge(html):
            log.warning(
                "AsuraScans: got a bot/JS challenge page for %s (canonical=%s) — "
                "likely IP/UA blocked, not a markup change",
                slug, canonical,
            )
        else:
            log.warning(
                "AsuraScans: no chapters found for %s (canonical=%s, %d bytes) — "
                "markup may have changed", slug, canonical, len(html),
            )
        return None

    log.debug(
        "AsuraScans: %s -> canonical=%s latest=%s", slug, canonical, best_chapter
    )

    m2 = CHAPTER_URL_RE.search(best_href)
    chapter_str = m2.group(1) if m2 else str(best_chapter)
    chapter_url = best_href if best_href.startswith("http") else f"https://asurascans.com{best_href}"

    og_image = soup.find("meta", property="og:image")
    cover_url = og_image["content"] if og_image and og_image.get("content") else None

    og_title = soup.find("meta", property="og:title")
    title = og_title["content"].strip() if og_title and og_title.get("content") else None
    if title:
        # The rebuilt site suffixes og:title with " | Asura Scans"; drop it so the
        # stored display title stays clean.
        title = re.sub(r"\s*\|\s*Asura ?Scans\s*$", "", title, flags=re.I).strip() or None

    return {
        "chapter": chapter_str,
        "url": chapter_url,
        "site": "AsuraScans",
        "site_key": "asura",
        "cover_url": cover_url,
        "title": title,
    }


async def get_latest_chapter(slug: str) -> dict | None:
    # Try the bare slug first (it redirects to the current canonical), then the
    # stored slug verbatim as a fallback. De-dupe while preserving order.
    candidates = list(dict.fromkeys([base_slug(slug), slug]))

    async with httpx.AsyncClient() as client:
        for candidate in candidates:
            url = BASE_URL.format(slug=candidate)
            try:
                resp = await client.get(
                    url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=30,
                    follow_redirects=True,
                )
                log.debug(
                    "AsuraScans GET %s -> %s (final=%s)",
                    url, resp.status_code, resp.url,
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                log.warning("AsuraScans request failed for %s: %s", candidate, exc)
                continue

            result = parse_latest_chapter(resp.text, slug)
            if result is not None:
                return result

    return None
