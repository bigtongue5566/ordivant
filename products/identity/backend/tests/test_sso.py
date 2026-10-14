from __future__ import annotations

import base64
import hashlib
import json
import secrets
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from fastapi import FastAPI
from starlette.requests import Request
from sqlalchemy import create_engine, select

from ordivant_identity.config import Settings
from ordivant_identity.main import create_app
from ordivant_identity.models import (
    AuthSession,
    BackchannelLogoutReplay,
    IdentityAuditEvent,
    IdentityLink,
    OIDCFlow,
    SSOConfiguration,
    User,
)
from ordivant_identity.api import _client_host
from ordivant_identity.security import hash_password, keyed_hash, session_hash
from ordivant_identity.sso import SSOFailure, _claims_email, _verify_signed_token


ORIGIN = "http://127.0.0.1:5173"
ADMIN_EMAIL = "sso-admin@example.com"
ADMIN_PASSWORD = "Synthetic admin password 9!"
CLIENT_SECRET = "Synthetic:client secret/+ value"


def _b64(value: int) -> str:
    size = (value.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(value.to_bytes(size, "big")).decode("ascii").rstrip("=")


class SyntheticProvider:
    def __init__(self, auth_methods: list[str] | None = None):
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = self.private_key.public_key().public_numbers()
        self.jwk = {"kty": "RSA", "kid": "sso-test-key", "use": "sig", "alg": "RS256", "n": _b64(public.n), "e": _b64(public.e)}
        self.private_pem = self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self.claims: dict = {}
        self.auth_methods = auth_methods or ["client_secret_post"]
        self.token_requests: list[dict] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_type())
        self.server.provider = self
        self.issuer = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def issue(self, claims: dict | None = None, *, signing_key=None, extra_headers: dict | None = None) -> str:
        key = signing_key or self.private_pem
        return jwt.encode(
            claims or self.claims,
            key,
            algorithm="RS256",
            headers={"kid": "sso-test-key", "typ": "JWT", **(extra_headers or {})},
        )

    def _handler_type(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                provider = self.server.provider
                path = urlsplit(self.path).path
                if path == "/.well-known/openid-configuration":
                    value = {
                        "issuer": provider.issuer,
                        "authorization_endpoint": provider.issuer + "/authorize",
                        "token_endpoint": provider.issuer + "/token",
                        "jwks_uri": provider.issuer + "/jwks",
                        "id_token_signing_alg_values_supported": ["RS256"],
                        "token_endpoint_auth_methods_supported": provider.auth_methods,
                    }
                elif path == "/jwks":
                    value = {"keys": [provider.jwk]}
                else:
                    self.send_error(404)
                    return
                payload = json.dumps(value).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self):
                provider = self.server.provider
                if urlsplit(self.path).path != "/token":
                    self.send_error(404)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                fields = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
                provider.token_requests.append(
                    {
                        "fields": {key: items[-1] for key, items in fields.items()},
                        "authorization": self.headers.get("Authorization"),
                    }
                )
                payload = json.dumps({"id_token": provider.issue()}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, _format, *_args):
                return

        return Handler


@pytest.fixture
def provider():
    value = SyntheticProvider()
    try:
        yield value
    finally:
        value.close()


@pytest.fixture
def identity(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{(tmp_path / 'identity.sqlite3').as_posix()}",
        mode="development",
        cookie_name="ordivant_sso_test",
        service_secret=secrets.token_urlsafe(48),
        auth_origins=(ORIGIN, "http://localhost:5173"),
        cookie_secure=False,
    )
    app = create_app(settings)
    with TestClient(app, base_url=ORIGIN, follow_redirects=False) as client:
        yield client, app, settings


def origin_headers(csrf: str | None = None, *, origin: str = ORIGIN) -> dict[str, str]:
    headers = {"Origin": origin}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return headers


