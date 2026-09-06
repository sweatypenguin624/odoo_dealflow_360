from datetime import datetime, timedelta, timezone

from app.models import EmailMessage, PasswordResetToken, RefreshToken, User, AuditLog
from tests.conftest import PASSWORD, TestingSessionLocal, USER_SPECS, login_as


def test_login_returns_session_and_sets_cookies(client):
    response = client.post("/auth/login", json={"email": "rep@test.local", "password": PASSWORD})
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["email"] == "rep@test.local"
    assert data["user"]["role"] == "sales_rep"
    assert "quote:create" in data["permissions"]
    assert "user:manage" not in data["permissions"]
    assert "hashed_password" not in data["user"]
    assert "df_access" in response.cookies
    assert "df_csrf" in response.cookies


def test_login_wrong_password_is_401_and_audited(client, db):
    response = client.post("/auth/login", json={"email": "rep@test.local", "password": "nope-nope-1"})
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"
    assert db.query(AuditLog).filter(AuditLog.action == "login_failed").count() == 1


def test_login_unknown_email_same_message(client):
    response = client.post("/auth/login", json={"email": "ghost@test.local", "password": PASSWORD})
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password."


def test_me_requires_auth_and_reports_permissions(as_manager):
    from fastapi.testclient import TestClient
    from app.main import app

    assert TestClient(app).get("/auth/me").status_code == 401
    me = as_manager.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["role"] == "sales_manager"
    assert "approval:manager" in me.json()["permissions"]


def test_cookie_session_requires_csrf_header_for_mutations(client):
    client.post("/auth/login", json={"email": "admin@test.local", "password": PASSWORD})
    # GET with cookie only is fine
    assert client.get("/auth/me").status_code == 200
    # mutating request with cookie but no CSRF header is rejected
    response = client.post("/users", json={})
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"
    csrf = client.cookies.get("df_csrf")
    ok = client.post(
        "/users",
        json={"email": "new@test.local", "full_name": "New User", "password": PASSWORD, "role": "sales_rep"},
        headers={"X-CSRF-Token": csrf},
    )
    assert ok.status_code == 201, ok.text


def test_refresh_rotates_token_and_logout_revokes(client):
    login = client.post("/auth/login", json={"email": "rep@test.local", "password": PASSWORD})
    old_refresh = login.cookies.get("df_refresh")
    refreshed = client.post("/auth/refresh")
    assert refreshed.status_code == 200
    new_refresh = refreshed.cookies.get("df_refresh")
    assert new_refresh and new_refresh != old_refresh
    # the old refresh token is now revoked
    client.cookies.set("df_refresh", old_refresh)
    assert client.post("/auth/refresh").status_code == 401
    client.cookies.set("df_refresh", new_refresh)
    assert client.post("/auth/logout").status_code == 200
    assert client.post("/auth/refresh").status_code == 401


def test_deactivated_user_cannot_use_existing_token(client, as_admin, db):
    rep = login_as(client, "rep")
    user = db.query(User).filter(User.email == "rep@test.local").one()
    res = as_admin.patch(f"/users/{user.id}", json={"is_active": False})
    assert res.status_code == 200
    assert rep.get("/auth/me").status_code == 401


def test_account_locks_after_repeated_failures(client, db):
    from app.config import settings

    for _ in range(settings.max_failed_logins_before_lock):
        client.post("/auth/login", json={"email": "rep2@test.local", "password": "wrong-password-1"})
    locked = client.post("/auth/login", json={"email": "rep2@test.local", "password": PASSWORD})
    assert locked.status_code == 401
    assert locked.json()["code"] == "account_locked"


def test_login_rate_limit(client):
    from app.config import settings

    for _ in range(settings.login_rate_limit_attempts):
        client.post("/auth/login", json={"email": "limit@test.local", "password": "x"})
    response = client.post("/auth/login", json={"email": "limit@test.local", "password": "x"})
    assert response.status_code == 429


