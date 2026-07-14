# FIXED: reuse-config-url-normalizer-remove-unsafe-fallback
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import normalize_database_url_for_asyncpg, settings

async_url = normalize_database_url_for_asyncpg(settings.DATABASE_URL)

engine = create_async_engine(async_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
