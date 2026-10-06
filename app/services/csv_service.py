from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chemical import Chemical, Supplier
from app.models.common import ContainerStatus, LocationType
from app.models.container import Container
from app.models.laboratory import Laboratory
from app.models.location import Location
from app.services.codes import assign_code

TEMPLATES: dict[str, list[str]] = {
    "laboratory": ["code", "name", "building", "floor", "description"],
    "location": ["name", "location_type", "parent_full_path", "laboratory_code"],
    "chemical": [
        "chemical_code", "name", "cas_number", "formula", "molecular_weight", "grade",
        "concentration", "manufacturer", "supplier", "catalog_number", "category",
        "storage_requirements", "temperature_requirements", "physical_state", "unit",
        "min_stock", "reorder_level", "target_stock", "safety_stock", "notes",
    ],
    "container": [
        "container_code", "chemical_code_or_name", "batch_lot", "container_size", "unit",
        "initial_quantity", "date_received", "date_opened", "expiry_date",
        "laboratory_code", "location_full_path", "notes",
    ],
}

VALID_LOCATION_TYPES = {t.value for t in LocationType}


@dataclass
class RowError:
    row: int
    field: str
    problem: str
    suggestion: str


@dataclass
class PreviewResult:
    entity_type: str
    total_rows: int
    to_create: list[dict] = field(default_factory=list)
    to_update: list[dict] = field(default_factory=list)
    duplicates_skipped: int = 0
    errors: list[RowError] = field(default_factory=list)

    @property
    def valid_count(self) -> int:
        return len(self.to_create) + len(self.to_update)


def template_csv(entity_type: str) -> str:
    columns = TEMPLATES[entity_type]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    return buf.getvalue()


def parse_csv(raw_bytes: bytes) -> list[dict[str, str]]:
    text = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for r in reader:
        rows.append({(k or "").strip(): (v or "").strip() for k, v in r.items() if k})
    return rows


def _to_float(value: str) -> float | None:
    try:
        return float(value) if value != "" else None
    except ValueError:
        return None


def _to_date(value: str) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def preview_import(db: Session, entity_type: str, rows: list[dict], mode: str = "add_and_update") -> PreviewResult:
    if entity_type == "laboratory":
        return _preview_laboratory(db, rows)
    if entity_type == "location":
        return _preview_location(db, rows)
    if entity_type == "chemical":
        return _preview_chemical(db, rows)
    if entity_type == "container":
        return _preview_container(db, rows)
    raise ValueError(f"Unknown entity type: {entity_type}")


def _preview_laboratory(db: Session, rows: list[dict]) -> PreviewResult:
    result = PreviewResult(entity_type="laboratory", total_rows=len(rows))
    seen_codes: set[str] = set()
    for i, row in enumerate(rows, start=2):
        code = row.get("code", "")
        name = row.get("name", "")
        if not code:
            result.errors.append(RowError(i, "code", "Missing required field", "Enter a unique laboratory code"))
            continue
        if not name:
            result.errors.append(RowError(i, "name", "Missing required field", "Enter a laboratory name"))
            continue
        if code in seen_codes:
            result.errors.append(RowError(i, "code", "Duplicate within this file", "Use a unique code per row"))
            continue
        seen_codes.add(code)

        existing = db.scalar(select(Laboratory).where(Laboratory.code == code))
        payload = {
            "code": code,
            "name": name,
            "building": row.get("building") or "Research Building",
            "floor": row.get("floor") or None,
            "description": row.get("description") or None,
        }
        if existing:
            result.to_update.append({"id": existing.id, **payload})
        else:
            result.to_create.append(payload)
    return result


def _resolve_location_by_path(db: Session, full_path: str) -> Location | None:
    if not full_path:
        return None
    return db.scalar(select(Location).where(Location.full_path == full_path))


def _preview_location(db: Session, rows: list[dict]) -> PreviewResult:
    result = PreviewResult(entity_type="location", total_rows=len(rows))
    for i, row in enumerate(rows, start=2):
        name = row.get("name", "")
        location_type = row.get("location_type", "").upper()
        parent_path = row.get("parent_full_path", "")
        lab_code = row.get("laboratory_code", "")

        if not name:
            result.errors.append(RowError(i, "name", "Missing required field", "Enter a location name"))
            continue
        if location_type not in VALID_LOCATION_TYPES:
            result.errors.append(
                RowError(i, "location_type", f"Invalid type '{location_type}'", f"Use one of: {', '.join(sorted(VALID_LOCATION_TYPES))}")
            )
            continue

        parent = None
        if parent_path:
            parent = _resolve_location_by_path(db, parent_path)
            if parent is None:
                result.errors.append(RowError(i, "parent_full_path", "Parent location not found", "Create the parent location first or check spelling"))
                continue

        laboratory = None
        if lab_code:
            laboratory = db.scalar(select(Laboratory).where(Laboratory.code == lab_code))
            if laboratory is None:
                result.errors.append(RowError(i, "laboratory_code", f"Laboratory '{lab_code}' not found", "Select an existing laboratory code"))
                continue

        full_path = f"{parent_path} > {name}" if parent_path else name
        existing = db.scalar(select(Location).where(Location.full_path == full_path))
        payload = {
            "name": name,
            "location_type": location_type,
            "parent_id": parent.id if parent else None,
            "laboratory_id": laboratory.id if laboratory else None,
            "full_path": full_path,
        }
        if existing:
            result.to_update.append({"id": existing.id, **payload})
        else:
            result.to_create.append(payload)
    return result


