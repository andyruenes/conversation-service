from __future__ import annotations

from typing import Any
from uuid import UUID

import uuid6
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cost import CostModel, TokenPriceModel
from app.models.session import SessionModel


class SqlCostRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def get_current_price(self, model_name: str) -> TokenPriceModel | None:
        # El catálogo de precios usa ids estilo OpenRouter (p.ej. "openai/gpt-4o"),
        # pero el modelo llamado vía OpenAI directo es un id desnudo ("gpt-4o").
        # Probamos coincidencia exacta y, si falla, el id con prefijo de proveedor.
        candidates = [model_name]
        if "/" not in model_name:
            candidates.append(f"openai/{model_name}")

        stmt = (
            select(TokenPriceModel)
            .where(TokenPriceModel.model_name.in_(candidates))
            .order_by(TokenPriceModel.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_organizations_costs(
        self,
        month: int | None = None,
        year: int | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
        from sqlalchemy import extract

        base_join = (
            select(
                SessionModel.organization_id,
                SessionModel.created_at,
                SessionModel.is_open,
                CostModel.total_cost,
                CostModel.input_tokens,
                CostModel.input_cost,
                CostModel.output_tokens,
                CostModel.output_cost,
                CostModel.cache_tokens,
                CostModel.cache_cost,
            )
            .join(CostModel, CostModel.session_id == SessionModel.id)
            .where(SessionModel.organization_id.is_not(None))
        )

        if month:
            base_join = base_join.where(extract("month", CostModel.created_at) == month)
        if year:
            base_join = base_join.where(extract("year", CostModel.created_at) == year)

        subq = base_join.subquery()

        agg_stmt = (
            select(
                subq.c.organization_id,
                func.min(subq.c.created_at).label("created_at"),
                func.bool_or(subq.c.is_open).label("is_active"),
                func.count().label("total_conversations"),
                func.sum(subq.c.total_cost).label("total_cost"),
                func.sum(subq.c.input_tokens).label("input_tokens"),
                func.sum(subq.c.input_cost).label("input_cost"),
                func.sum(subq.c.output_tokens).label("output_tokens"),
                func.sum(subq.c.output_cost).label("output_cost"),
                func.sum(subq.c.cache_tokens).label("cache_tokens"),
                func.sum(subq.c.cache_cost).label("cache_cost"),
            )
            .group_by(subq.c.organization_id)
            .order_by(func.sum(subq.c.total_cost).desc())
        )

        count_stmt = select(func.count(func.distinct(subq.c.organization_id)))
        total = (await self._session.execute(count_stmt)).scalar() or 0

        rows = (await self._session.execute(agg_stmt.offset(offset).limit(limit))).all()
        items = [
            {
                "organization_id": r.organization_id,
                "created_at": r.created_at,
                "is_active": r.is_active,
                "total_conversations": r.total_conversations,
                "total_cost": float(r.total_cost or 0),
                "input_tokens": r.input_tokens or 0,
                "input_cost": float(r.input_cost or 0),
                "output_tokens": r.output_tokens or 0,
                "output_cost": float(r.output_cost or 0),
                "cache_tokens": r.cache_tokens or 0,
                "cache_cost": float(r.cache_cost or 0),
                "agents_count": 0,
            }
            for r in rows
        ]

        # Reuse a single to_char expression so the format renders as one shared
        # bind parameter; otherwise Postgres sees distinct placeholders in
        # SELECT/GROUP BY and rejects the grouping (GroupingError).
        month_col = func.to_char(CostModel.created_at, "YYYY-MM")
        monthly_stmt = (
            select(
                month_col.label("month"),
                func.sum(CostModel.total_cost).label("total_cost"),
            )
            .join(SessionModel, CostModel.session_id == SessionModel.id)
            .where(SessionModel.organization_id.is_not(None))
            .group_by(month_col)
            .order_by(month_col)
        )
        monthly_rows = (await self._session.execute(monthly_stmt)).all()
        monthly = [
            {"month": r.month, "total_cost": float(r.total_cost or 0)}
            for r in monthly_rows
        ]

        return items, monthly, total

    async def get_organization_conversations_costs(
        self,
        organization_id: str,
        month: int | None = None,
        year: int | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        from sqlalchemy import extract

        stmt = (
            select(
                CostModel.session_id,
                SessionModel.user_id,
                SessionModel.is_open,
                SessionModel.closed_at,
                func.sum(CostModel.input_tokens).label("input_tokens"),
                func.sum(CostModel.output_tokens).label("output_tokens"),
                func.sum(CostModel.cache_tokens).label("cache_tokens"),
                func.sum(CostModel.input_cost).label("input_cost"),
                func.sum(CostModel.output_cost).label("output_cost"),
                func.sum(CostModel.cache_cost).label("cache_cost"),
                func.sum(CostModel.total_cost).label("total_cost"),
            )
            .join(SessionModel, CostModel.session_id == SessionModel.id)
            .where(SessionModel.organization_id == organization_id)
            .group_by(
                CostModel.session_id,
                SessionModel.user_id,
                SessionModel.is_open,
                SessionModel.closed_at,
            )
        )

        if month:
            stmt = stmt.where(extract("month", CostModel.created_at) == month)
        if year:
            stmt = stmt.where(extract("year", CostModel.created_at) == year)

        count_stmt = (
            select(func.count(func.distinct(CostModel.session_id)))
            .join(SessionModel, CostModel.session_id == SessionModel.id)
            .where(SessionModel.organization_id == organization_id)
        )
        if month:
            count_stmt = count_stmt.where(
                extract("month", CostModel.created_at) == month
            )
        if year:
            count_stmt = count_stmt.where(extract("year", CostModel.created_at) == year)

        total = (await self._session.execute(count_stmt)).scalar() or 0
        rows = (
            await self._session.execute(
                stmt.order_by(func.sum(CostModel.total_cost).desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()

        items = [
            {
                "session_id": r.session_id,
                "user_id": r.user_id,
                "is_open": r.is_open,
                "closed_at": r.closed_at,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cache_tokens": r.cache_tokens,
                "input_cost": float(r.input_cost or 0),
                "output_cost": float(r.output_cost or 0),
                "cache_cost": float(r.cache_cost or 0),
                "total_cost": float(r.total_cost or 0),
            }
            for r in rows
        ]
        return items, total

    async def get_breakdown(self) -> dict[str, Any]:
        total_stmt = select(
            func.sum(CostModel.input_tokens).label("input_tokens"),
            func.sum(CostModel.output_tokens).label("output_tokens"),
            func.sum(CostModel.cache_tokens).label("cache_tokens"),
            func.sum(CostModel.input_cost).label("input_cost"),
            func.sum(CostModel.output_cost).label("output_cost"),
            func.sum(CostModel.cache_cost).label("cache_cost"),
            func.sum(CostModel.total_cost).label("total_cost"),
        )
        totals = (await self._session.execute(total_stmt)).one()

        total_cost = float(totals.total_cost or 0)
        input_cost = float(totals.input_cost or 0)
        output_cost = float(totals.output_cost or 0)
        cache_cost = float(totals.cache_cost or 0)

        def pct(part: float) -> float:
            return round(part / total_cost * 100, 2) if total_cost else 0.0

        model_stmt = (
            select(
                CostModel.model_name,
                func.sum(CostModel.total_cost).label("cost"),
            )
            .group_by(CostModel.model_name)
            .order_by(func.sum(CostModel.total_cost).desc())
        )
        model_rows = (await self._session.execute(model_stmt)).all()

        return {
            "input_tokens": {
                "tokens": totals.input_tokens or 0,
                "cost": input_cost,
                "percentage": pct(input_cost),
            },
            "output_tokens": {
                "tokens": totals.output_tokens or 0,
                "cost": output_cost,
                "percentage": pct(output_cost),
            },
            "cache_tokens": {
                "tokens": totals.cache_tokens or 0,
                "cost": cache_cost,
                "percentage": pct(cache_cost),
            },
            "by_model": [
                {
                    "model": r.model_name,
                    "cost": float(r.cost or 0),
                    "percentage": pct(float(r.cost or 0)),
                }
                for r in model_rows
            ],
        }

    async def save(
        self,
        session_id: UUID,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        cache_tokens: int,
        input_cost: float,
        output_cost: float,
        cache_cost: float,
        total_cost: float,
    ) -> CostModel:
        cost = CostModel(
            id=uuid6.uuid7(),
            session_id=session_id,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_tokens=cache_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            cache_cost=cache_cost,
            total_cost=total_cost,
        )
        self._session.add(cost)
        await self._session.flush()
        await self._session.refresh(cost)
        return cost

    async def upsert_token_price(
        self,
        model_name: str,
        input_price_per_million: float,
        output_price_per_million: float,
        cache_price_per_million: float,
    ) -> TokenPriceModel:
        # Obtener el precio actual más reciente
        current = await self.get_current_price(model_name)

        # Si existe y no cambió, retornar el existente
        if current and (
            current.input_price_per_million == input_price_per_million
            and current.output_price_per_million == output_price_per_million
            and current.cache_price_per_million == cache_price_per_million
        ):
            return current

        # Insertar nuevo registro
        new_price = TokenPriceModel(
            id=uuid6.uuid7(),
            model_name=model_name,
            input_price_per_million=input_price_per_million,
            output_price_per_million=output_price_per_million,
            cache_price_per_million=cache_price_per_million,
        )
        self._session.add(new_price)
        await self._session.flush()
        await self._session.refresh(new_price)
        return new_price
