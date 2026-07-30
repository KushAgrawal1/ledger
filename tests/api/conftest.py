import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token, get_password_hash
from app.database import get_db
from app.main import app
from app.models.user import User


@pytest_asyncio.fixture
async def auth_db(db_session):
    """
    Alias so test_auth.py can request 'auth_db' and get the standard
    per-test postgres session from the root conftest.
    """
    yield db_session


@pytest_asyncio.fixture
async def client(db_session):
    """
    Authenticated HTTPX client for all API tests.

    Creates a test customer user, mints a valid JWT, and pre-sets the
    Authorization header so individual tests never have to deal with auth.

    Overrides the 'client' fixture in the root conftest for tests/api/ only.
    """
    user = User(
        id=9001,
        username="api_test_user",
        hashed_password=get_password_hash("testpass123"),
        role="customer",
    )
    db_session.add(user)
    await db_session.flush()

    token = create_access_token(subject=user.id, role=user.role)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
    await db_session.rollback()
