from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.flash import set_flash
from app.models.chemical import Project, Supplier
from app.models.common import Role
from app.models.laboratory import Laboratory
from app.models.audit import SystemSetting
from app.models.user import User
from app.render import invalidate_branding_cache, render
from app.security import hash_password, require_admin
from app.services.audit_service import log_action
from app.services.settings_service import get_setting_str, set_setting_str

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()

SETTINGS_KEYS = {
    "expiry_warning_days_1": ("Expiry warning - Tier 1 (days)", settings.expiry_warning_days_1),
    "expiry_warning_days_2": ("Expiry warning - Tier 2 (days)", settings.expiry_warning_days_2),
    "expiry_warning_days_3": ("Expiry warning - Tier 3 (days)", settings.expiry_warning_days_3),
    "dead_stock_days": ("Dead-stock detection window (days)", settings.dead_stock_days),
    "variance_tolerance_percent": ("Reconciliation variance tolerance (%)", settings.variance_tolerance_percent),
}

BRANDING_KEYS = {
    "app_short_name": ("Short name (sidebar, browser tab, footer)", settings.app_short_name),
    "app_name": ("Full application name", settings.app_name),
}


@router.get("/users")
def list_users(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    users = list(db.scalars(select(User).order_by(User.full_name)))
    laboratories = list(db.scalars(select(Laboratory).where(Laboratory.is_active.is_(True)).order_by(Laboratory.name)))
    return render(request, "admin/users.html", {"nav_active": "admin", "admin_tab": "users", "users": users, "laboratories": laboratories, "roles": [r.value for r in Role]})


@router.post("/users")
def create_user(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    laboratory_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    email_norm = email.strip().lower()
    existing = db.scalar(select(User).where(User.email == email_norm))
    if existing:
        response = RedirectResponse("/admin/users", status_code=302)
        set_flash(response, "error", f"A user with email {email_norm} already exists.")
        return response

    new_user = User(
        full_name=full_name.strip(),
        email=email_norm,
        password_hash=hash_password(password),
        role=role,
        laboratory_id=int(laboratory_id) if laboratory_id else None,
    )
    db.add(new_user)
    db.flush()
    log_action(db, user=user, action="CREATE", entity_type="user", entity_id=new_user.id, description=f"Created user {new_user.email} ({new_user.role}).")
    db.commit()
    response = RedirectResponse("/admin/users", status_code=302)
    set_flash(response, "success", f"User {new_user.full_name} created.")
    return response


@router.post("/users/{user_id}/toggle-active")
def toggle_user_active(request: Request, user_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    target = db.get(User, user_id)
    if target and target.id != user.id:
        target.is_active = not target.is_active
        log_action(db, user=user, action="UPDATE", entity_type="user", entity_id=target.id, description=f"Set {target.email} active={target.is_active}.")
        db.commit()
    response = RedirectResponse("/admin/users", status_code=302)
    set_flash(response, "success", "User updated.")
    return response


@router.get("/suppliers")
def list_suppliers(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    suppliers = list(db.scalars(select(Supplier).order_by(Supplier.name)))
    return render(request, "admin/suppliers.html", {"nav_active": "admin", "admin_tab": "suppliers", "suppliers": suppliers})


@router.post("/suppliers")
def create_supplier(
    request: Request,
    name: str = Form(...),
    contact_name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    db.add(Supplier(name=name.strip(), contact_name=contact_name.strip() or None, email=email.strip() or None, phone=phone.strip() or None, notes=notes.strip() or None))
    db.commit()
    response = RedirectResponse("/admin/suppliers", status_code=302)
    set_flash(response, "success", "Supplier added.")
    return response


@router.get("/projects")
def list_projects(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    projects = list(db.scalars(select(Project).order_by(Project.name)))
    laboratories = list(db.scalars(select(Laboratory).order_by(Laboratory.name)))
    return render(request, "admin/projects.html", {"nav_active": "admin", "admin_tab": "projects", "projects": projects, "laboratories": laboratories})


@router.post("/projects")
def create_project(
    request: Request,
    code: str = Form(...),
    name: str = Form(...),
    laboratory_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    db.add(Project(code=code.strip(), name=name.strip(), laboratory_id=int(laboratory_id) if laboratory_id else None))
    db.commit()
    response = RedirectResponse("/admin/projects", status_code=302)
    set_flash(response, "success", "Project added.")
    return response


@router.get("/settings")
def system_settings(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    stored = {s.key: s.value for s in db.scalars(select(SystemSetting))}
    values = {k: stored.get(k, str(default)) for k, (_, default) in SETTINGS_KEYS.items()}
    branding_values = {k: get_setting_str(db, k, default) for k, (_, default) in BRANDING_KEYS.items()}
    return render(
        request,
        "admin/settings.html",
        {
            "nav_active": "admin", "admin_tab": "settings",
            "settings_keys": SETTINGS_KEYS, "values": values,
            "branding_keys": BRANDING_KEYS, "branding_values": branding_values,
        },
    )


@router.post("/settings/save")
async def save_settings(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    form = await request.form()
    for key in SETTINGS_KEYS:
        if key in form:
            existing = db.get(SystemSetting, key)
            if existing:
                existing.value = str(form[key])
                existing.updated_by_id = user.id
            else:
                db.add(SystemSetting(key=key, value=str(form[key]), updated_by_id=user.id))

    branding_changed = False
    for key in BRANDING_KEYS:
        if key in form and str(form[key]).strip():
            set_setting_str(db, key, str(form[key]), updated_by_id=user.id)
            branding_changed = True

    log_action(db, user=user, action="UPDATE", entity_type="system_settings", entity_id=None, description="Updated system settings/thresholds.")
    db.commit()
    if branding_changed:
        invalidate_branding_cache()
    response = RedirectResponse("/admin/settings", status_code=302)
    set_flash(response, "success", "Settings saved.")
    return response