def setup_admin(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/setup",
        json={"name": "SSO Test Admin", "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers=origin_headers(),
    )
    assert response.status_code == 201, response.text
    return response.json()


def sso_settings(
    client: TestClient,
    admin: dict,
    provider: SyntheticProvider,
    *,
    revision: int = 0,
    provisioning: str = "jit",
    login_policy: str = "password_and_sso",
    group_mappings: list | None = None,
    auth_methods: list[str] | None = None,
    client_secret: str = CLIENT_SECRET,
) -> dict:
    body = {
        "revision": revision,
        "enabled": True,
        "display_name": "Synthetic OIDC",
        "issuer_url": provider.issuer,
        "client_id": "ordivant-test-client",
        "client_secret": client_secret,
        "scopes": ["openid", "profile", "email"],
        "allowed_email_domains": ["example.com"],
        "email_claim": "email",
        "require_email_verified": True,
        "groups_claim": "groups",
        "provisioning": provisioning,
        "default_permissions": {},
        "group_mappings": group_mappings or [],
        "login_policy": login_policy,
    }
    response = client.put(
        "/api/auth/sso/settings",
        json=body,
        headers=origin_headers(admin["csrf_token"]),
    )
    assert response.status_code == 200, response.text
    return response.json()


def begin_login(client: TestClient, *, origin: str = ORIGIN) -> dict[str, str]:
    response = client.post(
        "/api/auth/oidc/start",
        json={"return_to": "/code"},
        headers=origin_headers(origin=origin),
    )
    assert response.status_code == 200, response.text
    values = parse_qs(urlsplit(response.json()["authorization_url"]).query)
    assert values["response_type"] == ["code"]
    assert values["code_challenge_method"] == ["S256"]
    return {key: item[0] for key, item in values.items()}


def issue_login_claims(provider: SyntheticProvider, auth: dict[str, str], **updates) -> None:
    now = int(time.time())
    provider.claims = {
        "iss": provider.issuer,
        "sub": "subject-100",
        "aud": "ordivant-test-client",
        "iat": now,
        "exp": now + 300,
        "nonce": auth["nonce"],
        "email": "alice@example.com",
        "email_verified": True,
        "name": "Alice Test",
        "groups": ["engineering"],
        "sid": "idp-session-100",
        **updates,
    }


def callback(client: TestClient, settings: Settings, auth: dict[str, str], *, code: str = "synthetic-code"):
    binding_name = settings.cookie_name[:108] + "_oidc_binding"
    binding = client.cookies.get(binding_name)
    cookie_header = f"{binding_name}={binding}" if binding else ""
    headers = {"Cookie": cookie_header} if cookie_header else {}
    return client.get(
        "/api/auth/oidc/callback",
        params={"code": code, "state": auth["state"]},
        headers=headers,
    )


def redirect_error(response) -> str | None:
    query = parse_qs(urlsplit(response.headers["location"]).query)
    return query.get("auth_error", [None])[0]


def test_mfa_policy_enforced_on_verified_provider_callback_before_provisioning(identity, provider):
    client, app, settings = identity
    admin = setup_admin(client)
    configured = sso_settings(client, admin, provider, login_policy='sso_only')
    body = {key: value for key, value in configured.items()
        if key not in {'client_secret_configured', 'redirect_uri', 'backchannel_logout_uri'}}
    body.update(required_acr=['urn:company:mfa'], required_amr=['mfa'])
    saved = client.put('/api/auth/sso/settings', json=body, headers=origin_headers(admin['csrf_token']))
    assert saved.status_code == 200, saved.text
    for assurances in [{}, {'acr': 'weak', 'amr': ['mfa']}, {'acr': 'urn:company:mfa', 'amr': ['pwd']}]:
        auth = begin_login(client)
        assert auth['acr_values'] == 'urn:company:mfa'
        assert json.loads(auth['claims'])['id_token']['acr']['essential'] is True
        issue_login_claims(provider, auth, **assurances)
        result = callback(client, settings, auth)
        assert redirect_error(result) is not None
        with app.state.session_factory() as db:
            assert db.scalar(select(User.id).where(User.normalized_email == 'alice@example.com')) is None
    auth = begin_login(client)
    issue_login_claims(provider, auth, acr='urn:company:mfa', amr=['pwd', 'mfa'])
    assert redirect_error(callback(client, settings, auth)) is None
    session = client.get('/api/auth/me')
    assert session.status_code == 200
    assert session.json()['user']['email'] == 'alice@example.com'
    assert session.json()['authentication']['method'] == 'oidc'


def test_sso_settings_cas_secret_encryption_and_canonical_origin(identity, provider):
    client, app, settings = identity
    admin = setup_admin(client)
    assert client.get("/api/auth/status").json()["sso"]["public_origin"] == ORIGIN

    bad_alias = client.post(
        "/api/auth/oidc/start",
        json={"return_to": "/work"},
        headers=origin_headers(origin="http://localhost:5173"),
    )
    assert bad_alias.status_code == 403
    assert bad_alias.json()["detail"]["code"] == "sso_origin_mismatch"

    configured = sso_settings(client, admin, provider)
    assert configured["revision"] == 1
    assert configured["client_secret_configured"] is True
    assert configured["redirect_uri"] == ORIGIN + "/auth-api/oidc/callback"
    assert "client_secret" not in configured

    with app.state.session_factory() as db:
        row = db.get(SSOConfiguration, 1)
        stored = str(row.client_secret_ciphertext)
        assert CLIENT_SECRET not in stored
        assert row.client_secret_ciphertext.startswith("v1.")
        assert db.scalars(select(IdentityAuditEvent).where(IdentityAuditEvent.action == "sso.settings_changed")).first()

    stale_body = {
        key: value
        for key, value in configured.items()
        if key not in {"client_secret_configured", "redirect_uri", "backchannel_logout_uri"}
    }
    stale_body.update(revision=0, client_secret="")
    stale = client.put(
        "/api/auth/sso/settings",
        json=stale_body,
        headers=origin_headers(admin["csrf_token"]),
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "revision_conflict"

    replacement_missing = client.put(
        "/api/auth/sso/settings",
        json={
            "revision": 1,
            "enabled": True,
            "display_name": "Synthetic OIDC",
            "issuer_url": provider.issuer,
            "client_id": "different-client",
            "scopes": ["openid", "profile", "email"],
            "allowed_email_domains": ["example.com"],
            "email_claim": "email",
            "require_email_verified": True,
            "groups_claim": "groups",
            "provisioning": "jit",
            "default_permissions": {},
            "group_mappings": [],
            "login_policy": "password_and_sso",
        },
        headers=origin_headers(admin["csrf_token"]),
    )
    assert replacement_missing.status_code == 409
    assert replacement_missing.json()["detail"]["code"] == "client_secret_required"

    long_secret = "S" * 5000
    invalid = client.put(
        "/api/auth/sso/settings",
        json={"revision": 1, "client_secret": long_secret},
        headers=origin_headers(admin["csrf_token"]),
    )
    assert invalid.status_code == 422
    assert long_secret not in invalid.text
    assert (settings.data_dir / "sso.key").read_bytes().__len__() == 32


@pytest.mark.parametrize("auth_method", ["client_secret_post", "client_secret_basic"])
def test_real_oidc_pkce_jit_group_permissions_session_and_backchannel_logout(identity, provider, auth_method):
    client, app, settings = identity
    provider.auth_methods = [auth_method]
    admin = setup_admin(client)
    group_mappings = [
        {
            "group": "engineering",
            "permissions": {
                "work": {"role": "worker", "scope_ids": ["project-a"]},
                "knowledge": {"role": "writer", "scope_ids": ["space-a"]},
            },
        }
    ]
    configured = sso_settings(client, admin, provider, group_mappings=group_mappings)
    test_connection = client.post(
        "/api/auth/sso/test",
        headers=origin_headers(admin["csrf_token"]),
    )
    assert test_connection.status_code == 200
    assert test_connection.json()["status"] == "ok"
    assert test_connection.json()["supported_algs"] == ["RS256"]

    first_auth = begin_login(client)
    issue_login_claims(provider, first_auth)
    original_binding = client.cookies.get(settings.cookie_name[:108] + "_oidc_binding")
    completed = callback(client, settings, first_auth)
    assert completed.status_code == 303
    assert completed.headers["location"] == ORIGIN + "/code"
    user_session = client.get("/api/auth/me")
    assert user_session.status_code == 200
    assert user_session.json()["authentication"] == {"method": "oidc", "provider_name": "Synthetic OIDC"}
    user = user_session.json()["user"]
    assert user["credential_type"] == "sso"
    assert user["permissions_source"] == "sso"
    assert user["permissions"] == {
        "work": {"role": "worker", "scope_ids": ["project-a"]},
        "knowledge": {"role": "writer", "scope_ids": ["space-a"]},
    }
    with app.state.session_factory() as db:
        saved = db.scalar(
            select(OIDCFlow).where(
                OIDCFlow.state_hash == keyed_hash(settings.service_secret, "oidc-state", first_auth["state"])
            )
        )
        assert saved is not None and saved.consumed_at is not None
        assert first_auth["state"] not in saved.state_hash
        assert first_auth["nonce"] not in saved.nonce_hash
        assert first_auth["code_challenge"] == base64.urlsafe_b64encode(
            hashlib.sha256(provider.token_requests[-1]["fields"]["code_verifier"].encode("ascii")).digest()
        ).decode("ascii").rstrip("=")
        if auth_method == "client_secret_post":
            assert provider.token_requests[-1]["fields"]["client_secret"] == CLIENT_SECRET
            assert "Authorization" not in provider.token_requests[-1] or provider.token_requests[-1]["authorization"] is None
        else:
            assert "client_secret" not in provider.token_requests[-1]["fields"]
            assert provider.token_requests[-1]["authorization"].startswith("Basic ")
        first_handle = client.cookies.get(settings.cookie_name)
        assert first_handle
        sessions_before_replay = len(db.scalars(select(AuthSession)).all())

    replay = client.get(
        "/api/auth/oidc/callback",
        params={"code": "synthetic-code", "state": first_auth["state"]},
        headers={"Cookie": f"{settings.cookie_name[:108]}_oidc_binding={original_binding}"},
    )
    assert replay.status_code == 303
    assert redirect_error(replay) == "invalid_state"
    with app.state.session_factory() as db:
        assert len(db.scalars(select(AuthSession)).all()) == sessions_before_replay

    second_auth = begin_login(client)
    issue_login_claims(provider, second_auth, groups=[])
    second_login = callback(client, settings, second_auth)
    assert second_login.status_code == 303
    refreshed = client.get("/api/auth/me")
    assert refreshed.status_code == 200
    assert refreshed.json()["user"]["permissions"] == {}
    with app.state.session_factory() as db:
        first_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == session_hash(first_handle)))
        assert first_session is not None and first_session.revoked_at is not None
        second_handle = client.cookies.get(settings.cookie_name)
        assert second_handle

    now = int(time.time())
    malformed_logout = provider.issue(
        {
            "iss": provider.issuer,
            "aud": "ordivant-test-client",
            "iat": now,
            "jti": "logout-event-malformed",
            "sid": "idp-session-100",
            "events": [],
        },
        extra_headers={"typ": "logout+jwt"},
    )
    rejected_logout = client.post(
        "/api/auth/oidc/backchannel-logout",
        content=urlencode({"logout_token": malformed_logout}),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert rejected_logout.status_code == 400
    assert client.post(
        "/api/auth/introspect",
        json={"session_token": second_handle},
        headers={"Authorization": f"Bearer {settings.service_secret}"},
    ).status_code == 200

    logout_token = provider.issue(
        {
            "iss": provider.issuer,
            "aud": "ordivant-test-client",
            "iat": now,
            "jti": "logout-event-1",
            "sid": "idp-session-100",
            "events": {"http://schemas.openid.net/event/backchannel-logout": {}},
        },
        extra_headers={"typ": "logout+jwt"},
    )
    logged_out = client.post(
        "/api/auth/oidc/backchannel-logout",
        content=urlencode({"logout_token": logout_token}),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert logged_out.status_code == 200
    assert client.post(
        "/api/auth/introspect",
        json={"session_token": second_handle},
        headers={"Authorization": f"Bearer {settings.service_secret}"},
    ).status_code == 401
    replayed_logout = client.post(
        "/api/auth/oidc/backchannel-logout",
        content=urlencode({"logout_token": logout_token}),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert replayed_logout.status_code == 400
    with app.state.session_factory() as db:
        assert db.scalars(select(BackchannelLogoutReplay)).first() is not None
        assert db.scalars(select(IdentityAuditEvent).where(IdentityAuditEvent.action == "sso.backchannel_logout")).first()
    assert client.post(
        "/api/auth/introspect",
        json={"session_token": client.cookies.get(settings.cookie_name)},
        headers={"Authorization": f"Bearer {settings.service_secret}"},
    ).status_code == 401
    assert configured["revision"] == 1


@pytest.mark.parametrize(
    ("mutations", "expected_error"),
    [
        ({"nonce": "wrong-nonce"}, "sso_error"),
        ({"aud": "another-client"}, "sso_error"),
        ({"iss": "https://wrong.example.com"}, "sso_error"),
        ({"email_verified": False}, "email_unverified"),
        ({"email": "intruder@other.example"}, "email_domain_not_allowed"),
    ],
)
def test_oidc_rejects_forged_or_untrusted_identity_claims(identity, provider, mutations, expected_error):
    client, app, settings = identity
    admin = setup_admin(client)
    admin_handle = client.cookies.get(settings.cookie_name)
    sso_settings(client, admin, provider)
    auth = begin_login(client)
    issue_login_claims(provider, auth, **mutations)
    rejected = callback(client, settings, auth)
    assert rejected.status_code == 303
    assert redirect_error(rejected) == expected_error
    assert client.cookies.get(settings.cookie_name) == admin_handle
    assert client.get("/api/auth/me").json()["user"]["email"] == ADMIN_EMAIL
    with app.state.session_factory() as db:
        assert len(db.scalars(select(AuthSession)).all()) == 1


@pytest.mark.parametrize(
    ("configured_issuer", "token_issuer", "email_verified", "accepted"),
    [
        ("https://accounts.google.com", "https://accounts.google.com", True, True),
        ("https://accounts.google.com", "accounts.google.com", "true", True),
        ("https://accounts.google.com", "accounts.google.com", "True", False),
        ("http://127.0.0.1:9000", "http://127.0.0.1:9000", "true", False),
        ("http://127.0.0.1:9000", "accounts.google.com", True, False),
    ],
)
def test_google_issuer_alias_and_legacy_verified_email_are_narrowly_normalized(
    identity, provider, configured_issuer, token_issuer, email_verified, accepted
):
    _client, _app, settings = identity
    values = {
        "issuer_url": configured_issuer,
        "client_id": "ordivant-test-client",
        "allowed_email_domains": ["example.com"],
        "require_email_verified": True,
    }
    claims = {
        "iss": token_issuer,
        "sub": "google-subject",
        "aud": "ordivant-test-client",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "email": "alice@example.com",
        "email_verified": email_verified,
    }
    token = provider.issue(claims)
    if accepted:
        verified = _verify_signed_token(token, [provider.jwk], values, ["RS256"], settings=settings)
        assert _claims_email(values, verified) == ("alice@example.com", "alice@example.com")
    else:
        with pytest.raises(SSOFailure):
            verified = _verify_signed_token(token, [provider.jwk], values, ["RS256"], settings=settings)
            _claims_email(values, verified)


def test_client_ip_uses_x_real_ip_only_from_resolved_trusted_proxy(tmp_path, monkeypatch):
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{(tmp_path / 'proxy.sqlite3').as_posix()}",
        mode="development",
        cookie_name="ordivant_proxy_test",
        service_secret=secrets.token_urlsafe(48),
        auth_origins=(ORIGIN,),
        cookie_secure=False,
        auth_trusted_proxy_hosts=("proxy.internal",),
    )
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, _port, type=None: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 8080))
        ],
    )

    def request(peer: str, forwarded: tuple[str, ...]) -> Request:
        app = FastAPI()
        app.state.settings = settings
        headers = [(b"x-real-ip", value.encode("ascii")) for value in forwarded]
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": headers,
            "client": (peer, 1234),
            "server": ("identity", 80),
            "app": app,
        }
        return Request(scope)

    assert _client_host(request("127.0.0.1", ("198.51.100.4",))) == "198.51.100.4"
    assert _client_host(request("127.0.0.2", ("198.51.100.4",))) == "127.0.0.2"
    assert _client_host(request("127.0.0.1", ("198.51.100.4", "198.51.100.5"))) == "127.0.0.1"


