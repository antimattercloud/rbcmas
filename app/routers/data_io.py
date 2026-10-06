import base64

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.flash import set_flash
from app.models.chemical import Chemical
from app.models.container import Container
from app.models.laboratory import Laboratory
from app.models.location import Location
from app.models.audit import ImportAudit
from app.models.user import User
from app.render import render
from app.security import require_manager_or_admin, require_user
from app.services.csv_service import TEMPLATES, commit_import, parse_csv, preview_import, template_csv
from app.services.export_service import rows_to_csv

router = APIRouter(prefix="/data-io", tags=["data_io"])

ENTITY_LABELS = {"laboratory": "Laboratories", "location": "Locations", "chemical": "Chemicals", "container": "Containers"}

EXPORT_FUNCS = {
    "laboratory": lambda db: (
        ["code", "name", "building", "floor"],
        [[l.code, l.name, l.building, l.floor or ""] for l in db.scalars(select(Laboratory))],
    ),
    "location": lambda db: (
        ["name", "location_type", "parent_full_path", "laboratory_code"],
        [[l.name, l.location_type, l.parent.full_path if l.parent else "", l.laboratory.code if l.laboratory else ""] for l in db.scalars(select(Location))],
    ),
    "chemical": lambda db: (
        ["chemical_code", "name", "cas_number", "category", "manufacturer", "unit", "min_stock", "reorder_level"],
        [[c.chemical_code, c.name, c.cas_number or "", c.category or "", c.manufacturer or "", c.unit, c.min_stock, c.reorder_level] for c in db.scalars(select(Chemical))],
    ),
    "container": lambda db: (
        ["container_code", "chemical_code_or_name", "batch_lot", "container_size", "unit", "expected_quantity", "laboratory_code", "expiry_date", "status"],
        [[c.container_code, c.chemical.chemical_code, c.batch_lot or "", c.container_size, c.unit, round(c.expected_quantity, 3), c.laboratory.code, c.expiry_date.isoformat() if c.expiry_date else "", c.status] for c in db.scalars(select(Container))],
    ),
}


@router.get("")
def data_io_home(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    recent_imports = list(db.scalars(select(ImportAudit).order_by(ImportAudit.occurred_at.desc()).limit(15)))
    return render(request, "data_io/index.html", {"nav_active": "data_io", "entity_labels": ENTITY_LABELS, "recent_imports": recent_imports})


@router.get("/{entity_type}/template")
def download_template(entity_type: str, user: User = Depends(require_manager_or_admin)):
    if entity_type not in TEMPLATES:
        return Response(status_code=404)
    return Response(
        content=template_csv(entity_type),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{entity_type}_import_template.csv"'},
    )


@router.get("/{entity_type}/export")
def export_entity(entity_type: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if entity_type not in EXPORT_FUNCS:
        return Response(status_code=404)
    headers, rows = EXPORT_FUNCS[entity_type](db)
    return Response(
        content=rows_to_csv(headers, rows),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{entity_type}_export.csv"'},
    )


@router.post("/{entity_type}/preview")
async def preview_upload(request: Request, entity_type: str, file: UploadFile, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    if entity_type not in TEMPLATES:
        return render(request, "errors/404.html", {"nav_active": "data_io"}, status_code=404)
    raw = await file.read()
    rows = parse_csv(raw)
    result = preview_import(db, entity_type, rows)
    encoded = base64.b64encode(raw).decode("ascii")
    return render(
        request,
        "data_io/preview.html",
        {
            "nav_active": "data_io", "entity_type": entity_type, "entity_label": ENTITY_LABELS[entity_type],
            "result": result, "filename": file.filename, "encoded_csv": encoded,
        },
    )


@router.post("/{entity_type}/confirm")
def confirm_import(request: Request, entity_type: str, encoded_csv: str = Form(...), filename: str = Form(...), db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    raw = base64.b64decode(encoded_csv)
    rows = parse_csv(raw)
    result = preview_import(db, entity_type, rows)
    created, updated = commit_import(db, result, user, filename)
    db.commit()
    response = RedirectResponse("/data-io", status_code=302)
    set_flash(response, "success", f"Import complete: {created} created, {updated} updated, {len(result.errors)} rows skipped due to errors.")
    return response
