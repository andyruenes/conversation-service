from __future__ import annotations

from datetime import UTC, datetime

import uuid6

from app.domain.session.entities import Session
from app.domain.session.repository import AbstractSessionRepository


class FakeSessionRepository(AbstractSessionRepository):
    def __init__(self) -> None:
        self._store: dict[str, Session] = {}

    async def get_by_user_id(self, user_id: str) -> Session | None:
        return self._store.get(user_id)

    async def upsert(self, user_id: str) -> Session:
        if user_id in self._store:
            existing = self._store[user_id]
            updated = Session(
                id=existing.id,
                user_id=existing.user_id,
                created_at=existing.created_at,
                last_active_at=datetime.now(tz=UTC),
            )
            self._store[user_id] = updated
            return updated
        new = Session(
            id=uuid6.uuid7(),
            user_id=user_id,
            created_at=datetime.now(tz=UTC),
            last_active_at=datetime.now(tz=UTC),
        )
        self._store[user_id] = new
        return new
