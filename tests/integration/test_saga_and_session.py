"""Integration tests for SAGA-style agent.response / agent.failed and session behavior.

Exchange and routing keys must match ``app/messaging/consumer.py`` (queue bindings
and ``_handle_incoming_message``).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any, TypeVar

import aio_pika
import httpx
import pytest
import websockets
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.message import MessageModel
from app.models.session import SessionModel

# --- Strings must match app/messaging/consumer.py (declare_exchange / queue.bind) ---
CHATBOT_EXCHANGE = "chatbot"
RK_AGENT_RESPONSE = "agent.response"
RK_AGENT_FAILED = "agent.failed"

pytestmark = [
    pytest.mark.usefixtures("truncate_all", "wait_for_api", "wait_for_rabbitmq"),
    pytest.mark.requires_rabbit,
    pytest.mark.requires_ws,
]

M = TypeVar("M", bound=Any)


async def publish_fake_event(
    amqp_connection: aio_pika.abc.AbstractConnection,
    routing_key: str,
    payload: dict[str, Any],
) -> None:
    channel = await amqp_connection.channel()
    try:
        exchange = await channel.declare_exchange(
            CHATBOT_EXCHANGE,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(payload).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=routing_key,
        )
    finally:
        await channel.close()


async def wait_for_db_row(  # noqa: UP047
    model_class: type[M],
    timeout: float = 3.0,
    **filters: Any,
) -> M:
    """Poll DB until a matching row appears or timeout (fresh session each attempt)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        async with AsyncSessionLocal() as session:
            stmt = select(model_class)
            for col, val in filters.items():
                stmt = stmt.where(getattr(model_class, col) == val)
            result = await session.execute(stmt)
            row = result.scalars().first()
            if row is not None:
                await session.refresh(row)
                return row
        await asyncio.sleep(0.1)
    raise TimeoutError(
        f"Row {model_class.__name__} with {filters!r} not found within {timeout}s"
    )


async def recv_ws_matching(
    ws: websockets.ClientConnection,
    predicate: Callable[[str], bool],
    *,
    timeout: float = 30.0,
    max_frames: int = 5,
) -> str:
    """Read WS frames until one matches *predicate* or limits are hit."""
    deadline = time.monotonic() + timeout
    received: list[str] = []
    while time.monotonic() < deadline and len(received) < max_frames:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            frame = await asyncio.wait_for(ws.recv(), timeout=remaining)
            received.append(frame)
            if predicate(frame):
                return frame
        except TimeoutError:
            break
    raise AssertionError(
        f"No WS frame matched predicate after {len(received)} frames. "
        f"Received: {received!r}"
    )


@pytest.mark.integration
async def test_saga_agent_response_persists_assistant_message_and_delivers_over_ws(
    require_integration_mode: None,
) -> None:
    uri = "ws://localhost:8000/ws/saga-user-1"
    question = "Reply with only the word PARIS. Say nothing else."
    async with websockets.connect(uri) as ws:
        await ws.send(question)
        user_row = await wait_for_db_row(
            MessageModel,
            timeout=5.0,
            role="user",
            content=question,
        )
        session_id = user_row.session_id
        user_cid = user_row.correlation_id
        assert user_cid is not None

        assistant_row = await wait_for_db_row(
            MessageModel,
            timeout=180.0,
            role="assistant",
            session_id=session_id,
            correlation_id=user_cid,
        )

        frame = await recv_ws_matching(
            ws,
            lambda f: "paris" in f.strip().lower(),
            timeout=20.0,
        )
        assert "paris" in frame.strip().lower()
    assert "paris" in assistant_row.content.strip().lower()
    assert assistant_row.correlation_id == user_cid


@pytest.mark.integration
async def test_saga_agent_failed_persists_error_message_and_delivers_over_ws(
    amqp_connection: aio_pika.abc.AbstractConnection,
    client: httpx.AsyncClient,
    require_integration_mode: None,
) -> None:
    post = await client.post("/sessions", json={"user_id": "saga-user-2"})
    assert post.status_code == 201
    session_id = post.json()["id"]

    uri = "ws://localhost:8000/ws/saga-user-2"
    async with websockets.connect(uri) as ws:
        payload = {
            "session_id": session_id,
            "error": "OpenAI timeout",
            "agent_id": None,
        }
        await publish_fake_event(amqp_connection, RK_AGENT_FAILED, payload)

        frame = await recv_ws_matching(
            ws,
            lambda f: "OpenAI timeout" in f,
            timeout=10.0,
            max_frames=5,
        )
        assert "OpenAI timeout" in frame

        await ws.send("after-error ping")

    err_row = await wait_for_db_row(
        MessageModel,
        timeout=5.0,
        role="error",
        session_id=session_id,
    )
    assert "OpenAI timeout" in err_row.content


