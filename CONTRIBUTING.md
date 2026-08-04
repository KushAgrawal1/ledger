# Contributing

## Local setup

```bash
git clone https://github.com/KushAgrawal1/ledger.git
cd ledger
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add your SECRET_KEY
```

## Running the stack

```bash
docker compose up -d db kafka   # Postgres + Kafka
alembic upgrade head            # apply migrations
uvicorn app.main:app --reload   # API on :8000
```

## Running tests

Docker must be running (Testcontainers spins up a real Postgres container).

```bash
pytest --cov=app
```

## Code style

```bash
ruff check .        # lint
ruff check --fix .  # auto-fix
```

CI enforces ruff and 90% coverage on every push. PRs that fail either will not be merged.

## Commit style

Use conventional commits:
- `feat:` new feature
- `fix:` bug fix
- `chore:` tooling, deps, config
- `test:` test changes only
- `docs:` documentation only
