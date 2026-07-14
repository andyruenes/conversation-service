"""Agent HTTP mocking for `/ws/test/...`.

`respx` patches ``httpx`` in the **current Python process only**. Outbound calls
from a separate uvicorn/docker process are **not** intercepted. These tests
therefore use `starlette.testclient.TestClient` to run the FastAPI ``app``
in-process so the lifespan ``httpx.AsyncClient`` and ``respx`` share one
process.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.message import MessageModel
from app.models.session import SessionModel

pytestmark = [
    pytest.mark.usefixtures("truncate_all", "wait_for_api", "wait_for_rabbitmq"),
]


def _agent_test_url() -> str:
    return f"{settings.AGENT_SERVICE_URL.rstrip('/')}/agent/test/query"


async def test_ws_test_path_returns_agent_response(
    respx_mock: Any,
    db_session: AsyncSession,
) -> None:
    respx_mock.post(_agent_test_url()).mock(
        return_value=httpx.Response(
            200,
            json={"response": "mocked reply", "latency_ms": 42},
        )
    )

    def run() -> str:
        with TestClient(app) as client:
            with client.websocket_connect("/ws/test/fake-session-id-123") as ws:
                ws.send_text("what is 2+2")
                return ws.receive_text()

    received = await asyncio.to_thread(run)
    assert received == "mocked reply"
    n_msg = await db_session.scalar(select(func.count()).select_from(MessageModel))
    assert n_msg == 0


async def test_ws_test_path_handles_agent_error_gracefully(
    respx_mock: Any,
) -> None:
    respx_mock.post(_agent_test_url()).mock(
        return_value=httpx.Response(502, text="bad gateway"),
    )

    def run() -> str:
        with TestClient(app) as client:
            with client.websocket_connect("/ws/test/fake-session-id-error") as ws:
                ws.send_text("trigger error")
                return ws.receive_text()

    raw = await asyncio.to_thread(run)
    data = json.loads(raw)
    assert "error" in data


async def test_ws_test_path_does_not_create_session_in_db(
    respx_mock: Any,
    db_session: AsyncSession,
) -> None:
    respx_mock.post(_agent_test_url()).mock(
        return_value=httpx.Response(
            200,
            json={"response": "ok", "latency_ms": 1},
        )
    )

    def run() -> str:
        with TestClient(app) as client:
            with client.websocket_connect("/ws/test/no-session-uuid") as ws:
                ws.send_text("hello")
                return ws.receive_text()

    await asyncio.to_thread(run)
    n_sess = await db_session.scalar(select(func.count()).select_from(SessionModel))
    assert n_sess == 0
