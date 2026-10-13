from __future__ import annotations

import secrets

import pytest
from fastapi.testclient import TestClient

from ordivant_identity.config import Settings
from ordivant_identity.main import create_app


ORIGIN = "http://localhost:5173"
ADMIN_EMAIL = "directory-admin@example.com"
SYNTHETIC_PASSWORD = "Synthetic directory password 7!"


@pytest.fixture
def identity(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{(tmp_path / 'identity-directory.sqlite3').as_posix()}",
        mode="development",
        cookie_name="ordivant_directory_test",
        service_secret=secrets.token_urlsafe(48),
        auth_origins=(ORIGIN,),
        cookie_secure=False,
    )
    app = create_app(settings)
    with TestClient(app, base_url=ORIGIN) as client:
        yield client, app, settings


def browser_headers(csrf_token: str | None = None) -> dict[str, str]:
    headers = {"Origin": ORIGIN}
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token
    return headers


def setup_admin(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/setup",
        json={"name": "Directory Admin", "email": ADMIN_EMAIL, "password": SYNTHETIC_PASSWORD},
        headers=browser_headers(),
    )
    assert response.status_code == 201, response.text
    return response.json()


def invite_member(client: TestClient, app, admin: dict, *, name: str, email: str, permissions: dict) -> dict:
    invitation = client.post(
        "/api/auth/invitations",
        json={"name": name, "email": email, "role": "member", "permissions": permissions},
        headers=browser_headers(admin["csrf_token"]),
    )
    assert invitation.status_code == 201, invitation.text

    with TestClient(app, base_url=ORIGIN) as invitee:
        accepted = invitee.post(
            "/api/auth/accept-invitation",
            json={"invitation_code": invitation.json()["invitation_code"], "password": SYNTHETIC_PASSWORD},
            headers=browser_headers(),
        )
    assert accepted.status_code == 201, accepted.text
    return accepted.json()["user"]


def test_product_directory_requires_service_bearer_for_admin_and_member_cookies(identity):
    client, app, settings = identity
    admin = setup_admin(client)
    query = {"product": "work", "scope_id": "project-alpha"}

    admin_cookie_denied = client.get("/api/auth/directory", params=query)
    assert admin_cookie_denied.status_code == 401
    assert admin_cookie_denied.json()["detail"]["code"] == "service_unauthorized"

    invite_member(
        client,
        app,
        admin,
        name="Scoped Worker",
        email="directory-worker@example.com",
        permissions={"work": {"role": "worker", "scope_ids": ["project-alpha"]}},
    )
    # Registration occurs in a separate browser session; possession of a valid
    # ordinary Identity cookie still cannot call the service-only directory.
    member_cookie = TestClient(app, base_url=ORIGIN)
    try:
        login = member_cookie.post(
            "/api/auth/login",
            json={"email": "directory-worker@example.com", "password": SYNTHETIC_PASSWORD},
            headers=browser_headers(),
        )
        assert login.status_code == 200, login.text
        member_cookie_denied = member_cookie.get("/api/auth/directory", params=query)
        assert member_cookie_denied.status_code == 401
        assert member_cookie_denied.json()["detail"]["code"] == "service_unauthorized"
    finally:
        member_cookie.close()

    service_response = client.get(
        "/api/auth/directory",
        params=query,
        headers={"Authorization": f"Bearer {settings.service_secret}"},
    )
    assert service_response.status_code == 200, service_response.text
    assert "users" in service_response.json()


def test_directory_filters_active_product_scopes_and_omits_account_secrets(identity):
    client, app, settings = identity
    admin = setup_admin(client)
    project_alpha = "project-alpha"
    project_beta = "project-beta"
    users = {}
    for name, product, role, scope in (
        ("Work Scoped", "work", "worker", project_alpha),
        ("Work Other Scope", "work", "reviewer", project_beta),
        ("Knowledge Scoped", "knowledge", "writer", project_alpha),
        ("Code Scoped", "code", "reader", project_alpha),
        ("Inactive Work", "work", "manager", project_alpha),
    ):
        key = name.lower().replace(" ", "-")
        users[key] = invite_member(
            client,
            app,
            admin,
            name=name,
            email=f"{key}@example.com",
            permissions={product: {"role": role, "scope_ids": [scope]}},
        )

    inactive = client.patch(
        f"/api/auth/users/{users['inactive-work']['id']}",
        json={"active": False},
        headers=browser_headers(admin["csrf_token"]),
    )
    assert inactive.status_code == 200, inactive.text
    authorization = {"Authorization": f"Bearer {settings.service_secret}"}

    for product, expected_name in (
        ("work", "work-scoped"),
        ("knowledge", "knowledge-scoped"),
        ("code", "code-scoped"),
    ):
        response = client.get(
            "/api/auth/directory",
            params={"product": product, "scope_id": project_alpha},
            headers=authorization,
        )
        assert response.status_code == 200, response.text
        returned = response.json()["users"]
        returned_ids = {user["id"] for user in returned}
        assert returned_ids == {admin["user"]["id"], users[expected_name]["id"]}
        assert all(set(user) == {"id", "name", "role", "active", "permissions"} for user in returned)
        assert all(user["active"] is True for user in returned)
        assert "@example.com" not in response.text
        assert "password_hash" not in response.text
        assert "passwordhash" not in response.text

    work_beta = client.get(
        "/api/auth/directory",
        params={"product": "work", "scope_id": project_beta},
        headers=authorization,
    )
    assert work_beta.status_code == 200
    assert {user["id"] for user in work_beta.json()["users"]} == {
        admin["user"]["id"],
        users["work-other-scope"]["id"],
    }
