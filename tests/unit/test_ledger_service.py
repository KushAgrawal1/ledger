import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.account import Account
from app.models.entry import Entry
from app.services.exceptions import (
    AccountNotFoundError,
    CurrencyMismatchError,
    IdempotencyConflictError,
    InsufficientBalanceError,
    InvalidTransferError,
)
from app.services.ledger import execute_transfer

# Setup async in-memory SQLite engine
DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture
async def db_session():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()

@pytest.fixture
async def setup_accounts(db_session):
    acc1 = Account(id=1, currency="USD", balance=100.0, type="customer")
    acc2 = Account(id=2, currency="USD", balance=50.0, type="customer")
    acc3 = Account(id=3, currency="EUR", balance=50.0, type="customer")
    acc4 = Account(id=4, currency="USD", balance=0.0, type="external")
    db_session.add_all([acc1, acc2, acc3, acc4])
    await db_session.commit()
    return acc1, acc2, acc3, acc4


@pytest.mark.asyncio
async def test_happy_path_transfer(db_session, setup_accounts):
    transfer = await execute_transfer(
        db_session,
        idempotency_key="key_1",
        from_account_id=1,
        to_account_id=2,
        amount=20.0,
        currency="USD"
    )
    await db_session.commit()

    # Validate output structure
    assert transfer.status == "completed"
    
    # Check entries sum and count
    entries_res = await db_session.scalars(select(Entry).where(Entry.transfer_id == transfer.id))
    entries = entries_res.all()
    assert len(entries) == 2
    assert sum(e.amount for e in entries) == 0

    # Validate cached balances
    src_acc = await db_session.get(Account, 1)
    dst_acc = await db_session.get(Account, 2)
    assert src_acc.balance == 80.0
    assert dst_acc.balance == 70.0


@pytest.mark.asyncio
async def test_rejects_negative_or_zero_amount(db_session, setup_accounts):
    with pytest.raises(InvalidTransferError):
        await execute_transfer(db_session, idempotency_key="k", from_account_id=1, to_account_id=2, amount=0, currency="USD")


@pytest.mark.asyncio
async def test_rejects_transfer_to_same_account(db_session, setup_accounts):
    with pytest.raises(InvalidTransferError):
        await execute_transfer(db_session, idempotency_key="k", from_account_id=1, to_account_id=1, amount=10, currency="USD")


@pytest.mark.asyncio
async def test_rejects_mismatched_currency(db_session, setup_accounts):
    with pytest.raises(CurrencyMismatchError):
        await execute_transfer(db_session, idempotency_key="k", from_account_id=1, to_account_id=3, amount=10, currency="USD")


@pytest.mark.asyncio
async def test_rejects_nonexistent_account(db_session, setup_accounts):
    with pytest.raises(AccountNotFoundError):
        await execute_transfer(db_session, idempotency_key="k", from_account_id=1, to_account_id=999, amount=10, currency="USD")


@pytest.mark.asyncio
async def test_rejects_insufficient_balance(db_session, setup_accounts):
    with pytest.raises(InsufficientBalanceError):
        await execute_transfer(db_session, idempotency_key="k", from_account_id=1, to_account_id=2, amount=100.1, currency="USD")


@pytest.mark.asyncio
async def test_allows_external_accounts_to_go_negative(db_session, setup_accounts):
    await execute_transfer(
        db_session, idempotency_key="ext_1", from_account_id=4, to_account_id=1, amount=1000.0, currency="USD"
    )
    await db_session.commit()
    
    ext_acc = await db_session.get(Account, 4)
    assert ext_acc.balance == -1000.0


@pytest.mark.asyncio
async def test_idempotency_returns_original_payload(db_session, setup_accounts):
    t1 = await execute_transfer(db_session, idempotency_key="idem_key", from_account_id=1, to_account_id=2, amount=10.0, currency="USD")
    await db_session.commit()

    t2 = await execute_transfer(db_session, idempotency_key="idem_key", from_account_id=1, to_account_id=2, amount=10.0, currency="USD")
    assert t1.id == t2.id


@pytest.mark.asyncio
async def test_idempotency_raises_conflict_on_different_payload(db_session, setup_accounts):
    await execute_transfer(db_session, idempotency_key="idem_key", from_account_id=1, to_account_id=2, amount=10.0, currency="USD")
    await db_session.commit()

    with pytest.raises(IdempotencyConflictError):
        await execute_transfer(db_session, idempotency_key="idem_key", from_account_id=1, to_account_id=2, amount=25.0, currency="USD")


@pytest.mark.asyncio
async def test_balance_integrity_after_multi_transfers(db_session, setup_accounts):
    # Perform various transfers
    await execute_transfer(db_session, idempotency_key="t1", from_account_id=1, to_account_id=2, amount=10.0, currency="USD")
    await execute_transfer(db_session, idempotency_key="t2", from_account_id=2, to_account_id=1, amount=5.0, currency="USD")
    await db_session.commit()

    # Query directly to see if balance matches the ledger entries
    for acc_id in [1, 2]:
        acc = await db_session.get(Account, acc_id)
        entries_sum_res = await db_session.execute(
            select(func.sum(Entry.amount)).where(Entry.account_id == acc_id)
        )
        entries_sum = entries_sum_res.scalar() or 0.0
        
        # Initial starting balance + sum of all transaction entries == current balance
        initial_balance = 100.0 if acc_id == 1 else 50.0
        assert acc.balance == initial_balance + entries_sum