from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.flash import set_flash
from app.models.container import Container
from app.models.laboratory import Laboratory
from app.models.location import Location
from app.models.transfer import TransferRecord
from app.models.user import User
from app.pagination import paginate
from app.render import render
from app.security import require_write
from app.services.inventory_service import InsufficientQuantityError
from app.services.transfer_service import complete_transfer, create_transfer, reject_transfer

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.get("")
def list_transfers(request: Request, status: str = "", page: int = 1, db: Session = Depends(get_db), user: User = Depends(require_write)):
    stmt = select(TransferRecord).order_by(TransferRecord.requested_at.desc())
    if status:
        stmt = stmt.where(TransferRecord.status == status)
    page_obj = paginate(db, stmt, page=page)
    return render(request, "transfers/list.html", {"nav_active": "transfers", "page_obj": page_obj, "status": status})


@router.get("/new")
def new_transfer_form(request: Request, container_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(require_write)):
    container = db.get(Container, container_id) if container_id else None
    containers = []
    if not container:
        containers = list(db.scalars(select(Container).where(Container.expected_quantity > 0).order_by(Container.container_code).limit(500)))
    laboratories = list(db.scalars(select(Laboratory).where(Laboratory.is_active.is_(True)).order_by(Laboratory.name)))
    locations = list(db.scalars(select(Location).where(Location.is_active.is_(True)).order_by(Location.full_path)))
    return render(request, "transfers/form.html", {"nav_active": "transfers", "container": container, "containers": containers, "laboratories": laboratories, "locations": locations})


@router.post("/new")
def create_transfer_route(
    request: Request,
    container_id: int = Form(...),
    quantity: float = Form(...),
    destination_laboratory_id: int = Form(...),
    destination_location_id: str = Form(""),
    reason: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
):
    container = db.get(Container, container_id)
    if not container:
        return render(request, "errors/404.html", {"nav_active": "transfers"}, status_code=404)
    try:
        transfer = create_transfer(
            db,
            container=container,
            quantity=quantity,
            destination_laboratory_id=destination_laboratory_id,
            destination_location_id=int(destination_location_id) if destination_location_id else None,
            sender=user,
            reason=reason.strip() or None,
        )
    except (InsufficientQuantityError, ValueError) as e:
        laboratories = list(db.scalars(select(Laboratory).order_by(Laboratory.name)))
        locations = list(db.scalars(select(Location).order_by(Location.full_path)))
        return render(request, "transfers/form.html", {"nav_active": "transfers", "container": container, "containers": [], "laboratories": laboratories, "locations": locations, "error": str(e)}, status_code=400)

    db.commit()
    response = RedirectResponse("/transfers", status_code=302)
    set_flash(response, "success", f"Transfer {transfer.transfer_code} requested. Complete it once the receiving laboratory confirms.")
    return response


@router.post("/{transfer_id}/complete")
def complete_transfer_route(request: Request, transfer_id: int, db: Session = Depends(get_db), user: User = Depends(require_write)):
    transfer = db.get(TransferRecord, transfer_id)
    if not transfer:
        return render(request, "errors/404.html", {"nav_active": "transfers"}, status_code=404)
    try:
        complete_transfer(db, transfer=transfer, receiver=user)
    except (InsufficientQuantityError, ValueError) as e:
        db.rollback()
        response = RedirectResponse("/transfers", status_code=302)
        set_flash(response, "error", str(e))
        return response
    db.commit()
    response = RedirectResponse("/transfers", status_code=302)
    set_flash(response, "success", f"Transfer {transfer.transfer_code} completed.")
    return response


@router.post("/{transfer_id}/reject")
def reject_transfer_route(request: Request, transfer_id: int, reason: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_write)):
    transfer = db.get(TransferRecord, transfer_id)
    if not transfer:
        return render(request, "errors/404.html", {"nav_active": "transfers"}, status_code=404)
    reject_transfer(db, transfer=transfer, user=user, reason=reason.strip() or None)
    db.commit()
    response = RedirectResponse("/transfers", status_code=302)
    set_flash(response, "success", f"Transfer {transfer.transfer_code} rejected.")
    return response
