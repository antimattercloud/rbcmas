from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User


def log_action(
    db: Session,
    *,
    user: User | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    description: str,
) -> AuditLog:
    entry = AuditLog(
        user_id=user.id if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
    )
    db.add(entry)
    db.flush()
    return entry
