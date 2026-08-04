from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.exceptions import ledger_exception_handler
from app.api.routes import account_router
from app.api.routes import router as api_router
from app.core.logging_config import RequestIDMiddleware, configure_logging
from app.services.exceptions import LedgerError

configure_logging()

app = FastAPI(title="Distributed Ledger API")

# Structured JSON logging with per-request trace ID
app.add_middleware(RequestIDMiddleware)

# Map domain exceptions to structured HTTP responses
app.add_exception_handler(LedgerError, ledger_exception_handler)

# Auth routes: /auth/register, /auth/token, /auth/refresh
app.include_router(auth_router)

# Account routes: /accounts, /accounts/{id}, /accounts/{id}/statement
app.include_router(account_router)

# Transfer and health routes: /transfers, /readyz
app.include_router(api_router)


@app.get("/healthz", status_code=200)
async def healthz():
    """Liveness probe — confirms the process is running, no DB check."""
    return {"status": "healthy"}
