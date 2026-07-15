class LedgerError(Exception):
    """Base error for ledger operations."""

class IdempotencyConflictError(LedgerError):
    def __init__(self, key: str):
        super().__init__(f"Conflict: Idempotency key '{key}' already exists with a different payload.")

class AccountNotFoundError(LedgerError):
    def __init__(self, account_id: int):
        super().__init__(f"Account {account_id} not found.")

class CurrencyMismatchError(LedgerError):
    def __init__(self):
        super().__init__("Transfer currency must match both source and destination accounts.")

class InsufficientBalanceError(LedgerError):
    def __init__(self, account_id: int):
        super().__init__(f"Account {account_id} has insufficient funds.")

class InvalidTransferError(LedgerError):
    def __init__(self, message: str):
        super().__init__(message)