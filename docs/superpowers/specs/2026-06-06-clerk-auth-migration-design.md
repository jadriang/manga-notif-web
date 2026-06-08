# Clerk Auth Migration — Design Spec

**Date:** 2026-06-06
**Author:** Adrian
**Status:** Draft — pending design review
**Type:** Migration / Breaking change

---

## 1. Overview

Migrate authentication from Supabase Auth to Clerk, and replace the email allowlist with an invite-code system. The Neon Postgres database stays — Supabase is currently used only for auth.

## 2. Goals

1. Remove all Supabase dependencies from frontend and backend.
2. Use Clerk for sign-up, sign-in (email/password **and Google OAuth**), email verification, password reset.
3. Gate access with multi-use invite codes (each with a configurable `max_uses` limit) regardless of sign-in method.
4. Zero downtime to the manga library and Telegram notifications (no scraper changes).

## 3. Non-goals

- No other social providers (GitHub, Apple, etc.) in this migration — Google + email/password only.
- No admin UI for invite codes — codes are inserted via SQL/seed script.
- No 2FA in this migration.
- No migration of existing Supabase users (start fresh).
- No changes to scrapers, cron, or Telegram integration.

## 4. Stakeholders

| Role | Owner |
|---|---|
| Spec author | Adrian |
| Design reviewer | Adrian |
| Implementer | Claude + Adrian |
| QA / UAT | Adrian |
| Deploy operator | Adrian |

## 5. Architecture

```
┌─────────────────┐   1. Sign in    ┌──────────────┐
│  React SPA      │ ──────────────▶ │  Clerk       │
│  (GitHub Pages) │ ◀────JWT─────── │  (hosted)    │
└────────┬────────┘                 └──────────────┘
         │ 2. Authenticated API
         │    request + Clerk JWT
         ▼
┌─────────────────┐  3. Validate    ┌──────────────┐
│  FastAPI        │ ───── JWT ────▶ │  Clerk JWKS  │
│  (Render)       │ ◀── public key ─│  endpoint    │
└────────┬────────┘                 └──────────────┘
         │ 4. Look up User by clerk_id
         │    or return 403 invite_required
         ▼
┌─────────────────┐
│  Neon Postgres  │
└─────────────────┘
```

## 6. Auth & Invite Flow

### 6.1 New user flow

1. User opens app → `<SignedOut>` triggers Clerk's `<SignUp>` component, which presents both **email/password** and **Continue with Google** options.
2. User registers via their chosen method:
   - **Email/password**: Clerk sends a verification email; user clicks the link.
   - **Google**: Clerk redirects to Google OAuth consent; on return the Google-verified email is trusted (no separate verification step).
3. After verification (email path) or OAuth callback (Google path), user is signed in (Clerk JWT in browser).
4. SPA hits `/api/me` → backend validates JWT → no `User` row found.
5. Backend returns `403 {"detail": "invite_required"}`.
6. SPA routes to `/redeem-invite` page.
7. User submits code → `POST /api/auth/redeem-invite {code}`.
8. Backend validates code, increments `used_count`, creates `User` row keyed on `clerk_id`.
9. SPA re-fetches `/api/me` → success → routes to dashboard.

The invite-code gate applies identically to both sign-in methods — Google users still need an invite code on first access.

### 6.2 Returning user flow

1. Clerk session restored from cookie/localStorage.
2. SPA hits `/api/me` with Clerk JWT.
3. Backend validates JWT, finds `User` by `clerk_id`, returns profile.

### 6.3 Sign-out

1. User clicks sign out → Clerk's `signOut()` clears session.
2. SPA redirects to `/login`.

## 7. Data Model Changes

### 7.1 New table: `invite_codes`

```sql
CREATE TABLE invite_codes (
    code        VARCHAR(64) PRIMARY KEY,
    description TEXT,                       -- internal label, e.g. "friend-batch-1"
    max_uses    INTEGER NOT NULL,
    used_count  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT used_count_le_max CHECK (used_count <= max_uses)
);
```

### 7.2 `users` table

- **Add** `clerk_id VARCHAR(64) UNIQUE NOT NULL` — Clerk user IDs look like `user_2abc123xyz`.
- **Keep** `id UUID PRIMARY KEY` — existing FKs (`subscriptions.user_id`, `manga.added_by`) continue to work; new rows get fresh UUIDs.
- **Change** `id` default to `uuid.uuid4` (currently has no default because Supabase `sub` was used).

### 7.3 Dropped table: `allowed_emails`

Drop in the same migration. No data preservation needed.

### 7.4 Data migration (existing rows)

