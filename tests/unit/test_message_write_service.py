from __future__ import annotations

import pytest
import uuid6

from app.domain.message.exceptions import InvalidRole
from app.services.message_write import MessageWriteService
from tests.unit.fakes.fake_message_repo import FakeMessageRepository


async def test_save_user_message_persists_with_role_user() -> None:
    repo = FakeMessageRepository()
    service = MessageWriteService(repo)
    session_id = uuid6.uuid7()
    cid = uuid6.uuid7()
    result = await service.save_user_message(session_id, "hello", correlation_id=cid)
    assert result.role == "user"
    assert result.content == "hello"
    assert result.correlation_id == cid


async def test_save_assistant_message_persists_with_role_assistant() -> None:
    repo = FakeMessageRepository()
    service = MessageWriteService(repo)
    session_id = uuid6.uuid7()
    cid = uuid6.uuid7()
    result = await service.save_assistant_message(
        session_id, "world", correlation_id=cid
    )
    assert result.role == "assistant"


async def test_save_error_message_persists_with_role_error_and_null_correlation() -> (
    None
):
    repo = FakeMessageRepository()
    service = MessageWriteService(repo)
    session_id = uuid6.uuid7()
    result = await service.save_error_message(session_id, "oops", correlation_id=None)
    assert result.role == "error"
    assert result.correlation_id is None


async def test_save_with_invalid_role_raises_InvalidRole() -> None:  # noqa: N802
    repo = FakeMessageRepository()
    service = MessageWriteService(repo)
    session_id = uuid6.uuid7()
    cid = uuid6.uuid7()
    with pytest.raises(InvalidRole) as excinfo:
        await service._save(
            session_id,
            "admin",
            "x",
            None,
            cid,
        )
    assert "admin" in str(excinfo.value)


async def test_correlation_id_is_propagated_to_repo() -> None:
    repo = FakeMessageRepository()
    service = MessageWriteService(repo)
    session_id = uuid6.uuid7()
    cid = uuid6.uuid7()
    await service.save_user_message(session_id, "hello", correlation_id=cid)
    assert len(repo._store) == 1
    assert repo._store[0].correlation_id == cid
