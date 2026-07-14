from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import uuid6

from app.domain.message.entities import Message
from app.domain.message.repository import AbstractMessageRepository


class FakeMessageRepository(AbstractMessageRepository):
    def __init__(self) -> None:
        self._store: list[Message] = []

    async def save(
        self,
        session_id: UUID,
        role: str,
        content: str,
        agent_id: UUID | None,
        correlation_id: UUID | None,
    ) -> Message:
        msg = Message(
            id=uuid6.uuid7(),
            session_id=session_id,
            role=role,
            content=content,
            created_at=datetime.now(tz=UTC),
            agent_id=agent_id,
            correlation_id=correlation_id,
        )
        self._store.append(msg)
        return msg

    async def get_paginated(
        self,
        session_id: UUID,
        limit: int,
        before: datetime | None,
    ) -> list[Message]:
        results = [m for m in self._store if m.session_id == session_id]
        if before is not None:
            results = [m for m in results if m.created_at < before]
        results.sort(key=lambda m: m.created_at)
        return results[:limit]
