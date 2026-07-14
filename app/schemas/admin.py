from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.common import PaginatedResponse


class ClientStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    total_conversations: int
    open_conversations: int
    last_activity: datetime


class ClientListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    total_conversations: int
    open_conversations: int
    last_activity: datetime


ClientsListResponse = PaginatedResponse[ClientListItem]


class ConversationMetricsResponse(BaseModel):
    total_users: int
    today_conversations: int
    open_conversations: int
    total_conversations: int


class UserConversationListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: str
    created_at: datetime
    last_active_at: datetime
    is_open: bool
    closed_at: datetime | None
    message_count: int
    agent_name: str | None


UserConversationsResponse = PaginatedResponse[UserConversationListItem]


class ConversationDetailResponse(BaseModel):
    id: UUID
    user_name: str
    status: str
    started_at: datetime
    closed_at: datetime | None
    agent_name: str | None = None
    input_tokens: int
    output_tokens: int
    cache_tokens: int 
    total_tokens: int
    total_cost: float
