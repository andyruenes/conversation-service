from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import MessageModel
from app.repositories.session import SqlSessionRepository
from app.schemas.admin import (
    ClientListItem,
    ConversationDetailResponse,
    ConversationMetricsResponse,
    UserConversationListItem,
)


class AdminService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = SqlSessionRepository(session)

    async def list_clients(
        self,
        search: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[ClientListItem]:
        items, _ = await self._repo.get_clients_stats(
            search=search, offset=offset, limit=limit
        )
        return [ClientListItem(**item) for item in items]

    async def count_clients(self, search: str | None = None) -> int:
        _, total = await self._repo.get_clients_stats(search=search, offset=0, limit=1)
        return total

    async def list_user_conversations(
        self,
        user_id: str,
        status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[UserConversationListItem]:
        items, total = await self._repo.get_user_conversations(
            user_id=user_id,
            status=status,
            date_from=date_from,
            date_to=date_to,
            offset=offset,
            limit=limit,
        )

        # Para cada conversación, buscar si hay mensajes de agente y obtener su nombre
        for item in items:
            # Buscar mensajes de agente en esta sesión
            stmt = (
                select(MessageModel)
                .where(
                    MessageModel.session_id == item["id"],
                    MessageModel.agent_id.is_not(None),
                )
                .limit(1)
            )
            result = await self._repo._session.execute(stmt)
            agent_message = result.scalar_one_or_none()

            if agent_message and agent_message.agent_id:
                # Obtener nombre del agente (necesitas repositorio de agentes)
                # agent = await agent_repo.get_by_id(agent_message.agent_id)
                # item["agent_name"] = agent.name if agent else None
                item["agent_name"] = f"Agent {agent_message.agent_id}"  # Placeholder

        return [UserConversationListItem(**item) for item in items]

    async def get_conversation_detail(
        self, session_id: UUID
    ) -> ConversationDetailResponse | None:
        data = await self._repo.get_conversation_detail(session_id)
        if data is None:
            return None

        # agent_name: buscar un mensaje de agente en la sesión (mismo patrón que list)
        stmt = (
            select(MessageModel)
            .where(
                MessageModel.session_id == session_id,
                MessageModel.agent_id.is_not(None),
            )
            .limit(1)
        )
        agent_message = (await self._repo._session.execute(stmt)).scalar_one_or_none()
        if agent_message and agent_message.agent_id:
            data["agent_name"] = f"Agent {agent_message.agent_id}"  # Placeholder

        return ConversationDetailResponse(**data)

    async def count_open_conversations(self) -> int:
        return await self._repo.count_open_sessions()

    async def get_metrics(self) -> ConversationMetricsResponse:
        data = await self._repo.get_metrics()
        return ConversationMetricsResponse(**data)

    async def count_user_conversations(
        self,
        user_id: str,
        status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> int:
        _, total = await self._repo.get_user_conversations(
            user_id=user_id,
            status=status,
            date_from=date_from,
            date_to=date_to,
            offset=0,
            limit=1,
        )
        return total
