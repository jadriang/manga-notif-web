"""URL parser — extracts site + slug from a manga page URL."""

from __future__ import annotations

import re
from urllib.parse import urlparse

ASURA_RE = re.compile(r"^/comics/([^/]+)/?$")
DEMONIC_RE = re.compile(r"^/manga/([^/]+)/?$")


def parse_manga_url(url: str) -> dict | None:
    """Return ``{"site": "asura"|"demonic", "slug": "..."}`` or None."""
    parsed = urlparse(url)
    host = parsed.hostname or ""

    if "asurascans.com" in host or "asura" in host:
        m = ASURA_RE.match(parsed.path)
        if m:
            return {"site": "asura", "slug": m.group(1)}

    if "demonicscans.org" in host or "demonic" in host:
        m = DEMONIC_RE.match(parsed.path)
        if m:
            return {"site": "demonic", "slug": m.group(1)}

    return None
