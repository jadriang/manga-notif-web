"""Tests for the JWKS cache TTL in app.auth._get_jwks."""

import pytest
from unittest.mock import patch, MagicMock

import app.auth as auth_module


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def reset_cache():
    auth_module._jwks_cache = None
    auth_module._jwks_cached_at = 0.0
    yield
    auth_module._jwks_cache = None
    auth_module._jwks_cached_at = 0.0


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient used as an async context manager."""

    def __init__(self, payload):
        self.payload = payload
        self.get_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, *_args, **_kwargs):
        self.get_calls += 1
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value=self.payload)
        return resp


@pytest.mark.anyio
async def test_jwks_first_call_fetches():
    fake = _FakeAsyncClient({"keys": [{"kid": "k1"}]})
    with patch("app.auth.httpx.AsyncClient", return_value=fake):
        keys = await auth_module._get_jwks()
    assert keys == [{"kid": "k1"}]
    assert fake.get_calls == 1


@pytest.mark.anyio
async def test_jwks_second_call_within_ttl_uses_cache():
    fake = _FakeAsyncClient({"keys": [{"kid": "k1"}]})
    with patch("app.auth.httpx.AsyncClient", return_value=fake):
        await auth_module._get_jwks()
        await auth_module._get_jwks()
    assert fake.get_calls == 1


@pytest.mark.anyio
async def test_jwks_refetch_after_ttl(monkeypatch):
    fake_time = [1000.0]
    monkeypatch.setattr("app.auth.monotonic", lambda: fake_time[0])

    fake = _FakeAsyncClient({"keys": [{"kid": "k1"}]})
    with patch("app.auth.httpx.AsyncClient", return_value=fake):
        await auth_module._get_jwks()
        fake_time[0] += auth_module.JWKS_TTL_SECONDS + 1
        await auth_module._get_jwks()
    assert fake.get_calls == 2
