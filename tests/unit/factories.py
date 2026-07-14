from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import uuid6

from app.domain.message.entities import Message
from app.domain.session.entities import Session


def make_session(**overrides: Any) -> Session:
    defaults: dict[str, Any] = {
        "id": uuid6.uuid7(),
        "user_id": "test-user",
        "created_at": datetime.now(tz=UTC),
        "last_active_at": datetime.now(tz=UTC),
    }
    merged = {**defaults, **overrides}
    return Session(
        id=merged["id"],
        user_id=merged["user_id"],
        created_at=merged["created_at"],
        last_active_at=merged["last_active_at"],
    )


def make_message(**overrides: Any) -> Message:
    defaults: dict[str, Any] = {
        "id": uuid6.uuid7(),
        "session_id": uuid6.uuid7(),
        "role": "user",
        "content": "hello",
        "created_at": datetime.now(tz=UTC),
        "agent_id": None,
        "correlation_id": uuid6.uuid7(),
    }
    merged = {**defaults, **overrides}
    return Message(
        id=merged["id"],
        session_id=merged["session_id"],
        role=merged["role"],
        content=merged["content"],
        created_at=merged["created_at"],
        agent_id=merged["agent_id"],
        correlation_id=merged["correlation_id"],
    )
