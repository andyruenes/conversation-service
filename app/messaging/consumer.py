from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID
from datetime import datetime

from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import AbstractConnection, AbstractIncomingMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import matches_handoff_phrase
from app.repositories.cost import SqlCostRepository
from app.services.message_write import MessageWriteService

from app.repositories.session import SqlSessionRepository
from app.services.session import SessionService
from app.messaging.kafka_producer import OperatorHandoffProducer
 
logger = logging.getLogger(__name__)

# Metrics-style counters (process-wide; for logs / future Prometheus)
consumer_message_errors_total: dict[str, int] = {}
DLQ_ROUTING_KEY = "agent.responses.dlq"


def _parse_uuid(value: str, field: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as e:
        raise ValueError(f"invalid UUID for {field}: {value!r}") from e


def _bump_error_counter(key: str) -> None:
    consumer_message_errors_total[key] = consumer_message_errors_total.get(key, 0) + 1


async def _push_ws(app_state: Any, session_id_str: str, text: str) -> None:
    """Push to WebSocket if user is connected; never raises."""
    session_user_map: dict[str, str] = (
        getattr(app_state, "session_user_map", None) or {}
    )
    user_id = session_user_map.get(session_id_str)
    if user_id is None:
        logger.debug("No user_id in session_user_map for session %s", session_id_str)
        return
    ws_registry: dict[str, Any] = getattr(app_state, "ws_registry", None) or {}
    ws = ws_registry.get(user_id)
    if ws is None:
        logger.debug("No WebSocket in ws_registry for user %s", user_id)
        return
    try:
        await asyncio.wait_for(ws.send_text(text), timeout=5.0)
    except Exception:
        logger.warning(
            "WebSocket push failed for session=%s user=%s",
            session_id_str,
            user_id,
            exc_info=True,
        )


async def _publish_dlq(
    connection: AbstractConnection,
    raw_body: bytes,
    incoming_routing_key: str,
    reason: str,
) -> None:
    """Best-effort dead-letter publish for inspection (does not raise)."""
    try:
        channel = await connection.channel()
        try:
            exchange = await channel.declare_exchange(
                "chatbot",
                ExchangeType.TOPIC,
                durable=True,
            )
            envelope = {
                "failed_routing_key": incoming_routing_key,
                "error": reason[:8000],
                "original_body_b64": base64.b64encode(raw_body).decode("ascii"),
            }
            await exchange.publish(
                Message(
                    body=json.dumps(envelope).encode("utf-8"),
                    delivery_mode=DeliveryMode.PERSISTENT,
                ),
                routing_key=DLQ_ROUTING_KEY,
            )
            logger.warning(
                "Published message to DLQ routing_key=%s reason=%s",
                DLQ_ROUTING_KEY,
                reason[:200],
            )
        finally:
            if not getattr(channel, "is_closed", True):
                await channel.close()
    except Exception:
        logger.exception("Failed to publish to DLQ")


async def _dispatch_payload(
    payload: dict[str, Any],
    routing_key: str,
    app_state: Any,
    session_factory: async_sessionmaker[AsyncSession],
    message_write_service_factory: Callable[[AsyncSession], MessageWriteService],
    operator_handoff_producer: OperatorHandoffProducer | None = None,
) -> None:
    """Core handling; may raise on invalid data or DB errors."""
    if routing_key == "agent.token":
        # Reenviar cada token al WebSocket en el formato que espera el frontend
        # ({"type": "token", "content": ...}). Antes esta routing key caía en la
        # rama "unknown routing key" y se descartaba, por lo que la UI mostraba
        # la burbuja vacía (solo llegaba el "done" con la latencia).
        session_id_str = str(payload["session_id"])
        token = str(payload.get("token", ""))
        if token:
            await _push_ws(
                app_state,
                session_id_str,
                json.dumps({"type": "token", "content": token}),
            )
        return

    if routing_key == "agent.response":
        session_id_str = str(payload["session_id"])
        content = str(payload["response"])
        correlation_id = _parse_uuid(str(payload["correlation_id"]), "correlation_id")
        agent_raw = payload.get("agent_id")
        agent_id = (
            None if agent_raw is None else _parse_uuid(str(agent_raw), "agent_id")
        )
 
        # Verificar si es la frase de derivación
        if matches_handoff_phrase(content):
            async with session_factory() as session:
                session_service = SessionService(SqlSessionRepository(session))
                session_obj = await session_service.get_by_id_model(UUID(session_id_str))
                if session_obj:
                    session_obj.is_derived = True
                    session_obj.derived_at = datetime.utcnow()
                    await session.commit()
                    # El camino webchat (test UI) no pasa por hermes, así que no
                    # se emite ningún evento de sesión aquí. El admin-service es
                    # quien emite hacia hermes en el camino WhatsApp.
            
            # Guardar el mensaje de derivación y enviar WebSocket
            async with session_factory() as session:
                write_service = message_write_service_factory(session)
                await write_service.save_assistant_message(
                    UUID(session_id_str),
                    content,
                    correlation_id,
                    agent_id,
                )
                await session.commit()
            
            await _push_ws(app_state, session_id_str, json.dumps({"type": "done"}))
            logger.info(
                "Session %s derived to operator at %s",
                session_id_str,
                datetime.utcnow().isoformat()
            )
            return
    
        # Si no es frase de derivación, verificar si la sesión está derivada
        async with session_factory() as session:
            session_service = SessionService(SqlSessionRepository(session))
            session_obj = await session_service.get_by_id_model(UUID(session_id_str))
            
            if session_obj and session_obj.is_derived:
                logger.info(
                    "Session %s is derived to operator, ignoring AI response",
                    session_id_str
                )
                # No guardar ni procesar respuestas de IA cuando está derivado
                return
            
            # Procesamiento normal si no está derivado
            write_service = message_write_service_factory(session)
            await write_service.save_assistant_message(
                UUID(session_id_str),
                content,
                correlation_id,
                agent_id,
            )
    
            try:
                cost_repo = SqlCostRepository(session)
                model_name = payload.get("model_name") or "gpt-4o"
                input_tokens = payload.get("input_tokens") or 0
                output_tokens = payload.get("output_tokens") or 0
                cache_tokens = payload.get("cache_tokens") or 0
    
                if input_tokens == 0 and output_tokens == 0 and cache_tokens == 0:
                    logger.debug(
                        "No token usage for session %s; skipping cost row",
                        session_id_str,
                    )
                else:
                    price = await cost_repo.get_current_price(model_name)
                    if price is None:
                        logger.warning("No price found for model %s", model_name)
                    else:
                        input_cost = (
                            input_tokens / 1_000_000
                        ) * price.input_price_per_million
                        output_cost = (
                            output_tokens / 1_000_000
                        ) * price.output_price_per_million
                        cache_cost = (
                            cache_tokens / 1_000_000
                        ) * price.cache_price_per_million
                        total_cost = input_cost + output_cost + cache_cost
    
                        await cost_repo.save(
                            session_id=UUID(session_id_str),
                            model_name=model_name,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cache_tokens=cache_tokens,
                            input_cost=input_cost,
                            output_cost=output_cost,
                            cache_cost=cache_cost,
                            total_cost=total_cost,
                        )
                        logger.info(
                            "Cost saved for session %s: total=$%.6f",
                            session_id_str,
                            total_cost,
                        )
            except Exception as e:
                logger.exception("Failed to save cost: %s", e)
    
            await session.commit()
    
        await _push_ws(app_state, session_id_str, json.dumps({"type": "done"}))
        return

    if routing_key == "agent.failed":
        session_id_str = str(payload["session_id"])
        error_text = str(payload["error"])
        corr_raw = payload.get("correlation_id")
        failed_correlation_id: UUID | None = (
            _parse_uuid(str(corr_raw), "correlation_id")
            if corr_raw is not None
            else None
        )
        agent_raw = payload.get("agent_id")
        agent_id = (
            None if agent_raw is None else _parse_uuid(str(agent_raw), "agent_id")
        )

        async with session_factory() as session:
            write_service = message_write_service_factory(session)
            result = await write_service.save_error_message(
                UUID(session_id_str),
                error_text,
                failed_correlation_id,
                agent_id,
            )
            await session.commit()

        await _push_ws(
            app_state,
            session_id_str,
            json.dumps({"type": "error", "content": result.content}),
        )
        return

    logger.error("unknown routing key: %r; message skipped", routing_key)


async def _handle_incoming_message(
    message: AbstractIncomingMessage,
    connection: AbstractConnection,
    app_state: Any,
    session_factory: async_sessionmaker[AsyncSession],
    message_write_service_factory: Callable[[AsyncSession], MessageWriteService],
    operator_handoff_producer: OperatorHandoffProducer | None,
) -> None:
    raw = message.body
    rk = message.routing_key or ""

    async with message.process(requeue=False):
        try:
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                _bump_error_counter("json_decode")
                reason = f"invalid JSON or encoding: {e}"
                logger.exception("RabbitMQ message invalid JSON: %s", reason)
                await _publish_dlq(connection, raw, rk, reason)
                return

            if not isinstance(payload, dict):
                _bump_error_counter("payload_not_object")
                reason = "message payload must be a JSON object"
                logger.error(reason)
                await _publish_dlq(connection, raw, rk, reason)
                return

            await _dispatch_payload(
                payload,
                rk,
                app_state,
                session_factory,
                message_write_service_factory,
                operator_handoff_producer,
            )
        except Exception as e:
            _bump_error_counter(f"handler:{rk}")
            reason = f"{type(e).__name__}: {e}"
            logger.exception(
                "Error handling RabbitMQ message routing_key=%s body_preview=%r",
                rk,
                raw[:500],
            )
            await _publish_dlq(connection, raw, rk, reason)


async def start_consumer(
    connection: AbstractConnection,
    app_state: Any,
    session_factory: async_sessionmaker[AsyncSession],
    message_write_service_factory: Callable[[AsyncSession], MessageWriteService],
    operator_handoff_producer: OperatorHandoffProducer | None = None,
) -> None:
    channel = await connection.channel()
    try:
        exchange = await channel.declare_exchange(
            "chatbot",
            ExchangeType.TOPIC,
            durable=True,
        )
        queue = await channel.declare_queue("agent.responses", durable=True)
        await queue.bind(exchange, routing_key="agent.token")
        await queue.bind(exchange, routing_key="agent.response")
        await queue.bind(exchange, routing_key="agent.failed")

        dlq_queue = await channel.declare_queue("agent.responses.dlq", durable=True)
        await dlq_queue.bind(exchange, routing_key=DLQ_ROUTING_KEY)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                await _handle_incoming_message(
                    message,
                    connection,
                    app_state,
                    session_factory,
                    message_write_service_factory,
                    operator_handoff_producer,
                )
    except asyncio.CancelledError:
        raise
    finally:
        if not getattr(channel, "is_closed", True):
            await channel.close()
