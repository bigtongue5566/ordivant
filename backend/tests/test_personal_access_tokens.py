from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from sqlalchemy import select

from ordivant import identity
from ordivant.errors import DomainError
from ordivant.identity import IdentityBinding
from ordivant.models import Principal


def configure_identity(monkeypatch, tmp_path, user):
    token_file = tmp_path / "identity-service-token"
    token_file.write_text("test-service-token", encoding="utf-8")
    monkeypatch.setenv("ORDIVANT_AUTH_COOKIE_NAME", "suite_session")
    monkeypatch.setenv("ORDIVANT_AUTH_ORIGINS", "https://suite.example")
    monkeypatch.setenv("ORDIVANT_IDENTITY_URL", "http://identity.test")
    monkeypatch.setenv("ORDIVANT_IDENTITY_SERVICE_TOKEN_FILE", str(token_file))
    monkeypatch.delenv("ORDIVANT_IDENTITY_ORG_ID", raising=False)
    calls = {"cookie": [], "access": []}
    behavior = {"error": None}

    async def fake_session_introspect(identity_url, service_token, session_token):
        calls["cookie"].append((identity_url, service_token, session_token))
        return user, "csrf-value"

    async def fake_access_introspect(identity_url, service_token, access_token):
        calls["access"].append((identity_url, service_token, access_token))
        if behavior["error"] is not None:
            status_code, code = behavior["error"]
            raise DomainError(status_code, code, "synthetic Identity response")
        return user

    monkeypatch.setattr(identity, "_introspect", fake_session_introspect)
    monkeypatch.setattr(identity, "_introspect_access_token", fake_access_introspect)
    return calls, behavior


def test_pat_maps_to_cookie_human_and_reads_writes_only_its_work_scope(
    api_client, system, monkeypatch, tmp_path
):
    user = {
        "id": "identity-work-pat-user",
        "name": "PAT Manager",
        "role": "member",
        "active": True,
        "permissions": {
            "work": {"role": "manager", "scope_ids": [system["ids"]["project"]]},
        },
    }
    calls, behavior = configure_identity(monkeypatch, tmp_path, user)
    api_client.cookies.set("suite_session", "opaque-session")

    cookie_me = api_client.get("/api/me")
    pat_headers = {"Authorization": "Bearer ord_pat_work-test-token"}
    pat_me = api_client.get("/api/me", headers=pat_headers)
    assert cookie_me.status_code == pat_me.status_code == 200
    assert pat_me.json()["id"] == cookie_me.json()["id"]
    assert pat_me.json()["kind"] == "human"
    assert pat_me.json()["role"] == "manager"
    assert calls["cookie"] == [("http://identity.test", "test-service-token", "opaque-session")]
    assert calls["access"] == [("http://identity.test", "test-service-token", "ord_pat_work-test-token")]

    projects = api_client.get("/api/projects", headers=pat_headers)
    assert projects.status_code == 200
    assert [item["id"] for item in projects.json()] == [system["ids"]["project"]]
    assert api_client.get(f"/api/projects/{system['ids']['isolated_project']}", headers=pat_headers).status_code == 404

    created = api_client.post(
        "/api/tasks",
        headers={**pat_headers, "Idempotency-Key": "work-pat-task"},
        json={"project_id": system["ids"]["project"], "title": "Created with PAT"},
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    assert api_client.get(f"/api/tasks/{task_id}", headers=pat_headers).status_code == 200

    user["permissions"]["work"]["role"] = "worker"
    updated_role = api_client.get("/api/me", headers=pat_headers)
    assert updated_role.status_code == 200
    assert updated_role.json()["role"] == "worker"
    denied_scope_creation = api_client.post(
        "/api/projects",
        headers={**pat_headers, "Idempotency-Key": "work-pat-denied-project"},
        json={"key": "pat-project", "name": "PAT Project"},
    )
    assert denied_scope_creation.status_code == 403
    assert denied_scope_creation.json()["detail"]["code"] == "identity_admin_required"

    user["permissions"]["work"]["scope_ids"] = []
    assert api_client.get("/api/projects", headers=pat_headers).json() == []
    assert api_client.get(f"/api/tasks/{task_id}", headers=pat_headers).status_code == 404

    behavior["error"] = (401, "unauthenticated")
    cookie_calls_before_invalid_pat = len(calls["cookie"])
    invalid_with_valid_cookie = api_client.get("/api/me", headers=pat_headers)
    assert invalid_with_valid_cookie.status_code == 401
    assert len(calls["cookie"]) == cookie_calls_before_invalid_pat


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        ((403, "token_product_forbidden"), 403, "token_product_forbidden"),
        ((503, "identity_unavailable"), 503, "identity_unavailable"),
    ],
)
def test_pat_product_denial_and_identity_outage_fail_closed(
    api_client, monkeypatch, tmp_path, error, status_code, code
):
    user = {"id": "identity-work-errors", "name": "Work User", "role": "member", "active": True,
            "permissions": {"work": {"role": "worker", "scope_ids": []}}}
    _, behavior = configure_identity(monkeypatch, tmp_path, user)
    behavior["error"] = error

    response = api_client.get("/api/me", headers={"Authorization": "Bearer ord_pat_error-test-token"})

    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code


