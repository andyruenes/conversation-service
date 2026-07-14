from __future__ import annotations

from uuid import UUID

from app.domain.message.exceptions import InvalidRole
from app.domain.message.repository import AbstractMessageRepository
from app.schemas.message import MessageRead

VALID_ROLES = frozenset({"user", "assistant", "error", "operator"})


class MessageWriteService:
    def __init__(self, message_repo: AbstractMessageRepository) -> None:
        self._message_repo = message_repo

    async def _save(
        self,
        session_id: UUID,
        role: str,
        content: str,
        agent_id: UUID | None,
        correlation_id: UUID | None,
    ) -> MessageRead:
        if role not in VALID_ROLES:
            raise InvalidRole(role)
        result = await self._message_repo.save(
            session_id,
            role,
            content,
            agent_id,
            correlation_id,
        )
        return MessageRead.from_entity(result)

    async def save_user_message(
        self,
        session_id: UUID,
        content: str,
        correlation_id: UUID,
        agent_id: UUID | None = None,
    ) -> MessageRead:
        return await self._save(
            session_id,
            "user",
            content,
            agent_id,
            correlation_id,
        )

    async def save_assistant_message(
        self,
        session_id: UUID,
        content: str,
        correlation_id: UUID,
        agent_id: UUID | None = None,
    ) -> MessageRead:
        return await self._save(
            session_id,
            "assistant",
            content,
            agent_id,
            correlation_id,
        )

    async def save_error_message(
        self,
        session_id: UUID,
        content: str,
        correlation_id: UUID | None = None,
        agent_id: UUID | None = None,
    ) -> MessageRead:
        return await self._save(
            session_id,
            "error",
            content,
            agent_id,
            correlation_id,
        )

    async def save_operator_message(
        self,
        session_id: UUID,
        content: str,
        correlation_id: UUID | None = None,
        agent_id: UUID | None = None,
    ) -> MessageRead:
        return await self._save(
            session_id,
            "operator",
            content,
            agent_id,
            correlation_id,
        )