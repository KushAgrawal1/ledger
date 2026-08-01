# Ledger

![CI](https://github.com/KushAgrawal1/ledger/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Coverage](https://img.shields.io/badge/coverage-93%25-brightgreen)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688)

A double-entry ledger REST API built with FastAPI, PostgreSQL, and Kafka. Features idempotent transfers, deadlock-safe row locking, JWT authentication, role-based access control, and full Alembic migration history.

## Features

- **Double-entry transfers** — every transfer writes two linked Entry rows atomically
- **Deadlock-safe locking** — accounts locked in deterministic ID order via `SELECT FOR UPDATE`
- **Idempotent transfers** — replay the same `Idempotency-Key` safely; conflicts return 409
- **JWT authentication** — HS256 tokens via PyJWT with explicit algorithm allowlist (CVE-2024-33664 mitigated)
- **Role-based access control** — customers access only their own accounts; admins access any
- **Kafka event publishing** — completed transfers publish to `ledger.transfers` topic for downstream consumers
- **Structured error handling** — domain errors map to typed HTTP responses with error codes
- **Database migrations** — full Alembic history with performance indices on all query-critical columns

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Framework | FastAPI (async) |
| Database | PostgreSQL 16, SQLAlchemy 2 (async), Alembic |
| Auth | PyJWT, bcrypt |
| Events | Kafka (aiokafka), KRaft mode |
| Testing | pytest, pytest-asyncio, Testcontainers |
| Linting | ruff |
| CI | GitHub Actions |

## Getting started

```bash
git clone https://github.com/KushAgrawal1/ledger.git
cd ledger
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in SECRET_KEY
```

### Run locally

```bash
docker compose up -d db kafka   # start Postgres + Kafka
alembic upgrade head            # apply migrations
uvicorn app.main:app --reload   # start API
```

API available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Run tests

Tests use Testcontainers — Docker must be running.

```bash
pytest --cov=app
```

## API overview

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Create a user account |
| POST | `/auth/token` | Log in and receive a JWT |
| POST | `/accounts` | Create an account |
| GET | `/accounts/{id}` | Get account details and balance |
| GET | `/accounts/{id}/statement` | Paginated entry history |
| POST | `/transfers` | Transfer funds (idempotent) |
| GET | `/transfers/{id}` | Get transfer details |
| GET | `/healthz` | Liveness probe |
| GET | `/readyz` | Readiness probe (checks DB) |

## Project structure
app/
├── api/ # Routes, schemas, auth dependencies, exception mapping
├── core/ # Security utilities, config
├── models/ # SQLAlchemy models
├── services/ # Ledger business logic, Kafka publisher
└── database.py # Async engine and session
alembic/ # Database migrations
tests/
├── api/ # Endpoint-level tests
├── integration/ # Concurrent transfer and Kafka tests
└── unit/ # Service-layer tests
