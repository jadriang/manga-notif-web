# Clerk Auth Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Supabase Auth with Clerk (email/password + Google OAuth) and the email allowlist with invite codes.

**Architecture:** Clerk hosts auth (sign-up, sign-in, email verification, Google OAuth, password reset) via pre-built React components. FastAPI validates Clerk JWTs against Clerk's JWKS endpoint and gates first-time access behind a multi-use invite code stored in a new `invite_codes` table. Neon Postgres stays.

**Tech Stack:** React 19 + Vite 8, `@clerk/clerk-react`, FastAPI, SQLAlchemy 2 + asyncpg, Alembic, python-jose, httpx, Neon Postgres.

**Spec reference:** [`docs/superpowers/specs/2026-06-06-clerk-auth-migration-design.md`](../specs/2026-06-06-clerk-auth-migration-design.md)

---

## Prerequisites (manual, before running tasks)

Done by Adrian in the Clerk dashboard:

1. Create a Clerk application (dev instance).
2. **Sign-in methods enabled** (already configured):
   - **Email + password** with email verification required
   - **Google OAuth** (uses Clerk's shared dev credentials in dev; production needs your own Google Cloud OAuth Client ID + Secret added in the Clerk dashboard)
3. Whitelist redirect URLs:
   - `http://localhost:5173/manga-notif-web/`
   - `https://jadriang.github.io/manga-notif-web/`
4. **Create a JWT template named `default`** with custom claims:
   ```json
   {
     "email": "{{user.primary_email_address}}"
   }
   ```
   This is required because Clerk session tokens don't include `email` by default; `app/auth.py` reads it from the payload. The template returns the user's primary verified email regardless of whether they signed in with password or Google.
5. Note these values for env vars:
   - **Publishable key** (`pk_test_...`) → `VITE_CLERK_PUBLISHABLE_KEY`
   - **Frontend API URL** (e.g. `https://xxx.clerk.accounts.dev`) → use as `CLERK_ISSUER` and derive `CLERK_JWKS_URL = <frontend-api>/.well-known/jwks.json`
6. **For production only**: In Clerk dashboard → SSO Connections → Google → switch to custom credentials with a Google Cloud OAuth Client ID + Secret you own. Add the production redirect URL (`https://<frontend-api>.clerk.accounts.dev/v1/oauth_callback`) to the Google Cloud OAuth consent screen's authorized redirect URIs.

---

## Decisions locked from spec open questions

- **Existing users**: truncate `users` (cascades to `subscriptions`). Manga library + chapter state preserved.
- **Rate limiter**: hand-rolled in-memory dict (5 req/IP/min). No new dependency.
- **Initial invite codes**: one code with `max_uses=10` seeded via `seed.py`. Adrian generates more later by hand.
- **Clerk URLs**: provided by Adrian as env vars before deploy.

---

## File-Touch Map

### Backend

| File | Create / Modify / Delete | Purpose |
|---|---|---|
| `backend/app/models/tables.py` | Modify | Add `clerk_id` to `User`, remove `AllowedEmail`, add `InviteCode` |
| `backend/app/config.py` | Modify | Drop Supabase vars, add Clerk vars |
| `backend/app/auth.py` | Modify | Validate Clerk JWTs; lookup by `clerk_id`; return `invite_required` 403 |
| `backend/app/api/routes/auth.py` | Modify | Remove `/check-email`; add `/redeem-invite` |
| `backend/app/rate_limit.py` | Create | In-memory IP rate limiter |
| `backend/alembic/versions/<new>_clerk_auth_migration.py` | Create | DB migration |
| `backend/seed.py` | Modify | Add `seed_invite_code(code, max_uses)` helper |
| `backend/.env.example` | Modify | Swap vars |
| `backend/tests/conftest.py` | Modify | Helper to build Clerk-style JWT payloads |
| `backend/tests/test_get_current_user.py` | Modify | Update to new flow (clerk_id lookup, invite_required) |
| `backend/tests/test_auth_routes.py` | Modify | Remove check-email tests, add redeem-invite tests |
| `backend/tests/test_rate_limit.py` | Create | Rate limiter unit tests |

### Frontend

| File | Create / Modify / Delete | Purpose |
|---|---|---|
| `frontend/package.json` | Modify | Remove `@supabase/supabase-js`, add `@clerk/clerk-react` |
| `frontend/src/lib/supabase.ts` | Delete | |
| `frontend/src/contexts/AuthContext.tsx` | Delete | Replaced by Clerk hooks |
| `frontend/src/main.tsx` | Modify | Wrap in `<ClerkProvider>` |
| `frontend/src/lib/api.ts` | Modify | Get token from Clerk; handle `invite_required` |
| `frontend/src/lib/auth-token.ts` | Create | Token getter callback registered by `App.tsx` |
| `frontend/src/pages/LoginPage.tsx` | Modify | Replace custom form with Clerk `<SignIn>`/`<SignUp>` |
| `frontend/src/pages/RedeemInvitePage.tsx` | Create | Invite code entry |
| `frontend/src/App.tsx` | Modify | Use Clerk's `<SignedIn>`/`<SignedOut>`; add `/redeem-invite` route |
| `frontend/src/pages/DashboardPage.tsx` | Modify | Use `useUser()` for email; `useClerk().signOut()` for sign-out (if these are referenced today) |
| `frontend/src/pages/SettingsPage.tsx` | Modify | Same as above if referenced today |
| `frontend/src/vite-env.d.ts` | Create if missing | Type `VITE_CLERK_PUBLISHABLE_KEY` |
| `frontend/.env.example` | Modify | Swap vars |

### Infra / Docs

| File | Modify | Purpose |
|---|---|---|
| `render.yaml` | Modify | Swap env var declarations |
| `README.md` | Modify | Update stack table + flow |
| `DEPLOYMENT.md` | Modify | Swap secrets + add Clerk setup step |

---

## Task 1: Backend — Update DB models (add `InviteCode`, modify `User`, remove `AllowedEmail`)

**Files:**
- Modify: `backend/app/models/tables.py`

- [ ] **Step 1: Replace `tables.py` contents**

Open `backend/app/models/tables.py` and replace the entire file with:

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clerk_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    telegram_link_token: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Manga(Base):
    __tablename__ = "manga"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    asura_slug: Mapped[Optional[str]] = mapped_column(String(500))
    demonic_slug: Mapped[Optional[str]] = mapped_column(String(500))
    cover_url: Mapped[Optional[str]] = mapped_column(Text)
    added_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="manga", cascade="all, delete-orphan")
    chapter_states: Mapped[list[ChapterState]] = relationship(back_populates="manga", cascade="all, delete-orphan")


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "manga_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    manga_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("manga.id"), nullable=False)
    notify: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="subscriptions")
    manga: Mapped[Manga] = relationship(back_populates="subscriptions")


