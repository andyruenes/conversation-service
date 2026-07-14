from __future__ import annotations

from datetime import datetime
from uuid import UUID

import uuid6
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.message.entities import Message
from app.domain.message.repository import AbstractMessageRepository
from app.models.message import MessageModel


class SqlMessageRepository(AbstractMessageRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(
        self,
        session_id: UUID,
        role: str,
        content: str,
        agent_id: UUID | None,
        correlation_id: UUID | None,
    ) -> Message:
        message = MessageModel(
            id=uuid6.uuid7(),
            session_id=session_id,
            role=role,
            content=content,
            agent_id=agent_id,
            correlation_id=correlation_id,
        )
        self._session.add(message)
        await self._session.flush()
        await self._session.refresh(message)
        return self._to_entity(message)

    async def get_paginated(
        self,
        session_id: UUID,
        limit: int,
        before: datetime | None,
    ) -> list[Message]:
        stmt = select(MessageModel).where(MessageModel.session_id == session_id)
        if before is not None:
            stmt = stmt.where(MessageModel.created_at < before)
        # Trae los `limit` mensajes MAS RECIENTES y los devuelve en orden
        # cronologico. Antes ordenaba ASC + LIMIT, devolviendo el INICIO de la
        # sesion (el modelo recibia contexto viejo en sesiones largas).
        stmt = stmt.order_by(MessageModel.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        rows.reverse()
        return [self._to_entity(row) for row in rows]

    def _to_entity(self, row: MessageModel) -> Message:
        return Message(
            id=row.id,
            session_id=row.session_id,
            role=row.role,
            content=row.content,
            created_at=row.created_at,
            agent_id=row.agent_id,
            correlation_id=row.correlation_id,
        )
    async def count_by_session(self, session_id: UUID) -> int:
        from sqlalchemy import func, select
        stmt = select(func.count()).where(MessageModel.session_id == session_id)
        result = await self._session.execute(stmt)
        return result.scalar()
