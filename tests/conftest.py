from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import aio_pika
import httpx
import pytest
import respx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _load_env_tests_file() -> None:
    """Load key=value pairs from repo-root .env.tests for pytest runs."""
    env_path = Path(__file__).resolve().parents[1] / ".env.tests"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_tests_file()

TEST_API_BASE_URL = os.getenv("TEST_API_BASE_URL", "http://localhost:8000")
TEST_MODE = os.getenv("TEST_MODE", "isolation").strip().lower()


def is_integration_mode() -> bool:
    return TEST_MODE == "integration"


# After .env.tests so pydantic Settings sees DATABASE_URL / RABBITMQ_URL for fixtures.
from app.config import settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "isolation: runs only in TEST_MODE=isolation")
    config.addinivalue_line(
        "markers", "integration: runs only in TEST_MODE=integration"
    )
    config.addinivalue_line(
        "markers", "requires_rabbit: depends on RabbitMQ availability"
    )
    config.addinivalue_line("markers", "requires_ws: depends on websocket runtime")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if TEST_MODE not in ("isolation", "integration"):
        raise pytest.UsageError(
            f"Invalid TEST_MODE={TEST_MODE!r}. Use 'isolation' or 'integration'."
        )
    for item in items:
        has_integration_marker = item.get_closest_marker("integration") is not None
        has_isolation_marker = item.get_closest_marker("isolation") is not None
        if has_integration_marker and TEST_MODE != "integration":
            item.add_marker(pytest.mark.skip(reason="requires TEST_MODE=integration"))
        if has_isolation_marker and TEST_MODE != "isolation":
            item.add_marker(pytest.mark.skip(reason="requires TEST_MODE=isolation"))


@pytest.fixture(scope="session")
async def wait_for_api() -> None:
    """Block until the API health endpoint responds (docker stack is up)."""
    async with httpx.AsyncClient(base_url=TEST_API_BASE_URL) as c:
        for _attempt in range(30):
            try:
                r = await c.get("/health")
                if r.status_code == 200:
                    return
            except (httpx.HTTPError, OSError):
                pass
            await asyncio.sleep(1)
    msg = (
        f"API at {TEST_API_BASE_URL} did not become ready after 30 attempts "
        "(start the stack with docker-compose up)"
    )
    pytest.fail(msg)


@pytest.fixture(scope="session")
async def wait_for_rabbitmq() -> None:
    """Confirm RabbitMQ accepts connections (same URL as the app)."""
    for _ in range(15):
        try:
            conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            await conn.close()
            return
        except Exception:
            await asyncio.sleep(1)
    pytest.fail(
        "RabbitMQ did not become reachable after 15 attempts "
        f"({settings.RABBITMQ_URL!r})"
    )


@pytest.fixture(scope="session")
async def client(
    wait_for_api: None,
    wait_for_rabbitmq: None,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(base_url=TEST_API_BASE_URL) as c:
        yield c


@pytest.fixture
def require_integration_mode() -> None:
    if not is_integration_mode():
        pytest.skip("requires TEST_MODE=integration")


@pytest.fixture
def require_isolation_mode() -> None:
    if is_integration_mode():
        pytest.skip("requires TEST_MODE=isolation")


@pytest.fixture(scope="session")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    session = AsyncSessionLocal()
    try:
        yield session
    finally:
        await session.close()


@pytest.fixture(scope="session")
async def amqp_connection(wait_for_rabbitmq: None) -> AsyncGenerator[Any, None]:
    """Direct aio-pika connection for test-side publishing to RabbitMQ."""
    conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def truncate_all(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    # Clear any failed transaction left by a previous test on the shared session.
    await db_session.rollback()
    await db_session.execute(text("TRUNCATE TABLE messages RESTART IDENTITY CASCADE"))
    await db_session.execute(text("TRUNCATE TABLE sessions RESTART IDENTITY CASCADE"))
    await db_session.commit()
    yield
    # Reset session state after each test so the next test does not inherit a poisoned tx.
    await db_session.rollback()


@pytest.fixture
def respx_mock() -> Any:
    with respx.mock(assert_all_called=False) as mock:
        yield mock
