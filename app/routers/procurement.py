from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.flash import set_flash
from app.models.chemical import Chemical, Supplier
from app.models.common import utcnow
from app.models.procurement import PurchaseRequest
from app.models.user import User
from app.pagination import paginate
from app.render import render
from app.security import require_manager_or_admin, require_write
from app.services.analytics_service import low_stock_chemicals, suggest_purchase_quantity
from app.services.audit_service import log_action
from app.services.codes import assign_code

router = APIRouter(prefix="/procurement", tags=["procurement"])


@router.get("")
def list_requests(request: Request, status: str = "", page: int = 1, db: Session = Depends(get_db), user: User = Depends(require_write)):
    stmt = select(PurchaseRequest).order_by(PurchaseRequest.requested_at.desc())
    if status:
        stmt = stmt.where(PurchaseRequest.status == status)
    page_obj = paginate(db, stmt, page=page)
    low_stock = low_stock_chemicals(db)
    return render(request, "procurement/list.html", {"nav_active": "procurement", "page_obj": page_obj, "status": status, "low_stock": low_stock})


@router.get("/new")
def new_request_form(request: Request, chemical_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(require_write)):
    chemicals = list(db.scalars(select(Chemical).where(Chemical.is_archived.is_(False)).order_by(Chemical.name)))
    suppliers = list(db.scalars(select(Supplier).where(Supplier.is_active.is_(True)).order_by(Supplier.name)))
    suggestion = None
    chemical = None
    if chemical_id:
        chemical = db.get(Chemical, chemical_id)
        if chemical:
            suggestion = suggest_purchase_quantity(db, chemical)
    return render(request, "procurement/form.html", {"nav_active": "procurement", "chemicals": chemicals, "suppliers": suppliers, "chemical": chemical, "suggestion": suggestion})


@router.get("/suggest/{chemical_id}")
def suggest_json(request: Request, chemical_id: int, db: Session = Depends(get_db), user: User = Depends(require_write)):
    chemical = db.get(Chemical, chemical_id)
    if not chemical:
        return {"error": "not found"}
    return suggest_purchase_quantity(db, chemical)


@router.post("/new")
def create_request(
    request: Request,
    chemical_id: int = Form(...),
    quantity: float = Form(...),
    unit: str = Form(...),
    reason: str = Form(""),
    supplier_id: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
):
    req = PurchaseRequest(
        request_code="",
        chemical_id=chemical_id,
        laboratory_id=user.laboratory_id,
        quantity=quantity,
        unit=unit,
        reason=reason.strip() or None,
        supplier_id=int(supplier_id) if supplier_id else None,
        notes=notes.strip() or None,
        is_system_suggested=False,
        status="PENDING",
        requested_by_id=user.id,
    )
    db.add(req)
    assign_code(db, req, "request_code", "PR-")
    log_action(db, user=user, action="CREATE", entity_type="purchase_request", entity_id=req.id, description=f"Purchase request {req.request_code} created for {quantity:g} {unit}.")
    db.commit()
    response = RedirectResponse("/procurement", status_code=302)
    set_flash(response, "success", f"Purchase request {req.request_code} submitted for approval.")
    return response


@router.post("/{request_id}/decide")
def decide_request(
    request: Request,
    request_id: int,
    approve: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    req = db.get(PurchaseRequest, request_id)
    if not req:
        return render(request, "errors/404.html", {"nav_active": "procurement"}, status_code=404)
    req.status = "APPROVED" if approve == "yes" else "REJECTED"
    req.decided_by_id = user.id
    req.decided_at = utcnow()
    log_action(db, user=user, action="PROCUREMENT_DECISION", entity_type="purchase_request", entity_id=req.id, description=f"{req.request_code} marked {req.status}.")
    db.commit()
    response = RedirectResponse("/procurement", status_code=302)
    set_flash(response, "success", f"Request {req.request_code} {req.status.lower()}.")
    return response


@router.post("/{request_id}/mark-ordered")
def mark_ordered(request: Request, request_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    req = db.get(PurchaseRequest, request_id)
    if req and req.status == "APPROVED":
        req.status = "ORDERED"
        log_action(db, user=user, action="PROCUREMENT_ORDERED", entity_type="purchase_request", entity_id=req.id, description=f"{req.request_code} marked as ordered.")
        db.commit()
    response = RedirectResponse("/procurement", status_code=302)
    set_flash(response, "success", "Marked as ordered.")
    return response


@router.post("/{request_id}/mark-received")
def mark_received(request: Request, request_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    req = db.get(PurchaseRequest, request_id)
    if req and req.status == "ORDERED":
        req.status = "RECEIVED"
        log_action(db, user=user, action="PROCUREMENT_RECEIVED", entity_type="purchase_request", entity_id=req.id, description=f"{req.request_code} marked as received. Add the new container(s) under Containers > Add Container.")
        db.commit()
    response = RedirectResponse("/procurement", status_code=302)
    set_flash(response, "success", "Marked as received. Don't forget to add the new container(s) to inventory.")
    return response
