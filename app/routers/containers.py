from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.flash import set_flash
from app.models.chemical import Chemical
from app.models.common import ContainerStatus
from app.models.container import Container
from app.models.laboratory import Laboratory
from app.models.location import Location
from app.models.user import User
from app.pagination import paginate
from app.render import render
from app.security import require_write, require_user
from app.services.audit_service import log_action
from app.services.codes import assign_code
from app.services.inventory_service import calculate_balance_sheet, receive_container

router = APIRouter(prefix="/containers", tags=["containers"])


@router.get("")
def list_containers(
    request: Request,
    q: str = "",
    status: str = "",
    laboratory_id: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    stmt = select(Container).options(joinedload(Container.chemical), joinedload(Container.laboratory)).order_by(Container.container_code)
    if q:
        like = f"%{q}%"
        stmt = stmt.join(Chemical).where(or_(Container.container_code.ilike(like), Chemical.name.ilike(like), Container.batch_lot.ilike(like)))
    if status:
        stmt = stmt.where(Container.status == status)
    if laboratory_id:
        stmt = stmt.where(Container.laboratory_id == int(laboratory_id))

    page_obj = paginate(db, stmt, page=page)
    laboratories = list(db.scalars(select(Laboratory).where(Laboratory.is_active.is_(True)).order_by(Laboratory.name)))

    return render(
        request,
        "containers/list.html",
        {
            "nav_active": "containers",
            "page_obj": page_obj,
            "q": q,
            "status": status,
            "laboratory_id": laboratory_id,
            "laboratories": laboratories,
            "statuses": [s.value for s in ContainerStatus],
        },
    )


@router.get("/new")
def new_container_form(request: Request, db: Session = Depends(get_db), user: User = Depends(require_write)):
    chemicals = list(db.scalars(select(Chemical).where(Chemical.is_archived.is_(False)).order_by(Chemical.name)))
    laboratories = list(db.scalars(select(Laboratory).where(Laboratory.is_active.is_(True)).order_by(Laboratory.name)))
    locations = list(db.scalars(select(Location).where(Location.is_active.is_(True)).order_by(Location.full_path)))
    return render(request, "containers/form.html", {"nav_active": "containers", "chemicals": chemicals, "laboratories": laboratories, "locations": locations, "today": date.today().isoformat()})


@router.post("/new")
def create_container(
    request: Request,
    chemical_id: int = Form(...),
    batch_lot: str = Form(""),
    container_size: float = Form(...),
    unit: str = Form(...),
    initial_quantity: float = Form(...),
    date_received: str = Form(...),
    date_opened: str = Form(""),
    expiry_date: str = Form(""),
    laboratory_id: int = Form(...),
    location_id: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
):
    chem = db.get(Chemical, chemical_id)
    if initial_quantity > container_size:
        laboratories = list(db.scalars(select(Laboratory).order_by(Laboratory.name)))
        chemicals = list(db.scalars(select(Chemical).order_by(Chemical.name)))
        locations = list(db.scalars(select(Location).order_by(Location.full_path)))
        return render(
            request,
            "containers/form.html",
            {
                "nav_active": "containers", "chemicals": chemicals, "laboratories": laboratories, "locations": locations,
                "today": date.today().isoformat(),
                "error": "Initial quantity cannot exceed the container size.",
            },
            status_code=400,
        )

    container = Container(
        container_code="",
        chemical_id=chemical_id,
        batch_lot=batch_lot.strip() or None,
        container_size=container_size,
        unit=unit,
        initial_quantity=initial_quantity,
        expected_quantity=0.0,
        date_received=date.fromisoformat(date_received),
        date_opened=date.fromisoformat(date_opened) if date_opened else None,
        expiry_date=date.fromisoformat(expiry_date) if expiry_date else None,
        laboratory_id=laboratory_id,
        location_id=int(location_id) if location_id else None,
        responsible_user_id=user.id,
        status=ContainerStatus.AVAILABLE.value,
        notes=notes.strip() or None,
    )
    db.add(container)
    assign_code(db, container, "container_code", "CHEM-")
    receive_container(db, container=container, user=user)

    log_action(db, user=user, action="CREATE", entity_type="container", entity_id=container.id, description=f"Added container {container.container_code} ({chem.name}) to {container.laboratory.name}.")
    db.commit()
    response = RedirectResponse(f"/containers/{container.id}", status_code=302)
    set_flash(response, "success", f"Container {container.container_code} created.")
    return response


@router.get("/{container_id}")
def container_detail(request: Request, container_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    container = db.get(Container, container_id)
    if not container:
        return render(request, "errors/404.html", {"nav_active": "containers"}, status_code=404)
    balance = calculate_balance_sheet(container)
    transactions = sorted(container.transactions, key=lambda t: t.occurred_at, reverse=True)[:50]
    return render(request, "containers/detail.html", {"nav_active": "containers", "container": container, "balance": balance, "transactions": transactions})


@router.post("/{container_id}/status")
def set_container_status(
    request: Request,
    container_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
):
    container = db.get(Container, container_id)
    if not container:
        return render(request, "errors/404.html", {"nav_active": "containers"}, status_code=404)
    valid = {s.value for s in ContainerStatus}
    if status in valid:
        container.status = status
        log_action(db, user=user, action="STATUS_CHANGE", entity_type="container", entity_id=container.id, description=f"Status of {container.container_code} manually set to {status}.")
        db.commit()
    response = RedirectResponse(f"/containers/{container_id}", status_code=302)
    set_flash(response, "success", "Container status updated.")
    return response
