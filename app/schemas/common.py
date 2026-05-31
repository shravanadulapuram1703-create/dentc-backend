"""Cross-cutting API schemas: pagination, list envelope, error contract.

``PaginatedResponse[T]`` is referenced by every list endpoint so the OpenAPI spec
exposes a single, typed pagination component that Orval turns into a reusable
TypeScript generic.
"""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

SortOrder = Literal["asc", "desc"]


class ORMModel(BaseModel):
    """Base for read schemas that map from SQLAlchemy ORM objects."""

    model_config = ConfigDict(from_attributes=True)


class PageMeta(BaseModel):
    page: int = Field(..., ge=1, examples=[1])
    size: int = Field(..., ge=1, examples=[20])
    total: int = Field(..., ge=0, examples=[137])
    pages: int = Field(..., ge=0, examples=[7])


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    meta: PageMeta

    @classmethod
    def build(cls, items: list[T], total: int, page: int, size: int) -> "PaginatedResponse[T]":
        pages = (total + size - 1) // size if size else 0
        return cls(items=items, meta=PageMeta(page=page, size=size, total=total, pages=pages))


class ErrorDetail(BaseModel):
    code: str = Field(..., examples=["not_found"])
    message: str = Field(..., examples=["Patient 42 was not found"])
    details: object | None = None


class ErrorResponse(BaseModel):
    """The single error envelope returned by every failing endpoint."""

    error: ErrorDetail
