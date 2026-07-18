from pydantic import BaseModel, Field
from typing import List, Optional
from decimal import Decimal
from datetime import datetime

# ==========================================
# AUTH SCHEMAS (Phase 5)
# ==========================================

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=150)
    password: str = Field(..., min_length=6)
    role: Optional[str] = "customer"  # "customer" or "admin"

class UserResponse(BaseModel):
    id: int
    username: str
    role: str

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str


# ==========================================
# ACCOUNT SCHEMAS (Phase 4)
# ==========================================

class AccountCreate(BaseModel):
    currency: str = Field(..., min_length=3, max_length=3)
    type: str = Field("customer", pattern="^(customer|external)$")

class AccountResponse(BaseModel):
    id: int
    currency: str
    balance: Decimal
    type: str
    owner_id: Optional[int] = None

    class Config:
        from_attributes = True


# ==========================================
# TRANSFER & ENTRY SCHEMAS (Phase 4)
# ==========================================

class TransferRequest(BaseModel):
    from_account_id: int
    to_account_id: int
    amount: Decimal = Field(..., gt=0, max_digits=18, decimal_places=4)
    currency: str = Field(..., min_length=3, max_length=3)

class TransferResponse(BaseModel):
    id: int
    idempotency_key: str
    from_account_id: int
    to_account_id: int
    amount: Decimal
    currency: str
    status: str

    class Config:
        from_attributes = True

class EntryResponse(BaseModel):
    id: int
    transfer_id: int
    account_id: int
    amount: Decimal

    class Config:
        from_attributes = True


# ==========================================
# STATEMENT SCHEMAS (Phase 4)
# ==========================================

class StatementResponse(BaseModel):
    entries: List[EntryResponse]
    limit: int
    offset: int


# ==========================================
# KAFKA EVENT SCHEMAS (Phase 8)
# ==========================================

class TransferCompletedEvent(BaseModel):
    schema_version: int = Field(default=1, frozen=True)
    event_id: str
    transfer_id: int
    from_account_id: int
    to_account_id: int
    amount: Decimal
    currency: str
    timestamp: datetime

    class Config:
        from_attributes = True