from tests.conftest import login


def test_login_with_wrong_password_fails(app_client, base_fixtures):
    resp = app_client.post("/login", data={"email": "test-admin@example.com", "password": "wrong"})
    assert resp.status_code == 401


def test_login_success_redirects_to_dashboard(app_client, base_fixtures):
    resp = app_client.post(
        "/login", data={"email": "test-admin@example.com", "password": "pw12345678"}, follow_redirects=False
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard"


def test_unauthenticated_request_redirects_to_login(app_client, base_fixtures):
    resp = app_client.get("/admin/users", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


def test_researcher_cannot_reach_admin_area(app_client, base_fixtures):
    login(app_client, "test-researcher@example.com")
    resp = app_client.get("/admin/users")
    assert resp.status_code == 403


def test_admin_can_reach_admin_area(app_client, base_fixtures):
    login(app_client, "test-admin@example.com")
    resp = app_client.get("/admin/users")
    assert resp.status_code == 200


def test_auditor_cannot_record_usage(app_client, base_fixtures):
    login(app_client, "test-auditor@example.com")
    container = base_fixtures["container"]
    resp = app_client.post("/usage/new", data={"container_id": container.id, "quantity_used": 10})
    assert resp.status_code == 403


def test_researcher_can_record_usage(app_client, base_fixtures):
    login(app_client, "test-researcher@example.com")
    container = base_fixtures["container"]
    resp = app_client.post(
        "/usage/new", data={"container_id": container.id, "quantity_used": 10}, follow_redirects=False
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == f"/containers/{container.id}"


def test_dashboard_loads_for_every_role(app_client, base_fixtures):
    for email in ["test-admin@example.com", "test-manager@example.com", "test-researcher@example.com", "test-auditor@example.com"]:
        client = login(app_client, email)
        resp = client.get("/dashboard")
        assert resp.status_code == 200, email
