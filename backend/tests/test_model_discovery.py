from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import select

from conftest import headers
from ordivant import model_settings
from ordivant.identity import IdentityBinding
from ordivant.models import IdempotencyRecord, Organization, Principal
from ordivant.security import issue_token, new_id, now_utc
from test_model_settings import SYNTHETIC_KEY, put_settings, settings_body

PATH = "/api/model-settings/discover"
CONNECTION = {"id": "local-api", "base_url": "https://models.invalid/v1"}


def install_provider(monkeypatch, handler):
    def client():
        return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False, trust_env=False)
    monkeypatch.setattr(model_settings, "_model_discovery_client", client)


def discover(api_client, system, **values):
    return api_client.post(PATH, json={**CONNECTION, **values}, headers=headers(system, "manager", "not-cached"))


def test_unsaved_discovery_reads_real_api_shape_without_inventing_metadata(api_client, system, monkeypatch):
    calls = []

    def upstream(request):
        calls.append(request)
        assert str(request.url) == "https://models.invalid/v1/models"
        assert request.method == "GET"
        assert request.headers["Authorization"] == f"Bearer {SYNTHETIC_KEY}"
        return httpx.Response(200, json={"data": [
            {"id": "z", "owned_by": "synthetic", "api_key": SYNTHETIC_KEY},
            {"id": "a", "name": "A", "context_window": 32000, "max_output_tokens": 4096,
             "reasoning_efforts": ["low", "high"]}, {"id": "z"},
        ]})

    install_provider(monkeypatch, upstream)
    response = discover(api_client, system, api_key=SYNTHETIC_KEY, base_url=CONNECTION["base_url"] + "/")
    assert response.status_code == 200, response.text
    assert response.json() == {"source": "provider_api", "models": [
        {"id": "a", "name": "A", "context_window": 32000, "max_output_tokens": 4096, "reasoning_efforts": ["low", "high"]},
        {"id": "z", "name": "z"},
    ]}
    assert response.headers["cache-control"] == "no-store"
    assert SYNTHETIC_KEY not in response.text
    assert len(calls) == 1
    assert api_client.get("/api/model-settings", headers=headers(system, "manager")).json()["providers"] == []
    with system["factory"]() as session:
        assert session.scalar(select(IdempotencyRecord)) is None


def test_saved_key_only_reused_for_same_org_provider_and_url(api_client, system, monkeypatch, tmp_path):
    monkeypatch.setenv("ORDIVANT_DATA_DIR", str(tmp_path / "work"))
    assert put_settings(api_client, system, settings_body()).status_code == 200
    calls = []

    def upstream(request):
        calls.append(request)
        assert request.headers["authorization"] == f"Bearer {SYNTHETIC_KEY}"
        return httpx.Response(200, json={"data": []})

    install_provider(monkeypatch, upstream)
    assert discover(api_client, system).json()["models"] == []
    assert discover(api_client, system, base_url="https://other.invalid/v1").status_code == 422
    assert discover(api_client, system, id="different").status_code == 422
    assert len(calls) == 1
    with system["factory"]() as session:
        org = Organization(id=new_id(), name="Other", created_at=now_utc())
        session.add(org)
        session.flush()
        admin = Principal(id=new_id(), organization_id=org.id, name="Other admin", kind="human", role="admin", active=True)
        session.add(admin)
        session.flush()
        token = issue_token(session, admin.id)
        session.commit()
    response = api_client.post(PATH, json=CONNECTION, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 422
    assert len(calls) == 1
    # Discovery never changes the saved revision, defaults, or metadata.
    settings = api_client.get("/api/model-settings", headers=headers(system, "manager")).json()
    assert settings["revision"] == 1 and settings["default"] == settings_body()["default"]


def test_discovery_requires_admin_before_contacting_provider(api_client, system, monkeypatch):
    def unexpected(_):
        pytest.fail("Unauthorized discovery contacted upstream")
    install_provider(monkeypatch, unexpected)
    for identity in ("worker_a", "reviewer", "runtime"):
        response = api_client.post(PATH, json={**CONNECTION, "api_key": SYNTHETIC_KEY}, headers=headers(system, identity))
        assert response.status_code == 403
    monkeypatch.setenv("ORDIVANT_IDENTITY_URL", "https://identity.invalid")
    with system["factory"]() as session:
        binding = IdentityBinding(subject="synthetic", organization_id=system["ids"]["organization"],
                                  principal_id=system["ids"]["manager"], identity_admin=False)
        session.add(binding)
        session.commit()
    assert discover(api_client, system, api_key=SYNTHETIC_KEY).status_code == 403


@pytest.mark.parametrize(("status", "code"), [
    (401, "provider_models_unauthorized"), (403, "provider_models_unauthorized"),
    (404, "provider_models_unsupported"), (405, "provider_models_unsupported"),
    (429, "provider_models_unavailable"), (500, "provider_models_unavailable"),
    (302, "provider_models_unavailable"),
])
def test_upstream_failures_do_not_leak_or_follow_redirects(api_client, system, monkeypatch, status, code):
    calls = []
    def upstream(request):
        calls.append(request)
        return httpx.Response(status, text=SYNTHETIC_KEY, headers={"Location": "https://other.invalid/models"})
    install_provider(monkeypatch, upstream)
    response = discover(api_client, system, api_key=SYNTHETIC_KEY)
    assert response.status_code == 502 and response.json()["detail"]["code"] == code
    assert SYNTHETIC_KEY not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [None, {}, {"data": {}}, {"data": [None]}, {"data": [{"id": ""}]}, {"data": [{"id": "a" * 201}]}, {"data": [{"id": "a"}] * 2001}])