def _preview_chemical(db: Session, rows: list[dict]) -> PreviewResult:
    result = PreviewResult(entity_type="chemical", total_rows=len(rows))
    seen: set[str] = set()
    for i, row in enumerate(rows, start=2):
        name = row.get("name", "")
        if not name:
            result.errors.append(RowError(i, "name", "Missing required field", "Enter a chemical name"))
            continue

        code = row.get("chemical_code", "")
        cas = row.get("cas_number") or None
        dup_key = code or f"{name.lower()}|{(row.get('manufacturer') or '').lower()}"
        if dup_key in seen:
            result.errors.append(RowError(i, "name", "Duplicate within this file", "Combine or remove duplicate rows"))
            continue
        seen.add(dup_key)

        min_stock = _to_float(row.get("min_stock", "")) or 0.0
        reorder_level = _to_float(row.get("reorder_level", "")) or 0.0
        target_stock = _to_float(row.get("target_stock", "")) or 0.0
        safety_stock = _to_float(row.get("safety_stock", "")) or 0.0
        for fname, fval in [("min_stock", row.get("min_stock")), ("reorder_level", row.get("reorder_level"))]:
            if fval and _to_float(fval) is None:
                result.errors.append(RowError(i, fname, "Invalid number", "Enter a numeric value"))
                continue

        supplier_id = None
        supplier_name = row.get("supplier")
        if supplier_name:
            supplier = db.scalar(select(Supplier).where(Supplier.name == supplier_name))
            if supplier is None:
                supplier = Supplier(name=supplier_name)
                db.add(supplier)
                db.flush()
            supplier_id = supplier.id

        existing = None
        if code:
            existing = db.scalar(select(Chemical).where(Chemical.chemical_code == code))
        elif cas:
            existing = db.scalar(select(Chemical).where(Chemical.cas_number == cas))

        payload = {
            "name": name,
            "cas_number": cas,
            "formula": row.get("formula") or None,
            "molecular_weight": _to_float(row.get("molecular_weight", "")),
            "grade": row.get("grade") or None,
            "concentration": row.get("concentration") or None,
            "manufacturer": row.get("manufacturer") or None,
            "supplier_id": supplier_id,
            "catalog_number": row.get("catalog_number") or None,
            "category": row.get("category") or None,
            "storage_requirements": row.get("storage_requirements") or None,
            "temperature_requirements": row.get("temperature_requirements") or None,
            "physical_state": row.get("physical_state") or None,
            "unit": row.get("unit") or "mL",
            "min_stock": min_stock,
            "reorder_level": reorder_level,
            "target_stock": target_stock,
            "safety_stock": safety_stock,
            "notes": row.get("notes") or None,
        }
        if existing:
            result.to_update.append({"id": existing.id, **payload})
        else:
            result.to_create.append(payload)
    return result


