from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):  # noqa: UP046
    """Generic list wrapper; T is the Read schema per resource."""

    model_config = ConfigDict()

    items: list[T] = Field(description="Page of resources")
    total: int = Field(description="Total matching count before pagination")
    offset: int = Field(description="Number of items skipped")
    limit: int = Field(description="Maximum items in this page")
