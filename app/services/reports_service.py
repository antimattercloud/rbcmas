from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.audit import AuditLog
from app.models.chemical import Chemical
from app.models.container import Container
from app.models.procurement import PurchaseRequest
from app.models.transfer import PhysicalCount, TransferRecord
from app.services.analytics_service import (
    dead_stock_containers,
    laboratory_wise_inventory,
    low_stock_chemicals,
    monthly_average_consumption,
)

REPORT_DEFS = {
    "inventory": "Inventory Report",
    "consumption": "Chemical Consumption Report",
    "reconciliation": "Physical Reconciliation Report",
    "expiry": "Expiry Report",
    "low-stock": "Low Stock Report",
    "transfer": "Transfer Report",
    "procurement": "Procurement Report",
    "laboratory": "Laboratory-wise Report",
    "chemical-annual": "Chemical-wise Annual Report",
    "audit": "Audit Report",
    "dead-stock": "Inactive / Dead Stock Report",
}


def inventory_report(db: Session):
    headers = ["Container", "Chemical", "CAS", "Batch/Lot", "Expected Qty", "Unit", "Laboratory", "Location", "Expiry Date", "Status"]
    rows = []
    stmt = (
        select(Container)
        .options(joinedload(Container.chemical), joinedload(Container.laboratory), joinedload(Container.location))
        .order_by(Container.container_code)
    )
    for c in db.scalars(stmt):
        rows.append([
            c.container_code, c.chemical.name, c.chemical.cas_number or "", c.batch_lot or "",
            round(c.expected_quantity, 3), c.unit, c.laboratory.name,
            c.location.full_path if c.location else "", c.expiry_date.isoformat() if c.expiry_date else "", c.status,
        ])
    return headers, rows


def consumption_report(db: Session):
    headers = ["Chemical", "Unit", "Avg Monthly Consumption (6mo)"]
    rows = []
    for chem in db.scalars(select(Chemical).where(Chemical.is_archived.is_(False)).order_by(Chemical.name)):
        avg = monthly_average_consumption(db, chem.id, months=6)
        rows.append([chem.name, chem.unit, round(avg, 3)])
    return headers, rows


def reconciliation_report(db: Session):
    headers = ["Container", "Chemical", "Expected", "Physical", "Variance", "Variance %", "Reason", "Counted By", "Counted At"]
    rows = []
    stmt = (
        select(PhysicalCount)
        .options(joinedload(PhysicalCount.container).joinedload(Container.chemical), joinedload(PhysicalCount.counted_by))
        .order_by(PhysicalCount.counted_at.desc())
    )
    for pc in db.scalars(stmt):
        rows.append([
            pc.container.container_code, pc.container.chemical.name,
            round(pc.expected_quantity, 3), round(pc.physical_quantity, 3),
            round(pc.variance, 3), round(pc.variance_percent, 2),
            pc.reason or "", pc.counted_by.full_name, pc.counted_at.strftime("%Y-%m-%d %H:%M"),
        ])
    return headers, rows


def expiry_report(db: Session):
    headers = ["Container", "Chemical", "Laboratory", "Expiry Date", "Status"]
    rows = []
    stmt = (
        select(Container)
        .options(joinedload(Container.chemical), joinedload(Container.laboratory))
        .where(Container.expiry_date.is_not(None))
        .order_by(Container.expiry_date)
    )
    for c in db.scalars(stmt):
        rows.append([c.container_code, c.chemical.name, c.laboratory.name, c.expiry_date.isoformat(), c.status])
    return headers, rows


def low_stock_report(db: Session):
    headers = ["Chemical", "Available", "Reorder Level", "Min Stock", "Unit"]
    rows = []
    for row in low_stock_chemicals(db):
        chem = row["chemical"]
        rows.append([chem.name, round(row["total_available"], 3), chem.reorder_level, chem.min_stock, chem.unit])
    return headers, rows


