from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

# ── Auth ──────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=150)
    password: str = Field(..., min_length=6)
    role: str | None = "customer"

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str


# ── Accounts ──────────────────────────────────────────────────────────────────

class AccountCreate(BaseModel):
    currency: str = Field(..., min_length=3, max_length=3)
    type: str = Field("customer", pattern="^(customer|external)$")

class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    currency: str
    balance: Decimal
    type: str
    owner_id: int | None = None


# ── Transfers & Entries ───────────────────────────────────────────────────────

class TransferRequest(BaseModel):
    from_account_id: int
    to_account_id: int
    amount: Decimal = Field(..., gt=0, max_digits=18, decimal_places=4)
    currency: str = Field(..., min_length=3, max_length=3)

class TransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    idempotency_key: str
    from_account_id: int
    to_account_id: int
    amount: Decimal
    currency: str
    status: str

class EntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    transfer_id: int
    account_id: int
    amount: Decimal


# ── Statement ─────────────────────────────────────────────────────────────────

class StatementResponse(BaseModel):
    entries: list[EntryResponse]
    limit: int
    offset: int


# ── Kafka event ───────────────────────────────────────────────────────────────

class TransferCompletedEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    schema_version: int = Field(default=1, frozen=True)
    event_id: str
    transfer_id: int
    from_account_id: int
    to_account_id: int
    amount: Decimal
    currency: str
    timestamp: datetime