def test_legacy_agent_bearer_keeps_using_local_token_authentication(api_client, system, monkeypatch, tmp_path):
    user = {"id": "unused-identity-user", "name": "Unused", "role": "member", "active": True,
            "permissions": {"work": {"role": "worker", "scope_ids": []}}}
    calls, _ = configure_identity(monkeypatch, tmp_path, user)

    response = api_client.get("/api/me", headers={"Authorization": f"Bearer {system['tokens']['worker_a']}"})

    assert response.status_code == 200
    assert response.json()["kind"] == "agent"
    assert calls == {"cookie": [], "access": []}


@pytest.mark.parametrize("access_token", ["ord_pat_x", "ord_pat_" + "x" * 600])
def test_malformed_pat_length_fails_before_identity_without_cookie_fallback(
    api_client, system, monkeypatch, tmp_path, access_token
):
    user = {
        "id": "identity-work-malformed-pat",
        "name": "Work User",
        "role": "member",
        "active": True,
        "permissions": {"work": {"role": "worker", "scope_ids": []}},
    }
    calls, _ = configure_identity(monkeypatch, tmp_path, user)
    api_client.cookies.set("suite_session", "valid-session")
    valid_cookie = api_client.get("/api/me")
    assert valid_cookie.status_code == 200
    cookie_calls_before_malformed_pat = len(calls["cookie"])

    response = api_client.get(
        "/api/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthenticated"
    assert calls["access"] == []
    assert len(calls["cookie"]) == cookie_calls_before_malformed_pat


@pytest.mark.parametrize(
    ("status_code", "payload", "expected"),
    [
        (200, {"user": {"id": "subject", "name": "User", "active": True}}, (200, None)),
        (200, {"user": {"id": "subject", "name": "", "active": True}}, (503, "identity_unavailable")),
        (200, {"unexpected": True}, (503, "identity_unavailable")),
        (200, None, (503, "identity_unavailable")),
        (401, {"detail": "invalid"}, (401, "unauthenticated")),
        (403, {"detail": "wrong product"}, (403, "token_product_forbidden")),
        (503, {"detail": "offline"}, (503, "identity_unavailable")),
    ],
)
def test_access_token_introspection_uses_identity_service_boundary(
    monkeypatch, status_code, payload, expected
):
    requests = []
    original_async_client = httpx.AsyncClient

    async def respond(request):
        requests.append(request)
        if payload is None:
            return httpx.Response(status_code, content=b"not-json")
        return httpx.Response(status_code, json=payload)

    def mock_async_client(*args, **kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        assert isinstance(kwargs["timeout"], httpx.Timeout)
        assert kwargs["timeout"].connect == 1.0
        assert kwargs["timeout"].read == 3.0
        return original_async_client(*args, transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(identity.httpx, "AsyncClient", mock_async_client)

    if expected[1] is None:
        result = asyncio.run(
            identity._introspect_access_token("http://identity.test", "test-service-token", "ord_pat_synthetic")
        )
        assert result == payload["user"]
    else:
        with pytest.raises(DomainError) as raised:
            asyncio.run(
                identity._introspect_access_token("http://identity.test", "test-service-token", "ord_pat_synthetic")
            )
        assert (raised.value.status_code, raised.value.code) == expected

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == "http://identity.test/api/auth/access-tokens/introspect"
    assert request.headers["Authorization"] == "Bearer test-service-token"
    assert json.loads(request.content) == {"access_token": "ord_pat_synthetic", "product": "work"}
