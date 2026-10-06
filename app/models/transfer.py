from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.common import TransferStatus, utcnow


class TransferRecord(Base):
    __tablename__ = "transfer_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transfer_code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)

    source_laboratory_id: Mapped[int] = mapped_column(ForeignKey("laboratories.id"), nullable=False)
    destination_laboratory_id: Mapped[int] = mapped_column(ForeignKey("laboratories.id"), nullable=False)
    destination_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    destination_container_id: Mapped[int | None] = mapped_column(ForeignKey("containers.id"), nullable=True)

    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    receiver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=TransferStatus.PENDING.value, nullable=False, index=True)

    transaction_out_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_transactions.id"), nullable=True)
    transaction_in_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_transactions.id"), nullable=True)

    requested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    container = relationship("Container", foreign_keys=[container_id])
    destination_container = relationship("Container", foreign_keys=[destination_container_id])
    source_laboratory = relationship("Laboratory", foreign_keys=[source_laboratory_id])
    destination_laboratory = relationship("Laboratory", foreign_keys=[destination_laboratory_id])
    destination_location = relationship("Location")
    sender = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Transfer {self.transfer_code} {self.status}>"


class PhysicalCount(Base):
    __tablename__ = "physical_counts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), nullable=False, index=True)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_transactions.id"), nullable=True)

    expected_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    physical_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    variance: Mapped[float] = mapped_column(Float, nullable=False)
    variance_percent: Mapped[float] = mapped_column(Float, nullable=False)

    counted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    counted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    container = relationship("Container")
    counted_by = relationship("User")
    transaction = relationship("InventoryTransaction")


class InventoryAdjustment(Base):
    __tablename__ = "inventory_adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), nullable=False, index=True)
    physical_count_id: Mapped[int | None] = mapped_column(ForeignKey("physical_counts.id"), nullable=True)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_transactions.id"), nullable=True)

    previous_expected_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    physical_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    difference: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    reason_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approval_status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    container = relationship("Container")
    physical_count = relationship("PhysicalCount")
    transaction = relationship("InventoryTransaction")
    requested_by = relationship("User", foreign_keys=[requested_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
