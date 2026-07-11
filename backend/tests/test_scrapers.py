"""Tests for scraper HTML parsing (pure, no network)."""

from app.scrapers import asura, demonic
from app.scrapers.util import looks_like_challenge

ASURA_HTML = """
<html><head>
<meta property="og:title" content="Nano Machine" />
<meta property="og:image" content="https://cdn.asura.test/cover.jpg" />
</head><body>
<a href="/comics/nano-machine-abc123/chapter/1">Ch 1</a>
<a href="/comics/nano-machine-abc123/chapter/12.5">Ch 12.5</a>
<a href="/comics/nano-machine-abc123/chapter/3">Ch 3</a>
<a href="/comics/other-manga/chapter/99">unrelated</a>
</body></html>
"""

DEMONIC_HTML = """
<html><head>
<meta property="og:title" content="Solo Leveling" />
<meta property="og:image" content="https://cdn.demonic.test/cover.jpg" />
</head><body>
<a class="chplinks" href="/title/reader/?manga=solo&chapter=1">Ch 1</a>
<a class="chplinks" href="/title/reader/?manga=solo&chapter=20">Ch 20</a>
<a class="chplinks" href="/title/reader/?manga=solo&chapter=4">Ch 4</a>
</body></html>
"""


def test_asura_parse_extracts_title():
    result = asura.parse_latest_chapter(ASURA_HTML, "nano-machine-abc123")
    assert result is not None
    assert result["title"] == "Nano Machine"


def test_asura_parse_picks_highest_chapter():
    result = asura.parse_latest_chapter(ASURA_HTML, "nano-machine-abc123")
    assert result["chapter"] == "12.5"
    assert result["cover_url"] == "https://cdn.asura.test/cover.jpg"


def test_asura_parse_title_none_when_missing():
    html = ASURA_HTML.replace('<meta property="og:title" content="Nano Machine" />', "")
    result = asura.parse_latest_chapter(html, "nano-machine-abc123")
    assert result is not None
    assert result["title"] is None


def test_asura_parse_returns_none_without_chapters():
    assert asura.parse_latest_chapter("<html></html>", "whatever") is None


def test_asura_base_slug_strips_rotating_hash():
    # Asura appends a rotating "-<hash>" cache-buster to every slug.
    assert asura.base_slug("nano-machine-a80d257e") == "nano-machine"
    assert asura.base_slug("overgeared-5abb513e") == "overgeared"
    # A slug with no hash suffix is left alone.
    assert asura.base_slug("nano-machine") == "nano-machine"


# The page's canonical slug carries the *current* hash, which differs from the
# stored one after Asura rotates it. Parsing must follow the page's own slug.
ASURA_ROTATED_HTML = """
<html><head>
<link rel="canonical" href="https://asurascans.com/comics/nano-machine-NEWHASH" />
<meta property="og:title" content="Nano Machine | Asura Scans" />
<meta property="og:image" content="https://cdn.asura.test/cover.jpg" />
</head><body>
<a href="/comics/nano-machine-NEWHASH/chapter/1">Ch 1</a>
<a href="/comics/nano-machine-NEWHASH/chapter/320">Ch 320</a>
</body></html>
"""


def test_asura_parse_uses_canonical_slug_over_stored():
    # Requested with the OLD stored slug; page declares a new canonical slug.
    result = asura.parse_latest_chapter(ASURA_ROTATED_HTML, "nano-machine-OLDHASH")
    assert result is not None
    assert result["chapter"] == "320"
    assert result["url"] == "https://asurascans.com/comics/nano-machine-NEWHASH/chapter/320"


def test_demonic_parse_extracts_title():
    result = demonic.parse_latest_chapter(DEMONIC_HTML)
    assert result is not None
    assert result["title"] == "Solo Leveling"


def test_demonic_parse_picks_highest_chapter():
    result = demonic.parse_latest_chapter(DEMONIC_HTML)
    assert result["chapter"] == "20"
    assert result["cover_url"] == "https://cdn.demonic.test/cover.jpg"


def test_demonic_parse_title_none_when_missing():
    html = DEMONIC_HTML.replace('<meta property="og:title" content="Solo Leveling" />', "")
    result = demonic.parse_latest_chapter(html)
    assert result is not None
    assert result["title"] is None


def test_demonic_parse_returns_none_without_chapters():
    assert demonic.parse_latest_chapter("<html></html>") is None


def test_looks_like_challenge_detects_cloudflare():
    assert looks_like_challenge("<html><title>Just a moment...</title></html>")
    assert looks_like_challenge("<h1>Attention Required! | Cloudflare</h1>")
    assert not looks_like_challenge(ASURA_HTML)
    assert not looks_like_challenge(DEMONIC_HTML)
