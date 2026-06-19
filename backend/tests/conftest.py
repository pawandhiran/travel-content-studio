"""Shared test fixtures for Travel Content Studio backend."""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

os.environ["TCS_DATA_DIR"] = tempfile.mkdtemp(prefix="tcs_test_")

from main import create_app
from models.db_models import Base
from core.database import get_db


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_engine():
    """Create a fresh in-memory database for each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Provide a database session for tests."""
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest_asyncio.fixture
async def app(db_engine):
    """Create a test FastAPI application."""
    test_app = create_app()

    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with async_session() as session:
            yield session

    test_app.dependency_overrides[get_db] = override_get_db
    return test_app


@pytest_asyncio.fixture
async def client(app):
    """Create an async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_project_data():
    """Sample project creation data."""
    return {
        "name": "Test Bali Vlog",
        "description": "A week in Bali - temples, rice terraces, and beaches",
    }


@pytest.fixture
def temp_dir():
    """Provide a temporary directory for test files."""
    with tempfile.TemporaryDirectory(prefix="tcs_test_") as d:
        yield Path(d)
