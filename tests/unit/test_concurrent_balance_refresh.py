"""
Regression tests for a real concurrency bug: execute_transfer() acquires a
FOR UPDATE row lock correctly, but if the caller (the real route handler
always does this, for its ownership check) already loaded the same Account
into this session's identity map earlier in the request, SQLAlchemy does
NOT refresh that object's attributes just because it is selected again -
it hands back the same cached Python object. The database-level lock is
real; the balance this code then reads and writes from was not.

These tests use two independent sessions against the same temp-file
SQLite database (an in-memory DB is private per connection, so it can't
simulate a second, concurrent transaction) to reproduce exactly that
sequence: pre-fetch, concurrent write + commit elsewhere, then the
locking re-select execute_transfer() performs.
"""
import os
import tempfile
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.account import Account
from app.models.entry import Entry  # noqa: F401 - needed for Base.metadata FKs
from app.models.transfer import Transfer  # noqa: F401
from app.models.user import User  # noqa: F401
from app.services.exceptions import InsufficientBalanceError
from app.services.ledger import execute_transfer


@pytest.fixture
async def two_sessions():
    """A temp-file SQLite DB (not :memory:) so two independent engine
    connections can see the same data, plus a factory for making more
    independent sessions against it."""
    path = tempfile.mktemp(suffix=".db")
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    make_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with make_session() as seed:
        seed.add(Account(id=1, currency="USD", balance=Decimal("100.00"), type="customer"))
        seed.add(Account(id=2, currency="USD", balance=Decimal("0.00"), type="customer"))
        await seed.commit()

    session_a = make_session()
    yield session_a, make_session

    await session_a.close()
    await engine.dispose()
    os.remove(path)


async def _drain_account_1_to(make_session, new_balance: Decimal):
    """Simulates a different request's transfer that already completed
    and committed, using its own independent session/connection."""
    async with make_session() as other:
        acc = await other.get(Account, 1)
        acc.balance = new_balance
        await other.commit()


@pytest.mark.asyncio
async def test_balance_check_uses_fresh_data_not_a_stale_prefetch(two_sessions):
    """Mirrors app/api/routes.py's create_transfer(): it fetches the
    source account for an ownership check BEFORE calling execute_transfer
    on the same session - exactly the sequence that triggers the bug."""
    session_a, make_session = two_sessions

    # The route handler's ownership-check pre-fetch, unlocked.
    pre_fetched = await session_a.get(Account, 1)
    assert pre_fetched.balance == Decimal("100.00")

    # A concurrent transfer elsewhere already drained this account to 5.00
    # and committed, before execute_transfer ever takes its lock.
    await _drain_account_1_to(make_session, Decimal("5.00"))

    # The account can no longer cover a 50.00 transfer. If execute_transfer
    # were reading the stale pre-fetched 100.00, this would wrongly succeed.
    with pytest.raises(InsufficientBalanceError):
        await execute_transfer(
            session_a, idempotency_key="k1",
            from_account_id=1, to_account_id=2,
            amount=50.0, currency="USD",
        )


@pytest.mark.asyncio
async def test_successful_transfer_debits_from_the_fresh_balance(two_sessions):
    """Even when the transfer DOES succeed, the resulting balance must be
    computed from the real, current balance - not the number the caller
    happened to have cached before the lock was acquired."""
    session_a, make_session = two_sessions

    # Route handler's pre-fetch, held as a variable exactly like the real
    # app/api/routes.py does (src_account = await db.get(...), then used
    # again for the ownership check) - SQLAlchemy's identity map holds
    # WEAK references, so an unused, un-referenced pre-fetch would get
    # garbage-collected before execute_transfer ever runs and this test
    # would pass for the wrong reason, never exercising the real bug.
    src_account = await session_a.get(Account, 1)
    assert src_account.balance == Decimal("100.00")

    # Concurrently, the account's real balance drops to 80.00 and commits.
    await _drain_account_1_to(make_session, Decimal("80.00"))

    await execute_transfer(
        session_a, idempotency_key="k2",
        from_account_id=1, to_account_id=2,
        amount=50.0, currency="USD",
    )
    await session_a.commit()

    async with make_session() as verify:
        acc1 = await verify.get(Account, 1)
        # Correct: 80.00 - 50.00 = 30.00. The bug would have produced
        # 100.00 - 50.00 = 50.00, silently erasing the concurrent debit.
        assert acc1.balance == Decimal("30.00")


@pytest.mark.asyncio
async def test_locking_select_refreshes_an_already_identity_mapped_account(two_sessions):
    """Narrower unit check on the mechanism itself, independent of
    execute_transfer's business logic: after the populate_existing select,
    the SAME Python object must reflect the DB's current row."""
    session_a, make_session = two_sessions

    acc = await session_a.get(Account, 1)
    assert acc.balance == Decimal("100.00")

    await _drain_account_1_to(make_session, Decimal("42.00"))

    await session_a.execute(
        select(Account).where(Account.id == 1)
        .with_for_update().execution_options(populate_existing=True)
    )
    refreshed = await session_a.get(Account, 1)

    assert refreshed is acc            # same identity-mapped object
    assert refreshed.balance == Decimal("42.00")   # but now holding fresh data
