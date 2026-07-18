from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.services.exceptions import (
    AccountNotFoundError,
    CurrencyMismatchError,
    IdempotencyConflictError,
    InsufficientBalanceError,
    InvalidTransferError,
    LedgerError,
)


async def ledger_exception_handler(request: Request, exc: LedgerError):
    """
    Maps clean domain-level exceptions to structured HTTP responses.
    This keeps HTTP logic completely out of your core ledger services.
    """
    error_code = "internal_error"
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    if isinstance(exc, InsufficientBalanceError):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        error_code = "insufficient_balance"
    elif isinstance(exc, AccountNotFoundError):
        # We return 404 for missing accounts to prevent leaking existence
        status_code = status.HTTP_404_NOT_FOUND
        error_code = "account_not_found"
    elif isinstance(exc, CurrencyMismatchError):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        error_code = "currency_mismatch"
    elif isinstance(exc, IdempotencyConflictError):
        status_code = status.HTTP_409_CONFLICT
        error_code = "idempotency_conflict"
    elif isinstance(exc, InvalidTransferError):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        error_code = "invalid_transfer"

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": error_code,
                "message": str(exc)
            }
        }
    )