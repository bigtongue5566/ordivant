from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

import pytest
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from ordivant_identity.api import _new_session, _new_user
from ordivant_identity.config import Settings
from ordivant_identity.main import create_app
from ordivant_identity.models import IdentityAuditEvent, PersonalAccessToken, User
from ordivant_identity.security import csrf_token


ORIGIN = "http://localhost:5173"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "Initial synthetic password 7!"
MEMBER_PASSWORD = "Member synthetic password 8!"


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


def setup_admin(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/setup",
        json={"name": "First Admin", "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers=origin_headers(),
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_token(client: TestClient, csrf: str, *, name: str = "CLI", products=None, days: int = 30):
    return client.post(
        "/api/auth/access-tokens",
        json={"name": name, "products": products or ["work"], "expires_in_days": days},
        headers=origin_headers(csrf),
    )


def introspect(client: TestClient, token: str, settings: Settings, product: str = "work"):
    return client.post(
        "/api/auth/access-tokens/introspect",
        json={"access_token": token, "product": product},
        headers={"Authorization": f"Bearer {settings.service_secret}"},
    )


def seed_member(app, *, email: str = "member@example.com", permissions: dict | None = None):
    with app.state.session_factory() as db:
        user = _new_user(
            email=email,
            name="Member",
            role="member",
            password=MEMBER_PASSWORD,
            permissions=permissions or {},
        )
        db.add(user)
        db.flush()
        _auth_session, raw_handle = _new_session(db, user, app.state.settings)
        db.commit()
        return user.id, raw_handle


def set_cookie(client: TestClient, settings: Settings, raw_handle: str) -> str:
    client.cookies.clear()
    client.cookies.set(settings.cookie_name, raw_handle, domain="localhost.local", path="/")
    return csrf_token(settings.service_secret, raw_handle)


def test_access_token_is_one_time_secret_and_metadata_stores_only_hash(identity):
    client, app, settings = identity
    setup = setup_admin(client)
    created = create_token(client, setup["csrf_token"], name="  Local CLI  ", products=["work", "work", "code"])
    assert created.status_code == 201, created.text
    payload = created.json()
    raw_token = payload["token"]
    metadata = payload["access_token"]
    assert raw_token.startswith("ord_pat_")
    assert metadata["name"] == "Local CLI"
    assert metadata["products"] == ["work", "code"]
    assert metadata["prefix"] != raw_token
    assert raw_token.startswith(metadata["prefix"])
    assert created.headers["cache-control"] == "no-store"

    listed = client.get("/api/auth/access-tokens")
    assert listed.status_code == 200
    assert raw_token not in listed.text
    assert "token_hash" not in listed.text
    assert raw_token not in str(listed.json()["tokens"])
    assert listed.json()["tokens"] == [metadata]

    with app.state.session_factory() as db:
        row = db.scalar(select(PersonalAccessToken).where(PersonalAccessToken.id == metadata["id"]))
        audit = db.scalars(select(IdentityAuditEvent).where(IdentityAuditEvent.action == "access_token.created")).all()
        assert row.token_hash == hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        assert raw_token not in row.token_hash
        assert all(raw_token not in str(item.details) and row.token_hash not in str(item.details) for item in audit)

    valid = introspect(client, raw_token, settings)
    assert valid.status_code == 200, valid.text
    assert valid.json()["user"] == setup["user"]
    assert valid.json()["token_id"] == metadata["id"]
    assert valid.headers["cache-control"] == "no-store"
    assert client.get("/api/auth/access-tokens").json()["tokens"][0]["last_used_at"] is not None


def test_token_management_requires_session_and_csrf_and_rejects_unknown_fields(identity):
    client, _app, settings = identity
    setup = setup_admin(client)
    raw = create_token(client, setup["csrf_token"]).json()["token"]

    client.cookies.clear()
    bearer_only = client.get("/api/auth/access-tokens", headers={"Authorization": f"Bearer {raw}"})
    assert bearer_only.status_code == 401
    bearer_create = client.post(
        "/api/auth/access-tokens",
        json={"name": "child", "products": ["work"]},
        headers=origin_headers(setup["csrf_token"]) | {"Authorization": f"Bearer {raw}"},
    )
    assert bearer_create.status_code == 401

    client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers=origin_headers(),
    )
    csrf = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers=origin_headers(),
    ).json()["csrf_token"]
    missing_csrf = client.post(
        "/api/auth/access-tokens",
        json={"name": "missing csrf", "products": ["work"]},
        headers=origin_headers(),
    )
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["detail"]["code"] == "csrf_invalid"

    unknown = create_token(client, csrf, products=["work"], name="valid").json()
    assert unknown["token"].startswith("ord_pat_")
    extra = client.post(
        "/api/auth/access-tokens",
        json={"name": "valid", "products": ["work"], "user_id": "victim"},
        headers=origin_headers(csrf),
    )
    assert extra.status_code == 422
    assert raw not in str(extra.json())
    extra_introspect = client.post(
        "/api/auth/access-tokens/introspect",
        json={"access_token": raw, "product": "work", "user_id": "victim"},
        headers={"Authorization": f"Bearer {settings.service_secret}"},
    )
    assert extra_introspect.status_code == 422


