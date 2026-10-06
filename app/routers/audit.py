from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.audit import AuditLog
from app.models.user import User
from app.pagination import paginate
from app.render import render
from app.security import require_user

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def audit_log_view(request: Request, action: str = "", entity_type: str = "", page: int = 1, db: Session = Depends(get_db), user: User = Depends(require_user)):
    stmt = select(AuditLog).order_by(AuditLog.occurred_at.desc())
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    page_obj = paginate(db, stmt, page=page, per_page=40)

    actions = sorted({a[0] for a in db.execute(select(AuditLog.action).distinct())})
    entity_types = sorted({a[0] for a in db.execute(select(AuditLog.entity_type).distinct())})

    return render(
        request,
        "audit/list.html",
        {"nav_active": "audit", "page_obj": page_obj, "action": action, "entity_type": entity_type, "actions": actions, "entity_types": entity_types},
    )
