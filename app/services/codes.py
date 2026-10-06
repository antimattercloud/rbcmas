from sqlalchemy.orm import Session


def assign_code(db: Session, obj, field_name: str, prefix: str, pad: int = 6) -> str:
    """Assigns a deterministic, collision-free human-readable code derived
    from the object's autoincrement primary key, e.g. CHEM-000042.
    Call after db.add(obj); requires obj.id to be available (flush first)."""
    db.flush()
    code = f"{prefix}{obj.id:0{pad}d}"
    setattr(obj, field_name, code)
    db.flush()
    return code
