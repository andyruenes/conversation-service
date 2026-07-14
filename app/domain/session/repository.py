# FIXED: abstract-bodies-ellipsis
from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.session.entities import Session


class AbstractSessionRepository(ABC):
    @abstractmethod
    async def get_by_user_id(self, user_id: str) -> Session | None: ...

    @abstractmethod
    async def upsert(self, user_id: str) -> Session: ...

    @abstractmethod
    async def close_inactive_sessions(self, hours_threshold: int = 24) -> int: ...
