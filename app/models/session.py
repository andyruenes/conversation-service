# FIXED: document-orm-onupdate-semantics
from __future__ import annotations

from datetime import datetime
from uuid import UUID

import uuid6
from sqlalchemy import TIMESTAMP, Boolean, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    user_id: Mapped[str] = mapped_column(
        String(100),index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    # ORM-level onupdate: SQLAlchemy sets this on UPDATE rows touched via the ORM;
    # it is not a database trigger and does not run for raw SQL or other services.
    last_active_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    closed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    organization_id: Mapped[str] = mapped_column(String(100), nullable=True)

    is_derived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    derived_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    
    reactivated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=True)