def _preview_container(db: Session, rows: list[dict]) -> PreviewResult:
    result = PreviewResult(entity_type="container", total_rows=len(rows))
    for i, row in enumerate(rows, start=2):
        code = row.get("container_code", "")
        chem_ref = row.get("chemical_code_or_name", "")
        lab_code = row.get("laboratory_code", "")
        size = _to_float(row.get("container_size", ""))
        initial_qty = _to_float(row.get("initial_quantity", ""))
        date_received = _to_date(row.get("date_received", ""))

        if not chem_ref:
            result.errors.append(RowError(i, "chemical_code_or_name", "Missing required field", "Enter a chemical code or exact name"))
            continue
        chemical = db.scalar(select(Chemical).where(Chemical.chemical_code == chem_ref))
        if chemical is None:
            chemical = db.scalar(select(Chemical).where(Chemical.name == chem_ref))
        if chemical is None:
            result.errors.append(RowError(i, "chemical_code_or_name", f"Chemical '{chem_ref}' not found", "Import the chemical master first"))
            continue

        if not lab_code:
            result.errors.append(RowError(i, "laboratory_code", "Missing required field", "Enter an existing laboratory code"))
            continue
        laboratory = db.scalar(select(Laboratory).where(Laboratory.code == lab_code))
        if laboratory is None:
            result.errors.append(RowError(i, "laboratory_code", f"Laboratory '{lab_code}' not found", "Select an existing laboratory"))
            continue

        if size is None:
            result.errors.append(RowError(i, "container_size", "Invalid or missing number", "Enter a numeric container size"))
            continue
        if initial_qty is None:
            result.errors.append(RowError(i, "initial_quantity", "Invalid or missing number", "Enter a numeric initial quantity"))
            continue
        if date_received is None:
            result.errors.append(RowError(i, "date_received", "Invalid or missing date", "Use YYYY-MM-DD"))
            continue

        location = None
        loc_path = row.get("location_full_path")
        if loc_path:
            location = _resolve_location_by_path(db, loc_path)
            if location is None:
                result.errors.append(RowError(i, "location_full_path", "Location not found", "Import locations first or check spelling"))
                continue

        existing = None
        if code:
            existing = db.scalar(select(Container).where(Container.container_code == code))
            if existing and existing.chemical_id != chemical.id:
                result.errors.append(RowError(i, "container_code", "Duplicate container ID", "Use a unique container ID"))
                continue

        payload = {
            "chemical_id": chemical.id,
            "batch_lot": row.get("batch_lot") or None,
            "container_size": size,
            "unit": row.get("unit") or chemical.unit,
            "initial_quantity": initial_qty,
            "date_received": date_received,
            "date_opened": _to_date(row.get("date_opened", "")),
            "expiry_date": _to_date(row.get("expiry_date", "")),
            "laboratory_id": laboratory.id,
            "location_id": location.id if location else None,
            "notes": row.get("notes") or None,
        }
        if existing:
            result.to_update.append({"id": existing.id, **payload})
        else:
            result.to_create.append(payload)
    return result


def commit_import(db: Session, preview: PreviewResult, user, filename: str):
    from app.models.audit import ImportAudit
    from app.services.audit_service import log_action
    from app.services.inventory_service import receive_container, recompute_container_status

    created_count = 0
    updated_count = 0

    if preview.entity_type == "laboratory":
        for payload in preview.to_create:
            obj = Laboratory(**payload)
            db.add(obj)
            created_count += 1
        for payload in preview.to_update:
            obj = db.get(Laboratory, payload.pop("id"))
            for k, v in payload.items():
                setattr(obj, k, v)
            updated_count += 1

    elif preview.entity_type == "location":
        for payload in preview.to_create:
            obj = Location(**payload)
            db.add(obj)
            created_count += 1
        for payload in preview.to_update:
            obj = db.get(Location, payload.pop("id"))
            for k, v in payload.items():
                setattr(obj, k, v)
            updated_count += 1

    elif preview.entity_type == "chemical":
        for payload in preview.to_create:
            obj = Chemical(chemical_code="", **payload)
            db.add(obj)
            assign_code(db, obj, "chemical_code", "CHM-")
            created_count += 1
        for payload in preview.to_update:
            obj = db.get(Chemical, payload.pop("id"))
            for k, v in payload.items():
                setattr(obj, k, v)
            updated_count += 1

    elif preview.entity_type == "container":
        for payload in preview.to_create:
            obj = Container(
                container_code="",
                expected_quantity=0.0,
                status=ContainerStatus.AVAILABLE.value,
                **payload,
            )
            db.add(obj)
            assign_code(db, obj, "container_code", "CHEM-")
            receive_container(db, container=obj, user=user, notes="Received via CSV import")
            created_count += 1
        for payload in preview.to_update:
            obj = db.get(Container, payload.pop("id"))
            payload.pop("initial_quantity", None)  # never silently touch quantity history on update
            for k, v in payload.items():
                setattr(obj, k, v)
            recompute_container_status(db, obj)
            updated_count += 1

    db.flush()

    audit = ImportAudit(
        user_id=user.id,
        entity_type=preview.entity_type,
        filename=filename,
        total_rows=preview.total_rows,
        created=created_count,
        updated=updated_count,
        duplicates=preview.duplicates_skipped,
        errors=len(preview.errors),
    )
    db.add(audit)
    log_action(
        db,
        user=user,
        action="CSV_IMPORT",
        entity_type=preview.entity_type,
        entity_id=None,
        description=(
            f"Imported {filename}: {created_count} created, {updated_count} updated, "
            f"{len(preview.errors)} errors out of {preview.total_rows} rows."
        ),
    )
    db.flush()
    return created_count, updated_count
