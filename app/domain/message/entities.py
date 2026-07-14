from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class Message:
    id: UUID
    session_id: UUID
    role: str
    content: str
    created_at: datetime
    agent_id: UUID | None
    correlation_id: UUID | None
