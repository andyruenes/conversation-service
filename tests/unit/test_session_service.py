from __future__ import annotations

import asyncio

from app.schemas.session import SessionRead
from app.services.session import SessionService
from tests.unit.fakes.fake_session_repo import FakeSessionRepository


async def test_upsert_creates_new_session() -> None:
    repo = FakeSessionRepository()
    service = SessionService(repo)
    result = await service.upsert("alice")
    assert isinstance(result, SessionRead)
    assert result.user_id == "alice"


async def test_upsert_returns_existing_session_with_updated_last_active() -> None:
    repo = FakeSessionRepository()
    service = SessionService(repo)
    t1 = await service.upsert("alice")
    await asyncio.sleep(0.002)
    t2 = await service.upsert("alice")
    assert t2.user_id == t1.user_id
    assert t2.last_active_at >= t1.last_active_at


async def test_upsert_different_users_are_independent() -> None:
    repo = FakeSessionRepository()
    service = SessionService(repo)
    await service.upsert("alice")
    await service.upsert("bob")
    assert len(repo._store) == 2
    assert repo._store["alice"].id != repo._store["bob"].id
