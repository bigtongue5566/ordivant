from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from ordivant_identity.config import Settings
from ordivant_identity.main import create_app
from ordivant_identity.models import AuthSession, AuthThrottle, Invitation, RecoveryCode, User
from ordivant_identity.security import session_hash


ORIGIN = "http://localhost:5173"
EMAIL = "admin@example.com"
PASSWORD = "Initial synthetic password 7!"


@pytest.fixture
def identity(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{(tmp_path / 'identity.sqlite3').as_posix()}",
        mode="development",
        cookie_name="ordivant_test_identity",
        service_secret=secrets.token_urlsafe(48),
        auth_origins=(ORIGIN,),
        cookie_secure=False,
    )
    app = create_app(settings)
    with TestClient(app, base_url=ORIGIN) as client:
        yield client, app, settings


def origin_headers(csrf: str | None = None) -> dict[str, str]:
    headers = {"Origin": ORIGIN}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return headers


def switch_cookie(client: TestClient, name: str, handle: str) -> None:
    client.cookies.clear()
    client.cookies.set(name, handle, domain="localhost.local", path="/")


def setup_admin(client: TestClient, *, email: str = EMAIL, password: str = PASSWORD):
    response = client.post(
        "/api/auth/setup",
        json={"name": "First Admin", "email": email, "password": password},
        headers=origin_headers(),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_setup_race_has_one_winner_and_only_hashes_are_persisted(identity):
    client, app, settings = identity
    bodies = [
        {"name": "First Admin", "email": "first@example.com", "password": PASSWORD},
        {"name": "Other Admin", "email": "other@example.com", "password": "Other synthetic password 1!"},
    ]

    async def submit_setup(body: dict) -> int:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as separate_client:
            response = await separate_client.post("/api/auth/setup", json=body, headers=origin_headers())
            return response.status_code

    async def run_race() -> list[int]:
        return await asyncio.gather(*(submit_setup(body) for body in bodies))

    statuses = asyncio.run(run_race())
    assert sorted(statuses) == [201, 409]
    with app.state.session_factory() as db:
        user = db.scalar(select(User))
        users = db.scalars(select(User)).all()
        sessions = db.scalars(select(AuthSession)).all()
        recovery = db.scalars(select(RecoveryCode)).all()
        stored = " ".join(
            [user.password_hash, *(item.token_hash for item in sessions), *(item.code_hash for item in recovery)]
        )
        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in stored
        assert len(users) == 1
        assert len(sessions) == 1
        assert len(recovery) == 10


def test_origin_csrf_cookie_and_validation_errors(identity):
    client, app, _ = identity
    assert client.get("/api/auth/status").json() == {
        "setup_required": True,
        "sso": {
            "enabled": False,
            "display_name": "企業帳號",
            "login_policy": "password_and_sso",
            "configured": False,
            "public_origin": ORIGIN,
        },
    }
    denied = client.post(
        "/api/auth/setup",
        json={"name": "First Admin", "email": EMAIL, "password": PASSWORD},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "origin_not_allowed"
    assert denied.headers["cache-control"] == "no-store"

    invalid = client.post(
        "/api/auth/setup",
        json={"email": EMAIL, "password": PASSWORD},
        headers=origin_headers(),
    )
    assert invalid.status_code == 422
    assert PASSWORD not in invalid.text

    session = setup_admin(client)
    assert client.get("/api/auth/status").json()["setup_required"] is False
    set_cookie = client.cookies.get("ordivant_test_identity")
    assert set_cookie
    assert set_cookie not in str(session)
    cookie_header = client.cookies.jar
    cookie = next(item for item in cookie_header if item.name == "ordivant_test_identity")
    assert cookie.has_nonstandard_attr("HttpOnly")
    assert cookie.path == "/"
    assert cookie.get_nonstandard_attr("SameSite") == "lax"
    assert not cookie.secure
    raw_handle = client.cookies.get("ordivant_test_identity")
    with app.state.session_factory() as db:
        stored_session = db.scalar(select(AuthSession))
        recovery_rows = db.scalars(select(RecoveryCode)).all()
        assert raw_handle not in stored_session.token_hash
        assert all(
            code not in row.code_hash for row in recovery_rows for code in session["recovery_codes"]
        )

    rejected = client.post("/api/auth/logout", json={}, headers=origin_headers("incorrect"))
    assert rejected.status_code == 403
    assert rejected.json()["detail"]["code"] == "csrf_invalid"

    health = client.get("/api/health")
    assert health.json() == {"status": "ok", "database": "sqlite", "mode": "development"}


def test_login_throttle_survives_service_restart(identity):
    client, app, settings = identity
    email = "unknown@example.com"
    for expected in [401, 401, 401, 401, 429]:
        response = client.post(
            "/api/auth/login",
            json={"email": email, "password": PASSWORD},
            headers=origin_headers(),
        )
        assert response.status_code == expected
        assert response.json()["detail"]["message"] == "Unable to authenticate with those credentials"
    with app.state.session_factory() as db:
        assert db.scalar(select(AuthThrottle.scope_hash)) is not None

    with TestClient(create_app(settings), base_url=ORIGIN) as restarted:
        response = restarted.post(
            "/api/auth/login",
            json={"email": email, "password": PASSWORD},
            headers=origin_headers(),
        )
        assert response.status_code == 429


def test_sessions_expire_and_introspection_requires_internal_secret(identity):
    client, app, settings = identity
    session = setup_admin(client)
    raw_handle = client.cookies.get(settings.cookie_name)
    assert raw_handle
    current = client.get("/api/auth/me")
    assert current.status_code == 200
    assert current.json()["user"] == session["user"]
    assert "recovery_codes" not in current.json()

    public = client.post("/api/auth/introspect", json={"session_token": raw_handle})
    assert public.status_code == 401
    valid = client.post(
        "/api/auth/introspect",
        json={"session_token": raw_handle},
        headers={"Authorization": f"Bearer {settings.service_secret}"},
    )
    assert valid.status_code == 200
    assert valid.json()["csrf_token"] == session["csrf_token"]
    assert "session_token" not in valid.json()

    with app.state.session_factory() as db:
        auth_session = db.scalar(select(AuthSession))
        auth_session.idle_expires_at = auth_session.created_at.replace(year=2000)
        db.commit()
    expired = client.get("/api/auth/me")
    assert expired.status_code == 401
    assert expired.json()["detail"]["code"] == "session_expired"
    assert client.post(
        "/api/auth/introspect",
        json={"session_token": raw_handle},
        headers={"Authorization": f"Bearer {settings.service_secret}"},
    ).status_code == 401

    fresh = client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers=origin_headers(),
    )
    assert fresh.status_code == 200
    absolute_handle = client.cookies.get(settings.cookie_name)
    with app.state.session_factory() as db:
        auth_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == session_hash(absolute_handle)))
        auth_session.absolute_expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        auth_session.idle_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_password_change_recovery_codes_and_session_revocation(identity):
    client, _, settings = identity
    initial = setup_admin(client)
    first_handle = client.cookies.get(settings.cookie_name)

    login = client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers=origin_headers(),
    )
    assert login.status_code == 200
    assert "recovery_codes" not in login.json()
    second_handle = client.cookies.get(settings.cookie_name)
    assert first_handle != second_handle
    changed_password = "Updated synthetic password 8!"
    changed = client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": changed_password},
        headers=origin_headers(login.json()["csrf_token"]),
    )
    assert changed.status_code == 200
    third_handle = client.cookies.get(settings.cookie_name)
    assert third_handle not in {first_handle, second_handle}
    assert changed.json()["recovery_codes"]
    assert client.post(
        "/api/auth/introspect",
        json={"session_token": second_handle},
        headers={"Authorization": f"Bearer {settings.service_secret}"},
    ).status_code == 401
    assert initial["recovery_codes"][0] not in str(changed.json()["recovery_codes"])

    recovery_code = changed.json()["recovery_codes"][0]
    final_password = "Recovered synthetic password 9!"
    recovery = client.post(
        "/api/auth/recover",
        json={"email": EMAIL, "recovery_code": recovery_code, "new_password": final_password},
        headers=origin_headers(),
    )
    assert recovery.status_code == 200
    assert recovery.json()["recovery_codes"]

    replay = client.post(
        "/api/auth/recover",
        json={"email": EMAIL, "recovery_code": recovery_code, "new_password": final_password},
        headers=origin_headers(),
    )
    assert replay.status_code == 401
    for password in [PASSWORD, changed_password]:
        denied = client.post(
            "/api/auth/login", json={"email": EMAIL, "password": password}, headers=origin_headers()
        )
        assert denied.status_code == 401
    accepted = client.post(
        "/api/auth/login", json={"email": EMAIL, "password": final_password}, headers=origin_headers()
    )
    assert accepted.status_code == 200
    current_handle = client.cookies.get(settings.cookie_name)
    logged_out = client.post(
        "/api/auth/logout",
        json={},
        headers=origin_headers(accepted.json()["csrf_token"]),
    )
    assert logged_out.status_code == 200
    assert client.post(
        "/api/auth/introspect",
        json={"session_token": current_handle},
        headers={"Authorization": f"Bearer {settings.service_secret}"},
    ).status_code == 401


