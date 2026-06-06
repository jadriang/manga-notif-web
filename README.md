# Manga Notifier

Track manga series and get a Telegram message when a new chapter drops.

## Architecture

```
┌─────────────────┐        ┌──────────────────────┐        ┌─────────────┐
│  React SPA      │──JWT──▶│  FastAPI backend      │──SQL──▶│  Supabase   │
│  (GitHub Pages) │        │  (Render free)        │        │  Postgres   │
└─────────────────┘        └──────────┬───────────┘        └─────────────┘
                                      │                           │
                           ┌──────────▼──────────┐        ┌──────▼──────┐
                           │  GitHub Actions cron │        │  Supabase   │
                           │  (every 6 h)         │        │  Auth       │
                           └──────────────────────┘        └─────────────┘
                                      │
                           ┌──────────▼──────────┐
                           │  BeautifulSoup       │
                           │  scraper (AsuraScans │
                           │  + Demonic Scans)    │
                           └──────────┬───────────┘
                                      │ new chapter?
                           ┌──────────▼──────────┐
                           │  Telegram Bot API   │
                           │  (sends DM)         │
                           └─────────────────────┘
```

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 19 + TypeScript, Vite 8, React Router v7 |
| Auth (client) | `@supabase/supabase-js` — email/password with email verification |
| Backend | Python 3.12, FastAPI (async), SQLAlchemy 2 + asyncpg |
| Auth (server) | JWT validation via Supabase JWKS (RS256) |
| Migrations | Alembic |
| Scraping | httpx + BeautifulSoup4 + lxml (AsuraScans, Demonic Scans) |
| Notifications | Telegram Bot API (webhook → backend) |
| Cron | GitHub Actions, every 6h |

## Deployment

| Piece | Service | URL |
|---|---|---|
| Frontend | GitHub Pages | https://jadriang.github.io/manga-notif-web/ |
| Backend | Render (free web) | https://manga-notif-web.onrender.com |
| Cron | GitHub Actions | `.github/workflows/check-manga.yml` |
| DB + Auth | Supabase (free) | — |
| Telegram | Webhook → backend | — |

Render's free tier sleeps after ~15 min idle (~30–60s cold start). The cron warms it up before scraping. Health check: `GET /api/health` → `{"status":"ok"}`.

## How it works

1. **Sign-up** is allowlist-gated — only emails in the `allowed_emails` table can register via Supabase Auth.
2. **Chapter checks** run every 6 h via GitHub Actions. The cron hits `/api/cron/check` (bearer-token protected), which scrapes all tracked manga in two passes — read DB, release connection, scrape, reconnect, write diffs — to minimise DB connection time (Neon auto-suspend).
3. **Telegram linking** — user DMs the bot `/start`, which stores their `chat_id`. Subscriptions with `notify=true` + a linked `chat_id` receive a message when a new chapter is detected.

## Local development

```sh
# backend
cd backend
cp .env.example .env   # fill in Supabase + Telegram values
uvicorn app.main:app --reload

# frontend
cd frontend
cp .env.example .env   # fill in VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY, VITE_API_URL
npm install
npm run dev   # http://localhost:5173/manga-notif-web/
```

Full setup, secrets, and rollback steps → [DEPLOYMENT.md](DEPLOYMENT.md).
