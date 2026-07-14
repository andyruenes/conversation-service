from __future__ import annotations

from uuid import UUID
from app.domain.session.repository import AbstractSessionRepository
from app.schemas.session import SessionRead
from app.models.session import SessionModel


class SessionService:
    def __init__(self, session_repo: AbstractSessionRepository) -> None:
        self._session_repo = session_repo

    async def upsert(self, user_id: str) -> SessionRead:
        result = await self._session_repo.upsert(user_id)
        return SessionRead.from_entity(result)

    async def get_by_id_model(self, session_id: UUID) -> SessionModel | None:
        """Obtener una sesión por su ID (retorna el modelo directamente)."""
        return await self._session_repo.get_by_id_model(session_id)

    async def get_by_user_id_model(self, user_id: str) -> SessionModel | None:
        """Obtener la sesión más reciente de un usuario (retorna el modelo directamente)."""
        return await self._session_repo.get_by_user_id_model(user_id)