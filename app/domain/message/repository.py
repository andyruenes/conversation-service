# FIXED: abstract-bodies-ellipsis
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.domain.message.entities import Message


class AbstractMessageRepository(ABC):
    @abstractmethod
    async def save(
        self,
        session_id: UUID,
        role: str,
        content: str,
        agent_id: UUID | None,
        correlation_id: UUID | None,
    ) -> Message: ...

    @abstractmethod
    async def get_paginated(
        self, session_id: UUID, limit: int, before: datetime | None
    ) -> list[Message]: ...