def test_token_is_owner_scoped_and_revocation_is_idempotent(identity):
    client, app, settings = identity
    setup = setup_admin(client)
    admin_handle = client.cookies.get(settings.cookie_name)
    admin_token = create_token(client, setup["csrf_token"]).json()
    _, member_handle = seed_member(app)
    member_csrf = set_cookie(client, settings, member_handle)
    cross_owner = client.delete(
        f"/api/auth/access-tokens/{admin_token['access_token']['id']}",
        headers=origin_headers(member_csrf),
    )
    assert cross_owner.status_code == 404
    assert introspect(client, admin_token["token"], settings).status_code == 200
    admin_csrf = set_cookie(client, settings, admin_handle)
    own_revoke = client.delete(
        f"/api/auth/access-tokens/{admin_token['access_token']['id']}",
        headers=origin_headers(admin_csrf),
    )
    assert own_revoke.status_code == 204
    repeated = client.delete(
        f"/api/auth/access-tokens/{admin_token['access_token']['id']}",
        headers=origin_headers(admin_csrf),
    )
    assert repeated.status_code == 204
    assert introspect(client, admin_token["token"], settings).status_code == 401
    listed = client.get("/api/auth/access-tokens").json()["tokens"]
    assert listed[0]["revoked_at"] is not None


def test_member_can_only_mint_currently_permitted_products_and_introspection_uses_latest_user(identity):
    client, app, settings = identity
    setup = setup_admin(client)
    admin_handle = client.cookies.get(settings.cookie_name)
    user_id, member_handle = seed_member(
        app,
        permissions={"work": {"role": "worker", "scope_ids": ["project-1"]}},
    )
    member_csrf = set_cookie(client, settings, member_handle)
    denied = create_token(client, member_csrf, products=["code"])
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "token_product_forbidden"

    member_token = create_token(client, member_csrf, products=["work"]).json()
    allowed = introspect(client, member_token["token"], settings, product="work")
    assert allowed.status_code == 200
    assert allowed.json()["user"]["permissions"]["work"]["role"] == "worker"
    wrong_product = introspect(client, member_token["token"], settings, product="knowledge")
    assert wrong_product.status_code == 403
    assert wrong_product.json()["detail"]["code"] == "token_product_forbidden"

    admin_csrf = set_cookie(client, settings, admin_handle)
    changed = client.patch(
        f"/api/auth/users/{user_id}",
        json={"permissions": {"work": {"role": "reviewer", "scope_ids": ["project-2"]}}},
        headers=origin_headers(admin_csrf),
    )
    assert changed.status_code == 200, changed.text
    current = introspect(client, member_token["token"], settings, product="work")
    assert current.status_code == 200
    assert current.json()["user"]["permissions"]["work"] == {"role": "reviewer", "scope_ids": ["project-2"]}
    assert admin_handle


