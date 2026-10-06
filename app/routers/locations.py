from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.flash import set_flash
from app.models.laboratory import Laboratory
from app.models.location import Location
from app.models.common import LocationType
from app.models.user import User
from app.render import render
from app.security import require_manager_or_admin, require_user
from app.services.audit_service import log_action

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("")
def list_locations(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    locations = list(db.scalars(select(Location).where(Location.is_active.is_(True)).order_by(Location.full_path)))
    laboratories = list(db.scalars(select(Laboratory).where(Laboratory.is_active.is_(True)).order_by(Laboratory.name)))
    return render(
        request,
        "locations/list.html",
        {
            "nav_active": "locations",
            "locations": locations,
            "laboratories": laboratories,
            "location_types": [t.value for t in LocationType],
        },
    )


@router.post("")
def create_location(
    request: Request,
    name: str = Form(...),
    location_type: str = Form(...),
    parent_id: str = Form(""),
    laboratory_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    parent = db.get(Location, int(parent_id)) if parent_id else None
    laboratory = db.get(Laboratory, int(laboratory_id)) if laboratory_id else None
    full_path = f"{parent.full_path} > {name}" if parent else name

    existing = db.scalar(select(Location).where(Location.full_path == full_path))
    if existing:
        response = RedirectResponse("/locations", status_code=302)
        set_flash(response, "error", f"A location already exists at '{full_path}'.")
        return response

    loc = Location(
        name=name.strip(),
        location_type=location_type,
        parent_id=parent.id if parent else None,
        laboratory_id=laboratory.id if laboratory else None,
        full_path=full_path,
    )
    db.add(loc)
    db.flush()
    log_action(db, user=user, action="CREATE", entity_type="location", entity_id=loc.id, description=f"Created location {full_path}.")
    db.commit()
    response = RedirectResponse("/locations", status_code=302)
    set_flash(response, "success", f"Location '{name}' added.")
    return response


@router.post("/{location_id}/archive")
def archive_location(request: Request, location_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    loc = db.get(Location, location_id)
    if loc:
        loc.is_active = False
        log_action(db, user=user, action="ARCHIVE", entity_type="location", entity_id=loc.id, description=f"Archived location {loc.full_path}.")
        db.commit()
    response = RedirectResponse("/locations", status_code=302)
    set_flash(response, "success", "Location archived.")
    return response
