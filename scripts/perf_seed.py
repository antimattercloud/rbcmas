"""Bulk-generates synthetic containers directly (bypassing the ledger helpers,
which are correctness-first, not bulk-insert-optimized) so the dashboard,
search, and list pages can be sanity-checked at realistic scale.

Usage:
    python scripts/perf_seed.py --containers 5000
"""
import argparse
import random
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models.chemical import Chemical  # noqa: E402
from app.models.common import ContainerStatus  # noqa: E402
from app.models.container import Container  # noqa: E402
from app.models.laboratory import Laboratory  # noqa: E402
from app.models.user import User  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--containers", type=int, default=5000)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        chemicals = list(db.query(Chemical).all())
        labs = list(db.query(Laboratory).all())
        user = db.query(User).first()
        if not chemicals or not labs or not user:
            print("Run `python -m app.seed` first to create base demo data (chemicals/labs/users).")
            return

        existing_perf = db.query(Container).filter(Container.container_code.like("PERF-%")).count()
        offset = existing_perf

        start = time.time()
        today = date.today()
        created = 0
        for batch_start in range(0, args.containers, args.batch_size):
            batch = []
            for i in range(offset + batch_start, offset + min(batch_start + args.batch_size, args.containers)):
                chem = random.choice(chemicals)
                lab = random.choice(labs)
                size = round(random.uniform(50, 5000), 2)
                qty = round(size * random.uniform(0.05, 1.0), 2)
                expiry = today + timedelta(days=random.randint(-30, 900))
                batch.append(
                    Container(
                        container_code=f"PERF-{i:07d}",
                        chemical_id=chem.id,
                        batch_lot=f"PERFBATCH-{i}",
                        container_size=size,
                        unit=chem.unit,
                        initial_quantity=qty,
                        expected_quantity=qty,
                        date_received=today - timedelta(days=random.randint(1, 800)),
                        expiry_date=expiry,
                        laboratory_id=lab.id,
                        responsible_user_id=user.id,
                        status=ContainerStatus.AVAILABLE.value,
                    )
                )
            db.bulk_save_objects(batch)
            db.commit()
            created += len(batch)
            print(f"  {created}/{args.containers} containers inserted...")

        elapsed = time.time() - start
        print(f"Done: inserted {created} containers in {elapsed:.1f}s.")
        print("Now load /dashboard, /containers, and /search in the browser and check response times.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
