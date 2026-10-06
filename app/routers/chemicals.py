from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.flash import set_flash
from app.models.chemical import Chemical, ChemicalAlias, Supplier
from app.models.container import Container
from app.models.transaction import InventoryTransaction
from app.models.transfer import PhysicalCount, TransferRecord
from app.models.audit import AuditLog
from app.models.user import User
from app.pagination import paginate
from app.render import render
from app.security import require_manager_or_admin, require_user
from app.services.analytics_service import chemical_stock_summary, monthly_average_consumption
from app.services.audit_service import log_action
from app.services.codes import assign_code

router = APIRouter(prefix="/chemicals", tags=["chemicals"])


@router.get("")
def list_chemicals(request: Request, q: str = "", category: str = "", page: int = 1, db: Session = Depends(get_db), user: User = Depends(require_user)):
    stmt = select(Chemical).where(Chemical.is_archived.is_(False)).order_by(Chemical.name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Chemical.name.ilike(like), Chemical.chemical_code.ilike(like), Chemical.cas_number.ilike(like)))
    if category:
        stmt = stmt.where(Chemical.category == category)
    page_obj = paginate(db, stmt, page=page)

    categories = sorted({c[0] for c in db.execute(select(Chemical.category).where(Chemical.category.is_not(None)).distinct()) if c[0]})
    stock = {c.id: chemical_stock_summary(db, c) for c in page_obj.items}

    return render(request, "chemicals/list.html", {"nav_active": "chemicals", "page_obj": page_obj, "q": q, "category": category, "categories": categories, "stock": stock})


