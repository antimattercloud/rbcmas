from __future__ import annotations

from datetime import timedelta

from fastapi import Depends, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.common import Role
from app.models.user import User

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SESSION_COOKIE_NAME = "rbcmas_session"


class NotAuthenticated(Exception):
    """Raised by require_user when there is no valid session. Handled in
    main.py with a friendly redirect to /login instead of FastAPI's default
    HTTPException JSON body, which would look unprofessional to end users."""


class PermissionDenied(Exception):
    """Raised by require_roles when the logged-in user's role doesn't allow
    the action. Handled in main.py with a friendly 403 page."""


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="rbcmas-session")


def hash_password(raw_password: str) -> str:
    return pwd_context.hash(raw_password)


def verify_password(raw_password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(raw_password, password_hash)
    except ValueError:
        return False


def create_session_token(user_id: int) -> str:
    return _serializer().dumps({"user_id": user_id})


def read_session_token(token: str) -> int | None:
    try:
        data = _serializer().loads(
            token, max_age=int(timedelta(hours=settings.session_hours).total_seconds())
        )
    except (BadSignature, SignatureExpired):
        return None
    return data.get("user_id")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    user_id = read_session_token(token)
    if not user_id:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def require_user(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise NotAuthenticated()
    return user


def require_roles(*roles: Role):
    allowed = {r.value for r in roles}

    def _dependency(user: User = Depends(require_user)) -> User:
        if user.role not in allowed:
            raise PermissionDenied()
        return user

    return _dependency


# Common role bundles used across routers
require_admin = require_roles(Role.ADMIN)
require_write = require_roles(Role.ADMIN, Role.LAB_MANAGER, Role.RESEARCHER)
require_manager_or_admin = require_roles(Role.ADMIN, Role.LAB_MANAGER)
require_any = require_roles(Role.ADMIN, Role.LAB_MANAGER, Role.RESEARCHER, Role.AUDITOR)


def can_access_laboratory(user: User, laboratory_id: int | None) -> bool:
    """Admins and auditors see everything. Lab managers/researchers are scoped
    to their own laboratory when one is assigned."""
    if user.role in (Role.ADMIN.value, Role.AUDITOR.value):
        return True
    if user.laboratory_id is None:
        return True
    return user.laboratory_id == laboratory_id
