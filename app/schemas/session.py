from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.types import AwareDatetime

from app.domain.session.entities import Session


class SessionCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    organization_id: str | None = None


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: UUID
    user_id: str
    created_at: AwareDatetime
    last_active_at: AwareDatetime
    organization_id: str | None = None

    @classmethod
    def from_entity(cls, entity: Session) -> SessionRead:
        return cls.model_validate(entity.__dict__)