class ChapterState(Base):
    __tablename__ = "chapter_state"
    __table_args__ = (UniqueConstraint("manga_id", "site"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    manga_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("manga.id"), nullable=False)
    site: Mapped[str] = mapped_column(String(20), nullable=False)
    latest_chapter: Mapped[str] = mapped_column(String(20), nullable=False)
    chapter_url: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    manga: Mapped[Manga] = relationship(back_populates="chapter_states")


class InviteCode(Base):
    __tablename__ = "invite_codes"
    __table_args__ = (CheckConstraint("used_count <= max_uses", name="used_count_le_max"),)

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

Key differences from before: `User.id` now has `default=uuid.uuid4`; added `User.clerk_id`; removed `AllowedEmail`; added `InviteCode`.

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/tables.py
git commit -m "feat(models): add InviteCode and clerk_id, drop AllowedEmail"
```

---

## Task 2: Backend — Alembic migration

**Files:**
- Create: `backend/alembic/versions/a1b2c3d4e5f6_clerk_auth_migration.py`

- [ ] **Step 1: Generate revision file via Alembic**

```bash
cd backend
alembic revision -m "clerk auth migration"
```

This creates a new file in `backend/alembic/versions/`. Note the actual filename (the revision ID is auto-generated).

- [ ] **Step 2: Find the down_revision**

Run:

```bash
ls backend/alembic/versions/*.py
```

The previous head is `c192f2cc1ef6_add_allowed_emails.py` (revision id `c192f2cc1ef6`). Confirm by checking the `down_revision` of any existing file or by running `alembic heads`.

- [ ] **Step 3: Fill in the migration body**

Replace the body of the new revision file (keep its auto-generated revision id and `down_revision = 'c192f2cc1ef6'`) with:

```python
"""clerk auth migration

Revision ID: <KEEP AUTO-GENERATED>
Revises: c192f2cc1ef6
Create Date: <KEEP AUTO-GENERATED>

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '<KEEP AUTO-GENERATED>'
down_revision: Union[str, None] = 'c192f2cc1ef6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. invite_codes
    op.create_table(
        'invite_codes',
        sa.Column('code', sa.String(length=64), primary_key=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('max_uses', sa.Integer(), nullable=False),
        sa.Column('used_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('used_count <= max_uses', name='used_count_le_max'),
    )

    # 2. Truncate users (cascades to subscriptions). Keep manga + chapter_state.
    op.execute('TRUNCATE TABLE users CASCADE')

    # 3. users.clerk_id
    op.add_column('users', sa.Column('clerk_id', sa.String(length=64), nullable=False))
    op.create_unique_constraint('uq_users_clerk_id', 'users', ['clerk_id'])

    # 4. Drop allowed_emails
    op.drop_table('allowed_emails')


def downgrade() -> None:
    op.create_table(
        'allowed_emails',
        sa.Column('email', sa.String(length=320), primary_key=True),
    )
    op.drop_constraint('uq_users_clerk_id', 'users', type_='unique')
    op.drop_column('users', 'clerk_id')
    op.drop_table('invite_codes')
```

- [ ] **Step 4: Test the migration locally**

Note: This requires a working `DATABASE_URL` in `backend/.env`. **This is destructive** — only run against a local/dev DB or after backing up production:

```bash
cd backend
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

Expected: All three commands succeed without errors. After the final `upgrade head`, you can verify with:

```bash
psql "$DATABASE_URL" -c "\d invite_codes"
psql "$DATABASE_URL" -c "\d users"   # should show clerk_id column
psql "$DATABASE_URL" -c "\d allowed_emails"   # should error (does not exist)
```

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(db): clerk_id, invite_codes, drop allowed_emails"
```

---

## Task 3: Backend — Config changes

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Update `config.py`**

Replace `backend/app/config.py` with:

```python
from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Clerk
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""

    # Database
    database_url: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    # Cron secret (protects /api/cron/check)
    cron_secret: str = ""

    # CORS
    frontend_url: str = "http://localhost:5173"

    model_config = {"env_file": ".env"}


settings = Settings()
```

- [ ] **Step 2: Update `.env.example`**

Replace `backend/.env.example` with:

```sh
# Clerk
CLERK_JWKS_URL=https://<frontend-api>.clerk.accounts.dev/.well-known/jwks.json
CLERK_ISSUER=https://<frontend-api>.clerk.accounts.dev

# Database (Neon Postgres)
DATABASE_URL=postgresql+asyncpg://user:pass@host/db?ssl=require

# Telegram
TELEGRAM_BOT_TOKEN=

# Cron
CRON_SECRET=

# CORS
FRONTEND_URL=http://localhost:5173
```

- [ ] **Step 3: Update your local `backend/.env`**

Edit `backend/.env` to remove the three `SUPABASE_*` lines and add `CLERK_JWKS_URL` and `CLERK_ISSUER` from the Prerequisites section.

- [ ] **Step 4: Verify config loads**

```bash
cd backend
python -c "from app.config import settings; print(settings.clerk_jwks_url, settings.clerk_issuer)"
```

Expected: prints your two Clerk URLs.

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/.env.example
git commit -m "feat(config): swap Supabase env vars for Clerk"
```

---

## Task 4: Backend — Rate limiter module + tests

**Files:**
- Create: `backend/app/rate_limit.py`
- Create: `backend/tests/test_rate_limit.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_rate_limit.py`:

```python
import pytest
from app.rate_limit import RateLimiter


def test_allows_under_limit():
    rl = RateLimiter(max_attempts=3, window_seconds=60)
    assert rl.check("1.1.1.1") is True
    assert rl.check("1.1.1.1") is True
    assert rl.check("1.1.1.1") is True


def test_blocks_at_limit():
    rl = RateLimiter(max_attempts=3, window_seconds=60)
    for _ in range(3):
        rl.check("1.1.1.1")
    assert rl.check("1.1.1.1") is False


def test_separate_ips_tracked_separately():
    rl = RateLimiter(max_attempts=2, window_seconds=60)
    assert rl.check("1.1.1.1") is True
    assert rl.check("1.1.1.1") is True
    assert rl.check("2.2.2.2") is True


def test_window_expires(monkeypatch):
    fake_time = [1000.0]

    def fake_monotonic():
        return fake_time[0]

    monkeypatch.setattr("app.rate_limit.monotonic", fake_monotonic)
    rl = RateLimiter(max_attempts=2, window_seconds=60)
    rl.check("1.1.1.1")
    rl.check("1.1.1.1")
    assert rl.check("1.1.1.1") is False
    fake_time[0] += 61
    assert rl.check("1.1.1.1") is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
.venv/bin/pytest tests/test_rate_limit.py -v
```

Expected: ImportError — `app.rate_limit` does not exist.

- [ ] **Step 3: Implement the rate limiter**

Create `backend/app/rate_limit.py`:

```python
from __future__ import annotations

from collections import defaultdict
from time import monotonic


class RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._attempts: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> bool:
        """Record an attempt. Returns True if allowed, False if over limit."""
        now = monotonic()
        cutoff = now - self.window
        self._attempts[key] = [t for t in self._attempts[key] if t > cutoff]
        if len(self._attempts[key]) >= self.max_attempts:
            return False
        self._attempts[key].append(now)
        return True


invite_redeem_limiter = RateLimiter(max_attempts=5, window_seconds=60)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
.venv/bin/pytest tests/test_rate_limit.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/rate_limit.py backend/tests/test_rate_limit.py
git commit -m "feat(rate_limit): add in-memory IP rate limiter"
```

---

## Task 5: Backend — Rewrite `app/auth.py` for Clerk

**Files:**
- Modify: `backend/app/auth.py`
- Modify: `backend/tests/test_get_current_user.py`

- [ ] **Step 1: Rewrite the tests first**

Replace `backend/tests/test_get_current_user.py` with:

```python
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.models.tables import User


def _make_credentials(token="fake.jwt.token"):
    creds = MagicMock()
    creds.credentials = token
    return creds


def _make_db_session(existing_user=None):
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing_user
    session.execute.return_value = result
    return session


FAKE_PAYLOAD = {
    "sub": "user_2abc123xyz",
    "email": "newuser@example.com",
    "iss": "https://example.clerk.accounts.dev",
}


@pytest.mark.anyio
async def test_get_current_user_existing_user():
    """Existing User is returned by clerk_id lookup."""
    existing = MagicMock(spec=User)
    existing.clerk_id = "user_2abc123xyz"
    session = _make_db_session(existing_user=existing)

    with patch("app.auth._get_jwks", return_value=[]), \
         patch("app.auth.jwt.decode", return_value=FAKE_PAYLOAD):
        user = await get_current_user(
            credentials=_make_credentials(),
            db=session,
        )

    assert user is existing


@pytest.mark.anyio
async def test_get_current_user_no_row_returns_invite_required():
    """Authenticated but no User row -> 403 invite_required."""
    session = _make_db_session(existing_user=None)

    with patch("app.auth._get_jwks", return_value=[]), \
         patch("app.auth.jwt.decode", return_value=FAKE_PAYLOAD):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                credentials=_make_credentials(),
                db=session,
            )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "invite_required"


@pytest.mark.anyio
async def test_get_current_user_invalid_jwt():
    from jose import JWTError
    session = _make_db_session()

    with patch("app.auth._get_jwks", return_value=[]), \
         patch("app.auth.jwt.decode", side_effect=JWTError("bad sig")):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                credentials=_make_credentials(),
                db=session,
            )

    assert exc_info.value.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
.venv/bin/pytest tests/test_get_current_user.py -v
```

Expected: tests fail with import/attribute errors (current `app/auth.py` still uses `AllowedEmail`).

- [ ] **Step 3: Rewrite `app/auth.py`**

Replace `backend/app/auth.py` with:

```python
"""Clerk JWT auth dependency for FastAPI."""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwk, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.tables import User

logger = logging.getLogger(__name__)
security = HTTPBearer()

_jwks_cache: Optional[list] = None


async def _get_jwks() -> list:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    async with httpx.AsyncClient() as client:
        resp = await client.get(settings.clerk_jwks_url, timeout=10)
        resp.raise_for_status()
    _jwks_cache = resp.json().get("keys", [])
    return _jwks_cache


def _decode_with_jwks(token: str, keys: list) -> dict:
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")
    for key_data in keys:
        if kid and key_data.get("kid") != kid:
            continue
        public_key = jwk.construct(key_data)
        try:
            return jwt.decode(
                token,
                public_key,
                algorithms=[unverified_header.get("alg", "RS256")],
                issuer=settings.clerk_issuer,
                options={"verify_aud": False},  # Clerk session tokens don't set aud
            )
        except JWTError:
            continue
    raise JWTError("No matching key found in JWKS")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        keys = await _get_jwks()
        payload = _decode_with_jwks(token, keys)
    except JWTError as e:
        logger.warning("JWT decode failed: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    clerk_id = payload.get("sub")
    if not clerk_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.clerk_id == clerk_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invite_required")

    return user
```

Notes:
- Lookup is now by `clerk_id`, not UUID.
- No allowlist check — invite redemption (Task 6) is what creates the row.
- `_decode_with_jwks` enforces issuer; no `aud` check because Clerk session tokens don't set it.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
.venv/bin/pytest tests/test_get_current_user.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth.py backend/tests/test_get_current_user.py
git commit -m "feat(auth): validate Clerk JWTs and gate access behind invite_required"
```

---

## Task 6: Backend — Replace `/check-email` with `/redeem-invite`

**Files:**
- Modify: `backend/app/api/routes/auth.py`
- Modify: `backend/tests/test_auth_routes.py`

- [ ] **Step 1: Write the failing tests**

Replace `backend/tests/test_auth_routes.py` with:

```python
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.main import app
from app.models.tables import InviteCode, User
from app.rate_limit import invite_redeem_limiter


CLERK_PAYLOAD = {"sub": "user_2abc123", "email": "new@example.com"}
AUTH_HEADERS = {"Authorization": "Bearer fake-token-content-ignored-by-patch"}


def _make_db_session(invite=None, existing_user=None):
    session = AsyncMock(spec=AsyncSession)
    call_count = 0

    async def execute_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar_one_or_none.return_value = invite
        else:
            result.scalar_one_or_none.return_value = existing_user
        return result

    session.execute.side_effect = execute_side_effect
    return session


def _override_db(session):
    async def _get():
        yield session
    app.dependency_overrides[get_db] = _get


def _reset():
    app.dependency_overrides.clear()
    invite_redeem_limiter._attempts.clear()


@pytest.mark.anyio
async def test_redeem_invite_success(client):
    invite = InviteCode(code="GOODCODE", max_uses=5, used_count=0)
    session = _make_db_session(invite=invite, existing_user=None)
    _override_db(session)

    try:
        with patch("app.api.routes.auth._verify_clerk_token", return_value=CLERK_PAYLOAD):
            resp = await client.post("/api/auth/redeem-invite", json={"code": "GOODCODE"}, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert body["clerk_id"] == "user_2abc123"
        assert body["email"] == "new@example.com"
        assert invite.used_count == 1
        session.add.assert_called_once()
        session.commit.assert_called_once()
    finally:
        _reset()


@pytest.mark.anyio
async def test_redeem_invite_invalid_code(client):
    session = _make_db_session(invite=None)
    _override_db(session)

    try:
        with patch("app.api.routes.auth._verify_clerk_token", return_value=CLERK_PAYLOAD):
            resp = await client.post("/api/auth/redeem-invite", json={"code": "BADCODE"}, headers=AUTH_HEADERS)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "invalid_code"
    finally:
        _reset()


@pytest.mark.anyio
async def test_redeem_invite_code_exhausted(client):
    invite = InviteCode(code="USED", max_uses=2, used_count=2)
    session = _make_db_session(invite=invite, existing_user=None)
    _override_db(session)

    try:
        with patch("app.api.routes.auth._verify_clerk_token", return_value=CLERK_PAYLOAD):
            resp = await client.post("/api/auth/redeem-invite", json={"code": "USED"}, headers=AUTH_HEADERS)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "code_exhausted"
    finally:
        _reset()


@pytest.mark.anyio
async def test_redeem_invite_already_redeemed(client):
    invite = InviteCode(code="GOOD", max_uses=5, used_count=0)
    existing_user = MagicMock(spec=User)
    session = _make_db_session(invite=invite, existing_user=existing_user)
    _override_db(session)

    try:
        with patch("app.api.routes.auth._verify_clerk_token", return_value=CLERK_PAYLOAD):
            resp = await client.post("/api/auth/redeem-invite", json={"code": "GOOD"}, headers=AUTH_HEADERS)
        assert resp.status_code == 409
        assert resp.json()["detail"] == "already_redeemed"
    finally:
        _reset()


@pytest.mark.anyio
async def test_redeem_invite_rate_limited(client):
    session = _make_db_session(invite=None)
    _override_db(session)

    try:
        with patch("app.api.routes.auth._verify_clerk_token", return_value=CLERK_PAYLOAD):
            for _ in range(5):
                await client.post("/api/auth/redeem-invite", json={"code": "X"}, headers=AUTH_HEADERS)
            resp = await client.post("/api/auth/redeem-invite", json={"code": "X"}, headers=AUTH_HEADERS)
        assert resp.status_code == 429
    finally:
        _reset()


@pytest.mark.anyio
async def test_redeem_invite_unauthenticated(client):
    session = _make_db_session()
    _override_db(session)

    try:
        # No Authorization header — FastAPI's HTTPBearer dependency rejects with 403
        resp = await client.post("/api/auth/redeem-invite", json={"code": "X"})
        assert resp.status_code == 403
    finally:
        _reset()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
.venv/bin/pytest tests/test_auth_routes.py -v
```

Expected: fails (route doesn't exist yet).

- [ ] **Step 3: Rewrite `app/api/routes/auth.py`**

Replace `backend/app/api/routes/auth.py` with:

```python
"""Auth routes: invite redemption."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import _decode_with_jwks, _get_jwks
from app.database import get_db
from app.models.tables import InviteCode, User
from app.rate_limit import invite_redeem_limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()


class RedeemInviteBody(BaseModel):
    code: str


async def _verify_clerk_token(credentials: HTTPAuthorizationCredentials) -> dict:
    """Validate Clerk JWT and return payload. Raises 401 on failure."""
    try:
        keys = await _get_jwks()
        return _decode_with_jwks(credentials.credentials, keys)
    except JWTError as e:
        logger.warning("JWT decode failed: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


@router.post("/redeem-invite")
async def redeem_invite(
    body: RedeemInviteBody,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    if not invite_redeem_limiter.check(client_ip):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate_limited")

    payload = await _verify_clerk_token(credentials)
    clerk_id = payload.get("sub")
    email = payload.get("email", "")
    if not clerk_id or not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    # Look up the invite code
    result = await db.execute(select(InviteCode).where(InviteCode.code == body.code))
    invite = result.scalar_one_or_none()

    logged_result = "ok"
    try:
        if invite is None:
            logged_result = "invalid"
            raise HTTPException(status_code=400, detail="invalid_code")
        if invite.used_count >= invite.max_uses:
            logged_result = "exhausted"
            raise HTTPException(status_code=400, detail="code_exhausted")

        # Check User row doesn't already exist
        existing = await db.execute(select(User).where(User.clerk_id == clerk_id))
        if existing.scalar_one_or_none() is not None:
            logged_result = "already_redeemed"
            raise HTTPException(status_code=409, detail="already_redeemed")

        # Create User row and increment invite usage in one transaction
        user = User(clerk_id=clerk_id, email=email.lower())
        db.add(user)
        invite.used_count += 1
        await db.commit()
        await db.refresh(user)

        return {"id": str(user.id), "email": user.email, "clerk_id": user.clerk_id}
    finally:
        logger.info(
            "invite_redeem result=%s clerk_id=%s",
            logged_result,
            clerk_id,
        )
```

Notes:
- Rate limit check is performed *before* JWT validation so unauthenticated abuse is also throttled.
- `_verify_clerk_token` is a module-level function so tests can patch it.
- Reuses `_decode_with_jwks` and `_get_jwks` from `app.auth` — DRY.
- Code itself is never logged.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
.venv/bin/pytest tests/test_auth_routes.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/auth.py backend/tests/test_auth_routes.py
git commit -m "feat(auth): add /api/auth/redeem-invite with rate limiting"
```

---

## Task 7: Backend — Update seed.py for invite codes

**Files:**
- Modify: `backend/seed.py`

- [ ] **Step 1: Append an invite code seeding function**

Add to the bottom of `backend/seed.py`, before the `if __name__ == "__main__":` block:

```python
async def seed_invite_code(code: str, max_uses: int, description: str = "") -> None:
    """Insert (or skip if exists) a single invite code."""
    from app.models.tables import InviteCode

    async with async_session() as db:
        result = await db.execute(select(InviteCode).where(InviteCode.code == code))
        if result.scalar_one_or_none():
            print(f"  Skipping invite code {code} (already exists)")
            return
        db.add(InviteCode(code=code, max_uses=max_uses, description=description))
        await db.commit()
        print(f"  ✓ invite code {code} (max_uses={max_uses})")
```

- [ ] **Step 2: Modify the main block**

Replace the existing:

```python
if __name__ == "__main__":
    asyncio.run(seed())
```

With:

```python
async def main():
    import secrets
    await seed()
    # Initial invite code — token_urlsafe(12) → ~16 chars, ~96 bits entropy
    initial_code = secrets.token_urlsafe(12)
    await seed_invite_code(initial_code, max_uses=10, description="initial migration")
    print(f"\nIMPORTANT: save this invite code -> {initial_code}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Commit**

```bash
git add backend/seed.py
git commit -m "feat(seed): add invite code seeding"
```

---

## Task 8: Backend — Update render.yaml

**Files:**
- Modify: `render.yaml`

- [ ] **Step 1: Replace env var declarations**

Replace `render.yaml` with:

```yaml
services:
  - type: web
    name: manga-notif-api
    runtime: python
    plan: free
    region: oregon
    branch: main
    rootDir: backend
    autoDeploy: true
    healthCheckPath: /api/health
    buildCommand: pip install -r requirements.txt && alembic upgrade head
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: PYTHON_VERSION
        value: "3.12"
      - key: DATABASE_URL
        sync: false
      - key: CLERK_JWKS_URL
        sync: false
      - key: CLERK_ISSUER
        sync: false
      - key: TELEGRAM_BOT_TOKEN
        sync: false
      - key: CRON_SECRET
        sync: false
      - key: FRONTEND_URL
        sync: false
```

- [ ] **Step 2: Run the full backend test suite**

```bash
cd backend
.venv/bin/pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add render.yaml
git commit -m "chore(render): swap Supabase env vars for Clerk"
```

---

## Task 9: Frontend — Swap Supabase SDK for Clerk SDK

**Files:**
- Modify: `frontend/package.json`
- Delete: `frontend/src/lib/supabase.ts`
- Delete: `frontend/src/contexts/AuthContext.tsx`

- [ ] **Step 1: Install Clerk, uninstall Supabase**

```bash
cd frontend
npm uninstall @supabase/supabase-js
npm install @clerk/clerk-react
```

- [ ] **Step 2: Delete the two Supabase-coupled files**

```bash
rm frontend/src/lib/supabase.ts
rm frontend/src/contexts/AuthContext.tsx
```

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/lib frontend/src/contexts
git commit -m "chore(frontend): replace Supabase SDK with Clerk SDK"
```

---

## Task 10: Frontend — Type the new env var

**Files:**
- Create or Modify: `frontend/src/vite-env.d.ts`

- [ ] **Step 1: Check if `vite-env.d.ts` exists**

```bash
ls frontend/src/vite-env.d.ts 2>/dev/null || echo "missing"
```

- [ ] **Step 2: Create/replace with the typed env**

Write to `frontend/src/vite-env.d.ts`:

```ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_CLERK_PUBLISHABLE_KEY: string;
  readonly VITE_TELEGRAM_BOT_USERNAME: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/vite-env.d.ts
git commit -m "chore(frontend): type Clerk env var"
```

---

## Task 11: Frontend — Wire ClerkProvider in `main.tsx`

**Files:**
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Replace `main.tsx`**

Write to `frontend/src/main.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider } from '@clerk/clerk-react'
import './index.css'
import App from './App.tsx'

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

if (!PUBLISHABLE_KEY) {
  throw new Error('VITE_CLERK_PUBLISHABLE_KEY is not set')
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ClerkProvider publishableKey={PUBLISHABLE_KEY} afterSignOutUrl="/login">
      <App />
    </ClerkProvider>
  </StrictMode>,
)
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/main.tsx
git commit -m "feat(frontend): wrap app in ClerkProvider"
```

---

## Task 12: Frontend — Auth token registration module

**Files:**
- Create: `frontend/src/lib/auth-token.ts`

The non-React `api.ts` needs Clerk's token, but `getToken()` only exists inside React (`useAuth()`). Pattern: register a getter from inside the React tree at startup.

- [ ] **Step 1: Create the token registry**

Write to `frontend/src/lib/auth-token.ts`:

```ts
type TokenGetter = () => Promise<string | null>;

let getter: TokenGetter | null = null;

export function registerTokenGetter(fn: TokenGetter) {
  getter = fn;
}

export async function getAuthToken(): Promise<string | null> {
  if (!getter) return null;
  return getter();
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/auth-token.ts
git commit -m "feat(frontend): add token registry for non-React api layer"
```

---

## Task 13: Frontend — Rewrite `api.ts`

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Replace `api.ts`**

Write to `frontend/src/lib/api.ts`:

```ts
import { getAuthToken } from "./auth-token";

const API_URL = import.meta.env.VITE_API_URL as string;

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = await getAuthToken();
  if (!token) throw new ApiError(401, "Not authenticated");

  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...options.headers,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail || `API error ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Manga
  listManga: () => apiFetch<Manga[]>("/api/manga"),
  createManga: (url: string, title?: string) =>
    apiFetch<{ id: string; title: string; already_existed: boolean }>(
      "/api/manga",
      { method: "POST", body: JSON.stringify({ url, title }) }
    ),
  addMangaUrl: (mangaId: string, url: string) =>
    apiFetch<{ ok: boolean }>(`/api/manga/${mangaId}/add-url`, {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  // Subscriptions
  listSubscriptions: () =>
    apiFetch<{ manga_id: string; notify: boolean }[]>("/api/subscriptions"),
  toggleSubscription: (mangaId: string) =>
    apiFetch<{ subscribed: boolean }>("/api/subscriptions", {
      method: "POST",
      body: JSON.stringify({ manga_id: mangaId }),
    }),

  // Telegram
  generateTelegramLink: () =>
    apiFetch<{ token: string; telegram_chat_id: string | null }>(
      "/api/telegram/link",
      { method: "POST" }
    ),
  unlinkTelegram: () =>
    apiFetch<{ ok: boolean }>("/api/telegram/link", { method: "DELETE" }),

  // User
  getProfile: () => apiFetch<UserProfile>("/api/me"),

  // Invite redemption (not authenticated by virtue of UI, but uses Clerk token)
  redeemInvite: (code: string) =>
    apiFetch<{ id: string; email: string; clerk_id: string }>(
      "/api/auth/redeem-invite",
      { method: "POST", body: JSON.stringify({ code }) }
    ),
};

export interface Manga {
  id: string;
  title: string;
  asura_slug: string | null;
  demonic_slug: string | null;
  cover_url: string | null;
  subscribed: boolean;
  latest_chapters: Record<string, string>;
}

export interface UserProfile {
  id: string;
  email: string;
  telegram_chat_id: string | null;
  created_at: string;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(frontend): get bearer token from Clerk; expose redeemInvite"
```

---

## Task 14: Frontend — Replace `LoginPage` with Clerk components

**Files:**
- Modify: `frontend/src/pages/LoginPage.tsx`

Clerk's `<SignIn>` and `<SignUp>` components automatically render a **Continue with Google** button when Google is enabled in the Clerk dashboard (Prerequisites step 2). No additional frontend code is needed for Google sign-in.

- [ ] **Step 1: Replace `LoginPage.tsx`**

Write to `frontend/src/pages/LoginPage.tsx`:

```tsx
import { SignIn, SignUp } from "@clerk/clerk-react";
import { useState } from "react";

export default function LoginPage() {
  const [mode, setMode] = useState<"signin" | "signup">("signin");

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <h1>📖 Manga Notifier</h1>
          <p className="subtitle">Track new chapters automatically</p>
        </div>

        {mode === "signin" ? (
          <SignIn routing="hash" signUpUrl="#" />
        ) : (
          <SignUp routing="hash" signInUrl="#" />
        )}

        <p className="login-toggle">
          {mode === "signin" ? "Don't have an account?" : "Already have an account?"}{" "}
          <a href="#" onClick={(e) => { e.preventDefault(); setMode(mode === "signin" ? "signup" : "signin"); }}>
            {mode === "signin" ? "Sign up" : "Sign in"}
          </a>
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/LoginPage.tsx
git commit -m "feat(frontend): replace custom login form with Clerk components"
```

---

## Task 15: Frontend — Add `RedeemInvitePage`

**Files:**
- Create: `frontend/src/pages/RedeemInvitePage.tsx`

- [ ] **Step 1: Create the page**

Write to `frontend/src/pages/RedeemInvitePage.tsx`:

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useClerk } from "@clerk/clerk-react";
import { api, ApiError } from "../lib/api";

const ERROR_MESSAGES: Record<string, string> = {
  invalid_code: "That invite code isn't valid.",
  code_exhausted: "This invite code has been fully used.",
  already_redeemed: "Your account is already set up — try refreshing.",
  rate_limited: "Too many attempts. Wait a minute and try again.",
};

export default function RedeemInvitePage() {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { signOut } = useClerk();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.redeemInvite(code.trim());
      navigate("/");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(ERROR_MESSAGES[err.detail] ?? err.detail);
      } else {
        setError("Something went wrong. Try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <h1>📖 Manga Notifier</h1>
          <p className="subtitle">Enter your invite code to get started</p>
        </div>

        <form onSubmit={handleSubmit}>
          <input
            type="text"
            placeholder="Invite code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
            autoFocus
          />
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={loading || !code.trim()}>
            {loading ? "..." : "Redeem"}
          </button>
        </form>

        <p className="login-toggle">
          Wrong account?{" "}
          <a href="#" onClick={(e) => { e.preventDefault(); signOut(); }}>
            Sign out
          </a>
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/RedeemInvitePage.tsx
git commit -m "feat(frontend): add invite code redemption page"
```

---

## Task 16: Frontend — Rewrite `App.tsx` routing

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Replace `App.tsx`**

Write to `frontend/src/App.tsx`:

```tsx
import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { SignedIn, SignedOut, useAuth } from "@clerk/clerk-react";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import AddMangaPage from "./pages/AddMangaPage";
import SettingsPage from "./pages/SettingsPage";
import RedeemInvitePage from "./pages/RedeemInvitePage";
import { api, ApiError } from "./lib/api";
import { registerTokenGetter } from "./lib/auth-token";
import "./App.css";

function TokenBridge() {
  const { getToken } = useAuth();
  useEffect(() => {
    registerTokenGetter(() => getToken({ template: "default" }));
  }, [getToken]);
  return null;
}

type ProfileState = "loading" | "ok" | "invite_required" | "error";

function ProfileGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<ProfileState>("loading");
  const location = useLocation();

  useEffect(() => {
    let cancelled = false;
    api.getProfile()
      .then(() => { if (!cancelled) setState("ok"); })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 403 && err.detail === "invite_required") {
          setState("invite_required");
        } else {
          setState("error");
        }
      });
    return () => { cancelled = true; };
  }, [location.pathname]);

  if (state === "loading") return <div className="page">Loading...</div>;
  if (state === "invite_required") {
    if (location.pathname === "/redeem-invite") return <>{children}</>;
    return <Navigate to="/redeem-invite" replace />;
  }
  if (state === "error") return <div className="page">Could not load profile. Try refreshing.</div>;
  // state === "ok"
  if (location.pathname === "/redeem-invite") return <Navigate to="/" replace />;
  return <>{children}</>;
}

function AppRoutes() {
  return (
    <>
      <SignedOut>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </SignedOut>
      <SignedIn>
        <ProfileGate>
          <Routes>
            <Route path="/login" element={<Navigate to="/" replace />} />
            <Route path="/redeem-invite" element={<RedeemInvitePage />} />
            <Route path="/" element={<DashboardPage />} />
            <Route path="/add" element={<AddMangaPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </ProfileGate>
      </SignedIn>
    </>
  );
}

function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <TokenBridge />
      <AppRoutes />
    </BrowserRouter>
  );
}

export default App;
```

Notes:
- `TokenBridge` registers Clerk's `getToken` once on mount so non-React `api.ts` can use it.
- `ProfileGate` calls `/api/me` once on every signed-in mount; routes to `/redeem-invite` on the literal `invite_required` 403.
- `getToken({ template: "default" })` requires the JWT template created in Prerequisites (returns a token with `email` claim).

- [ ] **Step 2: Update `DashboardPage.tsx` to use Clerk's signOut**

The only page that references the old `AuthContext` is `DashboardPage.tsx` (lines 3 and 9). Change those two lines:

Replace:
```tsx
import { useAuth } from "../contexts/AuthContext";
```
With:
```tsx
import { useClerk } from "@clerk/clerk-react";
```

Replace:
```tsx
const { signOut } = useAuth();
```
With:
```tsx
const { signOut } = useClerk();
```

The `onClick={signOut}` at line 64 works as-is — Clerk's `signOut` is also a no-arg function.

Verify no other references remain:
```bash
grep -rn "AuthContext\|@supabase\|from \"../lib/supabase\"" frontend/src/
```
Expected: no matches.

- [ ] **Step 3: Build the frontend to catch type errors**

```bash
cd frontend
npm run build
```

Expected: build succeeds. Fix any TypeScript errors before continuing.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pages/
git commit -m "feat(frontend): Clerk-aware routing with profile gate and invite redemption"
```

---

## Task 17: Frontend — Update `.env.example`

**Files:**
- Modify: `frontend/.env.example`

- [ ] **Step 1: Replace `.env.example`**

Write to `frontend/.env.example`:

```sh
VITE_API_URL=http://localhost:8000
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
VITE_TELEGRAM_BOT_USERNAME=
```

- [ ] **Step 2: Update your local `.env`**

Edit `frontend/.env`: remove `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`. Add `VITE_CLERK_PUBLISHABLE_KEY` from Prerequisites.

- [ ] **Step 3: Commit**

```bash
git add frontend/.env.example
git commit -m "chore(frontend): swap Supabase env vars for Clerk publishable key"
```

---

## Task 18: Local smoke test

- [ ] **Step 1: Apply DB migration locally**

```bash
cd backend
alembic upgrade head
```

Expected: migration runs, prints the new revision id.

- [ ] **Step 2: Seed an invite code**

```bash
cd backend
python seed.py
```

Expected: prints `IMPORTANT: save this invite code -> <token>`. Copy the token.

- [ ] **Step 3: Start the backend**

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload
```

Leave running.

- [ ] **Step 4: Start the frontend (new terminal)**

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173/manga-notif-web/`.

- [ ] **Step 5: Walk through QA matrix (spec §14.4)**

Manually verify scenarios 1–17. At minimum:
- **Email path**: sign up → verify email → land on invite page → submit code → dashboard renders → `/api/me` returns 200.
- **Google path**: click "Continue with Google" → Google consent → returns signed in → invite page → submit code → dashboard renders.
- Both paths should produce a single `User` row when the same verified email is used (scenario 17).

- [ ] **Step 6: Run full backend test suite**

```bash
cd backend
.venv/bin/pytest -v
```

Expected: all tests pass.

---

## Task 19: Update README.md and DEPLOYMENT.md

**Files:**
- Modify: `README.md`
- Modify: `DEPLOYMENT.md`

- [ ] **Step 1: Update README stack table**

In `README.md`, replace the **Stack** table rows for Auth and the **Deployment** table row for "DB + Auth" with:

```
| Auth (client) | `@clerk/clerk-react` — email/password + Google OAuth |
| Auth (server) | JWT validation via Clerk JWKS |
```

```
| DB        | Neon Postgres          | — |
| Auth      | Clerk (free tier)      | — |
```

Also update the "How it works" §1 to:

> 1. **Sign-up** is invite-code-gated — after Clerk auth (email/password or Google), users must redeem an invite code (multi-use, stored in `invite_codes` table) before they can access the app.

- [ ] **Step 2: Update DEPLOYMENT.md**

Replace the secrets table for the backend in DEPLOYMENT.md §1:

```
| Var | Value |
|---|---|
| `DATABASE_URL` | Neon connection string |
| `CLERK_JWKS_URL` | `<clerk-frontend-api>/.well-known/jwks.json` |
| `CLERK_ISSUER` | `<clerk-frontend-api>` |
| `TELEGRAM_BOT_TOKEN` | from BotFather |
| `CRON_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `FRONTEND_URL` | `https://<owner>.github.io` (origin only) |
```

Replace the secrets table for the frontend (§3):

```
| Secret | Value |
|---|---|
| `VITE_CLERK_PUBLISHABLE_KEY` | from Clerk dashboard |
| `VITE_API_URL` | `https://<service>.onrender.com` |
| `VITE_TELEGRAM_BOT_USERNAME` | bot username without `@` |
```

Add a new section before §1 titled **"0. Clerk setup"** with steps:

1. Create Clerk application.
2. Enable email/password sign-in (require email verification) **and Google OAuth**.
3. For production: add your own Google Cloud OAuth Client ID + Secret in Clerk → SSO Connections → Google (replaces Clerk's shared dev credentials).
4. Whitelist redirect URLs (GitHub Pages prod + localhost dev).
5. Create JWT template named `default` with custom claim `{"email": "{{user.primary_email_address}}"}`.
6. Copy publishable key + frontend API URL.

- [ ] **Step 3: Commit**

```bash
git add README.md DEPLOYMENT.md
git commit -m "docs: update README and DEPLOYMENT for Clerk + invite codes"
```

---

## Task 20: Open PR

- [ ] **Step 1: Create branch + push**

Per the auto-memory rule (never push direct to main), this work should have been done on a feature branch. If you're currently on `main`, move commits to a branch first:

```bash
git checkout -b feat/clerk-auth-migration
git push -u origin feat/clerk-auth-migration
```

- [ ] **Step 2: Open PR (do not merge)**

```bash
gh pr create --title "Migrate auth: Supabase → Clerk + invite codes" --body "$(cat <<'EOF'
## Summary

- Replace Supabase Auth with Clerk (pre-built components)
- Replace email allowlist with multi-use invite codes (new `invite_codes` table)
- Truncate users on deploy (loses existing subscriptions; manga library preserved)
- Rate limit invite redemption: 5 req/IP/min

## Spec & Plan

- Spec: `docs/superpowers/specs/2026-06-06-clerk-auth-migration-design.md`
- Plan: `docs/superpowers/plans/2026-06-06-clerk-auth-migration.md`

## Test plan

- [ ] All backend unit tests pass (`pytest`)
- [ ] Local smoke test from plan Task 18
- [ ] Production deploy via Gate F checklist in spec §14.6
- [ ] UAT scenarios (spec §14.5)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Return the PR URL.

---

## Out-of-band manual steps (Gate F — Deployment)

These are not automatable from the plan; Adrian performs them before/after merging the PR:

1. `pg_dump` of production Neon DB → save backup.
2. Add Render env vars: `CLERK_JWKS_URL`, `CLERK_ISSUER`. Remove `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`.
3. Add GitHub Actions secret: `VITE_CLERK_PUBLISHABLE_KEY`. Remove `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.
4. Merge PR → Render auto-deploys + runs migration → GitHub Pages auto-deploys frontend.
5. After deploy: SSH to a one-off shell on Render (or run locally pointed at prod `DATABASE_URL`) → `python seed.py` to insert the initial invite code.
6. Run Gate F post-deploy verification (spec §14.6).
