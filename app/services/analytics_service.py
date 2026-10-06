from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.models.audit import AuditLog
from app.models.chemical import Chemical
from app.models.common import ContainerStatus
from app.models.container import Container
from app.models.laboratory import Laboratory
from app.models.procurement import PurchaseRequest
from app.models.transaction import InventoryTransaction
from app.models.transfer import InventoryAdjustment, TransferRecord
from app.models.user import User
from app.services.settings_service import get_setting

settings = get_settings()


def dashboard_metrics(db: Session) -> dict:
    today = date.today()
    total_chemicals = db.scalar(select(func.count(Chemical.id)).where(Chemical.is_archived.is_(False))) or 0
    total_containers = db.scalar(select(func.count(Container.id))) or 0
    total_labs = db.scalar(select(func.count(Laboratory.id)).where(Laboratory.is_active.is_(True))) or 0

    expiry_warning_days_1 = int(get_setting(db, "expiry_warning_days_1", settings.expiry_warning_days_1))
    expiring_soon = db.scalar(
        select(func.count(Container.id)).where(
            Container.expiry_date.is_not(None),
            Container.expiry_date >= today,
            Container.expiry_date <= today + timedelta(days=expiry_warning_days_1),
        )
    ) or 0
    expired = db.scalar(
        select(func.count(Container.id)).where(Container.status == ContainerStatus.EXPIRED.value)
    ) or 0
    low_stock = db.scalar(
        select(func.count(Container.id)).where(Container.status == ContainerStatus.LOW_STOCK.value)
    ) or 0
    discrepancies = db.scalar(
        select(func.count(InventoryAdjustment.id)).where(InventoryAdjustment.approval_status == "PENDING")
    ) or 0
    pending_transfers = db.scalar(
        select(func.count(TransferRecord.id)).where(TransferRecord.status == "PENDING")
    ) or 0
    pending_procurement = db.scalar(
        select(func.count(PurchaseRequest.id)).where(PurchaseRequest.status == "PENDING")
    ) or 0
    inactive_chemicals = len(dead_stock_containers(db))

    recent_activity = list(db.scalars(select(AuditLog).order_by(AuditLog.occurred_at.desc()).limit(12)))

    return {
        "total_chemicals": total_chemicals,
        "total_containers": total_containers,
        "total_labs": total_labs,
        "expiring_soon": expiring_soon,
        "expired": expired,
        "low_stock": low_stock,
        "discrepancies": discrepancies,
        "pending_transfers": pending_transfers,
        "pending_procurement": pending_procurement,
        "inactive_chemicals": inactive_chemicals,
        "recent_activity": recent_activity,
    }


def consumption_trend(db: Session, months: int = 6) -> list[dict]:
    """Total USE quantity per calendar month, most recent `months` months."""
    today = date.today()
    buckets: dict[str, float] = {}
    start_dates = []
    cursor = today.replace(day=1)
    for _ in range(months):
        start_dates.append(cursor)
        buckets[cursor.strftime("%Y-%m")] = 0.0
        prev_month = cursor - timedelta(days=1)
        cursor = prev_month.replace(day=1)
    earliest = min(start_dates)

    rows = db.execute(
        select(InventoryTransaction.occurred_at, InventoryTransaction.quantity_delta).where(
            InventoryTransaction.transaction_type == "USE",
            InventoryTransaction.occurred_at >= datetime(earliest.year, earliest.month, 1),
        )
    ).all()
    for occurred_at, delta in rows:
        key = occurred_at.strftime("%Y-%m")
        if key in buckets:
            buckets[key] += -delta

    ordered_keys = sorted(buckets.keys())
    return [{"month": k, "total_used": round(buckets[k], 3)} for k in ordered_keys]


def most_consumed_chemicals(db: Session, days: int = 90, limit: int = 8) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.execute(
        select(Chemical.name, Chemical.unit, func.sum(-InventoryTransaction.quantity_delta))
        .join(Container, InventoryTransaction.container_id == Container.id)
        .join(Chemical, Container.chemical_id == Chemical.id)
        .where(InventoryTransaction.transaction_type == "USE", InventoryTransaction.occurred_at >= cutoff)
        .group_by(Chemical.id)
        .order_by(func.sum(-InventoryTransaction.quantity_delta).desc())
        .limit(limit)
    ).all()
    return [{"name": r[0], "unit": r[1], "total_used": round(r[2] or 0, 3)} for r in rows]


