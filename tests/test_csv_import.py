from app.services.csv_service import commit_import, parse_csv, preview_import


def test_chemical_csv_creates_new_and_updates_existing(db, base_fixtures):
    chem = base_fixtures["chemical"]
    admin = base_fixtures["admin"]

    csv_text = (
        "chemical_code,name,cas_number,category,unit,min_stock,reorder_level\n"
        f"{chem.chemical_code},{chem.name},,Solvent,mL,50,150\n"  # update existing (change category/thresholds)
        ",Brand New Chemical,999-99-9,Acid,g,10,20\n"  # create new
    )
    rows = parse_csv(csv_text.encode("utf-8"))
    result = preview_import(db, "chemical", rows)

    assert len(result.to_update) == 1
    assert len(result.to_create) == 1
    assert not result.errors

    created, updated = commit_import(db, result, admin, "chemicals.csv")
    db.commit()

    assert created == 1
    assert updated == 1
    db.refresh(chem)
    assert chem.category == "Solvent"
    assert chem.reorder_level == 150


def test_chemical_csv_flags_missing_required_field(db, base_fixtures):
    rows = parse_csv(b"chemical_code,name,cas_number\n,,123-45-6\n")
    result = preview_import(db, "chemical", rows)

    assert result.valid_count == 0
    assert len(result.errors) == 1
    assert result.errors[0].field == "name"


def test_container_csv_rejects_unknown_chemical_and_lab(db, base_fixtures):
    rows = parse_csv(
        (
            "container_code,chemical_code_or_name,container_size,unit,initial_quantity,date_received,laboratory_code\n"
            "CHEM-999999,DOES-NOT-EXIST,100,mL,50,2026-01-01,LAB-A\n"
        ).encode("utf-8")
    )
    result = preview_import(db, "container", rows)
    assert result.valid_count == 0
    assert "not found" in result.errors[0].problem.lower()


def test_container_csv_creates_container_with_ledger_receive(db, base_fixtures):
    chem = base_fixtures["chemical"]
    admin = base_fixtures["admin"]

    rows = parse_csv(
        (
            "container_code,chemical_code_or_name,container_size,unit,initial_quantity,date_received,laboratory_code\n"
            f",{chem.chemical_code},1000,mL,300,2026-01-01,LAB-A\n"
        ).encode("utf-8")
    )
    result = preview_import(db, "container", rows)
    assert result.valid_count == 1
    assert not result.errors

    created, updated = commit_import(db, result, admin, "containers.csv")
    db.commit()
    assert created == 1

    from sqlalchemy import select

    from app.models.container import Container
    from app.models.transaction import InventoryTransaction

    new_container = db.scalar(select(Container).where(Container.chemical_id == chem.id, Container.initial_quantity == 300))
    assert new_container is not None
    assert new_container.expected_quantity == 300.0

    receive_txn = db.scalar(select(InventoryTransaction).where(InventoryTransaction.container_id == new_container.id))
    assert receive_txn is not None
    assert receive_txn.transaction_type == "RECEIVE"


def test_container_csv_update_never_touches_quantity_history(db, base_fixtures):
    container = base_fixtures["container"]
    admin = base_fixtures["admin"]
    original_expected = container.expected_quantity

    rows = parse_csv(
        (
            "container_code,chemical_code_or_name,container_size,unit,initial_quantity,date_received,laboratory_code,notes\n"
            f"{container.container_code},{container.chemical.chemical_code},{container.container_size},mL,999999,2026-01-01,LAB-A,Updated via CSV\n"
        ).encode("utf-8")
    )
    result = preview_import(db, "container", rows)
    assert result.valid_count == 1

    commit_import(db, result, admin, "containers.csv")
    db.commit()
    db.refresh(container)

    assert container.notes == "Updated via CSV"
    assert container.expected_quantity == original_expected  # quantity is ledger-controlled, not CSV-controlled
