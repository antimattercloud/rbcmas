from sqlalchemy.orm import Session

from app.models.audit import SystemSetting


def get_setting(db: Session, key: str, default: float) -> float:
    """Admin-configurable thresholds are stored in system_settings and override
    the .env default when present, so the Administration > Settings page in
    the UI actually takes effect rather than being decorative."""
    row = db.get(SystemSetting, key)
    if row is None:
        return default
    try:
        return float(row.value)
    except ValueError:
        return default


def get_setting_str(db: Session, key: str, default: str) -> str:
    row = db.get(SystemSetting, key)
    if row is None or not row.value.strip():
        return default
    return row.value.strip()


def set_setting_str(db: Session, key: str, value: str, updated_by_id: int | None = None) -> None:
    row = db.get(SystemSetting, key)
    value = value.strip()
    if row:
        row.value = value
        row.updated_by_id = updated_by_id
    else:
        db.add(SystemSetting(key=key, value=value, updated_by_id=updated_by_id))
