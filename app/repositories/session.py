from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import uuid6
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.session.entities import Session
from app.domain.session.repository import AbstractSessionRepository
from app.models.cost import CostModel
from app.models.message import MessageModel
from app.models.session import SessionModel


class SqlSessionRepository(AbstractSessionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: str) -> Session | None:
        # La conversacion en curso = sesion ABIERTA mas reciente. Con multiples
        # sesiones por usuario, scalar_one_or_none() sobre todas lanzaria
        # MultipleResultsFound.
        stmt = (
            select(SessionModel)
            .where(
                SessionModel.user_id == user_id,
                SessionModel.is_open.is_(True),
            )
            .order_by(SessionModel.created_at.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return self._to_entity(row)

    async def upsert(self, user_id: str) -> Session:
        # Reutiliza la sesion ABIERTA mas reciente del usuario; si no hay ninguna
        # (nunca escribio, o la ultima fue cerrada por inactividad), crea una
        # NUEVA. Ya NO se puede usar ON CONFLICT(user_id) porque user_id dejo de
        # ser unico al habilitar multiples sesiones por usuario (migracion
        # 4a203aab4edf), y esa clausula exige un indice unico.
        stmt = (
            select(SessionModel)
            .where(
                SessionModel.user_id == user_id,
                SessionModel.is_open.is_(True),
            )
            .order_by(SessionModel.created_at.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()

        if row is not None:
            row.last_active_at = func.now()
            await self._session.flush()
            await self._session.refresh(row)
            return self._to_entity(row)

        new_session = SessionModel(id=uuid6.uuid7(), user_id=user_id)
        self._session.add(new_session)
        await self._session.flush()
        await self._session.refresh(new_session)
        return self._to_entity(new_session)

    async def get_by_id_model(self, session_id: UUID) -> SessionModel | None:
        """Obtener una sesión por su ID (retorna el modelo directamente)."""
        stmt = select(SessionModel).where(SessionModel.id == session_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_id_model(self, user_id: str) -> SessionModel | None:
        """Obtener la sesión más reciente de un usuario (retorna el modelo directamente)."""
        stmt = select(SessionModel).where(SessionModel.user_id == user_id).order_by(SessionModel.created_at.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    def _to_entity(self, row: SessionModel) -> Session:
        return Session(
            id=row.id,
            user_id=row.user_id,
            created_at=row.created_at,
            last_active_at=row.last_active_at,
            is_open=row.is_open,
            closed_at=row.closed_at,
        )

    async def close_inactive_sessions(self, hours_threshold: int = 24) -> int:
        stmt = (
            update(SessionModel)
            .where(
                SessionModel.is_open,
                SessionModel.last_active_at
                < func.now() - func.make_interval(0, 0, 0, 0, hours_threshold),
            )
            .values(is_open=False, closed_at=func.now())
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount

    async def get_clients_stats(
        self,
        search: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        from sqlalchemy import case, func, select

        stmt = select(
            SessionModel.user_id.label("username"),
            func.count().label("total_conversations"),
            func.sum(case((SessionModel.is_open, 1), else_=0)).label(
                "open_conversations"
            ),
            func.max(SessionModel.last_active_at).label("last_activity"),
        ).group_by(SessionModel.user_id)

        if search:
            stmt = stmt.where(SessionModel.user_id.ilike(f"%{search}%"))

        stmt = stmt.order_by(func.max(SessionModel.last_active_at).desc())

        count_stmt = select(func.count(func.distinct(SessionModel.user_id)))
        if search:
            count_stmt = count_stmt.where(SessionModel.user_id.ilike(f"%{search}%"))

        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar()

        stmt = stmt.offset(offset).limit(limit)

        result = await self._session.execute(stmt)
        rows = result.all()

        items = [
            {
                "username": row.username,
                "total_conversations": row.total_conversations,
                "open_conversations": row.open_conversations or 0,
                "last_activity": row.last_activity,
            }
            for row in rows
        ]
        return items, total

    async def count_open_sessions(self) -> int:
        stmt = select(func.count()).where(SessionModel.is_open)
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def get_metrics(self) -> dict[str, int]:
        from sqlalchemy import Date, cast

        total_users = (
            await self._session.execute(
                select(func.count(func.distinct(SessionModel.user_id)))
            )
        ).scalar() or 0
        total_conversations = (
            await self._session.execute(select(func.count(SessionModel.id)))
        ).scalar() or 0
        open_conversations = (
            await self._session.execute(
                select(func.count()).where(SessionModel.is_open)
            )
        ).scalar() or 0
        today_conversations = (
            await self._session.execute(
                select(func.count()).where(
                    cast(SessionModel.created_at, Date) == func.current_date()
                )
            )
        ).scalar() or 0
        return {
            "total_users": total_users,
            "today_conversations": today_conversations,
            "open_conversations": open_conversations,
            "total_conversations": total_conversations,
        }

    async def get_user_conversations(
        self,
        user_id: str,
        status: str | None = None,  # "open" o "closed"
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        stmt = select(SessionModel).where(SessionModel.user_id == user_id)

        # Filtro por estado
        if status == "open":
            stmt = stmt.where(SessionModel.is_open)
        elif status == "closed":
            stmt = stmt.where(~SessionModel.is_open)

        # Filtro por rango de fechas
        if date_from:
            stmt = stmt.where(SessionModel.created_at >= date_from)
        if date_to:
            stmt = stmt.where(SessionModel.created_at <= date_to)

        # Contar total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar()

        # Aplicar paginación y ordenamiento
        stmt = stmt.order_by(SessionModel.created_at.desc())
        stmt = stmt.offset(offset).limit(limit)

        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        # Conteo de mensajes por sesión en una sola consulta agrupada (evita N+1)
        session_ids = [row.id for row in rows]
        message_counts: dict[UUID, int] = {}
        if session_ids:
            message_count_stmt = (
                select(
                    MessageModel.session_id,
                    func.count().label("message_count"),
                )
                .where(MessageModel.session_id.in_(session_ids))
                .group_by(MessageModel.session_id)
            )
            count_rows = await self._session.execute(message_count_stmt)
            message_counts = {
                row.session_id: row.message_count for row in count_rows.all()
            }

        # Convertir a diccionarios (agent_name se calculará después)
        items = [
            {
                "id": row.id,
                "user_id": row.user_id,
                "created_at": row.created_at,
                "last_active_at": row.last_active_at,
                "is_open": row.is_open,
                "closed_at": row.closed_at,
                "message_count": message_counts.get(row.id, 0),
                "agent_name": None,  # Se llenará desde el servicio
            }
            for row in rows
        ]
        return items, total

    async def get_conversation_detail(self, session_id: UUID) -> dict[str, Any] | None:
        session = (
            await self._session.execute(
                select(SessionModel).where(SessionModel.id == session_id)
            )
        ).scalar_one_or_none()
        if session is None:
            return None

        totals = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(CostModel.input_tokens), 0).label(
                        "input_tokens"
                    ),
                    func.coalesce(func.sum(CostModel.output_tokens), 0).label(
                        "output_tokens"
                    ),
                    func.coalesce(func.sum(CostModel.cache_tokens), 0).label(
                        "cache_tokens"
                    ),
                    func.coalesce(func.sum(CostModel.total_cost), 0.0).label(
                        "total_cost"
                    ),
                ).where(CostModel.session_id == session_id)
            )
        ).one()

        input_tokens = int(totals.input_tokens or 0)
        output_tokens = int(totals.output_tokens or 0)
        cache_tokens = int(totals.cache_tokens or 0)

        return {
            "id": session.id,
            "user_name": session.user_id,
            "status": "open" if session.is_open else "closed",
            "started_at": session.created_at,
            "closed_at": session.closed_at,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_tokens": cache_tokens,  
            "total_tokens": input_tokens + output_tokens + cache_tokens,
            "total_cost": float(totals.total_cost or 0),
        }
