from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.common import PurchaseStatus, utcnow


class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    chemical_id: Mapped[int] = mapped_column(ForeignKey("chemicals.id"), nullable=False, index=True)
    laboratory_id: Mapped[int | None] = mapped_column(ForeignKey("laboratories.id"), nullable=True)

    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_system_suggested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=PurchaseStatus.PENDING.value, nullable=False, index=True)

    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    requested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    chemical = relationship("Chemical")
    laboratory = relationship("Laboratory")
    supplier = relationship("Supplier")
    requested_by = relationship("User", foreign_keys=[requested_by_id])
    decided_by = relationship("User", foreign_keys=[decided_by_id])
