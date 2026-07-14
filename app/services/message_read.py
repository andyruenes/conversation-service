from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.domain.message.repository import AbstractMessageRepository
from app.domain.session.exceptions import SessionNotFound
from app.domain.session.repository import AbstractSessionRepository
from app.schemas.message import MessageRead, PaginatedMessages


class MessageReadService:
    def __init__(
        self,
        session_repo: AbstractSessionRepository,
        message_repo: AbstractMessageRepository,
    ) -> None:
        self._session_repo = session_repo
        self._message_repo = message_repo

    async def get_history(
        self,
        user_id: str,
        limit: int = 50,
        before: datetime | None = None,
    ) -> PaginatedMessages:
        session = await self._session_repo.get_by_user_id(user_id)
        if session is None:
            raise SessionNotFound(user_id)
        messages = await self._message_repo.get_paginated(
            session.id,
            limit,
            before,
        )
        items = [MessageRead.from_entity(m) for m in messages]
        return PaginatedMessages(
            items=items,
            total=len(items),
            has_more=len(items) == limit,
        )

    async def get_session_messages(
        self,
        session_id: UUID,
        limit: int = 50,
        before: datetime | None = None,
    ) -> PaginatedMessages:
        messages = await self._message_repo.get_paginated(session_id, limit, before)
        total = await self._message_repo.count_by_session(session_id)

        return PaginatedMessages(
            items=[MessageRead.from_entity(msg) for msg in messages],
            total=total,
            has_more=len(messages) == limit,
        )
