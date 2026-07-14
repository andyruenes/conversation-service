from __future__ import annotations

import json

from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import AbstractChannel


async def publish_msg_received(
    channel: AbstractChannel,
    payload: dict,
) -> None:
    exchange = await channel.declare_exchange(
        "chatbot",
        ExchangeType.TOPIC,
        durable=True,
    )
    body = json.dumps(payload).encode("utf-8")
    await exchange.publish(
        Message(body=body, delivery_mode=DeliveryMode.PERSISTENT),
        routing_key="msg.received",
    )
