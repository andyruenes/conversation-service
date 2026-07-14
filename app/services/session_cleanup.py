from __future__ import annotations

import asyncio
import logging

from app.domain.session.repository import AbstractSessionRepository

logger = logging.getLogger(__name__)


async def session_cleanup_task(
    session_repo: AbstractSessionRepository,
    interval_minutes: int = 15,
) -> None:
    while True:
        try:
            closed_count = await session_repo.close_inactive_sessions(
                hours_threshold=24
            )
            if closed_count > 0:
                logger.info(f"Closed {closed_count} inactive sessions")
        except Exception as e:
            logger.error(f"Error closing inactive sessions: {e}", exc_info=True)

        await asyncio.sleep(interval_minutes * 60)