def test_password_reset_flow_sends_email_and_updates_password(client, db):
    response = client.post("/auth/forgot-password", json={"email": "finance@test.local"})
    assert response.status_code == 200
    email = db.query(EmailMessage).filter(EmailMessage.template == "password_reset").one()
    assert "reset-password?token=" in email.body_text
    raw_token = email.body_text.split("token=")[1].split()[0]

    weak = client.post("/auth/reset-password", json={"token": raw_token, "new_password": "short"})
    assert weak.status_code == 422
    assert weak.json()["code"] == "weak_password"

    ok = client.post("/auth/reset-password", json={"token": raw_token, "new_password": "Brand-New-Pass-99"})
    assert ok.status_code == 200
    assert client.post("/auth/login", json={"email": "finance@test.local", "password": PASSWORD}).status_code == 401
    assert client.post("/auth/login", json={"email": "finance@test.local", "password": "Brand-New-Pass-99"}).status_code == 200
    # token is single-use
    again = client.post("/auth/reset-password", json={"token": raw_token, "new_password": "Another-Pass-99"})
    assert again.status_code == 422


def test_forgot_password_unknown_email_does_not_leak(client, db):
    response = client.post("/auth/forgot-password", json={"email": "nobody@test.local"})
    assert response.status_code == 200
    assert db.query(EmailMessage).count() == 0


def test_change_password_invalidates_sessions(client):
    rep = login_as(client, "rep")
    res = rep.post("/auth/change-password", json={"current_password": PASSWORD, "new_password": "Changed-Pass-2026"})
    assert res.status_code == 200
    assert rep.get("/auth/me").status_code == 401
    assert client.post("/auth/login", json={"email": "rep@test.local", "password": "Changed-Pass-2026"}).status_code == 200


# ---- RBAC ----


def test_customer_cannot_access_internal_endpoints(as_customer):
    assert as_customer.get("/users").status_code == 403
    assert as_customer.get("/settings").status_code == 403


def test_rep_cannot_manage_users_or_settings(as_rep):
    res = as_rep.get("/users")
    assert res.status_code == 403
    assert res.json()["code"] == "forbidden"
    assert as_rep.put("/settings/stall_threshold_days", json={"value": 3}).status_code == 403


def test_admin_user_management_crud_and_pagination(as_admin):
    for i in range(3):
        res = as_admin.post(
            "/users",
            json={"email": f"rep{i}@corp.local", "full_name": f"Rep {i}", "password": PASSWORD, "role": "sales_rep", "team": "North"},
        )
        assert res.status_code == 201, res.text
    dup = as_admin.post("/users", json={"email": "rep0@corp.local", "full_name": "Dup", "password": PASSWORD, "role": "sales_rep"})
    assert dup.status_code == 409

    page = as_admin.get("/users", params={"page": 1, "page_size": 2, "q": "corp.local"})
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 3 and body["page_size"] == 2 and body["total_pages"] == 2 and len(body["items"]) == 2

    too_big = as_admin.get("/users", params={"page_size": 1000})
    assert too_big.status_code == 422

    user_id = body["items"][0]["id"]
    updated = as_admin.patch(f"/users/{user_id}", json={"role": "sales_manager", "team": "South"})
    assert updated.status_code == 200
    assert updated.json()["role"] == "sales_manager"


def test_admin_cannot_deactivate_self(as_admin):
    res = as_admin.patch(f"/users/{as_admin.user_id}", json={"is_active": False})
    assert res.status_code == 422


def test_settings_roundtrip(as_admin):
    listing = as_admin.get("/settings")
    assert listing.status_code == 200
    keys = {s["key"] for s in listing.json()}
    assert "stall_threshold_days" in keys
    res = as_admin.put("/settings/stall_threshold_days", json={"value": 3})
    assert res.status_code == 200 and res.json()["value"] == 3
    bad = as_admin.put("/settings/stall_threshold_days", json={"value": "many"})
    assert bad.status_code == 422


def test_health_and_ready(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/ready").json()["status"] == "ready"
