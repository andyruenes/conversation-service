from __future__ import annotations

import asyncio
import time

import httpx
import pytest
import websockets
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.message import MessageModel
from app.models.session import SessionModel

pytestmark = [
    pytest.mark.usefixtures("truncate_all", "wait_for_api", "wait_for_rabbitmq"),
]


async def _wait_for_session_by_user_id(
    user_id: str,
    *,
    timeout: float = 5.0,
) -> SessionModel:
    """Poll until a session row committed by the API is visible (fresh pool connection each try)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        async with AsyncSessionLocal() as s:
            r = await s.execute(
                select(SessionModel).where(SessionModel.user_id == user_id)
            )
            row = r.scalar_one_or_none()
            if row is not None:
                return row
        await asyncio.sleep(0.1)
    msg = (
        f"Session row for user_id={user_id!r} not visible within {timeout}s "
        "(check DATABASE_URL matches the API container DB)"
    )
    raise AssertionError(msg)


async def test_ws_connect_and_send_message_persists_user_message(
    db_session: AsyncSession,
) -> None:
    uri = "ws://localhost:8000/ws/test-ws-user"
    async with websockets.connect(uri) as ws:
        await ws.send("hello integration")
        try:
            await asyncio.wait_for(ws.recv(), timeout=5.0)
        except TimeoutError:
            pass

    result = await db_session.execute(
        select(MessageModel).where(
            MessageModel.role == "user",
            MessageModel.content == "hello integration",
        )
    )
    assert result.scalar_one_or_none() is not None


async def test_ws_connect_stores_session_in_db() -> None:
    uri = "ws://localhost:8000/ws/integration-session-user"
    async with websockets.connect(uri):
        pass
    await _wait_for_session_by_user_id("integration-session-user")


async def test_ws_disconnect_is_clean() -> None:
    uri = "ws://localhost:8000/ws/disconnect-test-user"
    async with websockets.connect(uri) as ws:
        await ws.close()
    async with websockets.connect(uri) as ws2:
        await ws2.send("ping")


async def test_ws_upsert_reconnect_returns_same_session_id(
    client: httpx.AsyncClient,
) -> None:
    uri = "ws://localhost:8000/ws/reconnect-user"
    async with websockets.connect(uri):
        pass
    existing = await _wait_for_session_by_user_id("reconnect-user")
    expected_id = str(existing.id)

    post = await client.post("/sessions", json={"user_id": "reconnect-user"})
    assert post.status_code == 201
    assert post.json()["id"] == expected_id
