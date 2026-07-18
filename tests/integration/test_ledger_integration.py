import asyncio
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.models.account import Account
from app.models.transfer import Transfer
from app.models.user import User
from app.services.ledger import execute_transfer
from app.services.exceptions import InsufficientBalanceError

@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_transfers_cannot_double_spend(session_factory: async_sessionmaker[AsyncSession]):
    """
    Concurrency Test: Account A has balance 1000 (£10.00).
    Fire 20 concurrent transfers of 100 from A -> B.
    Only exactly 10 transfers should succeed; remaining 10 must raise InsufficientBalanceError.
    """
    # 1. Create source and destination accounts in database
    async with session_factory() as setup_session:
        acc_a = Account(id=101, currency="USD", balance=1000.0, type="customer")
        acc_b = Account(id=102, currency="USD", balance=0.0, type="customer")
        setup_session.add_all([acc_a, acc_b])
        await setup_session.commit()

    # Worker task simulating real-world concurrent execution context
    async def attempt_transfer(amount: float, key: str):
        async with session_factory() as task_session:
            try:
                tx = await execute_transfer(
                    db=task_session,
                    idempotency_key=key,
                    from_account_id=101,
                    to_account_id=102,
                    amount=amount,
                    currency="USD"
                )
                await task_session.commit()
                return tx
            except Exception as e:
                await task_session.rollback()
                return e

    # 2. Fire 20 parallel execution requests
    results = await asyncio.gather(
        *[attempt_transfer(amount=100.0, key=f"key-double-spend-{i}") for i in range(20)],
        return_exceptions=True
    )

    # 3. Validation and assertions
    succeeded = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]

    assert len(succeeded) == 10, f"Expected 10 successes, got {len(succeeded)}"
    assert any(isinstance(f, InsufficientBalanceError) for f in failures)

    async with session_factory() as verify_session:
        final_a = await verify_session.get(Account, 101)
        final_b = await verify_session.get(Account, 102)
        
        assert final_a.balance == 0.0, f"Balance A should be fully depleted. Got: {final_a.balance}"
        assert final_b.balance == 1000.0, f"Balance B should equal conserved fund volume. Got: {final_b.balance}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_same_idempotency_key_resolves_uniquely(session_factory: async_sessionmaker[AsyncSession]):
    """
    Tests that firing identical concurrent requests with the exact same Idempotency-Key
    inserts exactly one Transfer row due to DB unique constraints handling the race condition.
    """
    async with session_factory() as setup_session:
        acc_a = Account(id=201, currency="USD", balance=500.0, type="customer")
        acc_b = Account(id=202, currency="USD", balance=0.0, type="customer")
        setup_session.add_all([acc_a, acc_b])
        await setup_session.commit()

    async def run_task():
        async with session_factory() as task_session:
            try:
                tx = await execute_transfer(
                    db=task_session,
                    idempotency_key="same-idem-race-key",
                    from_account_id=201,
                    to_account_id=202,
                    amount=100.0,
                    currency="USD"
                )
                await task_session.commit()
                return tx
            except Exception as e:
                await task_session.rollback()
                return e

    # Execute tasks at the same time
    results = await asyncio.gather(*[run_task(), run_task()])
    
    # Collect successful executions
    succeeded = [r for r in results if isinstance(r, Transfer)]
    assert len(succeeded) >= 1, "At least one execution must succeed"
    
    async with session_factory() as verify_session:
        total_transfers = await verify_session.scalars(
            select(Transfer).where(Transfer.idempotency_key == "same-idem-race-key")
        )
        assert len(total_transfers.all()) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_opposing_transfers_complete_without_deadlock(session_factory: async_sessionmaker[AsyncSession]):
    """
    Simultaneously fires opposing concurrent transfers: A -> B and B -> A.
    Verifies that deterministic row-lock sorting prevents deadlock scenarios.
    """
    async with session_factory() as setup_session:
        acc_a = Account(id=301, currency="USD", balance=1000.0, type="customer")
        acc_b = Account(id=302, currency="USD", balance=1000.0, type="customer")
        setup_session.add_all([acc_a, acc_b])
        await setup_session.commit()

    async def transfer_a_to_b(i: int):
        async with session_factory() as task_session:
            try:
                await execute_transfer(
                    db=task_session,
                    idempotency_key=f"a-to-b-{i}",
                    from_account_id=301,
                    to_account_id=302,
                    amount=10.0,
                    currency="USD"
                )
                await task_session.commit()
            except Exception:
                await task_session.rollback()

    async def transfer_b_to_a(i: int):
        async with session_factory() as task_session:
            try:
                await execute_transfer(
                    db=task_session,
                    idempotency_key=f"b-to-a-{i}",
                    from_account_id=302,
                    to_account_id=301,
                    amount=10.0,
                    currency="USD"
                )
                await task_session.commit()
            except Exception:
                await task_session.rollback()

    # Interleave requests to increase the likelihood of lock conflicts
    tasks = []
    for i in range(10):
        tasks.append(transfer_a_to_b(i))
        tasks.append(transfer_b_to_a(i))

    # Should run and complete without getting stuck in a deadlock
    await asyncio.wait_for(asyncio.gather(*tasks), timeout=10.0)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_http_ledger_lifecycle_flow(client: AsyncClient):
    """
    Executes a complete high-fidelity client workflow:
    1. Register user
    2. Log in (Obtain JWT token)
    3. Create 2 accounts (Sender, Receiver)
    4. Deposit from external source
    5. Execute a cross-account Transfer
    6. Verify statement outputs are sorted newest-first
    """
    # 1. Register a new user
    reg_resp = await client.post(
        "/auth/register", 
        json={"username": "flow_user", "password": "super_secret_password_123"}
    )
    assert reg_resp.status_code == 201
    
    # 2. Log in and acquire a valid Bearer Token
    login_resp = await client.post(
        "/auth/token", 
        data={"username": "flow_user", "password": "super_secret_password_123"}
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 3. Create two accounts (GBP)
    acc1_resp = await client.post("/accounts", json={"currency": "GBP", "type": "customer"}, headers=auth_headers)
    acc2_resp = await client.post("/accounts", json={"currency": "GBP", "type": "customer"}, headers=auth_headers)
    assert acc1_resp.status_code == 201
    assert acc2_resp.status_code == 201
    
    acc1_id = acc1_resp.json()["id"]
    acc2_id = acc2_resp.json()["id"]

    # Register an admin/external system to generate an external source account for deposits
    admin_reg = await client.post(
        "/auth/register", 
        json={"username": "admin_system", "password": "system_admin_password", "role": "admin"}
    )
    admin_login = await client.post(
        "/auth/token", 
        data={"username": "admin_system", "password": "system_admin_password"}
    )
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    # Setup the external system account
    ext_acc_resp = await client.post("/accounts", json={"currency": "GBP", "type": "external"}, headers=admin_headers)
    ext_acc_id = ext_acc_resp.json()["id"]

    # 4. Deposit 500.00 GBP into the user's sender account from the external account
    deposit_resp = await client.post(
        "/transfers", 
        json={
            "from_account_id": ext_acc_id,
            "to_account_id": acc1_id,
            "amount": "500.00",
            "currency": "GBP"
        },
        headers={"Idempotency-Key": "deposit_external_101", **admin_headers}
    )
    assert deposit_resp.status_code == 201

    # 5. Transfer 150.00 GBP from Account 1 to Account 2
    transfer_resp = await client.post(
        "/transfers",
        json={
            "from_account_id": acc1_id,
            "to_account_id": acc2_id,
            "amount": "150.00",
            "currency": "GBP"
        },
        headers={"Idempotency-Key": "internal_transfer_202", **auth_headers}
    )
    assert transfer_resp.status_code == 201

    # 6. Retrieve Account 1's statement and assert order (Newest first)
    statement_resp = await client.get(f"/accounts/{acc1_id}/statement", headers=auth_headers)
    assert statement_resp.status_code == 200
    
    entries = statement_resp.json()["entries"]
    assert len(entries) == 2
    
    # Due to sorting (Newest first, descending ID), the second operation (internal transfer of -150) should be first
    assert float(entries[0]["amount"]) == -150.00
    assert float(entries[1]["amount"]) == 500.00