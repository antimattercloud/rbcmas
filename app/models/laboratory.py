from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.common import TimestampMixin


class Laboratory(Base, TimestampMixin):
    __tablename__ = "laboratories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    building: Mapped[str] = mapped_column(String(100), default="Research Building", nullable=False)
    floor: Mapped[str] = mapped_column(String(30), nullable=True)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    manager = relationship("User", foreign_keys=[manager_id])
    users = relationship("User", back_populates="laboratory", foreign_keys="User.laboratory_id")
    locations = relationship("Location", back_populates="laboratory")
    containers = relationship("Container", back_populates="laboratory")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Laboratory {self.code} {self.name}>"