def transfer_report(db: Session):
    headers = ["Transfer", "Container", "Chemical", "Quantity", "From", "To", "Status", "Sender", "Requested At"]
    rows = []
    stmt = (
        select(TransferRecord)
        .options(
            joinedload(TransferRecord.container).joinedload(Container.chemical),
            joinedload(TransferRecord.source_laboratory),
            joinedload(TransferRecord.destination_laboratory),
            joinedload(TransferRecord.sender),
        )
        .order_by(TransferRecord.requested_at.desc())
    )
    for t in db.scalars(stmt):
        rows.append([
            t.transfer_code, t.container.container_code, t.container.chemical.name, round(t.quantity, 3),
            t.source_laboratory.name, t.destination_laboratory.name, t.status, t.sender.full_name,
            t.requested_at.strftime("%Y-%m-%d %H:%M"),
        ])
    return headers, rows


def procurement_report(db: Session):
    headers = ["Request", "Chemical", "Quantity", "Unit", "Status", "Requested By", "Requested At"]
    rows = []
    stmt = (
        select(PurchaseRequest)
        .options(joinedload(PurchaseRequest.chemical), joinedload(PurchaseRequest.requested_by))
        .order_by(PurchaseRequest.requested_at.desc())
    )
    for r in db.scalars(stmt):
        rows.append([r.request_code, r.chemical.name, round(r.quantity, 3), r.unit, r.status, r.requested_by.full_name, r.requested_at.strftime("%Y-%m-%d")])
    return headers, rows


def laboratory_report(db: Session):
    headers = ["Laboratory", "Code", "Containers", "Total Quantity"]
    rows = [[r["name"], r["code"], r["container_count"], round(r["total_quantity"], 3)] for r in laboratory_wise_inventory(db)]
    return headers, rows


def chemical_annual_report(db: Session, year: int | None = None):
    year = year or datetime.now(timezone.utc).year
    headers = ["Chemical", "Year", "Total Used", "Unit"]
    rows = []
    from sqlalchemy import func

    from app.models.container import Container as ContainerModel
    from app.models.transaction import InventoryTransaction

    for chem in db.scalars(select(Chemical).where(Chemical.is_archived.is_(False)).order_by(Chemical.name)):
        total = db.scalar(
            select(func.coalesce(func.sum(-InventoryTransaction.quantity_delta), 0.0))
            .join(ContainerModel, InventoryTransaction.container_id == ContainerModel.id)
            .where(
                ContainerModel.chemical_id == chem.id,
                InventoryTransaction.transaction_type == "USE",
                func.strftime("%Y", InventoryTransaction.occurred_at) == str(year),
            )
        ) or 0.0
        if total:
            rows.append([chem.name, year, round(total, 3), chem.unit])
    return headers, rows


def audit_report(db: Session):
    headers = ["When", "User", "Action", "Entity Type", "Entity ID", "Description"]
    rows = []
    stmt = select(AuditLog).options(joinedload(AuditLog.user)).order_by(AuditLog.occurred_at.desc()).limit(2000)
    for a in db.scalars(stmt):
        rows.append([a.occurred_at.strftime("%Y-%m-%d %H:%M"), a.user.full_name if a.user else "System", a.action, a.entity_type, a.entity_id or "", a.description])
    return headers, rows


def dead_stock_report(db: Session):
    headers = ["Container", "Chemical", "Laboratory", "Remaining", "Unit", "Date Received"]
    rows = []
    for c in dead_stock_containers(db):
        rows.append([c.container_code, c.chemical.name, c.laboratory.name, round(c.expected_quantity, 3), c.unit, c.date_received.isoformat()])
    return headers, rows


REPORT_FUNCS = {
    "inventory": inventory_report,
    "consumption": consumption_report,
    "reconciliation": reconciliation_report,
    "expiry": expiry_report,
    "low-stock": low_stock_report,
    "transfer": transfer_report,
    "procurement": procurement_report,
    "laboratory": laboratory_report,
    "chemical-annual": chemical_annual_report,
    "audit": audit_report,
    "dead-stock": dead_stock_report,
}
