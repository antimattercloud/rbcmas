"""Seeds realistic DEMO DATA per spec section 59: >=20 chemicals, >=30
containers, 5 laboratories, multiple locations, usage transactions,
transfers, expired/low-stock/discrepancy examples, and sample procurement
requests. Every demo row is flagged is_demo=True where the model supports it,
and demo user/laboratory/container codes are all clearly recognizable."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.models.chemical import Chemical, ChemicalAlias, Supplier
from app.models.common import ContainerStatus, TransactionType
from app.models.container import Container
from app.models.laboratory import Laboratory
from app.models.location import Location
from app.models.procurement import PurchaseRequest
from app.models.user import User
from app.security import hash_password
from app.services.codes import assign_code
from app.services.inventory_service import receive_container, record_physical_count, record_transaction
from app.services.transfer_service import complete_transfer, create_transfer

DEMO_PASSWORD = "demo1234"


def _dt(days_ago: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def run(db: Session) -> None:
    if db.query(User).count() > 0:
        print("Database already has data - skipping seed. Delete data/rbcmas.db to reseed.")
        return

    # --- Laboratories -----------------------------------------------------
    labs_data = [
        ("LAB-201", "Organic Chemistry Lab", "Floor 2"),
        ("LAB-202", "Analytical Chemistry Lab", "Floor 2"),
        ("LAB-203", "Biochemistry Lab", "Floor 3"),
        ("LAB-204", "Materials Science Lab", "Floor 3"),
        ("LAB-205", "Instrumentation Lab", "Floor 1"),
    ]
    labs = {}
    for code, name, floor in labs_data:
        lab = Laboratory(code=code, name=name, building="Research Building", floor=floor, is_demo=True)
        db.add(lab)
        db.flush()
        labs[code] = lab

    # --- Users --------------------------------------------------------
    admin = User(full_name="Ditij Dhameliya (Admin)", email="admin@rbcmas.local", password_hash=hash_password(DEMO_PASSWORD), role="ADMIN", is_demo=True)
    lab_manager = User(full_name="Priya Sharma (Lab Manager)", email="labmanager@rbcmas.local", password_hash=hash_password(DEMO_PASSWORD), role="LAB_MANAGER", laboratory_id=labs["LAB-201"].id, is_demo=True)
    researcher = User(full_name="Arjun Mehta (Researcher)", email="researcher@rbcmas.local", password_hash=hash_password(DEMO_PASSWORD), role="RESEARCHER", laboratory_id=labs["LAB-201"].id, is_demo=True)
    auditor = User(full_name="Kavita Rao (Auditor)", email="auditor@rbcmas.local", password_hash=hash_password(DEMO_PASSWORD), role="AUDITOR", is_demo=True)
    db.add_all([admin, lab_manager, researcher, auditor])
    db.flush()
    for code, _, _ in labs_data:
        labs[code].manager_id = lab_manager.id if code == "LAB-201" else None

    # --- Locations ------------------------------------------------------
    building = Location(name="Research Building", location_type="BUILDING", full_path="Research Building", is_demo=True)
    db.add(building)
    db.flush()

    floors = {}
    for floor_name in ["Floor 1", "Floor 2", "Floor 3"]:
        floor = Location(name=floor_name, location_type="FLOOR", parent_id=building.id, full_path=f"Research Building > {floor_name}", is_demo=True)
        db.add(floor)
        db.flush()
        floors[floor_name] = floor

    lab_locations = {}
    for code, name, floor_name in labs_data:
        room = Location(name=f"{name} - Storage Room", location_type="ROOM", parent_id=floors[floor_name].id, laboratory_id=labs[code].id,
                         full_path=f"{floors[floor_name].full_path} > {name} - Storage Room", is_demo=True)
        db.add(room)
        db.flush()
        cabinet = Location(name="Cabinet A", location_type="CABINET", parent_id=room.id, laboratory_id=labs[code].id,
                            full_path=f"{room.full_path} > Cabinet A", is_demo=True)
        db.add(cabinet)
        db.flush()
        shelf1 = Location(name="Shelf 1", location_type="SHELF", parent_id=cabinet.id, laboratory_id=labs[code].id, full_path=f"{cabinet.full_path} > Shelf 1", is_demo=True)
        shelf2 = Location(name="Shelf 2", location_type="SHELF", parent_id=cabinet.id, laboratory_id=labs[code].id, full_path=f"{cabinet.full_path} > Shelf 2", is_demo=True)
        db.add_all([shelf1, shelf2])
        db.flush()
        lab_locations[code] = [shelf1, shelf2]

    # --- Suppliers --------------------------------------------------------
    suppliers = {}
    for name in ["Sigma-Aldrich", "Fisher Scientific", "Merck", "VWR International"]:
        s = Supplier(name=name, is_demo=True)
        db.add(s)
        db.flush()
        suppliers[name] = s

    # --- Chemicals ----------------------------------------------------
    chem_defs = [
        ("Methanol", "67-56-1", "CH3OH", "Solvent", "ACS", "mL", 500, 1000, 5000, 500, ["Methyl alcohol", "Wood spirit"]),
        ("Ethanol", "64-17-5", "C2H5OH", "Solvent", "HPLC", "mL", 500, 1000, 5000, 500, ["Ethyl alcohol"]),
        ("Acetone", "67-64-1", "C3H6O", "Solvent", "ACS", "mL", 300, 600, 4000, 300, ["Propan-2-one"]),
        ("Sodium Chloride", "7647-14-5", "NaCl", "Salt", "ACS", "g", 200, 400, 2000, 200, ["Table salt"]),
        ("Sulfuric Acid", "7664-93-9", "H2SO4", "Acid", "ACS", "mL", 200, 400, 2500, 250, []),
        ("Hydrochloric Acid", "7647-01-0", "HCl", "Acid", "ACS", "mL", 200, 400, 2500, 250, ["Muriatic acid"]),
        ("Sodium Hydroxide", "1310-73-2", "NaOH", "Base", "ACS", "g", 200, 400, 2000, 200, ["Caustic soda", "Lye"]),
        ("Potassium Permanganate", "7722-64-7", "KMnO4", "Oxidizer", "ACS", "g", 50, 100, 500, 50, []),
        ("Acetonitrile", "75-05-8", "CH3CN", "Solvent", "HPLC", "mL", 300, 600, 4000, 300, ["MeCN"]),
        ("Chloroform", "67-66-3", "CHCl3", "Solvent", "ACS", "mL", 200, 400, 2000, 200, ["Trichloromethane"]),
        ("Dichloromethane", "75-09-2", "CH2Cl2", "Solvent", "ACS", "mL", 200, 400, 2000, 200, ["DCM", "Methylene chloride"]),
        ("Toluene", "108-88-3", "C7H8", "Solvent", "ACS", "mL", 300, 600, 3000, 300, ["Methylbenzene"]),
        ("Hexane", "110-54-3", "C6H14", "Solvent", "ACS", "mL", 300, 600, 3000, 300, []),
        ("Diethyl Ether", "60-29-7", "C4H10O", "Solvent", "ACS", "mL", 150, 300, 1500, 150, ["Ether"]),
        ("Ammonium Hydroxide", "1336-21-6", "NH4OH", "Base", "ACS", "mL", 150, 300, 1500, 150, ["Ammonia solution"]),
        ("Nitric Acid", "7697-37-2", "HNO3", "Acid", "ACS", "mL", 150, 300, 1500, 150, []),
        ("Phosphoric Acid", "7664-38-2", "H3PO4", "Acid", "ACS", "mL", 150, 300, 1500, 150, []),
        ("Ethyl Acetate", "141-78-6", "C4H8O2", "Solvent", "ACS", "mL", 300, 600, 3000, 300, []),
        ("Dimethyl Sulfoxide", "67-68-5", "C2H6OS", "Solvent", "ACS", "mL", 100, 200, 1000, 100, ["DMSO"]),
        ("Glacial Acetic Acid", "64-19-7", "CH3COOH", "Acid", "ACS", "mL", 150, 300, 1500, 150, []),
        ("Isopropanol", "67-63-0", "C3H8O", "Solvent", "ACS", "mL", 300, 600, 3000, 300, ["IPA", "2-Propanol"]),
        ("Formaldehyde Solution", "50-00-0", "CH2O", "Fixative", "37%", "mL", 100, 200, 1000, 100, ["Formalin"]),
    ]
    chemicals = {}
    supplier_cycle = list(suppliers.values())
    for i, (name, cas, formula, category, grade, unit, min_stock, reorder, target, safety, aliases) in enumerate(chem_defs):
        chem = Chemical(
            chemical_code="", name=name, cas_number=cas, formula=formula, category=category, grade=grade,
            manufacturer=supplier_cycle[i % len(supplier_cycle)].name, supplier_id=supplier_cycle[i % len(supplier_cycle)].id,
            unit=unit, min_stock=min_stock, reorder_level=reorder, target_stock=target, safety_stock=safety,
            physical_state="Liquid" if unit == "mL" else "Solid",
            storage_requirements="Flammable cabinet" if category == "Solvent" else "Corrosive cabinet" if category in ("Acid", "Base") else "General storage",
            is_demo=True,
        )
        db.add(chem)
        assign_code(db, chem, "chemical_code", "CHM-")
        for alias in aliases:
            db.add(ChemicalAlias(chemical_id=chem.id, alias=alias))
        chemicals[name] = chem
    db.flush()

    # --- Containers + opening stock ----------------------------------
    lab_codes = list(labs.keys())
    today = date.today()
    containers = []
    container_plans = []
    for i, (name, *_rest) in enumerate(chem_defs):
        chem = chemicals[name]
        lab_code = lab_codes[i % len(lab_codes)]
        size = chem.reorder_level * 5 if chem.unit != "g" else chem.reorder_level * 5
        container_plans.append((chem, lab_code, size, today - timedelta(days=200 - i * 3), None))
        # give the first 10 chemicals a second container in a different lab for variety
        if i < 10:
            lab_code2 = lab_codes[(i + 2) % len(lab_codes)]
            container_plans.append((chem, lab_code2, size * 0.5, today - timedelta(days=120 - i), None))

    for idx, (chem, lab_code, size, received, _) in enumerate(container_plans):
        expiry = None
        if idx % 7 == 0:
            expiry = today - timedelta(days=5)  # already expired
        elif idx % 5 == 0:
            expiry = today + timedelta(days=15)  # expiring soon
        else:
            expiry = today + timedelta(days=400 + idx)

        initial_qty = size
        container = Container(
            container_code="", chemical_id=chem.id, batch_lot=f"BATCH-{2024}{idx:03d}",
            container_size=size, unit=chem.unit, initial_quantity=initial_qty, expected_quantity=0.0,
            date_received=received, expiry_date=expiry, laboratory_id=labs[lab_code].id,
            location_id=lab_locations[lab_code][idx % 2].id, responsible_user_id=lab_manager.id,
            status=ContainerStatus.AVAILABLE.value, is_demo=True,
        )
        db.add(container)
        assign_code(db, container, "container_code", "CHEM-")
        receive_container(db, container=container, user=admin, notes="DEMO DATA - initial stock")
        containers.append(container)
    db.flush()

    # --- Historical usage across ~5 months, for trend charts --------
    users_cycle = [lab_manager, researcher]
    for month_offset in range(5, 0, -1):
        for c_idx, container in enumerate(containers[:18]):
            if (c_idx + month_offset) % 3 != 0:
                continue
            qty = round(container.container_size * 0.03 * ((c_idx % 4) + 1), 2)
            if qty <= 0 or qty > container.expected_quantity:
                continue
            record_transaction(
                db, container=container, transaction_type=TransactionType.USE, quantity_delta=-qty,
                user=users_cycle[c_idx % 2], purpose="DEMO DATA - routine experiment use",
                occurred_at=_dt(month_offset * 30 - (c_idx % 5)),
            )

    # Make one container clearly LOW_STOCK and one clearly EMPTY for dashboard realism
    if len(containers) > 3:
        low_container = containers[3]
        record_transaction(
            db, container=low_container, transaction_type=TransactionType.USE,
            quantity_delta=-(low_container.expected_quantity - low_container.container_size * 0.05),
            user=researcher, purpose="DEMO DATA - depleting for low-stock example", occurred_at=_dt(2),
        )
    if len(containers) > 6:
        empty_container = containers[6]
        record_transaction(
            db, container=empty_container, transaction_type=TransactionType.USE,
            quantity_delta=-empty_container.expected_quantity, user=researcher,
            purpose="DEMO DATA - final use", occurred_at=_dt(1),
        )

    # --- Physical verification: one clean, one with a discrepancy ----
    if len(containers) > 1:
        record_physical_count(db, container=containers[1], physical_quantity=containers[1].expected_quantity, user=lab_manager, notes="DEMO DATA - routine check, no variance")
    if len(containers) > 2:
        c = containers[2]
        short_qty = max(c.expected_quantity - c.container_size * 0.08, 0)
        record_physical_count(db, container=c, physical_quantity=short_qty, user=researcher, reason="Spillage", notes="DEMO DATA - minor spill during transfer to fume hood")

    # --- Transfers: one completed between labs ------------------------
    if len(containers) > 8:
        src = containers[8]
        other_lab_ids = [lab.id for lab in labs.values() if lab.id != src.laboratory_id]
        dest_lab_id = other_lab_ids[0]
        if src.expected_quantity > 0:
            transfer = create_transfer(db, container=src, quantity=round(src.expected_quantity * 0.4, 2), destination_laboratory_id=dest_lab_id, destination_location_id=None, sender=lab_manager, reason="DEMO DATA - shared project need")
            complete_transfer(db, transfer=transfer, receiver=researcher)

    # --- Purchase requests --------------------------------------------
    for i, chem_name in enumerate(["Methanol", "Chloroform", "Potassium Permanganate"]):
        chem = chemicals[chem_name]
        req = PurchaseRequest(
            request_code="", chemical_id=chem.id, laboratory_id=labs[lab_codes[i % len(lab_codes)]].id,
            quantity=chem.reorder_level * 2, unit=chem.unit, reason="DEMO DATA - approaching reorder level",
            is_system_suggested=True, status=["PENDING", "APPROVED", "ORDERED"][i % 3], requested_by_id=lab_manager.id,
        )
        db.add(req)
        assign_code(db, req, "request_code", "PR-")

    db.commit()
    print(f"Seeded {len(chemicals)} chemicals, {len(containers)} containers, {len(labs)} laboratories, 4 demo users (password: {DEMO_PASSWORD}).")


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        run(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
