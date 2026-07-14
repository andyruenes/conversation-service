from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import PaginatedResponse


class OrganizationCostItem(BaseModel):
    organization_id: str
    created_at: datetime
    is_active: bool
    total_conversations: int
    total_cost: float
    input_tokens: int
    input_cost: float
    output_tokens: int
    output_cost: float
    cache_tokens: int
    cache_cost: float
    agents_count: int


class MonthlyCostItem(BaseModel):
    month: str
    total_cost: float


class OrganizationCostsResponse(BaseModel):
    items: list[OrganizationCostItem]
    monthly_evolution: list[MonthlyCostItem]
    total: int
    offset: int
    limit: int


class ConversationCostItem(BaseModel):
    session_id: UUID
    user_id: str
    input_tokens: int
    output_tokens: int
    cache_tokens: int
    input_cost: float
    output_cost: float
    cache_cost: float
    total_cost: float
    is_open: bool
    closed_at: datetime | None


OrganizationConversationsCostsResponse = PaginatedResponse[ConversationCostItem]


class TokenBreakdown(BaseModel):
    tokens: int
    cost: float
    percentage: float


class ModelCost(BaseModel):
    model: str
    cost: float
    percentage: float


class CostBreakdownResponse(BaseModel):
    input_tokens: TokenBreakdown
    output_tokens: TokenBreakdown
    cache_tokens: TokenBreakdown
    by_model: list[ModelCost]
