from __future__ import annotations

import json
from uuid import UUID

import uuid6
from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.api.deps import (
    message_write_service_from_db_session,
    session_service_from_db_session,
)
from app.config import settings
from app.db.session import AsyncSessionLocal
from app.messaging.publisher import publish_msg_received

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{user_id}/{agent_id}")
async def ws_chat(websocket: WebSocket, user_id: str, agent_id: UUID) -> None:
    session_id: UUID | None = None
    try:
        await websocket.accept()

        async with AsyncSessionLocal() as db:
            session_service = session_service_from_db_session(db)
            session_read = await session_service.upsert(user_id)
            await db.commit()
        session_id = session_read.id

        state = websocket.app.state
        state.ws_registry[user_id] = websocket
        state.session_user_map[str(session_id)] = user_id

        async for data in websocket.iter_text():
            correlation_id = uuid6.uuid7()
            try:
                async with AsyncSessionLocal() as db:
                    write_svc = message_write_service_from_db_session(db)
                    await write_svc.save_user_message(
                        session_id,
                        data,
                        correlation_id,
                        agent_id,
                    )
                    await db.commit()
            except Exception as e:
                await websocket.send_text(json.dumps({"error": str(e)}))
                continue

            payload = {
                "session_id": str(session_id),
                "user_id": user_id,
                "message": data,
                "correlation_id": str(correlation_id),
                "agent_id": str(agent_id),
            }
            try:
                await publish_msg_received(state.amqp_channel, payload)
            except Exception as e:
                await websocket.send_text(json.dumps({"error": str(e)}))
    except WebSocketDisconnect:
        pass
    finally:
        if session_id is not None:
            state = websocket.app.state
            state.ws_registry.pop(user_id, None)
            state.session_user_map.pop(str(session_id), None)


@router.websocket("/ws/test/{session_id}")
async def ws_test(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    client = websocket.app.state.http_client
    url = f"{settings.AGENT_SERVICE_URL.rstrip('/')}/agent/test/query"
    try:
        async for data in websocket.iter_text():
            try:
                response = await client.post(
                    url,
                    json={"session_id": session_id, "message": data},
                )
                response.raise_for_status()
                body = response.json()
                await websocket.send_text(body["response"])
            except Exception:
                await websocket.send_text(json.dumps({"error": "agent unavailable"}))
    except WebSocketDisconnect:
        pass