def test_invited_only_requires_member_invite_and_sso_only_keeps_admin_breakglass(identity, provider):
    client, _app, settings = identity
    admin = setup_admin(client)
    configured = sso_settings(client, admin, provider, provisioning="invited_only")
    auth = begin_login(client)
    issue_login_claims(provider, auth)
    denied = callback(client, settings, auth)
    assert redirect_error(denied) == "invitation_required"

    invitation = client.post(
        "/api/auth/invitations",
        json={"email": "alice@example.com", "name": "Invited Alice", "role": "member", "permissions": {"code": {"role": "writer", "scope_ids": ["repo-1"]}}},
        headers=origin_headers(admin["csrf_token"]),
    )
    assert invitation.status_code == 201
    auth = begin_login(client)
    issue_login_claims(provider, auth)
    accepted = callback(client, settings, auth)
    assert accepted.status_code == 303 and redirect_error(accepted) is None
    member_session = client.get("/api/auth/me").json()
    assert member_session["user"]["permissions"] == {"code": {"role": "writer", "scope_ids": ["repo-1"]}}
    assert "recovery_codes" not in member_session
    member_handle = client.cookies.get(settings.cookie_name)

    client.cookies.clear()
    local_login = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers=origin_headers(),
    )
    assert local_login.status_code == 200
    admin = local_login.json()
    assert admin["user"]["role"] == "admin"
    admin_handle = client.cookies.get(settings.cookie_name)
    switched = sso_settings(
        client,
        admin,
        provider,
        revision=configured["revision"],
        provisioning="invited_only",
        login_policy="sso_only",
    )
    assert switched["revision"] == 2
    member_profile = client.post(
        "/api/auth/introspect",
        json={"session_token": member_handle},
        headers={"Authorization": f"Bearer {settings.service_secret}"},
    )
    assert member_profile.status_code == 401

    new_invite = client.post(
        "/api/auth/invitations",
        json={"email": "password-invite@example.com", "name": "No Password", "role": "member"},
        headers=origin_headers(admin["csrf_token"]),
        cookies={settings.cookie_name: admin_handle},
    )
    assert new_invite.status_code == 201
    blocked_invitation = client.post(
        "/api/auth/accept-invitation",
        json={"invitation_code": new_invite.json()["invitation_code"], "password": "Invited synthetic password 5!"},
        headers=origin_headers(),
    )
    assert blocked_invitation.status_code == 409
    assert blocked_invitation.json()["detail"]["code"] == "sso_only"

    blocked_recovery = client.post(
        "/api/auth/recover",
        json={"email": "alice@example.com", "recovery_code": "synthetic-recovery-code", "new_password": "Recovery synthetic password 8!"},
        headers=origin_headers(),
    )
    assert blocked_recovery.status_code == 401
    assert blocked_recovery.json()["detail"]["code"] == "invalid_recovery"

    client.cookies.clear()
    blocked_member_login = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "Local Alice password 6!"},
        headers=origin_headers(),
    )
    assert blocked_member_login.status_code == 401
    admin_breakglass = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers=origin_headers(),
    )
    assert admin_breakglass.status_code == 200
    assert admin_breakglass.json()["user"]["role"] == "admin"


