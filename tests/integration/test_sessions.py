from __future__ import annotations

from datetime import datetime
from uuid import UUID

import httpx
import pytest

pytestmark = pytest.mark.usefixtures("truncate_all")


async def test_post_sessions_creates_new_session(client: httpx.AsyncClient) -> None:
    r = await client.post("/sessions", json={"user_id": "alice"})
    assert r.status_code == 201
    body = r.json()
    assert body["user_id"] == "alice"
    UUID(body["id"])  # valid UUID
    assert body["created_at"]
    assert body["last_active_at"]


async def test_post_sessions_upsert_returns_same_session(
    client: httpx.AsyncClient,
) -> None:
    t1 = (await client.post("/sessions", json={"user_id": "alice"})).json()
    t2 = (await client.post("/sessions", json={"user_id": "alice"})).json()
    assert t1["id"] == t2["id"]
    la1 = datetime.fromisoformat(t1["last_active_at"])
    la2 = datetime.fromisoformat(t2["last_active_at"])
    assert la2 >= la1


async def test_post_sessions_different_users_get_different_ids(
    client: httpx.AsyncClient,
) -> None:
    alice = (await client.post("/sessions", json={"user_id": "alice"})).json()
    bob = (await client.post("/sessions", json={"user_id": "bob"})).json()
    assert alice["id"] != bob["id"]


async def test_get_messages_returns_empty_for_new_session(
    client: httpx.AsyncClient,
) -> None:
    await client.post("/sessions", json={"user_id": "carol"})
    r = await client.get("/sessions/carol/messages")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["has_more"] is False


async def test_get_messages_returns_404_for_unknown_user(
    client: httpx.AsyncClient,
) -> None:
    r = await client.get("/sessions/ghost-user-xyz/messages")
    assert r.status_code == 404


async def test_get_messages_limit_query_param_is_validated(
    client: httpx.AsyncClient,
) -> None:
    await client.post("/sessions", json={"user_id": "alice"})
    r0 = await client.get("/sessions/alice/messages", params={"limit": 0})
    assert r0.status_code == 422
    r101 = await client.get("/sessions/alice/messages", params={"limit": 101})
    assert r101.status_code == 422
