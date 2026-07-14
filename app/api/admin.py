from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic.types import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_message_read_service, get_session
from app.schemas.admin import (
    ClientsListResponse,
    ConversationDetailResponse,
    ConversationMetricsResponse,
    UserConversationsResponse,
)
from app.schemas.message import PaginatedMessages
from app.services.admin import AdminService
from app.services.message_read import MessageReadService

router = APIRouter(tags=["admin"])


def get_admin_service(session: AsyncSession = Depends(get_session)) -> AdminService:
    return AdminService(session)


@router.get("/admin/clients", response_model=ClientsListResponse)
async def list_clients(
    search: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    admin_service: AdminService = Depends(get_admin_service),
) -> ClientsListResponse:
    items = await admin_service.list_clients(search=search, offset=offset, limit=limit)
    total = await admin_service.count_clients(search=search)
    return ClientsListResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/admin/clients/count")
async def count_clients(
    search: str | None = Query(None),
    admin_service: AdminService = Depends(get_admin_service),
) -> dict[str, int]:
    total = await admin_service.count_clients(search=search)
    return {"total": total}


@router.get("/admin/conversations/metrics", response_model=ConversationMetricsResponse)
async def get_conversation_metrics(
    admin_service: AdminService = Depends(get_admin_service),
) -> ConversationMetricsResponse:
    return await admin_service.get_metrics()


@router.get("/admin/conversations/count")
async def count_open_conversations(
    admin_service: AdminService = Depends(get_admin_service),
) -> dict[str, int]:
    count = await admin_service.count_open_conversations()
    return {"count": count}


@router.get(
    "/admin/clients/{user_id}/conversations", response_model=UserConversationsResponse
)
async def list_user_conversations(
    user_id: str,
    status: str | None = Query(None, description="Filter by status: open or closed"),
    date_from: datetime | None = Query(
        None, description="Filter conversations from this date"
    ),
    date_to: datetime | None = Query(
        None, description="Filter conversations until this date"
    ),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    admin_service: AdminService = Depends(get_admin_service),
) -> UserConversationsResponse:
    items = await admin_service.list_user_conversations(
        user_id=user_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        offset=offset,
        limit=limit,
    )
    total = await admin_service.count_user_conversations(
        user_id=user_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    return UserConversationsResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/admin/conversations/{session_id}/messages", response_model=PaginatedMessages
)
async def list_conversation_messages(
    session_id: UUID,
    message_read_service: MessageReadService = Depends(get_message_read_service),
    limit: int = Query(default=50, ge=1, le=100),
    before: AwareDatetime | None = Query(default=None),
) -> PaginatedMessages:
    # Necesitas modificar MessageReadService para aceptar session_id en lugar de user_id
    return await message_read_service.get_session_messages(session_id, limit, before)


@router.get(
    "/admin/conversations/{session_id}", response_model=ConversationDetailResponse
)
async def get_conversation_detail(
    session_id: UUID,
    admin_service: AdminService = Depends(get_admin_service),
) -> ConversationDetailResponse:
    detail = await admin_service.get_conversation_detail(session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return detail


@router.get("/admin/clients/{user_id}/conversations/count")
async def count_user_conversations(
    user_id: str,
    status: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    admin_service: AdminService = Depends(get_admin_service),
) -> dict[str, int]:
    total = await admin_service.count_user_conversations(
        user_id=user_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    return {"total": total}