def test_malformed_catalog_has_no_fabricated_fallback(api_client, system, monkeypatch, payload):
    install_provider(monkeypatch, lambda _: httpx.Response(200, content=json.dumps(payload)))
    response = discover(api_client, system, api_key=SYNTHETIC_KEY)
    assert response.status_code == 502 and response.json()["detail"]["code"] == "provider_models_invalid"


@pytest.mark.parametrize("failure", ["timeout", "network", "oversize", "html"])
def test_transport_and_response_limits(api_client, system, monkeypatch, failure):
    def upstream(request):
        if failure == "timeout":
            raise httpx.ReadTimeout(SYNTHETIC_KEY, request=request)
        if failure == "network":
            raise httpx.ConnectError(SYNTHETIC_KEY, request=request)
        return httpx.Response(200, content=b"x" * (1024 * 1024 + 1) if failure == "oversize" else b"<html>error</html>")
    install_provider(monkeypatch, upstream)
    response = discover(api_client, system, api_key=SYNTHETIC_KEY)
    assert response.status_code == (504 if failure == "timeout" else 502)
    assert SYNTHETIC_KEY not in response.text


def test_validation_redacts_key_and_invalid_url_never_connects(api_client, system, monkeypatch):
    install_provider(monkeypatch, lambda _: pytest.fail("Invalid request contacted upstream"))
    response = discover(api_client, system, api_key={"secret": SYNTHETIC_KEY})
    assert response.status_code == 422 and SYNTHETIC_KEY not in response.text
    assert response.headers["cache-control"] == "no-store"
    for url in ("file:///secrets", "https://user:password@models.invalid/v1", "https://models.invalid/v1?q=1", "https://[invalid", "https://models.invalid:wrong/v1", "https://models.invalid/\n"):
        assert discover(api_client, system, api_key=SYNTHETIC_KEY, base_url=url).status_code == 422


def test_cookie_discovery_checks_origin_csrf_and_identity_admin(api_client, system, monkeypatch, tmp_path):
    from test_identity_bridge import configure_identity

    user = {"id": "discovery-admin", "name": "Discovery admin", "role": "admin", "active": True,
            "permissions": {"work": {"role": "admin", "scope_ids": [system["ids"]["project"]]}}}
    configure_identity(monkeypatch, tmp_path, user)
    api_client.cookies.set("suite_session", "opaque-session")
    calls = []
    def upstream(request):
        calls.append(request)
        return httpx.Response(200, json={"data": [{"id": "model-a"}]})
    install_provider(monkeypatch, upstream)
    body = {**CONNECTION, "api_key": SYNTHETIC_KEY}
    for origin, csrf in (("https://evil.example", "csrf-value"), ("https://suite.example", "wrong")):
        response = api_client.post(PATH, json=body, headers={"Origin": origin, "X-CSRF-Token": csrf})
        assert response.status_code == 403
    assert not calls
    response = api_client.post(PATH, json=body, headers={"Origin": "https://suite.example", "X-CSRF-Token": "csrf-value"})
    assert response.status_code == 200, response.text
    assert len(calls) == 1
