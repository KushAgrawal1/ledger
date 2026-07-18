from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.exceptions import ledger_exception_handler
from app.api.routes import account_router
from app.api.routes import router as api_router
from app.services.exceptions import LedgerError

app = FastAPI(title="Distributed Ledger API")

# Register our domain-to-HTTP exception mapping handler
app.add_exception_handler(LedgerError, ledger_exception_handler)

# 1. Include the Authentication Routes (/auth/register, /auth/token)
app.include_router(auth_router)

# 2. Include the Accounts Routes (/accounts, /accounts/{id}, /accounts/{id}/statement)
app.include_router(account_router)

# 3. Include the Core Transfers and Readiness Routes (/transfers, /readyz)
app.include_router(api_router)


# ==========================================
# LIVENESS PROBE
# ==========================================
@app.get("/healthz", status_code=200)
async def healthz():
    """Simple liveness probe indicating the application process is running."""
    return {"status": "healthy"}