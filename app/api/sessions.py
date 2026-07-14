from __future__ import annotations
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic.types import AwareDatetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.session import SqlSessionRepository
from app.api.deps import get_message_read_service, get_session_service
from app.db.session import get_session
from app.schemas.message import PaginatedMessages
from app.schemas.session import SessionCreate, SessionRead
from app.services.message_read import MessageReadService
from app.services.session import SessionService

router = APIRouter(tags=["sessions"])


@router.post("/sessions", status_code=201, response_model=SessionRead)
async def create_session(
    body: SessionCreate,
    session_service: SessionService = Depends(get_session_service),
) -> SessionRead:
    return await session_service.upsert(body.user_id)


@router.get("/sessions/{user_id}/messages", response_model=PaginatedMessages)
async def list_messages(
    user_id: str,
    message_read_service: MessageReadService = Depends(get_message_read_service),
    limit: int = Query(default=50, ge=1, le=100),
    before: AwareDatetime | None = Query(default=None),
) -> PaginatedMessages:
    return await message_read_service.get_history(user_id, limit, before)

@router.post("/sessions/{session_id}/handoff")
async def handle_handoff_event(
    session_id: UUID,
    event_type: str = Query(..., description="handoff or reactivate"),
    agent_id: str | None = Query(None),
    phone_number: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Procesa eventos de handoff/reactivate desde admin-service."""
    from datetime import datetime
    
    session_service = SessionService(SqlSessionRepository(session))
    session_obj = await session_service.get_by_id_model(session_id)
    
    if not session_obj:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if event_type == "handoff":
        session_obj.is_derived = True
        session_obj.derived_at = datetime.utcnow()
    elif event_type == "reactivate":
        session_obj.is_derived = False
        session_obj.reactivated_at = datetime.utcnow()
    else:
        raise HTTPException(status_code=400, detail="Invalid event_type")
    
    await session.commit()
    
    return {"status": "success", "event_type": event_type}


@router.get("/sessions/{user_id}/state")
async def get_session_state(
    user_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    """Devuelve el estado de derivación de la sesión de un usuario.

    Lo usa el admin-service (camino WhatsApp) para no volver a llamar a la IA
    cuando la conversación ya fue derivada a un operador humano.
    """
    session_service = SessionService(SqlSessionRepository(session))
    session_obj = await session_service.get_by_user_id_model(user_id)
    if session_obj is None:
        print(
            f"[STATE] user_id={user_id!r} -> sin sesión -> is_derived=False",
            flush=True,
        )
        return {"is_derived": False}
    print(
        f"[STATE] user_id={user_id!r} session={session_obj.id} "
        f"is_open={session_obj.is_open} is_derived={session_obj.is_derived}",
        flush=True,
    )
    return {"is_derived": bool(session_obj.is_derived)}


@router.get("/health")
async def health(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    postgres = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        postgres = "error"

    rabbitmq = "error"
    try:
        conn = getattr(request.app.state, "amqp_connection", None)
        if conn is not None and not getattr(conn, "is_closed", True):
            rabbitmq = "ok"
    except Exception:
        rabbitmq = "error"

    if postgres == "ok" and rabbitmq == "ok":
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "postgres": postgres,
                "rabbitmq": rabbitmq,
            },
        )
    return JSONResponse(
        status_code=503,
        content={
            "status": "degraded",
            "postgres": postgres,
            "rabbitmq": rabbitmq,
        },
    )
