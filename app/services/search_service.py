from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.chemical import Chemical, ChemicalAlias
from app.models.container import Container
from app.models.laboratory import Laboratory
from app.models.transaction import InventoryTransaction
from app.models.user import User

# --- rule-based "smart search" patterns -------------------------------------
# Deterministic, indexed SQL queries. No external AI calls.

_WHERE_IS = re.compile(r"^(?:where is|find|locate)\s+(.+?)\??$", re.I)
_IN_LAB = re.compile(r"(?:chemicals?|containers?)\s+in\s+(?:lab(?:oratory)?\s*)?(.+?)\??$", re.I)
_EXPIRE_MONTH = re.compile(r"expir\w*\s+this\s+month", re.I)
_EXPIRE_WEEK = re.compile(r"expir\w*\s+this\s+week", re.I)
_EXPIRE_DAYS = re.compile(r"expir\w*.*?within\s+(\d+)\s*days?", re.I)
_BELOW_QTY = re.compile(r"below\s+(\d+(?:\.\d+)?)\s*([a-zA-Z]+)?", re.I)
_UNUSED_FOR = re.compile(r"unused\s+for\s+(\d+)\s*(day|week|month|year)s?", re.I)
_WHO_USED = re.compile(r"who\s+used\s+(.+?)\??$", re.I)


def _chemicals_by_name(db: Session, term: str) -> list[Chemical]:
    like = f"%{term}%"
    return list(
        db.scalars(
            select(Chemical)
            .outerjoin(ChemicalAlias)
            .where(
                or_(
                    Chemical.name.ilike(like),
                    Chemical.chemical_code.ilike(like),
                    Chemical.cas_number.ilike(like),
                    ChemicalAlias.alias.ilike(like),
                )
            )
            .distinct()
            .limit(25)
        )
    )


def smart_search(db: Session, query: str) -> dict:
    q = query.strip()
    if not q:
        return {"mode": "empty", "chemicals": [], "containers": [], "laboratories": [], "message": None}

    m = _WHO_USED.match(q)
    if m:
        term = m.group(1)
        chems = _chemicals_by_name(db, term)
        chem_ids = [c.id for c in chems]
        txns = []
        if chem_ids:
            txns = list(
                db.scalars(
                    select(InventoryTransaction)
                    .join(Container, InventoryTransaction.container_id == Container.id)
                    .where(Container.chemical_id.in_(chem_ids), InventoryTransaction.transaction_type == "USE")
                    .order_by(InventoryTransaction.occurred_at.desc())
                    .limit(25)
                )
            )
        return {
            "mode": "who_used",
            "chemicals": chems,
            "transactions": txns,
            "containers": [],
            "laboratories": [],
            "message": f"Recent usage of '{term}'",
        }

    m = _IN_LAB.match(q)
    if m:
        term = m.group(1).strip()
        like = f"%{term}%"
        lab = db.scalar(select(Laboratory).where(or_(Laboratory.name.ilike(like), Laboratory.code.ilike(like))))
        containers = []
        if lab:
            containers = list(
                db.scalars(select(Container).where(Container.laboratory_id == lab.id).limit(100))
            )
        return {
            "mode": "in_lab",
            "chemicals": [],
            "containers": containers,
            "laboratories": [lab] if lab else [],
            "message": f"Chemicals in {lab.name}" if lab else f"No laboratory matching '{term}'",
        }

    if _EXPIRE_MONTH.search(q) or _EXPIRE_WEEK.search(q) or _EXPIRE_DAYS.search(q):
        today = date.today()
        if _EXPIRE_WEEK.search(q):
            horizon = today + timedelta(days=7)
        elif m2 := _EXPIRE_DAYS.search(q):
            horizon = today + timedelta(days=int(m2.group(1)))
        else:
            next_month = today.replace(day=28) + timedelta(days=4)
            horizon = next_month.replace(day=1) - timedelta(days=1)
        containers = list(
            db.scalars(
                select(Container)
                .where(Container.expiry_date.is_not(None), Container.expiry_date <= horizon, Container.expiry_date >= today)
                .order_by(Container.expiry_date)
                .limit(100)
            )
        )
        return {
            "mode": "expiring",
            "chemicals": [],
            "containers": containers,
            "laboratories": [],
            "message": f"Expiring on or before {horizon.isoformat()}",
        }

    m = _BELOW_QTY.match(q)
    if m:
        qty = float(m.group(1))
        containers = list(
            db.scalars(select(Container).where(Container.expected_quantity < qty).order_by(Container.expected_quantity).limit(100))
        )
        return {
            "mode": "below_qty",
            "chemicals": [],
            "containers": containers,
            "laboratories": [],
            "message": f"Containers below {qty:g}",
        }

    m = _UNUSED_FOR.match(q)
    if m:
        amount, unit = int(m.group(1)), m.group(2)
        days = amount * {"day": 1, "week": 7, "month": 30, "year": 365}[unit]
        cutoff = date.today() - timedelta(days=days)
        used_recently_ids = set(
            db.scalars(
                select(InventoryTransaction.container_id)
                .where(InventoryTransaction.transaction_type == "USE", InventoryTransaction.occurred_at >= cutoff)
                .distinct()
            )
        )
        containers = list(
            db.scalars(
                select(Container)
                .where(Container.expected_quantity > 0, Container.date_received <= cutoff)
                .limit(300)
            )
        )
        containers = [c for c in containers if c.id not in used_recently_ids]
        return {
            "mode": "unused",
            "chemicals": [],
            "containers": containers[:100],
            "laboratories": [],
            "message": f"Not used in the last {amount} {unit}(s)",
        }

    m = _WHERE_IS.match(q)
    term = m.group(1) if m else q

    chemicals = _chemicals_by_name(db, term)
    like = f"%{term}%"
    containers = list(
        db.scalars(
            select(Container)
            .where(or_(Container.container_code.ilike(like), Container.batch_lot.ilike(like)))
            .limit(25)
        )
    )
    laboratories = list(
        db.scalars(select(Laboratory).where(or_(Laboratory.name.ilike(like), Laboratory.code.ilike(like))).limit(10))
    )

    return {
        "mode": "general",
        "chemicals": chemicals,
        "containers": containers,
        "laboratories": laboratories,
        "message": None,
    }