Current production data state needs decision (see Open Questions §16). **Recommendation:** truncate `users` (cascades to `subscriptions`), keep the `manga` and `chapter_state` tables. The manga library is the valuable shared data; subscriptions are per-user and cheap to rebuild.

## 8. API Contracts

### 8.1 New endpoint

```
POST /api/auth/redeem-invite
Headers: Authorization: Bearer <clerk-jwt>
Body:    {"code": "string"}

Responses:
  200 {"id": "uuid", "email": "string", "clerk_id": "string"}
  400 {"detail": "invalid_code"}        — code does not exist
  400 {"detail": "code_exhausted"}      — used_count >= max_uses
  409 {"detail": "already_redeemed"}    — User row already exists for this clerk_id
  401 — JWT invalid/missing
  429 — rate limited (see §13.2)
```

### 8.2 Modified behavior: `/api/me` and other authenticated endpoints

When JWT is valid but no `User` row exists for the `clerk_id`, return:
```
403 {"detail": "invite_required"}
```
Frontend uses this exact `detail` string as a signal to route to invite redemption.

### 8.3 Removed endpoint

```
GET /api/auth/check-email   — DELETE (allowlist concept retired)
```

## 9. Environment Variables

### 9.1 Removed

| Var | Used by |
|---|---|
| `SUPABASE_URL` | backend |
| `SUPABASE_ANON_KEY` | backend |
| `SUPABASE_JWT_SECRET` | backend |
| `VITE_SUPABASE_URL` | frontend |
| `VITE_SUPABASE_ANON_KEY` | frontend |

### 9.2 Added

| Var | Value | Used by |
|---|---|---|
| `CLERK_JWKS_URL` | `https://<frontend-api-domain>/.well-known/jwks.json` | backend |
| `CLERK_ISSUER` | `https://<frontend-api-domain>` (for JWT `iss` claim verification) | backend |
| `VITE_CLERK_PUBLISHABLE_KEY` | `pk_test_...` or `pk_live_...` | frontend |

### 9.3 Unchanged

`DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, `CRON_SECRET`, `FRONTEND_URL`, `VITE_API_URL`, `VITE_TELEGRAM_BOT_USERNAME`.

## 10. Frontend Changes

| File | Change |
|---|---|
| `package.json` | Remove `@supabase/supabase-js`, add `@clerk/clerk-react` |
| `src/lib/supabase.ts` | **Delete** |
| `src/contexts/AuthContext.tsx` | **Delete** (use Clerk's `useAuth()`, `useUser()` directly) |
| `src/main.tsx` | Wrap `<App>` in `<ClerkProvider publishableKey={...}>` |
| `src/pages/LoginPage.tsx` | Replace custom form with `<SignIn routing="hash" />` + `<SignUp routing="hash" />` |
| `src/pages/RedeemInvitePage.tsx` | **New** — code input form, POSTs to `/api/auth/redeem-invite` |
| `src/lib/api.ts` | Get bearer token via Clerk's `useAuth().getToken()`; catch 403 `invite_required` → redirect to `/redeem-invite` |
| `src/App.tsx` | Replace `ProtectedRoute` with Clerk's `<SignedIn>` / `<SignedOut>`; add `/redeem-invite` route |
| `.env.example` | Swap vars per §9 |

## 11. Backend Changes

| File | Change |
|---|---|
| `requirements.txt` | No change (python-jose, httpx already present) |
| `app/config.py` | Remove 3 Supabase settings, add `clerk_jwks_url`, `clerk_issuer` |
| `app/auth.py` | Change JWKS URL; verify `iss` claim; look up User by `clerk_id` (not UUID `sub`); remove `AllowedEmail` check; return 403 `invite_required` if no User row |
| `app/models/tables.py` | Add `clerk_id` to `User`; remove `AllowedEmail` class; add `InviteCode` class |
| `app/api/routes/auth.py` | Replace `check-email` route with `redeem-invite` route |
| `alembic/versions/<new>.py` | Migration: add `invite_codes`, add `users.clerk_id`, drop `allowed_emails`, truncate `users` |
| `render.yaml` | Swap env var declarations per §9 |
| `seed.py` | Add helper to insert invite codes; remove allowed-email seeding |

## 12. Test Plan

### 12.1 Unit tests (backend)

- `tests/test_auth_clerk.py` — JWT validation: valid token, expired token, wrong issuer, malformed token, missing kid.
- `tests/test_redeem_invite.py` — code valid → 200 + User row; code invalid → 400; code exhausted → 400; already-redeemed → 409; transactional safety on concurrent redemption.
- `tests/test_get_current_user.py` — extend: existing flow returns `User`; missing User row returns 403 `invite_required`.

### 12.2 Integration tests

- Migration up + down round-trips cleanly (Alembic).
- `seed.py` inserts a known invite code.
- `/api/me` returns 403 with the literal string `invite_required` (frontend depends on this).

### 12.3 Manual QA matrix (§14.4)

## 13. Security

### 13.1 Threat model

| Threat | Mitigation |
|---|---|
| Brute-force invite codes | Rate limit `/api/auth/redeem-invite` (see 13.2); use 16+ char random codes |
| JWT replay after Clerk session revoked | Clerk JWTs are short-lived (default ~60s); accept the small window |
| Token from wrong Clerk instance | Verify `iss` claim against `CLERK_ISSUER` env var |
| Email spoof during sign-up | Clerk enforces email verification (or Google-verified email) before issuing JWT |
| Stolen Clerk publishable key | Publishable key is public by design; only secret key is sensitive (not used in this stack) |
| User signs up but never redeems an invite | Harmless — they sit at the invite screen, no `User` row created, no data access |
| Google OAuth credentials leak (Client ID / Secret) | Stored only in the Clerk dashboard, never in this repo; rotate via Google Cloud Console + Clerk |
| Account takeover via email/password + Google with same address | Clerk's default behavior links identities for the same verified email — single `clerk_id`, single `User` row; verify this in QA scenario 17 |

### 13.2 Rate limiting

`/api/auth/redeem-invite`: **5 requests per IP per minute**. Implementation: SlowAPI or simple in-memory rate limiter (Render free tier is single-instance, so in-memory is fine for now).

### 13.3 Invite code format

- Generated with `secrets.token_urlsafe(12)` → ~16 chars, URL-safe, ~96 bits entropy.
- Stored as plaintext (acceptable — they grant access, not act as passwords).

### 13.4 Secret rotation runbook

If Clerk publishable key leaks: it's public, no action.
If Clerk secret key leaks (currently unused, but if ever introduced): rotate in Clerk dashboard, update Render env var, redeploy.
If `DATABASE_URL` leaks: rotate in Neon dashboard, update Render, redeploy.

## 14. Quality Gates

Each gate must be signed off before proceeding to the next.

### 14.1 Gate A — Design review

- [ ] All §16 open questions resolved
- [ ] Stakeholder (Adrian) signs off on this doc
- [ ] No outstanding "TBD" markers

### 14.2 Gate B — Code review

- [ ] All changes match this spec (file list in §10–11)
- [ ] No `@supabase/*` imports remain (`rg @supabase frontend/src`)
- [ ] No `supabase` references in backend (`rg -i supabase backend/app`)
- [ ] No `allowed_emails` references in backend (`rg allowed_emails backend`)
- [ ] All new endpoints have unit tests
- [ ] Migration tested up + down locally

### 14.3 Gate C — Security review

- [ ] JWT `iss`, `aud`, `exp`, `nbf` claims all validated
- [ ] Rate limiting active on `/api/auth/redeem-invite`
- [ ] Invite codes use `secrets.token_urlsafe` (not `random`)
- [ ] No JWT or invite code logged at INFO or higher
- [ ] CORS still locked to `FRONTEND_URL` only
- [ ] `redeem-invite` endpoint uses a transaction (concurrent redemption safe)

### 14.4 Gate D — QA (functional test matrix)

Run against a staging Render deployment + Clerk dev instance.

| # | Scenario | Expected |
|---|---|---|
| 1 | Sign up new user with valid email | Clerk verification email arrives; clicking link signs user in |
| 2 | Try signing in before email verified | Clerk blocks, shows verification prompt |
| 3 | Signed in, no invite redeemed → visit `/` | Routes to `/redeem-invite` |
| 4 | Submit invalid invite code | Inline error "Invalid code" |
| 5 | Submit valid invite code | Routes to dashboard; subsequent loads skip invite step |
| 6 | Use a code with `max_uses=2` twice, then a 3rd user tries | 3rd user sees "Code exhausted" |
| 7 | Sign out, sign back in | No invite re-prompt (User row persists) |
| 8 | Hit `/api/me` with no Authorization header | 401 |
| 9 | Hit `/api/me` with expired token | 401 |
| 10 | Spam `/api/auth/redeem-invite` 10× in 30s | After 5, get 429 |
| 11 | Hard-refresh on `/redeem-invite` deep link | Page renders (SPA fallback works) |
| 12 | DM Telegram bot `/start` after redemption | `telegram_chat_id` saved to user row |
| 13 | Trigger cron manually | Scrapes + notifies as before |
| 14 | **Sign up via Continue with Google** | Google consent screen → returns signed in → routes to `/redeem-invite` |
| 15 | **Google sign-up: redeem invite** | Same flow as email path; `User` row created with Google email |
| 16 | **Sign out, sign back in via Google with the same account** | Lands on dashboard, no invite re-prompt |
| 17 | **Google and email sign-up with the same email** | Clerk merges to one identity (configured behavior); single User row in our DB |

### 14.5 Gate E — UAT (end-to-end user scenarios)

Adrian walks through, with at least 2 test accounts:

- [ ] **Scenario A — Email/password user**: register → verify email → redeem invite → add a manga → link Telegram → wait for cron → receive notification.
- [ ] **Scenario B — Google user**: click "Continue with Google" → consent → redeem invite → add a manga → link Telegram → receive notification.
- [ ] **Scenario C — Returning user**: sign out → close browser → reopen → sign in → still authenticated, no re-redemption needed.
- [ ] **Scenario D — Failed onboarding**: register → verify email → close browser without redeeming → return next day → still prompted for invite (state preserved).
- [ ] **Scenario E — Telegram still works**: verify webhook delivers `/start`, `/help`, link/unlink flow.

### 14.6 Gate F — Deployment

**Pre-deploy:**
- [ ] All gates A–E signed off
- [ ] Production Clerk instance created (separate from dev)
- [ ] Production `VITE_CLERK_PUBLISHABLE_KEY` set in GitHub Actions secrets
- [ ] Production `CLERK_JWKS_URL`, `CLERK_ISSUER` set in Render
- [ ] Supabase env vars removed from Render + GitHub Actions
- [ ] Backup taken of production DB (`pg_dump` from Neon)
- [ ] Announce maintenance window if applicable

**Deploy steps:**
1. Merge PR to `main`.
2. Render auto-deploys backend; Alembic runs migration (drops `allowed_emails`, truncates `users`, adds `invite_codes`).
3. GitHub Pages builds + deploys frontend.
4. Seed at least one invite code via `seed.py` or direct SQL.

**Post-deploy verification:**
- [ ] `curl https://manga-notif-web.onrender.com/api/health` → 200
- [ ] `curl /api/me` without auth → 401 (not 500)
- [ ] Adrian registers fresh account end-to-end → reaches dashboard
- [ ] First cron run after deploy succeeds (check GitHub Actions log)

### 14.7 Gate G — Rollback

If Gate F post-deploy verification fails:

1. **Render** → service → Manual Deploy → previous commit. Backend reverts.
2. **GitHub Pages** → re-run prior `gh-pages` workflow run from Actions tab. Frontend reverts.
3. **DB** → restore from `pg_dump` snapshot taken in Gate F pre-deploy. This restores `allowed_emails` and any prior `users` rows.
4. Restore Supabase env vars in Render + GitHub Actions secrets (keep them in a safe place during the migration window — do not delete from password manager until 7 days post-deploy).

## 15. Observability

- Log invite redemption attempts at INFO: `{"event": "invite_redeem", "result": "ok|invalid|exhausted|already_redeemed", "clerk_id": "..."}`. Never log the invite code itself.
- Log JWT validation failures at WARNING (already present in `app/auth.py`).
- After 7 days, manually review Render logs for anomalies (multiple `invalid` redemption attempts from same IP → consider adding IP to a blocklist).

## 16. Open Questions

1. **Existing production users**: confirm "truncate `users` + cascade subscriptions" is acceptable (loses all current subscriptions). Alternative: keep rows and manually map to Clerk IDs after each user re-registers (more work, preserves subs).
2. **Clerk Frontend API URL**: needs to be looked up after creating Clerk app — value of `CLERK_JWKS_URL` and `CLERK_ISSUER` depends on this.
3. **Rate limit on `/api/auth/redeem-invite`**: SlowAPI adds a dep; in-memory dict adds ~10 LOC. Decision: SlowAPI or hand-rolled?
4. **Initial invite codes**: how many, what `max_uses`? Suggested: one code with `max_uses=10` for the initial migration, more added later.
5. **Domain redirect URLs in Clerk**: Clerk requires whitelisting redirect URLs. Add both `http://localhost:5173/manga-notif-web/` (dev) and `https://jadriang.github.io/manga-notif-web/` (prod).

## 17. Sign-off

| Gate | Owner | Date | Signature |
|---|---|---|---|
| A — Design review | Adrian | | |
| B — Code review | Adrian | | |
| C — Security review | Adrian | | |
| D — QA | Adrian | | |
| E — UAT | Adrian | | |
| F — Deployment | Adrian | | |
| G — Rollback (if invoked) | Adrian | | |
