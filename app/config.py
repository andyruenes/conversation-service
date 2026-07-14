# FIXED: async-url-normalization-centralized, reject-unknown-database-schemes
from __future__ import annotations

import re
import unicodedata

from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Frases de control de derivación ──────────────────────────────────────────
# Fuente única de verdad. La misma frase debe ir en la instrucción que el
# agent-service le inyecta al modelo (app/nodes/generator.py). La detección
# usa matches_handoff_phrase(), que es tolerante a diferencias menores (punto
# final, mayúsculas, acentos, espacios), porque el modelo casi siempre añade
# un punto al final.
HANDOFF_TO_OPERATOR_PHRASE = "Derivando a operador humano, enseguida le atenderemos"
REACTIVATE_AI_PHRASE = (
    "Le pondré en contacto con la inteligencia artificial para que siga su conversación"
)


def _normalize_phrase(text: str) -> str:
    """Minúsculas, sin acentos, sin puntuación y con espacios colapsados."""
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")  # quita acentos
    t = re.sub(r"[^\w\s]", " ", t)  # quita toda la puntuación
    t = re.sub(r"\s+", " ", t).strip()
    return t


def matches_handoff_phrase(text: str) -> bool:
    """True si `text` es —o empieza con— la frase de derivación.

    Tolera el punto final que el modelo suele añadir, además de diferencias de
    mayúsculas, acentos, espacios y otra puntuación. Evita que la derivación
    falle solo porque el LLM no reprodujo la frase byte a byte.
    """
    if not text:
        return False
    return _normalize_phrase(text).startswith(
        _normalize_phrase(HANDOFF_TO_OPERATOR_PHRASE)
    )


def matches_reactivate_phrase(text: str) -> bool:
    """True si `text` es —o empieza con— la frase de reactivación.

    Tolera punto final, mayúsculas, acentos y espacios, igual que la de
    derivación. El operador escribe la frase a mano, así que rara vez coincide
    byte a byte (acentos en 'pondré'/'conversación', punto final, etc.).
    """
    if not text:
        return False
    return _normalize_phrase(text).startswith(
        _normalize_phrase(REACTIVATE_AI_PHRASE)
    )


def normalize_database_url_for_asyncpg(url: str) -> str:
    """Return an asyncpg SQLAlchemy URL. Idempotent if ``+asyncpg`` is already present."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    raise ValueError(
        "DATABASE_URL must use postgresql://, postgres://, or postgresql+asyncpg:// "
        f"(received {url!r})"
    )


class Settings(BaseSettings):
    DATABASE_URL: str
    RABBITMQ_URL: str
    AGENT_SERVICE_URL: str
    ENVIRONMENT: str = "dev"
    LOG_LEVEL: str = "DEBUG"
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    KAFKA_SESSION_EVENTS_TOPIC: str = "chatbot.whatsapp.session.events"


    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()  # ty: ignore[missing-argument]  # env-backed fields via pydantic-settings
