from sqlalchemy import select
from app.models.account import Account
from app.models.transfer import Transfer
from app.models.entry import Entry
from app.services.exceptions import (
    IdempotencyConflictError,
    AccountNotFoundError,
    CurrencyMismatchError,
    InsufficientBalanceError,
    InvalidTransferError
)

async def execute_transfer(session, *, idempotency_key: str, from_account_id: int, to_account_id: int, amount: float, currency: str) -> Transfer:
    # 0. Basic Validation
    if amount <= 0:
        raise InvalidTransferError("Transfer amount must be greater than zero.")
    if from_account_id == to_account_id:
        raise InvalidTransferError("Cannot transfer to the same account.")

    # 1. Idempotency check
    existing = await session.scalar(
        select(Transfer).where(Transfer.idempotency_key == idempotency_key)
    )
    if existing:
        if (existing.from_account_id, existing.to_account_id, float(existing.amount), existing.currency) != \
           (from_account_id, to_account_id, float(amount), currency):
            raise IdempotencyConflictError(idempotency_key)
        return existing  # replay: return original result

    # 2. Lock both accounts in DETERMINISTIC ORDER (prevents deadlocks)
    first, second = sorted([from_account_id, to_account_id])
    accounts = {}
    for acc_id in (first, second):
        acc = await session.scalar(
            select(Account).where(Account.id == acc_id).with_for_update()
        )
        if acc is None:
            raise AccountNotFoundError(acc_id)
        accounts[acc.id] = acc

    src, dst = accounts[from_account_id], accounts[to_account_id]

    # 3. Currency & Balance Validation
    if src.currency != currency or dst.currency != currency:
        raise CurrencyMismatchError()
    if src.type != "external" and src.balance < amount:
        raise InsufficientBalanceError(src.id)

    # 4. Write transfer + two entries + update cached balances (one transaction context)
    transfer = Transfer(
        idempotency_key=idempotency_key, 
        from_account_id=src.id,
        to_account_id=dst.id, 
        amount=amount, 
        currency=currency,
        status="completed"
    )
    session.add(transfer)
    await session.flush()

    session.add_all([
        Entry(transfer_id=transfer.id, account_id=src.id, amount=-amount),
        Entry(transfer_id=transfer.id, account_id=dst.id, amount=amount),
    ])
    
    src.balance -= amount
    dst.balance += amount
    
    return transfer