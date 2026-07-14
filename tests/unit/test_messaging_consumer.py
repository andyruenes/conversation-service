"""Unit tests for RabbitMQ consumer helpers.

Contract: `agent.response` payloads from agent-service use `response` for assistant text.
"""

from app.messaging import consumer as consumer_mod


def test_consumer_error_counter_increments() -> None:
    consumer_mod.consumer_message_errors_total.clear()
    consumer_mod._bump_error_counter("json_decode")
    consumer_mod._bump_error_counter("json_decode")
    assert consumer_mod.consumer_message_errors_total["json_decode"] == 2
