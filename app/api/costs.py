from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.repositories.cost import SqlCostRepository
from app.schemas.costs import (
    ConversationCostItem,
    CostBreakdownResponse,
    OrganizationConversationsCostsResponse,
    OrganizationCostsResponse,
)

router = APIRouter(tags=["costs"])


def get_cost_repo(session: AsyncSession = Depends(get_session)) -> SqlCostRepository:
    return SqlCostRepository(session)


@router.get("/admin/costs/organizations", response_model=OrganizationCostsResponse)
async def list_organizations_costs(
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2020, le=2030),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    repo: SqlCostRepository = Depends(get_cost_repo),
) -> OrganizationCostsResponse:
    items, monthly, total = await repo.get_organizations_costs(
        month=month, year=year, offset=offset, limit=limit
    )
    return OrganizationCostsResponse(
        items=items,
        monthly_evolution=monthly,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/admin/costs/organizations/{organization_id}/conversations",
    response_model=OrganizationConversationsCostsResponse,
)
async def list_organization_conversations_costs(
    organization_id: str,
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2020, le=2030),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    repo: SqlCostRepository = Depends(get_cost_repo),
) -> OrganizationConversationsCostsResponse:
    items, total = await repo.get_organization_conversations_costs(
        organization_id=organization_id,
        month=month,
        year=year,
        offset=offset,
        limit=limit,
    )
    return OrganizationConversationsCostsResponse(
        items=[ConversationCostItem(**item) for item in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/admin/costs/breakdown", response_model=CostBreakdownResponse)
async def get_cost_breakdown(
    repo: SqlCostRepository = Depends(get_cost_repo),
) -> CostBreakdownResponse:
    data = await repo.get_breakdown()
    return CostBreakdownResponse(**data)
