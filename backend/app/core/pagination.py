"""Server-side pagination shared by every collection endpoint."""

from math import ceil
from typing import Generic, List, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Query as OrmQuery, Session

from app.config import settings

T = TypeVar("T")


class PageParams:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="1-based page number"),
        page_size: int = Query(
            settings.default_page_size, ge=1, le=settings.max_page_size, description="Rows per page"
        ),
    ):
        self.page = page
        self.page_size = min(page_size, settings.max_page_size)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def build(cls, items: List[T], total: int, params: PageParams) -> "Page[T]":
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            total_pages=max(1, ceil(total / params.page_size)) if total else 0,
        )


def paginate_query(query: OrmQuery, params: PageParams):
    """Apply LIMIT/OFFSET to a legacy-style ORM query and return (rows, total)."""
    total = query.order_by(None).count()
    rows = query.offset(params.offset).limit(params.page_size).all()
    return rows, total


def paginate_select(db: Session, stmt, params: PageParams):
    """Apply LIMIT/OFFSET to a 2.0-style select and return (rows, total)."""
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(stmt.offset(params.offset).limit(params.page_size)).all()
    return rows, total
