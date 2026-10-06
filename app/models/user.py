from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.common import Role, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    laboratory_id: Mapped[int | None] = mapped_column(
        ForeignKey("laboratories.id"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    laboratory = relationship("Laboratory", back_populates="users", foreign_keys=[laboratory_id])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email} ({self.role})>"

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN.value

    @property
    def is_lab_manager(self) -> bool:
        return self.role == Role.LAB_MANAGER.value

    @property
    def is_auditor(self) -> bool:
        return self.role == Role.AUDITOR.value

    @property
    def can_write(self) -> bool:
        return self.role in (Role.ADMIN.value, Role.LAB_MANAGER.value, Role.RESEARCHER.value)
