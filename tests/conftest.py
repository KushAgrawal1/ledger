import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from app.database import Base, get_db
from app.main import app

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(scope="session")
def pg_url():
    """Spins up an isolated PostgreSQL container via Testcontainers."""
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest_asyncio.fixture(scope="session")
async def pg_engine(pg_url):
    """
    Session-scoped engine using NullPool.

    NullPool never reuses connections between sessions — every
    async_sessionmaker() call gets a guaranteed fresh connection.
    This prevents 'another operation is in progress' errors caused
    by dirty connections being returned to a pool after a failed test.
    """
    engine = create_async_engine(pg_url, poolclass=NullPool, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
def session_factory(pg_engine):
    """Session-scoped factory — safe to use in integration tests directly."""
    return async_sessionmaker(
        bind=pg_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=True,
    )


@pytest_asyncio.fixture
async def db_session(pg_engine, session_factory):
    """
    Per-test database session for unit tests.

    Yields a clean session. After the test:
    1. Rolls back any open transaction (handles mid-test failures cleanly)
    2. TRUNCATEs all tables so the next test starts from a blank slate
    """
    async with session_factory() as session:
        yield session
        # Roll back anything left open — catches tests that fail mid-transaction
        await session.rollback()

    # Hard reset — faster than dropping/recreating tables
    async with pg_engine.begin() as conn:
        table_names = [
            f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables)
        ]
        if table_names:
            await conn.execute(
                text(
                    f"TRUNCATE TABLE {', '.join(table_names)} "
                    f"RESTART IDENTITY CASCADE"
                )
            )


@pytest_asyncio.fixture
async def client(pg_engine, session_factory):
    """
    Per-test HTTPX AsyncClient with a fresh isolated database session.

    Overrides the FastAPI get_db dependency so every HTTP request in
    the test hits the same Testcontainers database, not production.
    Table cleanup runs after each test via TRUNCATE.
    """
    async with session_factory() as session:

        async def override_get_db():
            yield session

        app.dependency_overrides[get_db] = override_get_db

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

        app.dependency_overrides.clear()
        await session.rollback()

    # Same hard reset as db_session
    async with pg_engine.begin() as conn:
        table_names = [
            f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables)
        ]
        if table_names:
            await conn.execute(
                text(
                    f"TRUNCATE TABLE {', '.join(table_names)} "
                    f"RESTART IDENTITY CASCADE"
                )
            )
