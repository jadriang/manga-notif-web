# Deployment

Free-tier stack:

| Piece | Service |
|---|---|
| Frontend | GitHub Pages (`https://<owner>.github.io/manga-notif-web/`) |
| Backend  | Render free web service (`https://<service>.onrender.com`) |
| Cron     | GitHub Actions (`.github/workflows/check-manga.yml`, every 6h) |
| DB        | Neon Postgres |
| Auth      | Clerk (free tier) |
| Telegram | Webhook → backend |

Render's free tier sleeps after ~15 min idle (~30–60s cold start). The cron warms it before scraping; Telegram retries webhook deliveries for ~24h, so cold starts don't lose updates.

---

## 0. Clerk setup

One-time setup in the [Clerk dashboard](https://dashboard.clerk.com):

1. Create a new Clerk application.
2. **Sign-in methods**: enable Email + password (require email verification) AND Google OAuth.
3. **For production**: in **SSO Connections → Google**, switch to custom credentials with your own Google Cloud OAuth Client ID + Secret (replaces Clerk's shared dev credentials).
4. **Redirect URLs** to whitelist: `http://localhost:5173/manga-notif-web/` (dev) and `https://<owner>.github.io/manga-notif-web/` (prod).
5. Create a **JWT template** named `default` with custom claims:
   ```json
   {
     "email": "{{user.primary_email_address}}"
   }
   ```
6. Note these values for later:
   - **Publishable key** (`pk_test_...` or `pk_live_...`) → goes in `VITE_CLERK_PUBLISHABLE_KEY`
   - **Frontend API URL** (e.g. `https://xxx.clerk.accounts.dev`) → derive `CLERK_ISSUER` and `CLERK_JWKS_URL`

## 1. Backend on Render

1. Push this branch to GitHub.
2. In Render → **New** → **Blueprint**, point at this repo. It picks up `render.yaml`.
3. Set the secrets in the Render dashboard for the `manga-notif-api` service:

   | Var | Value |
   |---|---|
   | `DATABASE_URL` | Neon connection string, `postgresql+asyncpg://user:pass@host/db?ssl=require` |
   | `CLERK_JWKS_URL` | `<clerk-frontend-api>/.well-known/jwks.json` |
   | `CLERK_ISSUER` | `<clerk-frontend-api>` |
   | `TELEGRAM_BOT_TOKEN` | from BotFather |
   | `CRON_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
   | `FRONTEND_URL` | `https://<owner>.github.io` (origin only — no trailing slash, no path) |

4. First deploy runs `pip install` and `alembic upgrade head`. Watch the logs until status is **Live**.
5. Sanity check: `curl https://<service>.onrender.com/api/health` → `{"status":"ok"}`.

## 2. Telegram webhook (one-time)

After the Render service is Live:

```sh
curl -F "url=https://<service>.onrender.com/api/telegram/webhook" \
  https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook
curl https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo
```

Re-run `setWebhook` if the Render service URL ever changes.

## 3. Frontend on GitHub Pages

1. **Repo → Settings → Pages**: source = **GitHub Actions**.
2. **Repo → Settings → Secrets and variables → Actions** — add:

   | Secret | Value |
   |---|---|
   | `VITE_CLERK_PUBLISHABLE_KEY` | from Clerk dashboard |
   | `VITE_API_URL` | `https://<service>.onrender.com` |
   | `VITE_TELEGRAM_BOT_USERNAME` | bot username without `@` |

3. Push to `main`. The `Deploy Frontend to GitHub Pages` workflow builds `frontend/`, copies `index.html` → `404.html` for SPA deep-link fallback, and publishes.
4. Site lives at `https://<owner>.github.io/manga-notif-web/`. The Vite `base` and `BrowserRouter` `basename` are wired to that path.

## 4. Cron (already wired)

`.github/workflows/check-manga.yml` runs every 6h. Required repo secrets:

| Secret | Value |
|---|---|
| `API_URL` | `https://<service>.onrender.com` |
| `CRON_SECRET` | same value as in Render |

Trigger manually any time via **Actions → Check Manga Updates → Run workflow**.

## 5a. First-time invite code seeding

After the first successful deploy, generate at least one invite code so users can register:

```sh
# Locally with prod DATABASE_URL set, or via a Render shell session:
python backend/seed.py
```

The seed script prints `IMPORTANT: save this invite code -> <token>`. Share that token with whoever should be able to sign up.

## 5. End-to-end verification

- `curl https://<service>.onrender.com/api/health` → 200.
- `curl -X POST https://<service>.onrender.com/api/cron/check` → 401 (auth enforced).
- `curl -X POST -H "Authorization: Bearer $CRON_SECRET" https://<service>.onrender.com/api/cron/check` → 200.
- Open `https://<owner>.github.io/manga-notif-web/`, sign in, hit Network tab — `/api/me` should return 200.
- Hard-refresh a deep link (e.g. `/manga-notif-web/settings`) — should render, not 404 (proves SPA fallback).
- DM the bot `/start` — `getWebhookInfo` shows `pending_update_count: 0` and a row appears in your users table.

## 6. Rollback

- Render → service → **Manual Deploy** → roll back to a previous commit.
- Disable the GitHub `check-manga` workflow to halt scrapes without taking the API down.
- Delete the Pages deployment from the **Environments** tab to take the frontend down.

## 7. Local development

Unchanged: `cd backend && uvicorn app.main:app --reload` and `cd frontend && npm run dev`. Vite's `base: '/manga-notif-web/'` means the dev server now serves the app at `http://localhost:5173/manga-notif-web/`.
