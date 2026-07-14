from __future__ import annotations

import uuid6
from uuid import UUID

from datetime import datetime
from fastapi import HTTPException, Request
from pydantic import BaseModel

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.config import matches_handoff_phrase, matches_reactivate_phrase
from app.repositories.message import SqlMessageRepository
from app.repositories.session import SqlSessionRepository
from app.schemas.message import MessageCreate, MessageRead
from app.services.message_write import MessageWriteService
from app.services.session import SessionService

router = APIRouter(tags=["messages"])

class OperatorMessageCreate(BaseModel):
    user_id: str
    content: str
    agent_id: UUID | None = None

@router.post("/messages", response_model=MessageRead, status_code=201)
async def create_message(
    body: MessageCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> MessageRead:
    session_service = SessionService(SqlSessionRepository(session))
    session_obj = await session_service.upsert(body.user_id)
    await session.commit()
    
    write_service = MessageWriteService(SqlMessageRepository(session))
    correlation_id = body.correlation_id or uuid6.uuid7()

    # Persistir el mensaje con el rol que llega en el payload. Antes se llamaba
    # SIEMPRE a save_user_message(), por lo que las respuestas de la IA (que el
    # admin-service envía con role="assistant") se guardaban como "user".
    role_savers = {
        "user": write_service.save_user_message,
        "assistant": write_service.save_assistant_message,
        "operator": write_service.save_operator_message,
        "error": write_service.save_error_message,
    }
    saver = role_savers.get(body.role)
    if saver is None:
        raise HTTPException(
            status_code=422, detail=f"Rol inválido: {body.role!r}"
        )

    message = await saver(
        session_obj.id,
        body.content,
        correlation_id,
        body.agent_id,
    )

    # Derivación a operador humano para el camino WhatsApp: si la respuesta del
    # assistant es exactamente la frase de handoff, marcar la sesión como
    # derivada. Es el equivalente, en este endpoint, de lo que el consumer de
    # RabbitMQ ya hace para el webchat.
    print(
        f"[DERIV][create_message] user_id={body.user_id!r} role={body.role!r} "
        f"content={body.content!r} handoff_match={matches_handoff_phrase(body.content)}",
        flush=True,
    )
    if body.role == "assistant" and matches_handoff_phrase(body.content):
        session_model = await session_service.get_by_user_id_model(body.user_id)
        print(
            f"[DERIV][create_message] HANDOFF detectado. "
            f"session={'None' if session_model is None else session_model.id} "
            f"is_derived_actual={None if session_model is None else session_model.is_derived}",
            flush=True,
        )
        if session_model is not None and not session_model.is_derived:
            session_model.is_derived = True
            session_model.derived_at = datetime.utcnow()
            print(
                f"[DERIV][create_message] -> is_derived = True (session={session_model.id})",
                flush=True,
            )
            # NOTA: el evento hacia hermes lo emite el admin-service (único
            # servicio conectado a hermes), no el conversation-service. Aquí solo
            # se actualiza el estado de la sesión (is_derived).

    await session.commit()

    return message


@router.post("/messages/operator", response_model=MessageRead, status_code=201)
async def create_operator_message(
    body: OperatorMessageCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> MessageRead:
    """
    Endpoint para recibir mensajes del operador humano.
    Verifica si es la frase de reactivación y maneja la lógica correspondiente.
    """
    session_service = SessionService(SqlSessionRepository(session))
    session_obj = await session_service.get_by_user_id_model(body.user_id)
    
    if not session_obj:
        print(
            f"[REACT][operator_message] 404 SESIÓN NO ENCONTRADA para user_id={body.user_id!r} "
            f"(¿el 'from' del operador es el número del cliente?)",
            flush=True,
        )
        raise HTTPException(status_code=404, detail="Session not found")

    # Verificar si es la frase de reactivación
    print(
        f"[REACT][operator_message] user_id={body.user_id!r} "
        f"session={'None' if session_obj is None else session_obj.id} "
        f"is_derived_actual={None if session_obj is None else session_obj.is_derived} "
        f"content={body.content!r} reactivate_match={matches_reactivate_phrase(body.content)}",
        flush=True,
    )
    if matches_reactivate_phrase(body.content):
        print(
            f"[REACT][operator_message] REACTIVACIÓN detectada -> is_derived = False "
            f"(session={session_obj.id})",
            flush=True,
        )
        session_obj.is_derived = False
        session_obj.reactivated_at = datetime.utcnow()
        await session.commit()

        # NOTA: el evento de reactivación hacia hermes lo emite el admin-service,
        # que es quien recibe el mensaje del operador desde hermes. Aquí solo se
        # actualiza el estado (is_derived = False).

        write_service = MessageWriteService(SqlMessageRepository(session))
        correlation_id = uuid6.uuid7()
        message = await write_service.save_operator_message(
            session_obj.id,
            body.content,
            correlation_id,
            body.agent_id,
        )
        await session.commit()
        
        return message
    
    # Si no es frase de reactivación, verificar si la sesión está derivada
    if not session_obj.is_derived:
        print(
            f"[REACT][operator_message] 400 SESIÓN NO DERIVADA (is_derived=False) "
            f"-> se rechaza el mensaje del operador (session={session_obj.id})",
            flush=True,
        )
        raise HTTPException(
            status_code=400, 
            detail="Session is not derived to operator. Cannot send operator messages."
        )
    
    # Guardar mensaje normal del operador
    write_service = MessageWriteService(SqlMessageRepository(session))
    correlation_id = uuid6.uuid7()
    message = await write_service.save_operator_message(
        session_obj.id,
        body.content,
        correlation_id,
        body.agent_id,
    )
    await session.commit()
    
    return message