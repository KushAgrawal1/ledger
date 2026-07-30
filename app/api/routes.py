from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schemas import (
    AccountCreate,
    AccountResponse,
    StatementResponse,
    TransferRequest,
    TransferResponse,
)
from app.database import get_db
from app.models.account import Account
from app.models.entry import Entry
from app.models.transfer import Transfer
from app.models.user import User
from app.services.ledger import execute_transfer

# We split into two routers to match Phase 4 specs: 
# account_router (prefixed in main.py) and router (for transfers/health)
router = APIRouter()
account_router = APIRouter(prefix="/accounts", tags=["accounts"])


# ==========================================
# ACCOUNTS ENDPOINTS (Phase 4 & 5)
# ==========================================

@account_router.post(
    "", 
    response_model=AccountResponse, 
    status_code=status.HTTP_201_CREATED
)
async def create_account(
    payload: AccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create account (GBP or custom currency) tied to authenticated user."""
    new_account = Account(
        currency=payload.currency,
        balance=0.0,
        type=payload.type,
        owner_id=current_user.id
    )
    db.add(new_account)
    await db.commit()
    await db.refresh(new_account)
    return new_account


@account_router.get(
    "/{id}", 
    response_model=AccountResponse
)
async def get_account(
    id: int, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve account + balance. Returns 404 instead of 403 to prevent resource leaks."""
    account = await db.get(Account, id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        
    # Guard: Customer can access own accounts only; admin can access any
    if current_user.role != "admin" and account.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        
    return account


@account_router.get(
    "/{id}/statement", 
    response_model=StatementResponse
)
async def get_statement(
    id: int,
    limit: int = 10,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Returns paginated entries, sorted newest first."""
    account = await db.get(Account, id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        
    if current_user.role != "admin" and account.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    # Order newest entries first
    query = (
        select(Entry)
        .where(Entry.account_id == id)
        .order_by(desc(Entry.id))
        .limit(limit)
        .offset(offset)
    )
    result = await db.scalars(query)
    entries = result.all()

    return {
        "entries": entries,
        "limit": limit,
        "offset": offset
    }


# ==========================================
# TRANSFERS ENDPOINTS (Phase 4 & 5)
# ==========================================

@router.post(
    "/transfers", 
    response_model=TransferResponse, 
    status_code=status.HTTP_201_CREATED
)
async def create_transfer(
    payload: TransferRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Execute a transfer securely inside a row-locked domain context."""
    # Guard: Verify transferring out of an account owned by current user (or Admin bypass)
    src_account = await db.get(Account, payload.from_account_id)
    if not src_account:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source account not found")
         
    if current_user.role != "admin" and src_account.owner_id != current_user.id:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source account not found")

    transfer = await execute_transfer(
        db,
        idempotency_key=idempotency_key,
        from_account_id=payload.from_account_id,
        to_account_id=payload.to_account_id,
        amount=payload.amount,
        currency=payload.currency
    )
    
    await db.commit()
    return transfer


@router.get(
    "/transfers/{id}", 
    response_model=TransferResponse
)
async def get_transfer(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get transfer details if the user is a participant or an admin."""
    transfer = await db.get(Transfer, id)
    if not transfer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer not found")

    # Assert participant status or admin permissions
    from_acc = await db.get(Account, transfer.from_account_id)
    to_acc   = await db.get(Account, transfer.to_account_id)
    is_participant = (
        (from_acc and from_acc.owner_id == current_user.id) or
        (to_acc   and to_acc.owner_id   == current_user.id)
    )
    if current_user.role != "admin" and not is_participant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer not found")

    return transfer


# ==========================================
# HEALTH ENDPOINTS (Phase 4)
# ==========================================

@router.get("/readyz", status_code=status.HTTP_200_OK)
async def readyz(db: AsyncSession = Depends(get_db)):
    """Verifies connection with Postgres before declaring ready."""
    try:
        await db.execute(select(1))
        return {"status": "ready"}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failure"
        ) from None