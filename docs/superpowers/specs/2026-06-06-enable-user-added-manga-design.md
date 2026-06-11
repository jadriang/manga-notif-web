# Enable user-added manga (Asura + Demonic)

**Date:** 2026-06-06
**Status:** Approved
**Base branch:** `main`

## Background

The "add manga" feature is fully built but was deliberately disabled in commit
`b442f6d` ("temporarily disable add manga to prevent spam"). The disable consists of:

- A `503` short-circuit at the top of `create_manga` (`backend/app/api/routes/manga.py`)
- A greyed-out `AddMangaPage.tsx` with a "temporarily disabled" banner

Everything else already works: URL parsing (`url_parser.py`), the Asura/Demonic
scrapers, the create flow (parse → dedupe by slug → scrape → create `Manga` +
`ChapterState` + auto-subscribe creator), the `/manga/{id}/add-url` route, and the
cron checker (which automatically picks up any manga in the table).

This is a **re-enable + polish** task, not a build-from-scratch.

## Decisions

1. **Abuse control: trust invited users.** The user base is gated (whitelist /
   invite codes), so no per-user rate limits, caps, or ownership restrictions are
   added. Re-enable as-is.
2. **Titles: scrape `og:title`.** Fix the broken title auto-detection (currently
   mangles the slug with a hardcoded hash literal). Prefer real `og:title`, fall
   back to a generically cleaned slug, then to a 400 asking for manual entry.
3. **Asura domain stays `asurascans.com`** (confirmed by user). No scraper domain
   change.

## Changes

### 1. Scrapers — `backend/app/scrapers/asura.py`, `demonic.py`
Both already extract `og:image`. Add parallel `og:title` extraction and include
`"title"` (or `None`) in the returned dict:

```python
og_title = soup.find("meta", property="og:title")
title = og_title["content"].strip() if og_title and og_title.get("content") else None
# return {..., "title": title}
```

### 2. `create_manga` — `backend/app/api/routes/manga.py`
- Delete the `raise HTTPException(503, ...)` line.
- Replace the slug-mangling title fallback. New precedence:
  1. `body.title` (explicit user override)
  2. scraped `result["title"]`
  3. generically cleaned slug — strip a trailing `-<hex>` Asura hash via regex
     (not a hardcoded literal), replace dashes, title-case
  4. else `400` asking for a manual title

### 3. Frontend — `frontend/src/pages/AddMangaPage.tsx`
- Remove the "temporarily disabled" banner and the `opacity`/`pointerEvents` lock
  on the form card.
- Update the hardcoded example URL containing a stale hash (cosmetic).

## Out of scope (YAGNI)

- Rate limiting / per-user caps / ownership-restricted management UI.
- Confirmation/preview step before saving.
- Changes to the cron checker or `add-url` route (both already handle new manga).

## Testing

- Unit test for `og:title` extraction in each scraper (parse fixed HTML, assert
  title). Use TDD: test first, then implement.
- Unit/route test that `create_manga` no longer returns `503` and applies the
  title fallback precedence.
- Existing suite (7 tests) must stay green.
