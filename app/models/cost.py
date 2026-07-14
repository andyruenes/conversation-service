from __future__ import annotations

from datetime import datetime
from uuid import UUID

import uuid6
from sqlalchemy import TIMESTAMP, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CostModel(Base):
    __tablename__ = "costs"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )

    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sessions.id"), nullable=False
    )

    model_name: Mapped[str] = mapped_column(String(255), nullable=False)

    input_tokens: Mapped[int] = mapped_column(nullable=False)

    output_tokens: Mapped[int] = mapped_column(nullable=False)

    cache_tokens: Mapped[int] = mapped_column(nullable=False, default=0)

    input_cost: Mapped[float] = mapped_column(nullable=False)

    output_cost: Mapped[float] = mapped_column(nullable=False)

    cache_cost: Mapped[float] = mapped_column(nullable=False, default=0)

    total_cost: Mapped[float] = mapped_column(nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class TokenPriceModel(Base):
    __tablename__ = "token_prices"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )

    model_name: Mapped[str] = mapped_column(String(255), nullable=False)

    input_price_per_million: Mapped[float] = mapped_column(nullable=False)

    output_price_per_million: Mapped[float] = mapped_column(nullable=False)

    cache_price_per_million: Mapped[float] = mapped_column(nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
