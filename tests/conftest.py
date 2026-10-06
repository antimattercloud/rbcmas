import os
import sys
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent / "test_rbcmas.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["SECRET_KEY"] = "test-secret-key"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.security import hash_password  # noqa: E402


@pytest.fixture(autouse=True)
def _setup_database():
    """Fresh schema for every test - simpler and safer than sharing state
    or relying on transaction rollback across the app's own sessions."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def app_client():
    from app.main import app

    return TestClient(app)


@pytest.fixture
def base_fixtures(db):
    """A minimal, consistent set of rows every test can build on: one
    laboratory, one chemical, one container, and one user per role."""
    from datetime import date

    from app.models.chemical import Chemical
    from app.models.container import Container
    from app.models.laboratory import Laboratory
    from app.models.user import User
    from app.services.codes import assign_code
    from app.services.inventory_service import receive_container

    lab_a = Laboratory(code="LAB-A", name="Lab A")
    lab_b = Laboratory(code="LAB-B", name="Lab B")
    db.add_all([lab_a, lab_b])
    db.flush()

    admin = User(full_name="Test Admin", email="test-admin@example.com", password_hash=hash_password("pw12345678"), role="ADMIN")
    manager = User(full_name="Test Manager", email="test-manager@example.com", password_hash=hash_password("pw12345678"), role="LAB_MANAGER", laboratory_id=lab_a.id)
    researcher = User(full_name="Test Researcher", email="test-researcher@example.com", password_hash=hash_password("pw12345678"), role="RESEARCHER", laboratory_id=lab_a.id)
    auditor = User(full_name="Test Auditor", email="test-auditor@example.com", password_hash=hash_password("pw12345678"), role="AUDITOR")
    db.add_all([admin, manager, researcher, auditor])
    db.flush()

    chem = Chemical(chemical_code="", name="Test Methanol", unit="mL", min_stock=100, reorder_level=200, target_stock=1000, safety_stock=100)
    db.add(chem)
    assign_code(db, chem, "chemical_code", "CHM-")

    container = Container(
        container_code="", chemical_id=chem.id, container_size=1000, unit="mL",
        initial_quantity=0.0, expected_quantity=0.0, date_received=date.today(),
        laboratory_id=lab_a.id, responsible_user_id=manager.id, status="AVAILABLE",
    )
    db.add(container)
    assign_code(db, container, "container_code", "CHEM-")
    container.initial_quantity = 500.0
    receive_container(db, container=container, user=admin)
    db.commit()

    return {
        "lab_a": lab_a, "lab_b": lab_b,
        "admin": admin, "manager": manager, "researcher": researcher, "auditor": auditor,
        "chemical": chem, "container": container,
    }


def login(client: TestClient, email: str, password: str = "pw12345678"):
    resp = client.post("/login", data={"email": email, "password": password}, follow_redirects=False)
    assert resp.status_code == 302, resp.text
    return client
