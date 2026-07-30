Ledger

A double-entry ledger REST API built with FastAPI, PostgreSQL, and SQLAlchemy. Supports account creation, authenticated transfers between accounts, and paginated statements, with idempotency handling and deadlock-safe balance updates.

Features


Double-entry transfers — every transfer writes two linked Entry rows (debit and credit) and updates account balances atomically
Deadlock-safe locking — accounts involved in a transfer are locked in a deterministic order (sorted by ID) using SELECT ... FOR UPDATE, so concurrent transfers can't deadlock each other
Idempotent transfers — every transfer request requires an Idempotency-Key header; replaying the same key returns the original result, and reusing a key with a different payload returns a 409 conflict
JWT authentication — user registration and login issue short-lived JWTs (HS256), with passwords hashed via bcrypt
Role-based access control — customers can only view/transfer from their own accounts; admins can access any account
Structured error handling — domain errors (insufficient balance, currency mismatch, account not found, idempotency conflict, invalid transfer) are mapped to appropriate HTTP status codes and JSON error bodies
Database migrations — schema managed with Alembic


Tech stack


Language: Python 3.12
Framework: FastAPI (async)
Database: PostgreSQL, SQLAlchemy (async), Alembic
Auth: python-jose (JWT), passlib/bcrypt
Testing: pytest, pytest-asyncio, Testcontainers (spins up a real Postgres instance for integration tests)
Linting: ruff


Getting started

Prerequisites


Python 3.12+
Docker (for the local PostgreSQL instance and for running the test suite)


Setup

bashgit clone https://github.com/KushAgrawal1/ledger.git
cd ledger
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

Run PostgreSQL locally

bashdocker compose up -d

This starts a postgres:16-alpine container on localhost:5432 (user/password/db: ledger).

Apply migrations

bashalembic upgrade head

Run the API

bashuvicorn app.main:app --reload

The API will be available at http://localhost:8000. Interactive docs are at http://localhost:8000/docs.

Running tests

Tests use Testcontainers to spin up an isolated PostgreSQL container, so Docker must be running.

bashpytest

Coverage is enforced via pyproject.toml (fail_under = 90, scoped to the app package).

API overview

MethodEndpointDescriptionPOST/auth/registerCreate a user accountPOST/auth/tokenLog in and receive a JWTPOST/accountsCreate an account (requires auth)GET/accounts/{id}Get account details and balanceGET/accounts/{id}/statementPaginated list of entries for an accountPOST/transfersTransfer funds between accounts (idempotent)GET/transfers/{id}Get transfer detailsGET/healthzLiveness probeGET/readyzReadiness probe (checks DB connectivity)

Project structure

app/
├── api/          # Routes, request/response schemas, auth dependencies, exception mapping
├── core/         # Security utilities (password hashing, JWT creation)
├── models/       # SQLAlchemy models (User, Account, Transfer, Entry)
├── services/     # Core ledger business logic (transfer execution)
├── database.py   # Engine/session setup
└── main.py       # FastAPI app entrypoint
alembic/          # Database migrations
tests/
├── api/          # Endpoint-level tests
└── unit/         # Service-layer tests

Roadmap / not yet implemented


Containerising the API itself (currently only PostgreSQL runs via Docker Compose)
CI pipeline (GitHub Actions workflow directory exists but is not yet configured)
Event publishing (e.g. Kafka) for downstream consumers such as audit trails or notifications

![CI](https://github.com/KushAgrawal1/ledger/actions/workflows/ci.yml/badge.svg)