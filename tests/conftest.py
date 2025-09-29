import pytest
import asyncio
from typing import AsyncGenerator
from httpx import AsyncClient
from fastapi import FastAPI
from unittest.mock import MagicMock, patch

from app.main import create_main_app
from app.core.db import get_session


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
def app():
    """Create app instance for testing."""
    app = create_main_app()

    # Mock session để không cần kết nối DB thật
    mock_session = MagicMock()

    async def override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_get_session
    return app


@pytest.fixture
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Return an async client for testing."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