def test_explicit_subject_link_never_joins_by_email(identity, provider):
    client, app, settings = identity
    admin = setup_admin(client)
    admin_handle = client.cookies.get(settings.cookie_name)
    configured = sso_settings(client, admin, provider, provisioning="jit")
    invitation = client.post(
        "/api/auth/invitations",
        json={"email": "alice@example.com", "name": "Local Alice", "role": "member", "permissions": {"work": {"role": "reviewer", "scope_ids": ["existing-project"]}}},
        headers=origin_headers(admin["csrf_token"]),
    )
    accepted = client.post(
        "/api/auth/accept-invitation",
        json={"invitation_code": invitation.json()["invitation_code"], "password": "Local Alice password 6!"},
        headers=origin_headers(),
    )
    assert accepted.status_code == 201
    user_id = accepted.json()["user"]["id"]

    first_auth = begin_login(client)
    issue_login_claims(provider, first_auth, email="alice@example.com")
    unlinked = callback(client, settings, first_auth)
    assert redirect_error(unlinked) == "account_link_required"
    assert client.cookies.get(settings.cookie_name) == accepted.cookies.get(settings.cookie_name)

    link = client.post(
        "/api/auth/sso/links",
        json={"user_id": user_id, "subject": "subject-100", "managed_permissions": False},
        headers=origin_headers(admin["csrf_token"]),
        cookies={settings.cookie_name: admin_handle},
    )
    assert link.status_code == 201, link.text

    linked_auth = begin_login(client)
    issue_login_claims(provider, linked_auth, email="alice@example.com")
    linked = callback(client, settings, linked_auth)
    assert linked.status_code == 303 and redirect_error(linked) is None
    profile = client.get("/api/auth/me").json()
    assert profile["user"]["id"] == user_id
    assert profile["user"]["permissions"] == {"work": {"role": "reviewer", "scope_ids": ["existing-project"]}}
    with app.state.session_factory() as db:
        link_row = db.scalar(select(IdentityLink).where(IdentityLink.user_id == user_id))
        assert link_row is not None and link_row.initial_email_checked_at is not None
    assert configured["revision"] == 1