@router.get("/new")
def new_chemical_form(request: Request, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    suppliers = list(db.scalars(select(Supplier).where(Supplier.is_active.is_(True)).order_by(Supplier.name)))
    return render(request, "chemicals/form.html", {"nav_active": "chemicals", "chemical": None, "suppliers": suppliers})


@router.post("/new")
def create_chemical(
    request: Request,
    name: str = Form(...),
    cas_number: str = Form(""),
    formula: str = Form(""),
    molecular_weight: str = Form(""),
    grade: str = Form(""),
    concentration: str = Form(""),
    manufacturer: str = Form(""),
    catalog_number: str = Form(""),
    category: str = Form(""),
    storage_requirements: str = Form(""),
    temperature_requirements: str = Form(""),
    physical_state: str = Form(""),
    unit: str = Form("mL"),
    min_stock: str = Form("0"),
    reorder_level: str = Form("0"),
    target_stock: str = Form("0"),
    safety_stock: str = Form("0"),
    notes: str = Form(""),
    aliases: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    if cas_number.strip():
        dup = db.scalar(select(Chemical).where(Chemical.cas_number == cas_number.strip()))
        if dup:
            suppliers = list(db.scalars(select(Supplier).order_by(Supplier.name)))
            return render(
                request,
                "chemicals/form.html",
                {"nav_active": "chemicals", "chemical": None, "suppliers": suppliers, "error": f"A chemical with CAS {cas_number} already exists ({dup.name})."},
                status_code=400,
            )

    chem = Chemical(
        chemical_code="",
        name=name.strip(),
        cas_number=cas_number.strip() or None,
        formula=formula.strip() or None,
        molecular_weight=float(molecular_weight) if molecular_weight else None,
        grade=grade.strip() or None,
        concentration=concentration.strip() or None,
        manufacturer=manufacturer.strip() or None,
        catalog_number=catalog_number.strip() or None,
        category=category.strip() or None,
        storage_requirements=storage_requirements.strip() or None,
        temperature_requirements=temperature_requirements.strip() or None,
        physical_state=physical_state.strip() or None,
        unit=unit.strip() or "mL",
        min_stock=float(min_stock or 0),
        reorder_level=float(reorder_level or 0),
        target_stock=float(target_stock or 0),
        safety_stock=float(safety_stock or 0),
        notes=notes.strip() or None,
    )
    db.add(chem)
    assign_code(db, chem, "chemical_code", "CHM-")

    for alias in [a.strip() for a in aliases.split(",") if a.strip()]:
        db.add(ChemicalAlias(chemical_id=chem.id, alias=alias))

    log_action(db, user=user, action="CREATE", entity_type="chemical", entity_id=chem.id, description=f"Created chemical {chem.chemical_code} - {chem.name}.")
    db.commit()
    response = RedirectResponse(f"/chemicals/{chem.id}", status_code=302)
    set_flash(response, "success", f"Chemical '{chem.name}' created as {chem.chemical_code}.")
    return response


@router.get("/{chemical_id}")
def chemical_detail(request: Request, chemical_id: int, tab: str = "identity", db: Session = Depends(get_db), user: User = Depends(require_user)):
    chem = db.get(Chemical, chemical_id)
    if not chem:
        return render(request, "errors/404.html", {"nav_active": "chemicals"}, status_code=404)

    containers = list(db.scalars(select(Container).where(Container.chemical_id == chemical_id).order_by(Container.container_code)))
    container_ids = [c.id for c in containers]

    context = {
        "nav_active": "chemicals",
        "chemical": chem,
        "containers": containers,
        "stock": chemical_stock_summary(db, chem),
        "avg_monthly": monthly_average_consumption(db, chem.id),
        "tab": tab,
    }

    if tab == "usage" and container_ids:
        context["usage_txns"] = list(
            db.scalars(
                select(InventoryTransaction)
                .where(InventoryTransaction.container_id.in_(container_ids), InventoryTransaction.transaction_type == "USE")
                .order_by(InventoryTransaction.occurred_at.desc())
                .limit(100)
            )
        )
    elif tab == "transfers" and container_ids:
        context["transfers"] = list(
            db.scalars(
                select(TransferRecord)
                .where(TransferRecord.container_id.in_(container_ids))
                .order_by(TransferRecord.requested_at.desc())
                .limit(100)
            )
        )
    elif tab == "verification" and container_ids:
        context["counts"] = list(
            db.scalars(
                select(PhysicalCount)
                .where(PhysicalCount.container_id.in_(container_ids))
                .order_by(PhysicalCount.counted_at.desc())
                .limit(100)
            )
        )
    elif tab == "audit":
        context["audit_entries"] = list(
            db.scalars(
                select(AuditLog)
                .where(AuditLog.entity_type == "chemical", AuditLog.entity_id == chemical_id)
                .order_by(AuditLog.occurred_at.desc())
                .limit(100)
            )
        )

    return render(request, "chemicals/detail.html", context)


@router.get("/{chemical_id}/edit")
def edit_chemical_form(request: Request, chemical_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    chem = db.get(Chemical, chemical_id)
    if not chem:
        return render(request, "errors/404.html", {"nav_active": "chemicals"}, status_code=404)
    suppliers = list(db.scalars(select(Supplier).order_by(Supplier.name)))
    return render(request, "chemicals/form.html", {"nav_active": "chemicals", "chemical": chem, "suppliers": suppliers})


@router.post("/{chemical_id}/edit")
def update_chemical(
    request: Request,
    chemical_id: int,
    name: str = Form(...),
    cas_number: str = Form(""),
    formula: str = Form(""),
    molecular_weight: str = Form(""),
    grade: str = Form(""),
    concentration: str = Form(""),
    manufacturer: str = Form(""),
    catalog_number: str = Form(""),
    category: str = Form(""),
    storage_requirements: str = Form(""),
    temperature_requirements: str = Form(""),
    physical_state: str = Form(""),
    unit: str = Form("mL"),
    min_stock: str = Form("0"),
    reorder_level: str = Form("0"),
    target_stock: str = Form("0"),
    safety_stock: str = Form("0"),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    chem = db.get(Chemical, chemical_id)
    if not chem:
        return render(request, "errors/404.html", {"nav_active": "chemicals"}, status_code=404)

    chem.name = name.strip()
    chem.cas_number = cas_number.strip() or None
    chem.formula = formula.strip() or None
    chem.molecular_weight = float(molecular_weight) if molecular_weight else None
    chem.grade = grade.strip() or None
    chem.concentration = concentration.strip() or None
    chem.manufacturer = manufacturer.strip() or None
    chem.catalog_number = catalog_number.strip() or None
    chem.category = category.strip() or None
    chem.storage_requirements = storage_requirements.strip() or None
    chem.temperature_requirements = temperature_requirements.strip() or None
    chem.physical_state = physical_state.strip() or None
    chem.unit = unit.strip() or "mL"
    chem.min_stock = float(min_stock or 0)
    chem.reorder_level = float(reorder_level or 0)
    chem.target_stock = float(target_stock or 0)
    chem.safety_stock = float(safety_stock or 0)
    chem.notes = notes.strip() or None

    log_action(db, user=user, action="UPDATE", entity_type="chemical", entity_id=chem.id, description=f"Updated chemical {chem.chemical_code}.")
    db.commit()
    response = RedirectResponse(f"/chemicals/{chem.id}", status_code=302)
    set_flash(response, "success", "Chemical updated.")
    return response


@router.post("/{chemical_id}/archive")
def archive_chemical(request: Request, chemical_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    chem = db.get(Chemical, chemical_id)
    if chem:
        chem.is_archived = True
        log_action(db, user=user, action="ARCHIVE", entity_type="chemical", entity_id=chem.id, description=f"Archived chemical {chem.chemical_code}.")
        db.commit()
    response = RedirectResponse("/chemicals", status_code=302)
    set_flash(response, "success", "Chemical archived.")
    return response
