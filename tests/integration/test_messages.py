from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import uuid6
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import MessageModel
from app.models.session import SessionModel

pytestmark = pytest.mark.usefixtures("truncate_all")


async def test_get_messages_returns_history_in_asc_order(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    sid = uuid6.uuid7()
    db_session.add(SessionModel(id=sid, user_id="dave"))
    await db_session.flush()
    base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    contents = ["first-msg", "second-msg", "third-msg"]
    for i, content in enumerate(contents):
        db_session.add(
            MessageModel(
                id=uuid6.uuid7(),
                session_id=sid,
                role="user",
                content=content,
                created_at=base + timedelta(seconds=i * 10),
                agent_id=None,
                correlation_id=None,
            )
        )
    await db_session.commit()

    r = await client.get("/sessions/dave/messages")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 3
    got = [item["content"] for item in body["items"]]
    assert got == contents


async def test_get_messages_limit_paginates_correctly(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    sid = uuid6.uuid7()
    db_session.add(SessionModel(id=sid, user_id="pageuser"))
    await db_session.flush()
    base = datetime(2025, 2, 1, 0, 0, 0, tzinfo=UTC)
    for i in range(10):
        db_session.add(
            MessageModel(
                id=uuid6.uuid7(),
                session_id=sid,
                role="user",
                content=f"m{i}",
                created_at=base + timedelta(seconds=i),
                agent_id=None,
                correlation_id=None,
            )
        )
    await db_session.commit()

    r = await client.get("/sessions/pageuser/messages", params={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 5
    assert body["has_more"] is True


async def test_get_messages_before_filters_correctly(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    sid = uuid6.uuid7()
    db_session.add(SessionModel(id=sid, user_id="beforeuser"))
    await db_session.flush()
    base = datetime(2025, 3, 1, 0, 0, 0, tzinfo=UTC)
    times = [base + timedelta(seconds=i) for i in range(5)]
    for i, t in enumerate(times):
        db_session.add(
            MessageModel(
                id=uuid6.uuid7(),
                session_id=sid,
                role="user",
                content=f"t{i}",
                created_at=t,
                agent_id=None,
                correlation_id=None,
            )
        )
    await db_session.commit()

    before = times[2]
    r = await client.get(
        "/sessions/beforeuser/messages",
        params={"before": before.isoformat()},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    assert [item["content"] for item in body["items"]] == ["t0", "t1"]
    assert body["has_more"] is False


async def test_get_messages_has_more_false_when_fewer_than_limit(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    sid = uuid6.uuid7()
    db_session.add(SessionModel(id=sid, user_id="fewuser"))
    await db_session.flush()
    base = datetime(2025, 4, 1, 0, 0, 0, tzinfo=UTC)
    for i in range(3):
        db_session.add(
            MessageModel(
                id=uuid6.uuid7(),
                session_id=sid,
                role="user",
                content=f"x{i}",
                created_at=base + timedelta(seconds=i),
                agent_id=None,
                correlation_id=None,
            )
        )
    await db_session.commit()

    r = await client.get("/sessions/fewuser/messages", params={"limit": 10})
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 3
    assert body["has_more"] is False