def test_expired_revoked_password_reset_and_disabled_tokens_are_rejected(identity):
    client, app, settings = identity
    setup = setup_admin(client)
    csrf = setup["csrf_token"]

    expired = create_token(client, csrf, name="expired").json()
    with app.state.session_factory() as db:
        row = db.get(PersonalAccessToken, expired["access_token"]["id"])
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    expired_check = introspect(client, expired["token"], settings)
    assert expired_check.status_code == 401
    assert expired_check.json()["detail"]["code"] == "access_token_invalid"

    revocable = create_token(client, csrf, name="revoked").json()
    token_id = revocable["access_token"]["id"]
    assert client.delete(f"/api/auth/access-tokens/{token_id}", headers=origin_headers(csrf)).status_code == 204
    assert client.delete(f"/api/auth/access-tokens/{token_id}", headers=origin_headers(csrf)).status_code == 204
    assert introspect(client, revocable["token"], settings).status_code == 401

    password_token = create_token(client, csrf, name="password-change").json()
    changed_password = "Updated synthetic password 9!"
    changed = client.post(
        "/api/auth/change-password",
        json={"current_password": ADMIN_PASSWORD, "new_password": changed_password},
        headers=origin_headers(csrf),
    )
    assert changed.status_code == 200, changed.text
    assert introspect(client, password_token["token"], settings).status_code == 401

    recovery_token = create_token(client, changed.json()["csrf_token"], name="recovery").json()
    recovered_password = "Recovered synthetic password 1!"
    recovery = client.post(
        "/api/auth/recover",
        json={
            "email": ADMIN_EMAIL,
            "recovery_code": changed.json()["recovery_codes"][0],
            "new_password": recovered_password,
        },
        headers=origin_headers(),
    )
    assert recovery.status_code == 200, recovery.text
    assert introspect(client, recovery_token["token"], settings).status_code == 401

    member_id, member_handle = seed_member(app, permissions={"work": {"role": "worker", "scope_ids": ["x"]}})
    member_csrf = set_cookie(client, settings, member_handle)
    member_token = create_token(client, member_csrf, name="member-disable").json()

    admin_login = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": recovered_password},
        headers=origin_headers(),
    )
    disabled = client.patch(
        f"/api/auth/users/{member_id}",
        json={"active": False},
        headers=origin_headers(admin_login.json()["csrf_token"]),
    )
    assert disabled.status_code == 200
    result = introspect(client, member_token["token"], settings)
    assert result.status_code == 401
    assert result.json()["detail"]["code"] == "access_token_invalid"


@pytest.mark.parametrize("lifecycle", ["disable", "delete"])
def test_scim_deactivation_permanently_revokes_personal_access_tokens(identity, lifecycle):
    client, app, settings = identity
    setup_admin(client)
    object.__setattr__(settings, "scim_token", "synthetic-scim-token-for-pat-lifecycle-test")
    scim_headers = {"Authorization": f"Bearer {settings.scim_token}"}
    created_user = client.post(
        "/api/scim/v2/Users",
        json={"userName": f"{lifecycle}@example.com", "displayName": "SCIM Member", "active": True},
        headers=scim_headers,
    )
    assert created_user.status_code == 201, created_user.text
    scim_id = created_user.json()["id"]
    user_id = None
    with app.state.session_factory() as db:
        user = db.scalar(select(User).where(User.normalized_email == f"{lifecycle}@example.com"))
        user_id = user.id
        user.permissions = {"work": {"role": "worker", "scope_ids": ["scim-project"]}}
        _auth_session, raw_handle = _new_session(db, user, settings)
        db.commit()

    member_csrf = set_cookie(client, settings, raw_handle)
    token = create_token(client, member_csrf, name=f"{lifecycle}-token").json()
    assert introspect(client, token["token"], settings).status_code == 200

    if lifecycle == "disable":
        response = client.patch(
            f"/api/scim/v2/Users/{scim_id}",
            json={"Operations": [{"op": "replace", "path": "active", "value": False}]},
            headers=scim_headers,
        )
        assert response.status_code == 200, response.text
        reactivated = client.patch(
            f"/api/scim/v2/Users/{scim_id}",
            json={"Operations": [{"op": "replace", "path": "active", "value": True}]},
            headers=scim_headers,
        )
        assert reactivated.status_code == 200, reactivated.text
        assert reactivated.json()["active"] is True
    else:
        deleted = client.delete(f"/api/scim/v2/Users/{scim_id}", headers=scim_headers)
        assert deleted.status_code == 204

    result = introspect(client, token["token"], settings)
    assert result.status_code == 401
    assert result.json()["detail"]["code"] == "access_token_invalid"
    with app.state.session_factory() as db:
        stored = db.scalar(select(PersonalAccessToken).where(PersonalAccessToken.id == token["access_token"]["id"]))
        assert stored.user_id == user_id
        assert stored.revoked_at is not None