def test_invitations_permissions_consumption_and_last_admin_protection(identity):
    client, app, settings = identity
    first = setup_admin(client)
    first_handle = client.cookies.get(settings.cookie_name)
    first_id = first["user"]["id"]

    self_disable = client.patch(
        f"/api/auth/users/{first_id}",
        json={"active": False},
        headers=origin_headers(first["csrf_token"]),
    )
    assert self_disable.status_code == 409
    assert self_disable.json()["detail"]["code"] == "last_admin"

    first_admin_invite = client.post(
        "/api/auth/invitations",
        json={"email": "second@example.com", "name": "Second Admin", "role": "admin"},
        headers=origin_headers(first["csrf_token"]),
    )
    member_invite = client.post(
        "/api/auth/invitations",
        json={
            "email": "member@example.com",
            "name": "Scoped Member",
            "role": "member",
            "permissions": {"code": {"role": "writer", "scope_ids": ["repo-1"]}},
        },
        headers=origin_headers(first["csrf_token"]),
    )
    assert first_admin_invite.status_code == member_invite.status_code == 201
    first_code = first_admin_invite.json()["invitation_code"]
    member_code = member_invite.json()["invitation_code"]
    with app.state.session_factory() as db:
        stored_invitation = db.scalar(select(Invitation).where(Invitation.normalized_email == "member@example.com"))
        assert stored_invitation.code_hash != member_code
        assert member_code not in stored_invitation.code_hash

    accepted_admin = client.post(
        "/api/auth/accept-invitation",
        json={"invitation_code": first_code, "password": "Second synthetic password 4!"},
        headers=origin_headers(),
    )
    assert accepted_admin.status_code == 201
    second = accepted_admin.json()
    second_handle = client.cookies.get(settings.cookie_name)
    second_id = second["user"]["id"]
    assert client.post(
        "/api/auth/accept-invitation",
        json={"invitation_code": first_code, "password": "Another synthetic password 5!"},
        headers=origin_headers(),
    ).status_code == 401
    switch_cookie(client, settings.cookie_name, first_handle)
    with_another_admin = client.patch(
        f"/api/auth/users/{first_id}",
        json={"active": False},
        headers=origin_headers(first["csrf_token"]),
    )
    assert with_another_admin.status_code == 409
    assert with_another_admin.json()["detail"]["code"] == "self_lockout"
    switch_cookie(client, settings.cookie_name, second_handle)

    third_invite = client.post(
        "/api/auth/invitations",
        json={"email": "third@example.com", "name": "Third Admin", "role": "admin"},
        headers=origin_headers(second["csrf_token"]),
    )
    third_accept = client.post(
        "/api/auth/accept-invitation",
        json={"invitation_code": third_invite.json()["invitation_code"], "password": "Third synthetic password 2!"},
        headers=origin_headers(),
    )
    assert third_accept.status_code == 201
    third = third_accept.json()
    third_id = third["user"]["id"]

    accepted_member = client.post(
        "/api/auth/accept-invitation",
        json={"invitation_code": member_code, "password": "Member synthetic password 6!"},
        headers=origin_headers(),
    )
    assert accepted_member.status_code == 201
    assert accepted_member.json()["user"]["permissions"]["code"] == {
        "role": "writer",
        "scope_ids": ["repo-1"],
    }
    assert set(accepted_member.json()["user"]["permissions"]) == {"code"}
    member_handle = client.cookies.get(settings.cookie_name)
    member_denied = client.get("/api/auth/users")
    assert member_denied.status_code == 403

    switch_cookie(client, settings.cookie_name, second_handle)
    updated_member = client.patch(
        f"/api/auth/users/{accepted_member.json()['user']['id']}",
        json={"permissions": {"code": {"role": "reader", "scope_ids": ["repo-1"]}}},
        headers=origin_headers(second["csrf_token"]),
    )
    assert updated_member.status_code == 200
    assert updated_member.json()["permissions"]["code"]["role"] == "reader"
    assert client.post(
        "/api/auth/introspect",
        json={"session_token": member_handle},
        headers={"Authorization": f"Bearer {settings.service_secret}"},
    ).status_code == 401

    # An administrator may disable another account but cannot disable their own.
    switch_cookie(client, settings.cookie_name, second_handle)
    disabled_first = client.patch(
        f"/api/auth/users/{first_id}",
        json={"active": False},
        headers=origin_headers(second["csrf_token"]),
    )
    assert disabled_first.status_code == 200
    assert disabled_first.json()["active"] is False
    disabled_login = client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers=origin_headers(),
    )
    assert disabled_login.status_code == 401
    assert disabled_login.json()["detail"]["message"] == "Unable to authenticate with those credentials"

    disabled_third = client.patch(
        f"/api/auth/users/{third_id}",
        json={"active": False},
        headers=origin_headers(second["csrf_token"]),
    )
    assert disabled_third.status_code == 200
    sole_admin = client.patch(
        f"/api/auth/users/{second_id}",
        json={"active": False},
        headers=origin_headers(second["csrf_token"]),
    )
    assert sole_admin.status_code == 409
    assert sole_admin.json()["detail"]["code"] == "last_admin"

    unauthorized_users = client.get("/api/auth/users")
    assert unauthorized_users.status_code == 200
    assert sum(1 for row in unauthorized_users.json()["users"] if row["role"] == "admin" and row["active"]) == 1
    member = next(row for row in unauthorized_users.json()["users"] if row["email"] == "member@example.com")
    assert member["permissions"]["code"]["scope_ids"] == ["repo-1"]


