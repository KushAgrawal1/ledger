from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.entry import Entry
from app.models.transfer import Transfer
from app.services.exceptions import (
    AccountNotFoundError,
    CurrencyMismatchError,
    IdempotencyKeyConflictError,
    InsufficientBalanceError,
    InvalidTransferError,
)
from app.services.publisher import TransferEventPublisher


def _to_decimal(value) -> Decimal:
    """
    Safely convert any numeric type to Decimal.
    Needed because fixture-created Account objects hold Python floats,
    while DB-fetched objects return Decimal from the Numeric column.
    """
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


async def execute_transfer(
    db: AsyncSession,
    idempotency_key: str,
    from_account_id: int,
    to_account_id: int,
    amount: float | Decimal,
    currency: str,
    publisher: TransferEventPublisher | None = None,
) -> Transfer:

    # 1. Validate inputs before touching the database
    amount = _to_decimal(amount)

    if amount <= Decimal("0"):
        raise InvalidTransferError("Transfer amount must be positive")

    if from_account_id == to_account_id:
        raise InvalidTransferError("Source and destination accounts must differ")

    # 2. Idempotency check
    existing = (await db.execute(
        select(Transfer).where(Transfer.idempotency_key == idempotency_key)
    )).scalar_one_or_none()

    if existing:
        if (
            existing.from_account_id != from_account_id
            or existing.to_account_id != to_account_id
            or _to_decimal(existing.amount) != amount
            or existing.currency != currency
        ):
            raise IdempotencyKeyConflictError("Idempotency key payload mismatch")
        return existing

    # 3. Lock rows in deterministic order to prevent deadlocks
    first_id, second_id = sorted([from_account_id, to_account_id])

    await db.execute(
        select(Account).where(Account.id == first_id).with_for_update()
    )
    await db.execute(
        select(Account).where(Account.id == second_id).with_for_update()
    )

    from_acc = await db.get(Account, from_account_id)
    to_acc = await db.get(Account, to_account_id)

    if from_acc is None:
        raise AccountNotFoundError(f"Source account {from_account_id} not found")
    if to_acc is None:
        raise AccountNotFoundError(f"Destination account {to_account_id} not found")

    # 4. Currency check — raises CurrencyMismatchError (not InvalidTransferError)
    if from_acc.currency != currency or to_acc.currency != currency:
        raise CurrencyMismatchError(
            f"Currency mismatch: accounts use "
            f"{from_acc.currency}/{to_acc.currency}, transfer requested {currency}"
        )

    # 5. Balance check — external accounts are allowed to go negative (they fund the system)
    from_balance = _to_decimal(from_acc.balance)
    if from_acc.type != "external" and from_balance < amount:
        raise InsufficientBalanceError(
            f"Insufficient balance: have {from_balance}, need {amount}"
        )

    # 6. Atomic balance update
    from_acc.balance = from_balance - amount
    to_acc.balance = _to_decimal(to_acc.balance) + amount

    transfer = Transfer(
        idempotency_key=idempotency_key,
        from_account_id=from_account_id,
        to_account_id=to_account_id,
        amount=amount,
        currency=currency,
    )
    db.add(transfer)
    await db.flush()

    db.add_all([
        Entry(account_id=from_account_id, transfer_id=transfer.id, amount=-amount),
        Entry(account_id=to_account_id,   transfer_id=transfer.id, amount=amount),
    ])

    if publisher:
        try:
            await publisher.publish_transfer_completed(transfer)
        except Exception:
            pass

    return transfer
