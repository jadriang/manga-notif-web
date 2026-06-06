"""Tests for scraper HTML parsing (pure, no network)."""

from app.scrapers import asura, demonic

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
