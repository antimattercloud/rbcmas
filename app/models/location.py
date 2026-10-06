from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.common import TimestampMixin


class Location(Base, TimestampMixin):
    """A node in the Building -> Floor -> Laboratory -> Room -> Storage Unit ->
    Cabinet -> Shelf hierarchy. Self-referential tree via parent_id."""

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    location_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True, index=True)
    laboratory_id: Mapped[int | None] = mapped_column(
        ForeignKey("laboratories.id"), nullable=True, index=True
    )
    full_path: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    parent = relationship("Location", remote_side=[id], back_populates="children")
    children = relationship("Location", back_populates="parent")
    laboratory = relationship("Laboratory", back_populates="locations")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Location {self.full_path or self.name}>"
