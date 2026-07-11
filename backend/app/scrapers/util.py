"""Shared scraper helpers: browser UA + challenge-page detection."""

from __future__ import annotations

# A real browser UA. Both sites are Cloudflare-fronted and challenge/block
# obvious bot agents (and datacenter IPs), which is the most likely reason a
# scrape fails from the deployed host while the HTML selectors are unchanged.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Markers Cloudflare (and similar) inject into an interstitial/challenge page.
# We only scan the head of the document to keep this cheap.
_CHALLENGE_MARKERS = (
    "just a moment",
    "attention required",
    "checking your browser",
    "cf-browser-verification",
    "cf-chl-",
    "enable javascript and cookies to continue",
)


def looks_like_challenge(html: str) -> bool:
    """True if the response looks like a bot/JS challenge rather than content."""
    head = html[:4000].lower()
    return any(marker in head for marker in _CHALLENGE_MARKERS)