def test_mail_recovery_password_reset_revokes_personal_access_tokens(identity):
    from ordivant_identity.enterprise_models import MailOutbox
    from ordivant_identity.sso import _decrypt

    client, app, settings = identity
    setup = setup_admin(client)
    token = create_token(client, setup["csrf_token"], name="email-recovery").json()
    object.__setattr__(settings, "smtp_host", "local-mail-sink")
    object.__setattr__(settings, "smtp_sender", "noreply@example.com")
    requested = client.post(
        "/api/auth/request-recovery",
        json={"email": ADMIN_EMAIL},
        headers=origin_headers(),
    )
    assert requested.status_code == 200
    with app.state.session_factory() as db:
        queued = db.scalar(select(MailOutbox).where(MailOutbox.kind == "recovery"))
        recovery_code = json.loads(_decrypt(settings, queued.payload_ciphertext, b"mail"))["code"]

    recovered = client.post(
        "/api/auth/recover",
        json={
            "email": ADMIN_EMAIL,
            "recovery_code": recovery_code,
            "new_password": "Email recovered synthetic password 3!",
        },
        headers=origin_headers(),
    )
    assert recovered.status_code == 200, recovered.text
    assert introspect(client, token["token"], settings).status_code == 401


def test_access_token_limit_counts_only_active_unexpired_tokens(identity):
    client, app, settings = identity
    setup = setup_admin(client)
    csrf = setup["csrf_token"]
    for index in range(50):
        created = create_token(client, csrf, name=f"token-{index}")
        assert created.status_code == 201, created.text
    limited = create_token(client, csrf, name="token-51")
    assert limited.status_code == 409
    assert limited.json()["detail"]["code"] == "token_limit"

    with app.state.session_factory() as db:
        first = db.scalar(select(PersonalAccessToken).order_by(PersonalAccessToken.created_at, PersonalAccessToken.id))
        first.revoked_at = datetime.now(timezone.utc)
        db.commit()
    replacement = create_token(client, csrf, name="replacement")
    assert replacement.status_code == 201, replacement.text

    with app.state.session_factory() as db:
        spare = db.scalar(
            select(PersonalAccessToken)
            .where(PersonalAccessToken.user_id == setup["user"]["id"], PersonalAccessToken.revoked_at.is_(None))
            .order_by(PersonalAccessToken.created_at, PersonalAccessToken.id)
        )
        spare.revoked_at = datetime.now(timezone.utc)
        db.commit()

    cookie = client.cookies.get(settings.cookie_name)

    async def create_concurrently(name: str) -> int:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as concurrent_client:
            response = await concurrent_client.post(
                "/api/auth/access-tokens",
                json={"name": name, "products": ["work"]},
                headers=origin_headers(csrf) | {"Cookie": f"{settings.cookie_name}={cookie}"},
            )
            return response.status_code

    async def run_race() -> list[int]:
        return await asyncio.gather(create_concurrently("race-a"), create_concurrently("race-b"))

    assert sorted(asyncio.run(run_race())) == [201, 409]


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "products": ["work"]},
        {"name": "   ", "products": ["work"]},
        {"name": "x" * 101, "products": ["work"]},
        {"name": "valid", "products": []},
        {"name": "valid", "products": ["other"]},
        {"name": "valid", "products": ["work"], "expires_in_days": 0},
        {"name": "valid", "products": ["work"], "expires_in_days": 366},
    ],
)
def test_invalid_access_token_requests_are_422(identity, body):
    client, _app, _settings = identity
    setup = setup_admin(client)
    response = client.post(
        "/api/auth/access-tokens",
        json=body,
        headers=origin_headers(setup["csrf_token"]),
    )
    assert response.status_code == 422, response.text
