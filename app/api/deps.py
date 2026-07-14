from __future__ import annotations

from fastapi import Depends, Request
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.repositories.message import SqlMessageRepository
from app.repositories.session import SqlSessionRepository
from app.services.message_read import MessageReadService
from app.services.message_write import MessageWriteService
from app.services.session import SessionService


def session_service_from_db_session(session: AsyncSession) -> SessionService:
    """Composition root for WebSocket / non-request code paths (no FastAPI Request)."""
    return SessionService(SqlSessionRepository(session))


def message_write_service_from_db_session(session: AsyncSession) -> MessageWriteService:
    """Composition root for WebSocket / consumer (no FastAPI Request)."""
    return MessageWriteService(SqlMessageRepository(session))


def get_session_service(
    session: AsyncSession = Depends(get_session),
) -> SessionService:
    return SessionService(SqlSessionRepository(session))


def get_message_write_service(
    session: AsyncSession = Depends(get_session),
) -> MessageWriteService:
    return MessageWriteService(SqlMessageRepository(session))


def get_message_read_service(
    session: AsyncSession = Depends(get_session),
) -> MessageReadService:
    session_repo = SqlSessionRepository(session)
    message_repo = SqlMessageRepository(session)
    return MessageReadService(session_repo, message_repo)


def get_agent_client(request: Request) -> AsyncClient:
    return request.app.state.http_client
