from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

DEFAULT_PAGE_SIZE = 25


@dataclass
class Page:
    items: list
    page: int
    per_page: int
    total: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total + self.per_page - 1) // self.per_page)

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages


def paginate(db: Session, stmt, page: int = 1, per_page: int = DEFAULT_PAGE_SIZE) -> Page:
    page = max(page, 1)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.limit(per_page).offset((page - 1) * per_page)))
    return Page(items=items, page=page, per_page=per_page, total=total)
