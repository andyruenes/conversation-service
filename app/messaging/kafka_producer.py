"""Kafka producer for WhatsApp session events (handoff / reactivate).

Publica al topic `chatbot.whatsapp.session.events` (settings.KAFKA_SESSION_EVENTS_TOPIC),
que es el que consume el admin-service (consumer `consume_session_events`) para
notificar a hermes la derivación/reactivación. Antes existía además un topic
`operator.handoff` al que nadie se suscribía: se eliminó para no publicar dos veces
ni a un topic muerto.
"""

import json
import logging
from datetime import datetime

from aiokafka import AIOKafkaProducer

from app.config import settings

logger = logging.getLogger(__name__)


class OperatorHandoffProducer:
    """Producer para publicar eventos de derivación/reactivación a operador humano."""

    def __init__(self, producer: AIOKafkaProducer) -> None:
        self._producer = producer

    async def publish_session_event(
        self,
        session_id: str,
        user_id: str,
        agent_id: str | None,
        phone_number: str,
        event_type: str,  # "handoff" | "reactivate"
    ) -> None:
        """Publica el evento al topic `chatbot.whatsapp.session.events`.

        Args:
            session_id: ID de la sesión de conversación.
            user_id: ID del usuario.
            agent_id: ID del agente (opcional).
            phone_number: Número de teléfono del usuario.
            event_type: "handoff" o "reactivate".
        """
        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "agent_id": agent_id,
            "phone_number": phone_number,
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
        }
        try:
            await self._producer.send(
                settings.KAFKA_SESSION_EVENTS_TOPIC,
                json.dumps(payload).encode(),
            )
            logger.info(
                "Published session event: topic=%s session=%s user=%s event=%s",
                settings.KAFKA_SESSION_EVENTS_TOPIC,
                session_id,
                user_id,
                event_type,
            )
        except Exception as e:
            logger.error(
                "Failed to publish session event: session=%s error=%s",
                session_id,
                e,
                exc_info=True,
            )

    # Alias de compatibilidad: cualquier llamada antigua a publish_handoff_event
    # ahora publica al MISMO topic (chatbot.whatsapp.session.events). Evita
    # romper llamadas existentes sin reintroducir el topic muerto operator.handoff.
    publish_handoff_event = publish_session_event