def test_invitation_acceptance_race_consumes_code_once(identity):
    client, app, _ = identity
    admin = setup_admin(client)
    invitation = client.post(
        "/api/auth/invitations",
        json={"email": "race@example.com", "name": "Race Member", "role": "member"},
        headers=origin_headers(admin["csrf_token"]),
    )
    code = invitation.json()["invitation_code"]
    body = {"invitation_code": code, "password": "Race synthetic password 8!"}

    async def accept() -> int:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as separate_client:
            response = await separate_client.post("/api/auth/accept-invitation", json=body, headers=origin_headers())
            return response.status_code

    async def run_race() -> list[int]:
        return await asyncio.gather(accept(), accept())

    statuses = asyncio.run(run_race())
    assert sorted(statuses) == [201, 401]
    with app.state.session_factory() as db:
        assert len(db.scalars(select(User).where(User.normalized_email == "race@example.com")).all()) == 1


def test_expired_invitation_cannot_be_accepted(identity):
    client, app, _ = identity
    admin = setup_admin(client)
    invite = client.post(
        "/api/auth/invitations",
        json={"email": "expired@example.com", "name": "Expired Invite", "role": "member"},
        headers=origin_headers(admin["csrf_token"]),
    )
    invitation_code = invite.json()["invitation_code"]
    with app.state.session_factory() as db:
        row = db.scalar(select(Invitation).where(Invitation.normalized_email == "expired@example.com"))
        row.expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        db.commit()
    accepted = client.post(
        "/api/auth/accept-invitation",
        json={"invitation_code": invitation_code, "password": "Expired synthetic password 3!"},
        headers=origin_headers(),
    )
    assert accepted.status_code == 401
    assert accepted.json()["detail"]["code"] == "invalid_invitation"


