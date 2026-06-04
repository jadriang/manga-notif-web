# Manga Notifier

Track manga series and get a Telegram message when a new chapter drops.

- **Frontend** — React + Vite SPA (sign in, manage tracked series)
- **Backend** — FastAPI API (auth, tracking, scraping, Telegram webhook)
- **Cron** — GitHub Actions checks for new chapters every 6h

## Deployment

| Piece     | Service                | URL                                          |
| --------- | ---------------------- | -------------------------------------------- |
| Frontend  | GitHub Pages           | https://jadriang.github.io/manga-notif-web/  |
| Backend   | Render (free web)      | https://manga-notif-web.onrender.com         |
| Cron      | GitHub Actions         | `.github/workflows/check-manga.yml` (every 6h) |
| DB + Auth | Supabase (free)        | —                                            |
| Telegram  | Webhook → backend      | —                                            |

Render's free tier sleeps after ~15 min idle (~30–60s cold start); the cron warms it before scraping. Health check: https://manga-notif-web.onrender.com/api/health → `{"status":"ok"}`.

Full setup, secrets, and rollback steps are in [DEPLOYMENT.md](DEPLOYMENT.md).

## Local development

```sh
# backend
cd backend && uvicorn app.main:app --reload

# frontend
cd frontend && npm run dev   # http://localhost:5173/manga-notif-web/
```
