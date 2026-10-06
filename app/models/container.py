from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.common import ContainerStatus, TimestampMixin


class Container(Base, TimestampMixin):
    __tablename__ = "containers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    container_code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    chemical_id: Mapped[int] = mapped_column(ForeignKey("chemicals.id"), nullable=False, index=True)
    batch_lot: Mapped[str | None] = mapped_column(String(100), nullable=True)

    container_size: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)

    initial_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    expected_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    last_physical_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_physical_count_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    date_received: Mapped[date] = mapped_column(Date, nullable=False)
    date_opened: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True, index=True)
    laboratory_id: Mapped[int] = mapped_column(ForeignKey("laboratories.id"), nullable=False, index=True)
    responsible_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), default=ContainerStatus.AVAILABLE.value, nullable=False, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    chemical = relationship("Chemical", back_populates="containers")
    laboratory = relationship("Laboratory", back_populates="containers")
    location = relationship("Location")
    responsible_user = relationship("User", foreign_keys=[responsible_user_id])
    transactions = relationship(
        "InventoryTransaction", back_populates="container", order_by="InventoryTransaction.occurred_at"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Container {self.container_code}>"
