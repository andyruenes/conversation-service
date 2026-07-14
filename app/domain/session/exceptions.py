# FIXED: future-annotations
from __future__ import annotations

from app.domain.shared.exceptions import DomainException


class SessionNotFound(DomainException):
    def __init__(self, user_id: str) -> None:
        super().__init__(f"Session not found for user '{user_id}'")
