import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    LAB_MANAGER = "LAB_MANAGER"
    RESEARCHER = "RESEARCHER"
    AUDITOR = "AUDITOR"


class LocationType(str, enum.Enum):
    BUILDING = "BUILDING"
    FLOOR = "FLOOR"
    LABORATORY = "LABORATORY"
    ROOM = "ROOM"
    STORAGE_UNIT = "STORAGE_UNIT"
    CABINET = "CABINET"
    SHELF = "SHELF"


class ContainerStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    LOW_STOCK = "LOW_STOCK"
    EXPIRING_SOON = "EXPIRING_SOON"
    EXPIRED = "EXPIRED"
    EMPTY = "EMPTY"
    UNDER_REVIEW = "UNDER_REVIEW"
    ARCHIVED = "ARCHIVED"


class TransactionType(str, enum.Enum):
    RECEIVE = "RECEIVE"
    OPEN = "OPEN"
    USE = "USE"
    TRANSFER_OUT = "TRANSFER_OUT"
    TRANSFER_IN = "TRANSFER_IN"
    ADJUSTMENT = "ADJUSTMENT"
    RETURN = "RETURN"
    PHYSICAL_COUNT = "PHYSICAL_COUNT"


class TransferStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    AUTO_APPROVED = "AUTO_APPROVED"


class PurchaseStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    ORDERED = "ORDERED"
    RECEIVED = "RECEIVED"
    REJECTED = "REJECTED"


class AdjustmentReason(str, enum.Enum):
    MEASUREMENT_ERROR = "Measurement error"
    SPILLAGE = "Spillage"
    UNRECORDED_USAGE = "Unrecorded usage"
    EVAPORATION = "Evaporation"
    TRANSFER_NOT_RECORDED = "Transfer not recorded"
    CONTAINER_DAMAGE = "Container damage"
    DATA_ENTRY_ERROR = "Data-entry error"
    OTHER = "Other"
