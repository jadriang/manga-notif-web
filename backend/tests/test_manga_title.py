"""Tests for manga title resolution precedence (pure)."""

from app.api.routes.manga import resolve_manga_title


def test_prefers_user_title():
    assert resolve_manga_title("  My Title ", "Scraped", "some-slug-abc123") == "My Title"


def test_falls_back_to_scraped_title():
    assert resolve_manga_title(None, "  Solo Leveling ", "solo-slug") == "Solo Leveling"
    assert resolve_manga_title("   ", "Solo Leveling", "solo-slug") == "Solo Leveling"


def test_derives_from_slug_and_strips_asura_hash():
    # Asura slugs carry a trailing -<hex> suffix that must be dropped.
    assert resolve_manga_title(None, None, "nano-machine-75e30c62") == "Nano Machine"


def test_derives_from_slug_without_hash():
    assert resolve_manga_title(None, None, "solo-leveling") == "Solo Leveling"


def test_does_not_strip_numeric_chapter_like_segment():
    # A short numeric-ish word is not a hex hash; keep it.
    assert resolve_manga_title(None, "", "tower-of-god") == "Tower Of God"
