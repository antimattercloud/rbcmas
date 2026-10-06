"""Manual backup/restore for the SQLite database (section 38).
For PostgreSQL deployments, use pg_dump/pg_restore instead - this script
only handles the default local SQLite file.

Usage:
    python scripts/backup.py backup
    python scripts/backup.py restore backups/rbcmas_2026-09-22_101500.db
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import database_url  # noqa: E402

BACKUP_DIR = Path(__file__).resolve().parent.parent / "backups"


def _db_path() -> Path:
    if not database_url.startswith("sqlite"):
        raise SystemExit("This script only backs up the local SQLite database. Use pg_dump/pg_restore for PostgreSQL.")
    return Path(database_url.split("///")[-1])


def backup():
    db_path = _db_path()
    if not db_path.exists():
        raise SystemExit(f"No database found at {db_path}.")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dest = BACKUP_DIR / f"rbcmas_{stamp}.db"
    shutil.copy2(db_path, dest)
    print(f"Backup created: {dest}")


def restore(backup_path: str):
    db_path = _db_path()
    src = Path(backup_path)
    if not src.exists():
        raise SystemExit(f"Backup file not found: {src}")
    if db_path.exists():
        safety_copy = db_path.with_suffix(".pre-restore.db")
        shutil.copy2(db_path, safety_copy)
        print(f"Existing database saved as {safety_copy} before restoring.")
    shutil.copy2(src, db_path)
    print(f"Database restored from {src}.")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("backup", "restore"):
        print(__doc__)
        raise SystemExit(1)
    if sys.argv[1] == "backup":
        backup()
    else:
        if len(sys.argv) < 3:
            raise SystemExit("Usage: python scripts/backup.py restore <path-to-backup.db>")
        restore(sys.argv[2])
