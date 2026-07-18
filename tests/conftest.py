import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from testcontainers.postgres import PostgresContainer

from app.database import Base, get_db
from app.main import app

# --- CONFIGURATION & EVENT LOOP MANAGEMENT ---
# Setting the default loop scope to "session" ensures all async fixtures and tests
# share the same event loop, preventing "Event loop is closed" errors.
pytestmark = pytest.mark.asyncio(loop_scope="session")

@pytest_asyncio.fixture(scope="session")
def pg_url():
    """
    Spins up an isolated PostgreSQL container using Testcontainers.
    Yields an async-compatible asyncpg database connection URL.
    """
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()

@pytest_asyncio.fixture(scope="session")
async def pg_engine(pg_url):
    """Creates a persistent SQLAlchemy database engine for the test container."""
    engine = create_async_engine(
        pg_url, 
        pool_size=30,          # Supported high-concurrency testing
        max_overflow=10, 
        echo=False
    )
    
    # Run migrations/table creation once per session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture(scope="session")
def session_factory(pg_engine):
    """Yields a thread-safe Async Session Factory mapped to the Postgres instance."""
    return async_sessionmaker(bind=pg_engine, class_=AsyncSession, expire_on_commit=False)

@pytest_asyncio.fixture
async def session(pg_engine, session_factory):
    """
    Yields an active database session for tests.
    Truncates all user tables after each test to guarantee complete isolation.
    """
    async with session_factory() as session:
        yield session
        
    # Isolation: Fast truncation of all tables to clean state
    async with pg_engine.begin() as conn:
        # Generate the dynamic truncation SQL in a single execute step
        table_names = [f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables)]
        if table_names:
            tables_csv = ", ".join(table_names)
            await conn.execute(text(f"TRUNCATE TABLE {tables_csv} RESTART IDENTITY CASCADE;"))

@pytest_asyncio.fixture
async def client(session):
    """
    Configures an HTTPX AsyncClient targeting the FastAPI application.
    Overrides the database dependency dynamically and cleans it up after the test.
    """
    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
        
    app.dependency_overrides.clear()