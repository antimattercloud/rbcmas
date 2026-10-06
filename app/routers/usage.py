from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.flash import set_flash
from app.models.chemical import Project
from app.models.container import Container
from app.models.transaction import InventoryTransaction
from app.models.user import User
from app.pagination import paginate
from app.render import render
from app.security import require_write
from app.services.inventory_service import InsufficientQuantityError, record_usage

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("")
def usage_history(request: Request, page: int = 1, db: Session = Depends(get_db), user: User = Depends(require_write)):
    stmt = select(InventoryTransaction).where(InventoryTransaction.transaction_type == "USE").order_by(InventoryTransaction.occurred_at.desc())
    page_obj = paginate(db, stmt, page=page)
    return render(request, "usage/list.html", {"nav_active": "usage", "page_obj": page_obj})


@router.get("/new")
def usage_form(request: Request, container_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(require_write)):
    container = db.get(Container, container_id) if container_id else None
    projects = list(db.scalars(select(Project).where(Project.is_active.is_(True)).order_by(Project.name)))
    containers = []
    if not container:
        containers = list(db.scalars(select(Container).where(Container.expected_quantity > 0).order_by(Container.container_code).limit(500)))
    return render(request, "usage/form.html", {"nav_active": "usage", "container": container, "containers": containers, "projects": projects})


@router.post("/new")
def usage_submit(
    request: Request,
    container_id: int = Form(...),
    quantity_used: float = Form(...),
    purpose: str = Form(""),
    project_id: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
):
    container = db.get(Container, container_id)
    if not container:
        return render(request, "errors/404.html", {"nav_active": "usage"}, status_code=404)
    try:
        record_usage(
            db,
            container=container,
            quantity_used=quantity_used,
            user=user,
            purpose=purpose.strip() or None,
            project_id=int(project_id) if project_id else None,
            notes=notes.strip() or None,
        )
    except (InsufficientQuantityError, ValueError) as e:
        projects = list(db.scalars(select(Project).where(Project.is_active.is_(True)).order_by(Project.name)))
        return render(request, "usage/form.html", {"nav_active": "usage", "container": container, "containers": [], "projects": projects, "error": str(e)}, status_code=400)

    db.commit()
    response = RedirectResponse(f"/containers/{container.id}", status_code=302)
    set_flash(response, "success", f"{quantity_used:g} {container.unit} usage recorded successfully.")
    return response
