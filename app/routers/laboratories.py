from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.flash import set_flash
from app.models.audit import AuditLog
from app.models.common import ContainerStatus
from app.models.container import Container
from app.models.laboratory import Laboratory
from app.models.transaction import InventoryTransaction
from app.models.user import User
from app.pagination import paginate
from app.render import render
from app.security import require_admin, require_user
from app.services.audit_service import log_action

router = APIRouter(prefix="/laboratories", tags=["laboratories"])
settings = get_settings()


@router.get("")
def list_laboratories(request: Request, q: str = "", page: int = 1, db: Session = Depends(get_db), user: User = Depends(require_user)):
    stmt = select(Laboratory).order_by(Laboratory.name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Laboratory.name.ilike(like), Laboratory.code.ilike(like)))
    page_obj = paginate(db, stmt, page=page)
    return render(request, "laboratories/list.html", {"nav_active": "laboratories", "page_obj": page_obj, "q": q})


@router.get("/new")
def new_laboratory_form(request: Request, user: User = Depends(require_admin)):
    return render(request, "laboratories/form.html", {"nav_active": "laboratories", "lab": None})


@router.post("/new")
def create_laboratory(
    request: Request,
    code: str = Form(...),
    name: str = Form(...),
    building: str = Form("Research Building"),
    floor: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    existing = db.scalar(select(Laboratory).where(Laboratory.code == code.strip()))
    if existing:
        return render(
            request,
            "laboratories/form.html",
            {"nav_active": "laboratories", "lab": None, "error": f"Laboratory code '{code}' already exists.", "form": request},
            status_code=400,
        )
    lab = Laboratory(code=code.strip(), name=name.strip(), building=building.strip() or "Research Building", floor=floor.strip() or None, description=description.strip() or None)
    db.add(lab)
    db.flush()
    log_action(db, user=user, action="CREATE", entity_type="laboratory", entity_id=lab.id, description=f"Created laboratory {lab.code} - {lab.name}.")
    db.commit()
    response = RedirectResponse(f"/laboratories/{lab.id}", status_code=302)
    set_flash(response, "success", f"Laboratory {lab.code} created successfully.")
    return response


@router.get("/{lab_id}")
def laboratory_detail(request: Request, lab_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    lab = db.get(Laboratory, lab_id)
    if not lab:
        return render(request, "errors/404.html", {"nav_active": "laboratories"}, status_code=404)

    containers = list(db.scalars(select(Container).where(Container.laboratory_id == lab_id)))
    total_qty = sum(c.expected_quantity for c in containers)
    low_stock = sum(1 for c in containers if c.status == ContainerStatus.LOW_STOCK.value)
    expiring = sum(1 for c in containers if c.status == ContainerStatus.EXPIRING_SOON.value)
    expired = sum(1 for c in containers if c.status == ContainerStatus.EXPIRED.value)

    month_ago = date.today() - timedelta(days=30)
    monthly_consumption = db.scalar(
        select(func.coalesce(func.sum(-InventoryTransaction.quantity_delta), 0.0))
        .join(Container, InventoryTransaction.container_id == Container.id)
        .where(Container.laboratory_id == lab_id, InventoryTransaction.transaction_type == "USE", InventoryTransaction.occurred_at >= month_ago)
    ) or 0.0

    recent_activity = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type.in_(["container", "transfer"]))
            .order_by(AuditLog.occurred_at.desc())
            .limit(15)
        )
    )

    return render(
        request,
        "laboratories/detail.html",
        {
            "nav_active": "laboratories",
            "lab": lab,
            "containers": containers[:50],
            "total_containers": len(containers),
            "total_quantity": total_qty,
            "low_stock": low_stock,
            "expiring": expiring,
            "expired": expired,
            "monthly_consumption": monthly_consumption,
            "recent_activity": recent_activity,
        },
    )


@router.get("/{lab_id}/edit")
def edit_laboratory_form(request: Request, lab_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    lab = db.get(Laboratory, lab_id)
    if not lab:
        return render(request, "errors/404.html", {"nav_active": "laboratories"}, status_code=404)
    return render(request, "laboratories/form.html", {"nav_active": "laboratories", "lab": lab})


@router.post("/{lab_id}/edit")
def update_laboratory(
    request: Request,
    lab_id: int,
    code: str = Form(...),
    name: str = Form(...),
    building: str = Form("Research Building"),
    floor: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    lab = db.get(Laboratory, lab_id)
    if not lab:
        return render(request, "errors/404.html", {"nav_active": "laboratories"}, status_code=404)
    dup = db.scalar(select(Laboratory).where(Laboratory.code == code.strip(), Laboratory.id != lab_id))
    if dup:
        return render(request, "laboratories/form.html", {"nav_active": "laboratories", "lab": lab, "error": f"Code '{code}' is already in use."}, status_code=400)

    lab.code, lab.name, lab.building, lab.floor, lab.description = code.strip(), name.strip(), building.strip() or "Research Building", floor.strip() or None, description.strip() or None
    log_action(db, user=user, action="UPDATE", entity_type="laboratory", entity_id=lab.id, description=f"Updated laboratory {lab.code}.")
    db.commit()
    response = RedirectResponse(f"/laboratories/{lab.id}", status_code=302)
    set_flash(response, "success", "Laboratory updated.")
    return response


@router.post("/{lab_id}/archive")
def archive_laboratory(request: Request, lab_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    lab = db.get(Laboratory, lab_id)
    if lab:
        lab.is_active = False
        log_action(db, user=user, action="ARCHIVE", entity_type="laboratory", entity_id=lab.id, description=f"Archived laboratory {lab.code}.")
        db.commit()
    response = RedirectResponse("/laboratories", status_code=302)
    set_flash(response, "success", "Laboratory archived.")
    return response
