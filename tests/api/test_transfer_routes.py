import pytest
import pytest_asyncio

from app.models.account import Account


@pytest_asyncio.fixture
async def setup_accounts(db_session):
    """Seeds two funded USD accounts owned by the api_test_user (id=9001)."""
    acc1 = Account(id=1, currency="USD", balance=100.0, type="customer", owner_id=9001)
    acc2 = Account(id=2, currency="USD", balance=50.0,  type="customer", owner_id=9001)
    db_session.add_all([acc1, acc2])
    await db_session.commit()


@pytest.mark.asyncio
async def test_post_transfers_without_idempotency_header_fails(client, setup_accounts):
    """POST /transfers without Idempotency-Key header → 422"""
    payload = {
        "from_account_id": 1,
        "to_account_id": 2,
        "amount": "20.00",
        "currency": "USD",
    }
    response = await client.post("/transfers", json=payload)
    assert response.status_code == 422
    assert "Idempotency-Key" in response.json()["detail"][0]["loc"]


@pytest.mark.asyncio
async def test_post_transfers_insufficient_balance_returns_structured_error(client, setup_accounts):
    """POST /transfers with insufficient balance → 422 with structured error code"""
    payload = {
        "from_account_id": 1,
        "to_account_id": 2,
        "amount": "200.00",   # exceeds 100.00 balance
        "currency": "USD",
    }
    headers = {"Idempotency-Key": "test_idem_fail"}
    response = await client.post("/transfers", json=payload, headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "insufficient_balance"


@pytest.mark.asyncio
async def test_new_transfer_happy_path(client, setup_accounts):
    """New transfer → 201 Created with correct schema"""
    payload = {
        "from_account_id": 1,
        "to_account_id": 2,
        "amount": "10.00",
        "currency": "USD",
    }
    headers = {"Idempotency-Key": "test_idem_success"}
    response = await client.post("/transfers", json=payload, headers=headers)

    assert response.status_code == 201
    data = response.json()
    assert data["idempotency_key"] == "test_idem_success"
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_replayed_idempotency_returns_original_transfer(client, setup_accounts):
    """Replayed idempotency key returns the same transfer, not a new one"""
    payload = {
        "from_account_id": 1,
        "to_account_id": 2,
        "amount": "10.00",
        "currency": "USD",
    }
    headers = {"Idempotency-Key": "replay_key"}

    resp1 = await client.post("/transfers", json=payload, headers=headers)
    assert resp1.status_code == 201
    original_id = resp1.json()["id"]

    resp2 = await client.post("/transfers", json=payload, headers=headers)
    assert resp2.status_code in [200, 201]
    assert resp2.json()["id"] == original_id
