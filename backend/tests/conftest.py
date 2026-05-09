import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.database import get_db


def make_db_override(scalar_value=None):
    """Return a callable that yields a mock AsyncSession.
    scalar_value is what session.execute(...).scalar_one_or_none() returns."""
    async def _mock_db():
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = scalar_value
        session.execute.return_value = result
        yield session
    return _mock_db


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
