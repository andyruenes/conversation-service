from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import aio_pika
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from aiokafka import AIOKafkaProducer

from app.api.admin import router as admin_router
from app.api.costs import router as costs_router
from app.api.deps import message_write_service_from_db_session
from app.api.sessions import router as sessions_router
from app.api.websocket import router as ws_router
from app.api.messages import router as messages_router
from app.config import settings
from app.db.session import AsyncSessionLocal, engine
from app.domain.message.exceptions import InvalidRole, MessageNotFound
from app.domain.session.exceptions import SessionNotFound
from app.domain.shared.exceptions import DomainException
from app.messaging.consumer import start_consumer
from app.services.session_cleanup import session_cleanup_task
from app.services.token_prices_sync import token_prices_sync_task

logger = logging.getLogger(__name__)


def _log_consumer_task_result(task: asyncio.Task) -> None:
    """Surface consumer crashes that would otherwise only appear as Task exception."""
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected error reading consumer task result")
        return
    if exc is not None:
        logger.critical(
            "RabbitMQ consumer task exited with error",
            exc_info=exc,
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # --- startup ---
    app.state.ws_registry = {}
    app.state.session_user_map = {}
    app.state.http_client = httpx.AsyncClient(base_url=settings.AGENT_SERVICE_URL)
    app.state.amqp_connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    app.state.amqp_channel = await app.state.amqp_connection.channel()
    
    
    kafka_producer = None
    operator_handoff_producer = None
    try:
        kafka_producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        )
        await kafka_producer.start()
        app.state.kafka_producer = kafka_producer
        from app.messaging.kafka_producer import OperatorHandoffProducer
        operator_handoff_producer = OperatorHandoffProducer(kafka_producer)

        logger.info("Kafka producer started")
    except Exception as e:
        logger.warning("Failed to start Kafka producer: %s", e)
        app.state.kafka_producer = None
        operator_handoff_producer = None

    app.state.consumer_task = asyncio.create_task(
        start_consumer(
            app.state.amqp_connection,
            app.state,
            AsyncSessionLocal,
            message_write_service_from_db_session,
            operator_handoff_producer,
        )
    )
    app.state.consumer_task.add_done_callback(_log_consumer_task_result)

    # Start session cleanup task
    async def cleanup_wrapper():
        async with AsyncSessionLocal() as db:
            from app.repositories.session import SqlSessionRepository

            repo = SqlSessionRepository(db)
            await session_cleanup_task(repo, interval_minutes=15)

    app.state.session_cleanup_task = asyncio.create_task(cleanup_wrapper())
    app.state.session_cleanup_task.add_done_callback(_log_consumer_task_result)

    # Start token prices sync task
    async def token_prices_sync_wrapper():
        async with AsyncSessionLocal() as db:
            from app.repositories.cost import SqlCostRepository
            
            repo = SqlCostRepository(db)
            await token_prices_sync_task(repo, interval_hours=24)

    app.state.token_prices_sync_task = asyncio.create_task(token_prices_sync_wrapper())
    app.state.token_prices_sync_task.add_done_callback(_log_consumer_task_result)


    yield

    # --- shutdown ---
    app.state.consumer_task.cancel()
    app.state.session_cleanup_task.cancel()
    app.state.token_prices_sync_task.cancel()
    await asyncio.gather(app.state.consumer_task, return_exceptions=True)
    await asyncio.gather(app.state.session_cleanup_task, return_exceptions=True)
    await asyncio.gather(app.state.token_prices_sync_task, return_exceptions=True)
    
    if hasattr(app.state, "kafka_producer") and app.state.kafka_producer:
        await app.state.kafka_producer.stop()
        logger.info("Kafka producer stopped")   
    
    await app.state.amqp_connection.close()
    await app.state.http_client.aclose()
    await engine.dispose()


app = FastAPI(
    title="conversation-service",
    version="1.0.0",
    root_path="/api/conv",
    lifespan=lifespan,
)

app.include_router(sessions_router, prefix="")
app.include_router(ws_router)
app.include_router(admin_router, prefix="")
app.include_router(costs_router, prefix="")
app.include_router(messages_router, prefix="")


@app.exception_handler(SessionNotFound)
async def session_not_found_handler(
    request: Request,
    exc: SessionNotFound,
) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(MessageNotFound)
async def message_not_found_handler(
    request: Request,
    exc: MessageNotFound,
) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InvalidRole)
async def invalid_role_handler(request: Request, exc: InvalidRole) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(DomainException)
async def domain_exception_handler(
    request: Request,
    exc: DomainException,
) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
