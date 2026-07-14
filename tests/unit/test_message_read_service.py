from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.domain.session.exceptions import SessionNotFound
from app.schemas.message import PaginatedMessages
from app.services.message_read import MessageReadService
from tests.unit.factories import make_message
from tests.unit.fakes.fake_message_repo import FakeMessageRepository
from tests.unit.fakes.fake_session_repo import FakeSessionRepository


async def test_get_history_raises_SessionNotFound_for_unknown_user() -> None:  # noqa: N802
    session_repo = FakeSessionRepository()
    message_repo = FakeMessageRepository()
    service = MessageReadService(session_repo, message_repo)
    with pytest.raises(SessionNotFound) as excinfo:
        await service.get_history("ghost")
    assert "ghost" in str(excinfo.value)


async def test_get_history_returns_empty_paginated_for_new_session() -> None:
    session_repo = FakeSessionRepository()
    message_repo = FakeMessageRepository()
    await session_repo.upsert("alice")
    service = MessageReadService(session_repo, message_repo)
    result = await service.get_history("alice", limit=10)
    assert isinstance(result, PaginatedMessages)
    assert result.items == []
    assert result.total == 0
    assert result.has_more is False


async def test_get_history_returns_messages_ordered_by_created_at() -> None:
    session_repo = FakeSessionRepository()
    message_repo = FakeMessageRepository()
    session = await session_repo.upsert("alice")
    sid = session.id
    base = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
    m3 = make_message(
        session_id=sid,
        role="user",
        content="third",
        created_at=base + timedelta(seconds=3),
    )
    m1 = make_message(
        session_id=sid,
        role="user",
        content="first",
        created_at=base + timedelta(seconds=1),
    )
    m2 = make_message(
        session_id=sid,
        role="user",
        content="second",
        created_at=base + timedelta(seconds=2),
    )
    message_repo._store.extend([m3, m1, m2])
    service = MessageReadService(session_repo, message_repo)
    result = await service.get_history("alice", limit=50)
    contents = [item.content for item in result.items]
    assert contents == ["first", "second", "third"]


async def test_get_history_has_more_is_true_when_page_is_full() -> None:
    session_repo = FakeSessionRepository()
    message_repo = FakeMessageRepository()
    session = await session_repo.upsert("alice")
    sid = session.id
    base = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
    for i in range(5):
        message_repo._store.append(
            make_message(
                session_id=sid,
                role="user",
                content=f"m{i}",
                created_at=base + timedelta(seconds=i),
            )
        )
    service = MessageReadService(session_repo, message_repo)
    result = await service.get_history("alice", limit=5)
    assert len(result.items) == 5
    assert result.has_more is True


async def test_get_history_has_more_is_false_when_fewer_than_limit() -> None:
    session_repo = FakeSessionRepository()
    message_repo = FakeMessageRepository()
    session = await session_repo.upsert("alice")
    sid = session.id
    base = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
    for i in range(3):
        message_repo._store.append(
            make_message(
                session_id=sid,
                role="user",
                content=f"m{i}",
                created_at=base + timedelta(seconds=i),
            )
        )
    service = MessageReadService(session_repo, message_repo)
    result = await service.get_history("alice", limit=5)
    assert len(result.items) == 3
    assert result.has_more is False


async def test_get_history_before_filters_correctly() -> None:
    session_repo = FakeSessionRepository()
    message_repo = FakeMessageRepository()
    session = await session_repo.upsert("alice")
    sid: UUID = session.id
    base = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
    times = [base + timedelta(seconds=i) for i in range(5)]
    for i, t in enumerate(times):
        message_repo._store.append(
            make_message(
                session_id=sid,
                role="user",
                content=f"m{i}",
                created_at=t,
            )
        )
    service = MessageReadService(session_repo, message_repo)
    before = times[2]
    result = await service.get_history("alice", limit=50, before=before)
    assert len(result.items) == 2
    assert [item.content for item in result.items] == ["m0", "m1"]
