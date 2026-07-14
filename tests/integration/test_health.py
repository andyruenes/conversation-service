from __future__ import annotations

import httpx


async def test_health_returns_200_when_stack_is_up(client: httpx.AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["postgres"] == "ok"
    assert body["rabbitmq"] == "ok"