def test_logout_all_revokes_every_session_and_own_session_scope(identity):
    client, _, settings = identity
    setup = setup_admin(client)
    first_handle = client.cookies.get(settings.cookie_name)
    login = client.post(
        "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=origin_headers()
    )
    second_handle = client.cookies.get(settings.cookie_name)
    session_list = client.get("/api/auth/sessions")
    assert session_list.status_code == 200
    assert len(session_list.json()["sessions"]) == 2
    assert sum(1 for row in session_list.json()["sessions"] if row["current"]) == 1

    earlier = next(row for row in session_list.json()["sessions"] if not row["current"])
    revoked = client.delete(
        f"/api/auth/sessions/{earlier['id']}",
        headers=origin_headers(login.json()["csrf_token"]),
    )
    assert revoked.status_code == 200
    assert client.post(
        "/api/auth/introspect",
        json={"session_token": first_handle},
        headers={"Authorization": f"Bearer {settings.service_secret}"},
    ).status_code == 401

    invitation = client.post(
        "/api/auth/invitations",
        json={"email": "session-owner@example.com", "name": "Other User", "role": "member"},
        headers=origin_headers(login.json()["csrf_token"]),
    )
    member = client.post(
        "/api/auth/accept-invitation",
        json={"invitation_code": invitation.json()["invitation_code"], "password": "Other synthetic password 3!"},
        headers=origin_headers(),
    )
    assert member.status_code == 201
    member_handle = client.cookies.get(settings.cookie_name)
    member_introspection = client.post(
        "/api/auth/introspect",
        json={"session_token": member_handle},
        headers={"Authorization": f"Bearer {settings.service_secret}"},
    )
    member_session_id = member_introspection.json()["session_id"]
    switch_cookie(client, settings.cookie_name, second_handle)
    foreign_revoke = client.delete(
        f"/api/auth/sessions/{member_session_id}",
        headers=origin_headers(login.json()["csrf_token"]),
    )
    assert foreign_revoke.status_code == 404

    logout = client.post(
        "/api/auth/logout-all", json={}, headers=origin_headers(login.json()["csrf_token"])
    )
    assert logout.status_code == 200
    assert not client.cookies.get(settings.cookie_name)
    for raw in [first_handle, second_handle]:
        response = client.post(
            "/api/auth/introspect",
            json={"session_token": raw},
            headers={"Authorization": f"Bearer {settings.service_secret}"},
        )
        assert response.status_code == 401
    assert setup["csrf_token"] != login.json()["csrf_token"]


