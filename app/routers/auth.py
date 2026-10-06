from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.flash import set_flash
from app.models.common import Role
from app.models.laboratory import Laboratory
from app.render import render
from app.security import SESSION_COOKIE_NAME, create_session_token, hash_password, verify_password
from app.models.user import User
from app.services.audit_service import log_action

router = APIRouter()


@router.get("/")
def root(request: Request):
    if getattr(request.state, "user", None):
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


@router.get("/login")
def login_form(request: Request):
    if getattr(request.state, "user", None):
        return RedirectResponse("/dashboard", status_code=302)
    return render(request, "login.html", {})


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return render(
            request,
            "login.html",
            {"error": "Invalid email or password.", "email": email},
            status_code=401,
        )
    token = create_session_token(user.id)
    response = RedirectResponse("/dashboard", status_code=302)
    response.set_cookie(SESSION_COOKIE_NAME, token, httponly=True, samesite="lax", max_age=60 * 60 * 12)
    return response


@router.get("/register")
def register_form(request: Request, db: Session = Depends(get_db)):
    if getattr(request.state, "user", None):
        return RedirectResponse("/dashboard", status_code=302)
    laboratories = list(db.scalars(select(Laboratory).where(Laboratory.is_active.is_(True)).order_by(Laboratory.name)))
    return render(request, "register.html", {"laboratories": laboratories})


@router.post("/register")
def register_submit(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    laboratory_id: str = Form(""),
    db: Session = Depends(get_db),
):
    laboratories = list(db.scalars(select(Laboratory).where(Laboratory.is_active.is_(True)).order_by(Laboratory.name)))
    form_state = {"laboratories": laboratories, "full_name": full_name, "email": email, "laboratory_id": laboratory_id}

    email_norm = email.strip().lower()
    if len(password) < 8:
        return render(request, "register.html", {**form_state, "error": "Password must be at least 8 characters long."}, status_code=400)
    if password != confirm_password:
        return render(request, "register.html", {**form_state, "error": "Passwords do not match."}, status_code=400)
    if db.scalar(select(User).where(User.email == email_norm)):
        return render(request, "register.html", {**form_state, "error": "An account with that email already exists."}, status_code=400)

    # Self-registered accounts start as the lowest-privilege role and inactive
    # until an administrator approves them (Administration > Users) - RBAC and
    # laboratory scoping are deliberate, accountable decisions, not something
    # a public signup form should grant on its own.
    user = User(
        full_name=full_name.strip(),
        email=email_norm,
        password_hash=hash_password(password),
        role=Role.RESEARCHER.value,
        laboratory_id=int(laboratory_id) if laboratory_id else None,
        is_active=False,
    )
    db.add(user)
    db.flush()
    log_action(db, user=None, action="SELF_REGISTERED", entity_type="user", entity_id=user.id, description=f"{user.email} requested an account (pending admin approval).")
    db.commit()

    response = RedirectResponse("/login", status_code=302)
    set_flash(response, "success", "Account request submitted. An administrator must approve your account before you can sign in.")
    return response


@router.post("/logout")
def logout(request: Request):
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE_NAME)
    set_flash(response, "info", "You have been signed out.")
    return response
