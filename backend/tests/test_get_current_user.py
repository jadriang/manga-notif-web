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


@pytest.fixture
def anyio_backend():
    return "asyncio"
