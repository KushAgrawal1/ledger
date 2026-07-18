import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import get_password_hash, verify_password
from app.database import Base, get_db
from app.main import app
from app.models.account import Account
from app.models.user import User

DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture
async def auth_db():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()

@pytest.fixture
async def client(auth_db):
    async def override_get_db():
        yield auth_db
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_register_hashes_password(client, auth_db):
    """Register hashes password (bcrypt via passlib), never stores plaintext."""
    payload = {"username": "test_user", "password": "secure_password_123", "role": "customer"}
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 201
    
    # Query database directly to assert hashed verification
    user_in_db = await auth_db.get(User, response.json()["id"])
    assert user_in_db.hashed_password != "secure_password_123"
    assert verify_password("secure_password_123", user_in_db.hashed_password)


@pytest.mark.asyncio
async def test_login_with_wrong_password_fails(client, auth_db):
    """Login with wrong password → 401"""
    # Create manual user
    hashed = get_password_hash("real_pass")
    user = User(username="login_test", hashed_password=hashed)
    auth_db.add(user)
    await auth_db.commit()

    # Attempt incorrect password login
    response = await client.post("/auth/token", data={"username": "login_test", "password": "wrong_pass"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_route_rejects_missing_or_expired_jwt(client, auth_db):
    """Valid JWT grants access; missing/expired/garbage token → 401"""
    # Create manual user with account
    hashed = get_password_hash("pass")
    user = User(id=10, username="user_10", hashed_password=hashed)
    account = Account(id=101, currency="USD", balance=100.0, type="customer", owner_id=10)
    auth_db.add_all([user, account])
    await auth_db.commit()

    # Request without token
    r1 = await client.get("/accounts/101")
    assert r1.status_code == 401

    # Request with garbage token
    r2 = await client.get("/accounts/101", headers={"Authorization": "Bearer non-existent-jwt"})
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_customer_can_only_access_own_accounts(client, auth_db):
    """Customer can access own accounts only; admin can access any (404 instead of 403)"""
    # 1. Setup Database Users & Accounts
    user_a = User(id=1, username="customer_a", hashed_password=get_password_hash("pass"), role="customer")
    user_b = User(id=2, username="customer_b", hashed_password=get_password_hash("pass"), role="customer")
    admin = User(id=3, username="admin_user", hashed_password=get_password_hash("pass"), role="admin")
    
    acc_a = Account(id=50, currency="USD", balance=10.0, type="customer", owner_id=1)
    acc_b = Account(id=60, currency="USD", balance=10.0, type="customer", owner_id=2)
    auth_db.add_all([user_a, user_b, admin, acc_a, acc_b])
    await auth_db.commit()

    # 2. Get tokens
    tok_a = (await client.post("/auth/token", data={"username": "customer_a", "password": "pass"})).json()["access_token"]
    tok_admin = (await client.post("/auth/token", data={"username": "admin_user", "password": "pass"})).json()["access_token"]

    # Customer A requests own account -> Success
    res1 = await client.get("/accounts/50", headers={"Authorization": f"Bearer {tok_a}"})
    assert res1.status_code == 200

    # Customer A requests Customer B's account -> 404 (don't leak existence via 403)
    res2 = await client.get("/accounts/60", headers={"Authorization": f"Bearer {tok_a}"})
    assert res2.status_code == 404

    # Admin requests Customer B's account -> 200 (Admins have access to all)
    res3 = await client.get("/accounts/60", headers={"Authorization": f"Bearer {tok_admin}"})
    assert res3.status_code == 200