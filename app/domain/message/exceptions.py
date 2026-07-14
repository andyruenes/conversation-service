# FIXED: future-annotations
from __future__ import annotations

from uuid import UUID

from app.domain.shared.exceptions import DomainException


class MessageNotFound(DomainException):
    def __init__(self, message_id: UUID) -> None:
        super().__init__(f"Message not found for id '{message_id}'")


class InvalidRole(DomainException):
    def __init__(self, role: str) -> None:
        valid_roles = ("user", "assistant", "error")
        super().__init__(
            f"Invalid role '{role}'. Valid values are: {', '.join(valid_roles)}"
        )