def test_production_configuration_requires_postgres_and_https(tmp_path, monkeypatch):
    from ordivant_identity.config import get_settings

    secret_path = tmp_path / "service-token"
    secret_path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    monkeypatch.setenv("ORDIVANT_MODE", "production")
    monkeypatch.setenv("ORDIVANT_AUTH_COOKIE_NAME", "ordivant_prod_identity")
    monkeypatch.setenv("ORDIVANT_AUTH_COOKIE_SECURE", "true")
    monkeypatch.setenv("ORDIVANT_AUTH_ORIGINS", "https://suite.example.com")
    monkeypatch.setenv("ORDIVANT_IDENTITY_SERVICE_TOKEN_FILE", str(secret_path))
    monkeypatch.setenv("ORDIVANT_IDENTITY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ORDIVANT_IDENTITY_DATABASE_URL", f"sqlite:///{(tmp_path / 'identity.sqlite3').as_posix()}")
    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        get_settings()

    monkeypatch.setenv("ORDIVANT_IDENTITY_DATABASE_URL", "postgresql+psycopg://identity@localhost/identity")
    configured = get_settings()
    assert configured.cookie_secure is True
    assert configured.auth_origins == ("https://suite.example.com",)

    monkeypatch.setenv("ORDIVANT_AUTH_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="exact trusted browser origins"):
        get_settings()

    monkeypatch.setenv("ORDIVANT_AUTH_ORIGINS", "http://127.0.0.1:8088")
    monkeypatch.setenv("ORDIVANT_AUTH_COOKIE_SECURE", "false")
    local = get_settings()
    assert local.mode == "production"
    assert local.cookie_secure is False
    assert local.auth_origins == ("http://127.0.0.1:8088",)


def test_loopback_http_production_mode_setup_and_login(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{(tmp_path / 'local-production.sqlite3').as_posix()}",
        mode="production",
        cookie_name="ordivant_local_prod",
        service_secret=secrets.token_urlsafe(48),
        auth_origins=("http://127.0.0.1:8088",),
        cookie_secure=False,
    )
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8088") as client:
        created = client.post(
            "/api/auth/setup",
            json={"name": "Synthetic Local Admin", "email": "local@example.com", "password": PASSWORD},
            headers={"Origin": "http://127.0.0.1:8088"},
        )
        assert created.status_code == 201
        cookie = next(item for item in client.cookies.jar if item.name == settings.cookie_name)
        assert cookie.has_nonstandard_attr("HttpOnly")
        assert not cookie.secure
        assert client.post(
            "/api/auth/logout",
            json={},
            headers={"Origin": "http://127.0.0.1:8088", "X-CSRF-Token": created.json()["csrf_token"]},
        ).status_code == 200
        logged_in = client.post(
            "/api/auth/login",
            json={"email": "local@example.com", "password": PASSWORD},
            headers={"Origin": "http://127.0.0.1:8088"},
        )
        assert logged_in.status_code == 200
        assert logged_in.json()["user"]["role"] == "admin"


def test_permission_snapshot_prevents_stale_project_grants(identity):
    client, app, settings = identity
    admin = setup_admin(client)
    admin_handle = client.cookies.get(settings.cookie_name)
    invite = client.post('/api/auth/invitations', json={
        'email': 'scoped-person@example.com', 'name': 'Scoped Person', 'role': 'member',
        'permissions': {'work': {'role': 'worker', 'scope_ids': ['project-a']}, 'code': {'role': 'reader', 'scope_ids': ['code-a']}},
    }, headers=origin_headers(admin['csrf_token']))
    assert invite.status_code == 201
    accepted = client.post('/api/auth/accept-invitation', json={'invitation_code': invite.json()['invitation_code'], 'password': 'Synthetic project test password 9!'}, headers=origin_headers())
    assert accepted.status_code == 201
    member_handle = client.cookies.get(settings.cookie_name)
    user = accepted.json()['user']
    switch_cookie(client, settings.cookie_name, admin_handle)
    route = '/api/auth/users/'+user['id']
    before = user['permissions']
    changed = {**before, 'knowledge': {'role': 'reader', 'scope_ids': ['space-a']}}
    first = client.patch(route, json={'permissions': changed, 'expected_permissions': before}, headers=origin_headers(admin['csrf_token']))
    assert first.status_code == 200, first.text
    stale = client.patch(route, json={'permissions': {**before, 'work': {'role': 'worker', 'scope_ids': ['project-a', 'project-b']}}, 'expected_permissions': before}, headers=origin_headers(admin['csrf_token']))
    assert stale.status_code == 409
    assert stale.json()['detail']['code'] == 'permissions_changed'
    latest = first.json()['permissions']
    after = {**latest, 'work': {'role': 'worker', 'scope_ids': ['project-a', 'project-b']}}
    saved = client.patch(route, json={'permissions': after, 'expected_permissions': latest}, headers=origin_headers(admin['csrf_token']))
    assert saved.status_code == 200
    assert saved.json()['permissions']['code'] == before['code']
    assert saved.json()['permissions']['knowledge'] == changed['knowledge']
    assert client.post('/api/auth/introspect', json={'session_token': member_handle}, headers={'Authorization': 'Bearer '+settings.service_secret}).status_code == 401
    assert client.patch(route, json={'expected_permissions': None, 'permissions': before}, headers=origin_headers(admin['csrf_token'])).status_code == 422
