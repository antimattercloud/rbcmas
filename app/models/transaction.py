from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.common import utcnow


class InventoryTransaction(Base):
    """Append-only ledger. This is the single source of truth for every
    quantity change on a container. Never edit or delete a row here -
    corrections are made by inserting a new ADJUSTMENT transaction."""

    __tablename__ = "inventory_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    quantity_delta: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    expected_quantity_before: Mapped[float] = mapped_column(Float, nullable=False)
    expected_quantity_after: Mapped[float] = mapped_column(Float, nullable=False)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)

    purpose: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiments.id"), nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    container = relationship("Container", back_populates="transactions")
    user = relationship("User")
    project = relationship("Project")
    experiment = relationship("Experiment")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Txn {self.transaction_type} {self.quantity_delta} container={self.container_id}>"
