"""
Targeted tests written to close specific coverage gaps.
Each test is labelled with the file and line(s) it covers.
"""
import time

import jwt
import pytest
from fastapi import HTTPException

from app.api.deps import require_role
from app.core.config import settings
from app.core.security import (
    CredentialsError,
    TokenExpiredError,
    TokenTypeError,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)
from app.models.account import Account
from app.models.user import User

# ── security.py — refresh token paths (lines 51-58, 79-92) ───────────────────

def test_create_and_decode_refresh_token():
    token = create_refresh_token(subject="42", role="customer")
    payload = decode_refresh_token(token)
    assert payload["sub"] == "42"
    assert payload["type"] == "refresh"


def test_decode_refresh_token_rejects_access_token():
    access = create_access_token(subject="42", role="customer")
    with pytest.raises(TokenTypeError):
        decode_refresh_token(access)


def test_decode_access_token_rejects_refresh_token():
    refresh = create_refresh_token(subject="42", role="customer")
    with pytest.raises(TokenTypeError):
        decode_access_token(refresh)


def test_decode_access_token_rejects_expired():
    """security.py lines 69-70."""
    expired = jwt.encode(
        {"sub": "1", "role": "customer", "type": "access", "exp": int(time.time()) - 60},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    with pytest.raises(TokenExpiredError):
        decode_access_token(expired)


def test_decode_refresh_token_rejects_expired():
    expired = jwt.encode(
        {"sub": "1", "role": "customer", "type": "refresh", "exp": int(time.time()) - 60},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    with pytest.raises(TokenExpiredError):
        decode_refresh_token(expired)


def test_decode_access_token_rejects_garbage():
    """security.py lines 73-74."""
    with pytest.raises(CredentialsError):
        decode_access_token("not.a.real.jwt")


# ── deps.py — error paths (lines 24, 38, 46, 55-62) ─────────────────────────

def test_require_role_allows_correct_role():
    """deps.py lines 55-61."""
    checker = require_role("admin")
    admin = User(id=1, username="admin", role="admin")
    result = checker(current_user=admin)
    assert result.role == "admin"


def test_require_role_rejects_wrong_role():
    """deps.py lines 56-60."""
    checker = require_role("admin")
    customer = User(id=2, username="cust", role="customer")
    with pytest.raises(HTTPException) as exc_info:
        checker(current_user=customer)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_expired_token_returns_401(client):
    """deps.py line 24 — TokenExpiredError branch."""
    expired = jwt.encode(
        {"sub": "9001", "role": "customer", "type": "access", "exp": int(time.time()) - 60},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    resp = await client.get(
        "/accounts/1",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_token_without_sub_returns_401(client):
    """deps.py line 38 — user_id is None branch."""
    token = jwt.encode(
        {"role": "customer", "type": "access", "exp": int(time.time()) + 3600},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    resp = await client.get(
        "/accounts/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_for_nonexistent_user_returns_401(client):
    """deps.py line 46 — user not found in DB branch."""
    ghost_token = jwt.encode(
        {"sub": "99999", "role": "customer", "type": "access", "exp": int(time.time()) + 3600},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    resp = await client.get(
        "/accounts/1",
        headers={"Authorization": f"Bearer {ghost_token}"},
    )
    assert resp.status_code == 401


# ── routes.py — account 404 and RBAC paths (lines 90, 93, 132, 135) ──────────

@pytest.mark.asyncio
async def test_get_account_not_found(client):
    """routes.py line 90."""
    resp = await client.get("/accounts/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_account_wrong_owner_returns_404(client, db_session):
    """routes.py line 93 — customer cannot see another user's account."""
    other = Account(id=800, currency="GBP", balance=0.0, type="customer", owner_id=None)
    db_session.add(other)
    await db_session.flush()
    resp = await client.get("/accounts/800")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_statement_not_found(client):
    """routes.py line 132."""
    resp = await client.get("/accounts/99999/statement")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_statement_wrong_owner_returns_404(client, db_session):
    """routes.py line 135."""
    other = Account(id=801, currency="GBP", balance=0.0, type="customer", owner_id=None)
    db_session.add(other)
    await db_session.flush()
    resp = await client.get("/accounts/801/statement")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_statement_returns_paginated_entries(client, db_session):
    """routes.py statement happy path."""
    acc = Account(id=802, currency="GBP", balance=100.0, type="customer", owner_id=9001)
    db_session.add(acc)
    await db_session.commit()
    resp = await client.get("/accounts/802/statement?limit=5&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert "entries" in body
    assert body["limit"] == 5
    assert body["offset"] == 0


@pytest.mark.asyncio
async def test_create_account_returns_201(client):
    """routes.py create_account + db.refresh (line 67)."""
    resp = await client.post("/accounts", json={"currency": "EUR", "type": "customer"})
    assert resp.status_code == 201
    assert resp.json()["currency"] == "EUR"


# ── routes.py — transfer retrieval (lines 160-172) ───────────────────────────

@pytest.mark.asyncio
async def test_get_transfer_not_found(client):
    """routes.py line 163."""
    resp = await client.get("/transfers/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_transfer_happy_path(client, db_session):
    """routes.py lines 160-172."""
    acc1 = Account(id=901, currency="USD", balance=200.0, type="customer", owner_id=9001)
    acc2 = Account(id=902, currency="USD", balance=0.0,   type="customer", owner_id=9001)
    db_session.add_all([acc1, acc2])
    await db_session.commit()

    create_resp = await client.post(
        "/transfers",
        json={"from_account_id": 901, "to_account_id": 902, "amount": "15.00", "currency": "USD"},
        headers={"Idempotency-Key": "get-transfer-test"},
    )
    assert create_resp.status_code == 201
    transfer_id = create_resp.json()["id"]

    get_resp = await client.get(f"/transfers/{transfer_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == transfer_id


# ── exceptions.py — domain error → HTTP status mapping (lines 25-36) ─────────

@pytest.mark.asyncio
async def test_exception_handler_account_not_found(client, db_session):
    """exceptions.py lines 25-27 — AccountNotFoundError → 404 account_not_found."""
    src = Account(id=1001, currency="USD", balance=100.0, type="customer", owner_id=9001)
    db_session.add(src)
    await db_session.commit()
    resp = await client.post(
        "/transfers",
        json={"from_account_id": 1001, "to_account_id": 99999, "amount": "10.00", "currency": "USD"},
        headers={"Idempotency-Key": "exc-no-dest"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "account_not_found"


@pytest.mark.asyncio
async def test_exception_handler_currency_mismatch(client, db_session):
    """exceptions.py lines 28-30 — CurrencyMismatchError → 422 currency_mismatch."""
    usd = Account(id=1002, currency="USD", balance=100.0, type="customer", owner_id=9001)
    gbp = Account(id=1003, currency="GBP", balance=0.0,   type="customer", owner_id=9001)
    db_session.add_all([usd, gbp])
    await db_session.commit()
    resp = await client.post(
        "/transfers",
        json={"from_account_id": 1002, "to_account_id": 1003, "amount": "10.00", "currency": "USD"},
        headers={"Idempotency-Key": "exc-currency"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "currency_mismatch"


@pytest.mark.asyncio
async def test_exception_handler_idempotency_conflict(client, db_session):
    """exceptions.py lines 31-33 — IdempotencyConflictError → 409."""
    acc1 = Account(id=1004, currency="USD", balance=200.0, type="customer", owner_id=9001)
    acc2 = Account(id=1005, currency="USD", balance=0.0,   type="customer", owner_id=9001)
    db_session.add_all([acc1, acc2])
    await db_session.commit()

    await client.post(
        "/transfers",
        json={"from_account_id": 1004, "to_account_id": 1005, "amount": "10.00", "currency": "USD"},
        headers={"Idempotency-Key": "conflict-key"},
    )
    resp = await client.post(
        "/transfers",
        json={"from_account_id": 1004, "to_account_id": 1005, "amount": "99.00", "currency": "USD"},
        headers={"Idempotency-Key": "conflict-key"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "idempotency_conflict"


@pytest.mark.asyncio
async def test_exception_handler_invalid_transfer(client, db_session):
    """exceptions.py lines 34-36 — InvalidTransferError → 422 invalid_transfer."""
    acc = Account(id=1006, currency="USD", balance=100.0, type="customer", owner_id=9001)
    db_session.add(acc)
    await db_session.commit()
    resp = await client.post(
        "/transfers",
        json={"from_account_id": 1006, "to_account_id": 1006, "amount": "10.00", "currency": "USD"},
        headers={"Idempotency-Key": "exc-same-acct"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_transfer"
