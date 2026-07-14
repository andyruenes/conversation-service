from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.types import AwareDatetime

from app.domain.message.entities import Message


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: UUID
    session_id: UUID
    agent_id: UUID | None
    role: str
    content: str
    correlation_id: UUID | None
    created_at: AwareDatetime

    @classmethod
    def from_entity(cls, entity: Message) -> MessageRead:
        return cls.model_validate(entity.__dict__)


class PaginatedMessages(BaseModel):
    items: list[MessageRead]
    total: int
    has_more: bool


class MessageCreate(BaseModel):
    user_id: str
    agent_id: UUID
    role: str  # "user" | "assistant" | "error"
    content: str
    correlation_id: UUID | None = None