def laboratory_wise_inventory(db: Session) -> list[dict]:
    rows = db.execute(
        select(
            Laboratory.name,
            Laboratory.code,
            func.count(Container.id),
            func.coalesce(func.sum(Container.expected_quantity), 0.0),
        )
        .outerjoin(Container, Container.laboratory_id == Laboratory.id)
        .where(Laboratory.is_active.is_(True))
        .group_by(Laboratory.id)
        .order_by(Laboratory.name)
    ).all()
    return [{"name": r[0], "code": r[1], "container_count": r[2], "total_quantity": r[3]} for r in rows]


def chemical_stock_summary(db: Session, chemical: Chemical) -> dict:
    total_available = db.scalar(
        select(func.coalesce(func.sum(Container.expected_quantity), 0.0)).where(
            Container.chemical_id == chemical.id,
            Container.status.not_in([ContainerStatus.ARCHIVED.value, ContainerStatus.EMPTY.value]),
        )
    ) or 0.0
    return {
        "total_available": total_available,
        "is_low": total_available <= chemical.reorder_level if chemical.reorder_level else False,
        "is_below_min": total_available <= chemical.min_stock if chemical.min_stock else False,
    }


def low_stock_chemicals(db: Session) -> list[dict]:
    chemicals = list(db.scalars(select(Chemical).where(Chemical.is_archived.is_(False))))
    out = []
    for chem in chemicals:
        summary = chemical_stock_summary(db, chem)
        if chem.reorder_level and summary["total_available"] <= chem.reorder_level:
            out.append({"chemical": chem, **summary})
    return sorted(out, key=lambda r: r["total_available"])


def dead_stock_containers(db: Session, days: int | None = None) -> list[Container]:
    days = days or int(get_setting(db, "dead_stock_days", settings.dead_stock_days))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    used_recently_ids = set(
        db.scalars(
            select(InventoryTransaction.container_id).where(
                InventoryTransaction.transaction_type == "USE", InventoryTransaction.occurred_at >= cutoff
            )
        )
    )
    candidates = list(
        db.scalars(
            select(Container)
            .options(joinedload(Container.chemical), joinedload(Container.laboratory))
            .where(
                Container.expected_quantity > 0,
                Container.date_received <= cutoff.date(),
                Container.status.not_in([ContainerStatus.ARCHIVED.value, ContainerStatus.EMPTY.value]),
            )
        )
    )
    return [c for c in candidates if c.id not in used_recently_ids]


def monthly_average_consumption(db: Session, chemical_id: int, months: int = 6) -> float:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30 * months)
    total = db.scalar(
        select(func.coalesce(func.sum(-InventoryTransaction.quantity_delta), 0.0))
        .join(Container, InventoryTransaction.container_id == Container.id)
        .where(
            Container.chemical_id == chemical_id,
            InventoryTransaction.transaction_type == "USE",
            InventoryTransaction.occurred_at >= cutoff,
        )
    ) or 0.0
    return total / months if months else 0.0


def suggest_purchase_quantity(db: Session, chemical: Chemical) -> dict:
    """Simple, clearly-labelled forecast: 3-month moving average consumption
    projected forward, plus safety stock, minus current + pending stock."""
    avg_monthly = monthly_average_consumption(db, chemical.id, months=3)
    forecast_3m = avg_monthly * 3
    current_stock = chemical_stock_summary(db, chemical)["total_available"]
    pending_qty = db.scalar(
        select(func.coalesce(func.sum(PurchaseRequest.quantity), 0.0)).where(
            PurchaseRequest.chemical_id == chemical.id,
            PurchaseRequest.status.in_(["PENDING", "APPROVED", "ORDERED"]),
        )
    ) or 0.0
    suggested = forecast_3m + chemical.safety_stock - current_stock - pending_qty
    return {
        "avg_monthly_consumption": round(avg_monthly, 3),
        "forecast_3_month": round(forecast_3m, 3),
        "current_stock": current_stock,
        "pending_orders": pending_qty,
        "safety_stock": chemical.safety_stock,
        "suggested_quantity": round(max(suggested, 0.0), 3),
    }

