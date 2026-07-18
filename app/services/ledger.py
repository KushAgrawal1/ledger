from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.entry import Entry
from app.models.transfer import Transfer
from app.services.exceptions import (
    CurrencyMismatchError,
    IdempotencyKeyConflictError,
    InsufficientBalanceError,
)
from app.services.publisher import TransferEventPublisher


async def execute_transfer(
    db: AsyncSession,
    idempotency_key: str,
    from_account_id: int,
    to_account_id: int,
    amount: float,
    currency: str,
    publisher: TransferEventPublisher | None = None
) -> Transfer:
    # 1. Deduplication guard check
    existing_tx_query = await db.execute(
        select(Transfer).where(Transfer.idempotency_key == idempotency_key)
    )
    existing_tx = existing_tx_query.scalar_one_or_none()
    if existing_tx:
        # Prevent payload mutations across identical keys
        if (existing_tx.from_account_id != from_account_id or 
            existing_tx.to_account_id != to_account_id or 
            existing_tx.amount != amount or 
            existing_tx.currency != currency):
            raise IdempotencyKeyConflictError("Idempotency key payload mismatch")
        return existing_tx

    # 2. Prevent race deadlocks by locking rows in deterministic ID order
    first_lock_id, second_lock_id = sorted([from_account_id, to_account_id])
    
    # Executing row-locking queries
    await db.execute(
        select(Account).where(Account.id == first_lock_id).with_for_update()
    )
    await db.execute(
        select(Account).where(Account.id == second_lock_id).with_for_update()
    )

    # Fetch fresh post-lock accounts
    from_acc = await db.get(Account, from_account_id)
    to_acc = await db.get(Account, to_account_id)

    if not from_acc or not to_acc:
        raise ValueError("Invalid account identifiers provided")

    # 3. Currency matching checks
    if from_acc.currency != currency or to_acc.currency != currency:
        raise CurrencyMismatchError("Transaction currency must match target accounts")

    # 4. Solvency validation
    # If source is an external system account, skip balance check (source of funds)
    if from_acc.type != "external" and from_acc.balance < amount:
         raise InsufficientBalanceError(f"Insufficient funds inside account {from_account_id}")

    # 5. Mutate balances atomically
    from_acc.balance -= amount
    to_acc.balance += amount

    # 6. Create atomic transfer record
    transfer = Transfer(
        idempotency_key=idempotency_key,
        from_account_id=from_account_id,
        to_account_id=to_account_id,
        amount=amount,
        currency=currency
    )
    db.add(transfer)
    await db.flush() # Secure valid ID before commit

    # 7. Create ledger entries (Double-entry principle)
    from_entry = Entry(account_id=from_account_id, transfer_id=transfer.id, amount=-amount)
    to_entry = Entry(account_id=to_account_id, transfer_id=transfer.id, amount=amount)
    db.add_all([from_entry, to_entry])

    # Save details to DB context
    await db.commit()

    # 8. Post-Commit Callback: Publish completed transfer event
    if publisher is not None:
        await publisher.publish_transfer_completed(transfer)

    return transfer