"""Removes all DEMO DATA (chemicals, containers, laboratories, locations,
demo users, and their ledger/transfer/audit history) and leaves the
database ready for real use.

Since this also deletes the demo admin/lab-manager/researcher/auditor
accounts, you MUST create a real admin account first - this script does
that for you in one step so you are never locked out.

Usage:
    python scripts/remove_demo_data.py --admin-name "Your Name" --admin-email you@yourlab.org --admin-password "a-strong-password"

Add --keep-users to remove only chemicals/containers/labs/locations and
leave all existing user accounts (including the demo ones) untouched.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models.audit import AuditLog, ImportAudit  # noqa: E402
from app.models.chemical import Chemical, ChemicalAlias  # noqa: E402
from app.models.common import Role  # noqa: E402
from app.models.container import Container  # noqa: E402
from app.models.laboratory import Laboratory  # noqa: E402
from app.models.location import Location  # noqa: E402
from app.models.procurement import PurchaseRequest  # noqa: E402
from app.models.transaction import InventoryTransaction  # noqa: E402
from app.models.transfer import InventoryAdjustment, PhysicalCount, TransferRecord  # noqa: E402
from app.models.user import User  # noqa: E402
from app.security import hash_password  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin-name", required=True)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    parser.add_argument("--keep-users", action="store_true", help="Leave all user accounts (incl. demo ones) untouched")
    args = parser.parse_args()

    if len(args.admin_password) < 8:
        raise SystemExit("Admin password must be at least 8 characters.")

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        email_norm = args.admin_email.strip().lower()
        admin = db.scalar(select(User).where(User.email == email_norm))
        if admin is None:
            admin = User(
                full_name=args.admin_name.strip(),
                email=email_norm,
                password_hash=hash_password(args.admin_password),
                role=Role.ADMIN.value,
                is_active=True,
                is_demo=False,
            )
            db.add(admin)
            db.flush()
            print(f"Created real admin account: {email_norm}")
        else:
            admin.is_active = True
            admin.is_demo = False
            print(f"Admin account already existed, confirmed active: {email_norm}")
        db.commit()

        demo_container_ids = [c.id for c in db.scalars(select(Container).where(Container.is_demo.is_(True)))]
        demo_chemical_ids = [c.id for c in db.scalars(select(Chemical).where(Chemical.is_demo.is_(True)))]
        demo_lab_ids = [lab.id for lab in db.scalars(select(Laboratory).where(Laboratory.is_demo.is_(True)))]
        demo_location_ids = [loc.id for loc in db.scalars(select(Location).where(Location.is_demo.is_(True)))]
        demo_user_ids = [u.id for u in db.scalars(select(User).where(User.is_demo.is_(True)))]

        # Safety net: never delete a demo chemical/laboratory that a REAL
        # (non-demo) container still points to - that would silently orphan
        # real data. Keep it instead and tell the user to re-point it by hand.
        real_containers = list(db.scalars(select(Container).where(Container.is_demo.is_(False))))
        chemical_ids_in_use = {c.chemical_id for c in real_containers}
        lab_ids_in_use = {c.laboratory_id for c in real_containers}
        protected_chemicals = [cid for cid in demo_chemical_ids if cid in chemical_ids_in_use]
        protected_labs = [lid for lid in demo_lab_ids if lid in lab_ids_in_use]
        if protected_chemicals:
            print(f"NOTE: keeping {len(protected_chemicals)} demo chemical(s) - a real container still references them.")
            demo_chemical_ids = [cid for cid in demo_chemical_ids if cid not in protected_chemicals]
        if protected_labs:
            print(f"NOTE: keeping {len(protected_labs)} demo laboratory(ies) - a real container still references them.")
            demo_lab_ids = [lid for lid in demo_lab_ids if lid not in protected_labs]

        if demo_container_ids:
            db.query(InventoryTransaction).filter(InventoryTransaction.container_id.in_(demo_container_ids)).delete(synchronize_session=False)
            db.query(PhysicalCount).filter(PhysicalCount.container_id.in_(demo_container_ids)).delete(synchronize_session=False)
            db.query(InventoryAdjustment).filter(InventoryAdjustment.container_id.in_(demo_container_ids)).delete(synchronize_session=False)
            db.query(TransferRecord).filter(
                TransferRecord.container_id.in_(demo_container_ids) | TransferRecord.destination_container_id.in_(demo_container_ids)
            ).delete(synchronize_session=False)
            db.query(AuditLog).filter(AuditLog.entity_type == "container", AuditLog.entity_id.in_(demo_container_ids)).delete(synchronize_session=False)

        if demo_chemical_ids:
            db.query(ChemicalAlias).filter(ChemicalAlias.chemical_id.in_(demo_chemical_ids)).delete(synchronize_session=False)
            db.query(PurchaseRequest).filter(PurchaseRequest.chemical_id.in_(demo_chemical_ids)).delete(synchronize_session=False)
            db.query(AuditLog).filter(AuditLog.entity_type == "chemical", AuditLog.entity_id.in_(demo_chemical_ids)).delete(synchronize_session=False)

        if demo_lab_ids:
            db.query(AuditLog).filter(AuditLog.entity_type == "laboratory", AuditLog.entity_id.in_(demo_lab_ids)).delete(synchronize_session=False)

        db.query(Container).filter(Container.is_demo.is_(True)).delete(synchronize_session=False)
        db.query(Chemical).filter(Chemical.is_demo.is_(True)).delete(synchronize_session=False)
        db.query(Location).filter(Location.is_demo.is_(True)).delete(synchronize_session=False)
        db.query(Laboratory).filter(Laboratory.is_demo.is_(True)).delete(synchronize_session=False)

        removed_users = 0
        if not args.keep_users:
            other_demo_user_ids = [uid for uid in demo_user_ids if uid != admin.id]
            if other_demo_user_ids:
                db.query(ImportAudit).filter(ImportAudit.user_id.in_(other_demo_user_ids)).delete(synchronize_session=False)
                db.query(AuditLog).filter(AuditLog.user_id.in_(other_demo_user_ids)).update({AuditLog.user_id: None}, synchronize_session=False)
                removed_users = db.query(User).filter(User.id.in_(other_demo_user_ids)).delete(synchronize_session=False)

        db.commit()

        print(f"Removed {len(demo_container_ids)} demo containers, {len(demo_chemical_ids)} demo chemicals, "
              f"{len(demo_lab_ids)} demo laboratories, {len(demo_location_ids)} demo locations, {removed_users} demo user accounts.")
        print(f"\nYou can now sign in as: {email_norm}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
