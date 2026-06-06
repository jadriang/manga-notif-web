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
        # No Authorization header — FastAPI's HTTPBearer dependency rejects with 401
        resp = await client.post("/api/auth/redeem-invite", json={"code": "X"})
        assert resp.status_code == 401
    finally:
        _reset()
