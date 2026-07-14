from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class Session:
    id: UUID
    user_id: str
    created_at: datetime
    last_active_at: datetime
    is_open: bool
    closed_at: datetime | None
