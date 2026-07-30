import pytest

from app.core.security import get_password_hash, verify_password
from app.models.account import Account
from app.models.user import User


@pytest.mark.asyncio
async def test_register_hashes_password(client, db_session):
    """POST /auth/register hashes the password and never stores plaintext."""
    payload = {"username": "register_test", "password": "secure_pass_123", "role": "customer"}
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 201

    user_in_db = await db_session.get(User, response.json()["id"])
    assert user_in_db.hashed_password != "secure_pass_123"
    assert verify_password("secure_pass_123", user_in_db.hashed_password)


@pytest.mark.asyncio
async def test_register_duplicate_username_returns_400(client, db_session):
    """Registering the same username twice → 400."""
    payload = {"username": "duplicate_user", "password": "pass123", "role": "customer"}
    r1 = await client.post("/auth/register", json=payload)
    assert r1.status_code == 201

    r2 = await client.post("/auth/register", json=payload)
    assert r2.status_code == 400
    assert "already registered" in r2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_success_returns_token(client, db_session):
    """POST /auth/token with correct credentials → 200 with access_token."""
    user = User(
        username="login_ok_user",
        hashed_password=get_password_hash("correct_pass"),
        role="customer",
    )
    db_session.add(user)
    await db_session.flush()

    response = await client.post(
        "/auth/token",
        data={"username": "login_ok_user", "password": "correct_pass"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_with_wrong_password_returns_401(client, db_session):
    """POST /auth/token with wrong password → 401."""
    user = User(
        username="login_fail_user",
        hashed_password=get_password_hash("real_pass"),
        role="customer",
    )
    db_session.add(user)
    await db_session.flush()

    response = await client.post(
        "/auth/token",
        data={"username": "login_fail_user", "password": "wrong_pass"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_route_rejects_missing_token(client, db_session):
    """Request without Authorization header → 401."""
    acc = Account(id=501, currency="USD", balance=0.0, type="customer", owner_id=9001)
    db_session.add(acc)
    await db_session.flush()

    r = await client.get("/accounts/501", headers={"Authorization": ""})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_route_rejects_garbage_token(client, db_session):
    """Request with a malformed token → 401."""
    acc = Account(id=502, currency="USD", balance=0.0, type="customer", owner_id=9001)
    db_session.add(acc)
    await db_session.flush()

    r = await client.get(
        "/accounts/502",
        headers={"Authorization": "Bearer this.is.garbage"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_customer_can_only_access_own_account(client, db_session):
    """Customer sees own account (200) and gets 404 for another user's account."""
    user_a = User(username="cust_a", hashed_password=get_password_hash("pass"), role="customer")
    user_b = User(username="cust_b", hashed_password=get_password_hash("pass"), role="customer")
    db_session.add_all([user_a, user_b])
    await db_session.flush()

    acc_a = Account(id=601, currency="USD", balance=10.0, type="customer", owner_id=user_a.id)
    acc_b = Account(id=602, currency="USD", balance=10.0, type="customer", owner_id=user_b.id)
    db_session.add_all([acc_a, acc_b])
    await db_session.flush()

    tok_a = (
        await client.post("/auth/token", data={"username": "cust_a", "password": "pass"})
    ).json()["access_token"]

    r1 = await client.get("/accounts/601", headers={"Authorization": f"Bearer {tok_a}"})
    assert r1.status_code == 200

    r2 = await client.get("/accounts/602", headers={"Authorization": f"Bearer {tok_a}"})
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_access_any_account(client, db_session):
    """Admin role can access any account regardless of ownership."""
    admin = User(username="admin_test", hashed_password=get_password_hash("pass"), role="admin")
    owner = User(username="acc_owner", hashed_password=get_password_hash("pass"), role="customer")
    db_session.add_all([admin, owner])
    await db_session.flush()

    acc = Account(id=603, currency="USD", balance=10.0, type="customer", owner_id=owner.id)
    db_session.add(acc)
    await db_session.flush()

    tok_admin = (
        await client.post("/auth/token", data={"username": "admin_test", "password": "pass"})
    ).json()["access_token"]

    r = await client.get("/accounts/603", headers={"Authorization": f"Bearer {tok_admin}"})
    assert r.status_code == 200
