import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.models.tables import AllowedEmail, User


def _make_credentials(token="fake.jwt.token"):
    creds = MagicMock()
    creds.credentials = token
    return creds


def _make_db_session(existing_user=None, allowed_email=None):
    """Mock AsyncSession: 1st execute returns existing_user lookup, 2nd returns allowed_email lookup."""
    session = AsyncMock(spec=AsyncSession)
    call_count = 0

    async def execute_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar_one_or_none.return_value = existing_user
        else:
            result.scalar_one_or_none.return_value = allowed_email
        return result

    session.execute.side_effect = execute_side_effect
    return session


FAKE_PAYLOAD = {
    "sub": str(uuid.uuid4()),
    "email": "newuser@example.com",
    "aud": "authenticated",
}


@pytest.mark.anyio
async def test_get_current_user_new_user_whitelisted():
    """First login for a whitelisted email creates a User row."""
    allowed = AllowedEmail(email="newuser@example.com")
    session = _make_db_session(existing_user=None, allowed_email=allowed)

    with patch("app.auth._get_jwks", return_value=[]), \
         patch("app.auth.jwt.decode", return_value=FAKE_PAYLOAD):
        user = await get_current_user(
            credentials=_make_credentials(),
            db=session,
        )

    session.add.assert_called_once()
    session.commit.assert_called_once()
    assert user.email == "newuser@example.com"


@pytest.mark.anyio
async def test_get_current_user_new_user_not_whitelisted():
    """First login for a non-whitelisted email raises 403."""
    session = _make_db_session(existing_user=None, allowed_email=None)

    with patch("app.auth._get_jwks", return_value=[]), \
         patch("app.auth.jwt.decode", return_value=FAKE_PAYLOAD):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                credentials=_make_credentials(),
                db=session,
            )

    assert exc_info.value.status_code == 403


@pytest.mark.anyio
async def test_get_current_user_existing_user_not_rechecked():
    """Returning users bypass the whitelist check (no second DB query)."""
    existing = MagicMock(spec=User)
    existing.email = "existing@example.com"
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    session.execute.return_value = result

    payload = {**FAKE_PAYLOAD, "email": "existing@example.com"}

    with patch("app.auth._get_jwks", return_value=[]), \
         patch("app.auth.jwt.decode", return_value=payload):
        user = await get_current_user(
            credentials=_make_credentials(),
            db=session,
        )

    assert user is existing
    assert session.execute.call_count == 1  # only User lookup, no AllowedEmail lookup
