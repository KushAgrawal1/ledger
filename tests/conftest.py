import asyncio
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from testcontainers.postgres import PostgresContainer

from app.database import Base, get_db
from app.main import app

# Force loop scope to session for concurrent executions
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
def pg_url():
    """
    Spins up an isolated PostgreSQL container using Testcontainers.
    Yields an async-compatible asyncpg database connection URL.
    """
    # Force driver to asyncpg natively
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        connection_url = pg.get_connection_url()
        yield connection_url

@pytest.fixture(scope="session")
async def pg_engine(pg_url):
    """Creates a persistent SQLAlchemy database engine for the test container."""
    engine = create_async_engine(
        pg_url, 
        pool_size=30,          # Large pool to support high-concurrency testing
        max_overflow=10, 
        echo=False
    )
    
    # Programmatic database setup using Alembic (to match production schema layout)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    yield engine
    await engine.dispose()

@pytest.fixture(scope="session")
def session_factory(pg_engine):
    """Yields a thread-safe Async Session Factory mapped to the Postgres instance."""
    return async_sessionmaker(bind=pg_engine, class_=AsyncSession, expire_on_commit=False)

@pytest.fixture
async def session(pg_engine, session_factory):
    """
    Yields an active database session for tests.
    Truncates all tables (excluding system tables) after each test to guarantee complete isolation.
    """
    async with session_factory() as session:
        yield session
        
    # Isolation: Truncate tables between individual runs
    async with pg_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE;'))

@pytest.fixture
async def client(session):
    """
    Configures an HTTPX AsyncClient targeting the application.
    Overrides FastAPI's `get_db` dependency to use the active container session.
    """
    from httpx import AsyncClient, ASGITransport

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()