class LedgerError(Exception):
    """Base exception for all ledger and transaction operations."""
    pass


class InsufficientBalanceError(LedgerError):
    """Raised when an account has insufficient funds to complete a transfer."""
    pass


class IdempotencyKeyConflictError(LedgerError):
    """
    Raised when an incoming request uses an existing idempotency key,
    but the payload details (amounts, accounts, or currency) do not match 
    the original transaction.
    """
    pass


# Alias to maintain compatibility with app/api/exceptions.py
IdempotencyConflictError = IdempotencyKeyConflictError


class CurrencyMismatchError(LedgerError):
    """Raised when transfer currencies do not match the target accounts' native currencies."""
    pass


class AccountNotFoundError(LedgerError):
    """Raised when a requested account identifier does not exist in the database."""
    pass


class InvalidTransferError(LedgerError):
    """Raised when a transfer is structurally invalid (e.g., self-transfers)."""
    pass