@pytest.mark.isolation
async def test_correlation_id_links_user_message_to_assistant_message(
    amqp_connection: aio_pika.abc.AbstractConnection,
    require_isolation_mode: None,
) -> None:
    uri = "ws://localhost:8000/ws/corr-user-1"
    text = "hello correlation"
    async with websockets.connect(uri) as ws:
        await ws.send(text)
        user_row = await wait_for_db_row(
            MessageModel,
            timeout=2.0,
            role="user",
            content=text,
        )
        user_cid = user_row.correlation_id
        assert user_cid is not None
        sid = user_row.session_id

        payload = {
            "session_id": str(sid),
            "response": "corr-ack",
            "correlation_id": str(user_cid),
            "agent_id": None,
        }
        await publish_fake_event(amqp_connection, RK_AGENT_RESPONSE, payload)
        await asyncio.wait_for(ws.recv(), timeout=3.0)

    assistant_row = await wait_for_db_row(
        MessageModel,
        timeout=3.0,
        role="assistant",
        content="corr-ack",
        session_id=sid,
    )
    assert assistant_row.correlation_id == user_row.correlation_id
    assert assistant_row.session_id == user_row.session_id


@pytest.mark.integration
async def test_concurrent_sessions_messages_do_not_cross(
    require_integration_mode: None,
) -> None:
    prompt_a = "Reply with only the word ALPHA. Say nothing else."
    prompt_b = "Reply with only the word BETA. Say nothing else."
    uri_a = "ws://localhost:8000/ws/concurrent-user-a"
    uri_b = "ws://localhost:8000/ws/concurrent-user-b"
    async with (
        websockets.connect(uri_a) as ws_a,
        websockets.connect(uri_b) as ws_b,
    ):
        await ws_a.send(prompt_a)
        await ws_b.send(prompt_b)

        user_a = await wait_for_db_row(
            MessageModel,
            timeout=5.0,
            role="user",
            content=prompt_a,
        )
        user_b = await wait_for_db_row(
            MessageModel,
            timeout=5.0,
            role="user",
            content=prompt_b,
        )
        sid_a = user_a.session_id
        sid_b = user_b.session_id
        assert sid_a != sid_b

        assistant_a, assistant_b = await asyncio.gather(
            wait_for_db_row(
                MessageModel,
                timeout=240.0,
                role="assistant",
                session_id=sid_a,
                correlation_id=user_a.correlation_id,
            ),
            wait_for_db_row(
                MessageModel,
                timeout=240.0,
                role="assistant",
                session_id=sid_b,
                correlation_id=user_b.correlation_id,
            ),
        )

        msg_a = await recv_ws_matching(
            ws_a,
            lambda f: "alpha" in f.strip().lower(),
            timeout=20.0,
        )
        msg_b = await recv_ws_matching(
            ws_b,
            lambda f: "beta" in f.strip().lower(),
            timeout=20.0,
        )
        assert "alpha" in msg_a.strip().lower()
        assert "beta" in msg_b.strip().lower()
    assert "alpha" in assistant_a.content.strip().lower()
    assert "beta" in assistant_b.content.strip().lower()


@pytest.mark.isolation
async def test_ws_message_updates_last_active_at(
    client: httpx.AsyncClient,
) -> None:
    post = await client.post("/sessions", json={"user_id": "activity-user"})
    assert post.status_code == 201
    body = post.json()
    t1 = datetime.fromisoformat(body["last_active_at"])

    await asyncio.sleep(0.1)

    uri = "ws://localhost:8000/ws/activity-user"
    async with websockets.connect(uri) as ws:
        await ws.send("ping")
        await wait_for_db_row(
            MessageModel,
            timeout=2.0,
            role="user",
            content="ping",
        )

    async with AsyncSessionLocal() as s:
        res = await s.execute(
            select(SessionModel).where(SessionModel.user_id == "activity-user")
        )
        row = res.scalar_one()

    assert row.last_active_at > t1
