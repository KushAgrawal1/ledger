import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.account import Account

# In-memory SQLite for rapid route unit testing
DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture
async def api_db():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()

@pytest.fixture
async def setup_accounts(api_db):
    acc1 = Account(id=1, currency="USD", balance=100.0, type="customer")
    acc2 = Account(id=2, currency="USD", balance=50.0, type="customer")
    api_db.add_all([acc1, acc2])
    await api_db.commit()

@pytest.fixture
async def client(api_db):
    # Dependency override: swap out the production DB for our test memory DB
    async def override_get_db():
        yield api_db

    app.dependency_overrides[get_db] = override_get_db
    
    # Use ASGITransport for testing async apps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
        
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_transfers_without_idempotency_header_fails(client, setup_accounts):
    """POST /transfers without Idempotency-Key header → 422"""
    payload = {
        "from_account_id": 1,
        "to_account_id": 2,
        "amount": "20.00",
        "currency": "USD"
    }
    response = await client.post("/transfers", json=payload)
    assert response.status_code == 422
    assert "Idempotency-Key" in response.json()["detail"][0]["loc"]


@pytest.mark.asyncio
async def test_post_transfers_insufficient_balance_returns_structured_error(client, setup_accounts):
    """POST /transfers with insufficient balance → 422 with structured code"""
    payload = {
        "from_account_id": 1,
        "to_account_id": 2,
        "amount": "200.00", # Exceeds 100.00 limit
        "currency": "USD"
    }
    headers = {"Idempotency-Key": "test_idem_fail"}
    response = await client.post("/transfers", json=payload, headers=headers)
    
    assert response.status_code == 422
    error_data = response.json()["error"]
    assert error_data["code"] == "insufficient_balance"


@pytest.mark.asyncio
async def test_new_transfer_happy_path(client, setup_accounts):
    """New transfer → 201 Created and correct schema"""
    payload = {
        "from_account_id": 1,
        "to_account_id": 2,
        "amount": "10.00",
        "currency": "USD"
    }
    headers = {"Idempotency-Key": "test_idem_success"}
    response = await client.post("/transfers", json=payload, headers=headers)
    
    assert response.status_code == 201
    data = response.json()
    assert data["idempotency_key"] == "test_idem_success"
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_replayed_idempotency_returns_original_transfer(client, setup_accounts):
    """Replayed idempotency key → 201 for the first, then 201 or 200 with original transfer ID"""
    payload = {
        "from_account_id": 1,
        "to_account_id": 2,
        "amount": "10.00",
        "currency": "USD"
    }
    headers = {"Idempotency-Key": "replay_key"}
    
    # First execution
    resp1 = await client.post("/transfers", json=payload, headers=headers)
    assert resp1.status_code == 201
    id1 = resp1.json()["id"]

    # Replay execution (it should bypass creation and safely return the exact same payload)
    resp2 = await client.post("/transfers", json=payload, headers=headers)
    assert resp2.status_code in [200, 201]  # FastAPI defaults to route's success status code, but returns the same object
    assert resp2.json()["id"] == id1