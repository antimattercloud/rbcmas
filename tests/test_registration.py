from sqlalchemy import select

from app.models.user import User


def test_register_creates_inactive_researcher_pending_approval(app_client, db, base_fixtures):
    resp = app_client.post(
        "/register",
        data={
            "full_name": "New Person",
            "email": "new-person@example.com",
            "password": "pw12345678",
            "confirm_password": "pw12345678",
            "laboratory_id": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"

    user = db.scalar(select(User).where(User.email == "new-person@example.com"))
    assert user is not None
    assert user.role == "RESEARCHER"
    assert user.is_active is False


def test_pending_account_cannot_log_in_until_approved(app_client, db, base_fixtures):
    app_client.post(
        "/register",
        data={"full_name": "Pending Person", "email": "pending@example.com", "password": "pw12345678", "confirm_password": "pw12345678"},
    )
    resp = app_client.post("/login", data={"email": "pending@example.com", "password": "pw12345678"})
    assert resp.status_code == 401

    user = db.scalar(select(User).where(User.email == "pending@example.com"))
    user.is_active = True
    db.commit()

    resp = app_client.post("/login", data={"email": "pending@example.com", "password": "pw12345678"}, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard"


def test_register_rejects_mismatched_passwords(app_client, base_fixtures):
    resp = app_client.post(
        "/register",
        data={"full_name": "X", "email": "mismatch@example.com", "password": "pw12345678", "confirm_password": "different"},
    )
    assert resp.status_code == 400


def test_register_rejects_duplicate_email(app_client, base_fixtures):
    resp = app_client.post(
        "/register",
        data={
            "full_name": "Dup",
            "email": "test-admin@example.com",  # already exists from base_fixtures
            "password": "pw12345678",
            "confirm_password": "pw12345678",
        },
    )
    assert resp.status_code == 400