def test_legacy_account_and_session_survive_additive_sso_migration(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    handle = secrets.token_urlsafe(32)
    created = datetime.now(timezone.utc)
    expires = created + timedelta(hours=12)
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE identity_users (id VARCHAR(36) PRIMARY KEY, email VARCHAR(320) NOT NULL, normalized_email VARCHAR(320) NOT NULL UNIQUE, name VARCHAR(160) NOT NULL, role VARCHAR(16) NOT NULL, active BOOLEAN NOT NULL, permissions JSON NOT NULL, password_hash TEXT NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE identity_sessions (id VARCHAR(36) PRIMARY KEY, token_hash VARCHAR(64) NOT NULL UNIQUE, user_id VARCHAR(36) NOT NULL, created_at DATETIME NOT NULL, last_seen_at DATETIME NOT NULL, idle_expires_at DATETIME NOT NULL, absolute_expires_at DATETIME NOT NULL, revoked_at DATETIME, FOREIGN KEY(user_id) REFERENCES identity_users(id))"
        )
        connection.exec_driver_sql(
            "INSERT INTO identity_users (id,email,normalized_email,name,role,active,permissions,password_hash,created_at,updated_at) VALUES ('legacy-user','legacy@example.com','legacy@example.com','Legacy Admin','admin',1,'{}',?, ?, ?)"
        , (hash_password("Legacy account password 8!"), created.isoformat(), created.isoformat()))
        connection.exec_driver_sql(
            "INSERT INTO identity_sessions (id,token_hash,user_id,created_at,last_seen_at,idle_expires_at,absolute_expires_at,revoked_at) VALUES ('legacy-session',?,'legacy-user',?,?,?, ?, NULL)"
        , (session_hash(handle), created.isoformat(), created.isoformat(), expires.isoformat(), expires.isoformat()))
        connection.exec_driver_sql(
            "CREATE TABLE identity_setup_marker (id INTEGER PRIMARY KEY, admin_user_id VARCHAR(36) NOT NULL UNIQUE)"
        )
        connection.exec_driver_sql("INSERT INTO identity_setup_marker (id,admin_user_id) VALUES (1,'legacy-user')")
    engine.dispose()

    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{database.as_posix()}",
        mode="development",
        cookie_name="ordivant_migration_test",
        service_secret=secrets.token_urlsafe(48),
        auth_origins=(ORIGIN,),
        cookie_secure=False,
    )
    with TestClient(create_app(settings), base_url=ORIGIN, follow_redirects=False) as client:
        client.cookies.set(settings.cookie_name, handle, domain="127.0.0.1", path="/")
        profile = client.get("/api/auth/me")
        assert profile.status_code == 200
        assert profile.json()["user"]["email"] == "legacy@example.com"
        assert profile.json()["user"]["credential_type"] == "local"
        assert profile.json()["authentication"]["method"] == "password"
        with client.app.state.session_factory() as db:
            session = db.get(AuthSession, "legacy-session")
            user = db.get(User, "legacy-user")
            assert user.password_hash.startswith("$argon2id$")
            assert session.authentication_method == "password"
            assert session.oidc_issuer is None
