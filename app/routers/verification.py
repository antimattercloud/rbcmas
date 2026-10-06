from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.flash import set_flash
from app.models.common import AdjustmentReason
from app.models.container import Container
from app.models.transfer import InventoryAdjustment, PhysicalCount
from app.models.user import User
from app.pagination import paginate
from app.render import render
from app.security import require_manager_or_admin, require_write
from app.services.inventory_service import ReasonRequiredError, decide_adjustment, record_physical_count

router = APIRouter(prefix="/verification", tags=["verification"])
settings = get_settings()


@router.get("")
def verification_list(request: Request, page: int = 1, db: Session = Depends(get_db), user: User = Depends(require_write)):
    stmt = select(PhysicalCount).order_by(PhysicalCount.counted_at.desc())
    page_obj = paginate(db, stmt, page=page)

    pending_adjustments = list(
        db.scalars(select(InventoryAdjustment).where(InventoryAdjustment.approval_status == "PENDING").order_by(InventoryAdjustment.created_at.desc()))
    )
    return render(request, "verification/list.html", {"nav_active": "verification", "page_obj": page_obj, "pending_adjustments": pending_adjustments})


@router.get("/new")
def verification_form(request: Request, container_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(require_write)):
    container = db.get(Container, container_id) if container_id else None
    containers = []
    if not container:
        containers = list(db.scalars(select(Container).order_by(Container.container_code).limit(500)))
    return render(
        request,
        "verification/form.html",
        {
            "nav_active": "verification",
            "container": container,
            "containers": containers,
            "tolerance": settings.variance_tolerance_percent,
            "reasons": [r.value for r in AdjustmentReason],
        },
    )


@router.post("/new")
def verification_submit(
    request: Request,
    container_id: int = Form(...),
    physical_quantity: float = Form(...),
    reason: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
):
    container = db.get(Container, container_id)
    if not container:
        return render(request, "errors/404.html", {"nav_active": "verification"}, status_code=404)
    try:
        count, txn, adjustment = record_physical_count(
            db, container=container, physical_quantity=physical_quantity, user=user, reason=reason or None, notes=notes.strip() or None
        )
    except ReasonRequiredError as e:
        return render(
            request,
            "verification/form.html",
            {
                "nav_active": "verification", "container": container, "containers": [],
                "tolerance": settings.variance_tolerance_percent, "reasons": [r.value for r in AdjustmentReason],
                "error": str(e), "prefill_qty": physical_quantity,
            },
            status_code=400,
        )
    db.commit()
    response = RedirectResponse(f"/containers/{container.id}", status_code=302)
    if adjustment:
        set_flash(response, "warning", "INVENTORY DISCREPANCY - REVIEW REQUIRED. The variance exceeded tolerance; an adjustment is pending approval.")
    else:
        set_flash(response, "success", "Physical verification recorded. No significant variance found.")
    return response


@router.post("/adjustments/{adjustment_id}/decide")
def decide_adjustment_route(
    request: Request,
    adjustment_id: int,
    approve: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    adjustment = db.get(InventoryAdjustment, adjustment_id)
    if not adjustment:
        return render(request, "errors/404.html", {"nav_active": "verification"}, status_code=404)
    try:
        decide_adjustment(db, adjustment=adjustment, approve=(approve == "yes"), approver=user)
    except ValueError as e:
        response = RedirectResponse("/verification", status_code=302)
        set_flash(response, "error", str(e))
        return response
    db.commit()
    response = RedirectResponse("/verification", status_code=302)
    set_flash(response, "success", "Adjustment approved." if approve == "yes" else "Adjustment rejected.")
    return response
