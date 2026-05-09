import pytest
from app.database import get_db
from app.models.tables import AllowedEmail
from tests.conftest import make_db_override
from app.main import app


@pytest.mark.anyio
async def test_check_email_allowed(client):
    allowed = AllowedEmail(email="approved@example.com")
    app.dependency_overrides[get_db] = make_db_override(scalar_value=allowed)
    try:
        resp = await client.get("/api/auth/check-email?email=approved@example.com")
        assert resp.status_code == 200
        assert resp.json() == {"allowed": True}
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_check_email_not_allowed(client):
    app.dependency_overrides[get_db] = make_db_override(scalar_value=None)
    try:
        resp = await client.get("/api/auth/check-email?email=stranger@example.com")
        assert resp.status_code == 200
        assert resp.json() == {"allowed": False}
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_check_email_lowercases_input(client):
    allowed = AllowedEmail(email="user@example.com")
    app.dependency_overrides[get_db] = make_db_override(scalar_value=allowed)
    try:
        resp = await client.get("/api/auth/check-email?email=USER@EXAMPLE.COM")
        assert resp.status_code == 200
        assert resp.json() == {"allowed": True}
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_check_email_missing_param(client):
    resp = await client.get("/api/auth/check-email")
    assert resp.status_code == 422
