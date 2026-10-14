from datetime import timedelta
from sqlalchemy import select
from test_auth import identity, setup_admin, origin_headers
from ordivant_identity.api import _new_session, _now
from ordivant_identity.enterprise_models import ScimResource, MailOutbox, RecoveryMailCredential
from ordivant_identity.models import User, AuthSession, IdentityAuditEvent
from ordivant_identity.sso import _verify_authentication_assurance, SSOFailure, _decrypt
import pytest


def scim(identity):
    client, app, settings = identity
    object.__setattr__(settings, "scim_token", "synthetic-provisioning-token-for-isolated-test")
    return client, app, settings, {"Authorization": f"Bearer {settings.scim_token}"}


def test_scim_dedicated_auth_and_cannot_adopt_admin(identity):
    client, app, settings, headers = scim(identity)
    setup_admin(client)
    assert client.get("/api/scim/v2/Users").status_code == 401
    denied = client.post("/api/scim/v2/Users", json={"userName": "admin@example.com"}, headers=headers)
    assert denied.status_code == 409
    assert client.post("/api/scim/v2/Users", json={"userName": "member@example.com", "role": "admin"}, headers=headers).status_code == 400
    user = client.post("/api/scim/v2/Users", json={"userName": "member@example.com", "externalId": "upstream-1", "displayName": "Colleague", "active": True}, headers=headers)
    assert user.status_code == 201, user.text
    assert "password" not in user.text
    found = client.get('/api/scim/v2/Users?filter=userName eq "MEMBER@example.com"', headers=headers).json()
    assert found["totalResults"] == 1
    assert client.get('/api/scim/v2/Users?filter=userName co "member"', headers=headers).status_code == 400
    with app.state.session_factory() as db:
        member = db.scalar(select(User).where(User.normalized_email == "member@example.com"))
        assert member.role == "member" and member.credential_type == "sso" and member.permissions == {}


def test_scim_group_grants_revoke_sessions_and_atomic_patch(identity):
    client, app, settings, headers = scim(identity)
    admin = setup_admin(client)
    assert client.put("/api/auth/enterprise", json={"audit_retention_days": 365,
        "scim_group_mappings": {"Engineering": {"work": {"role": "worker", "scope_ids": ["project-a"]}}}},
        headers=origin_headers(admin["csrf_token"])).status_code == 200
    user = client.post("/api/scim/v2/Users", json={"userName": "dev@example.com"}, headers=headers).json()
    group = client.post("/api/scim/v2/Groups", json={"displayName": "Engineering", "members": [{"value": user["id"]}]}, headers=headers).json()
    with app.state.session_factory() as db:
        row = db.get(ScimResource, user["id"])
        member = db.get(User, row.user_id)
        assert member.permissions["work"]["scope_ids"] == ["project-a"]
        session, _handle = _new_session(db, member, settings, authentication_method="oidc")
        session_id = session.id
        db.commit()
    failure = client.patch(f'/api/scim/v2/Groups/{group["id"]}', json={"Operations": [
        {"op": "remove", "path": f'members[value eq "{user["id"]}"]'},
        {"op": "replace", "path": "unsupported", "value": "x"}]}, headers=headers)
    assert failure.status_code == 400
    assert client.get(f'/api/scim/v2/Groups/{group["id"]}', headers=headers).json()["members"]
    removed = client.patch(f'/api/scim/v2/Groups/{group["id"]}', json={"Operations": [
        {"op": "remove", "path": f'members[value eq "{user["id"]}"]'}]}, headers=headers)
    assert removed.status_code == 200
    with app.state.session_factory() as db:
        assert db.get(User, row.user_id).permissions == {}
        assert db.get(AuthSession, session_id).revoked_at is not None
    assert client.patch(f'/api/scim/v2/Users/{user["id"]}', json={"Operations": [{"op": "replace", "path": "active", "value": False}]}, headers=headers).status_code == 200


def test_assurance_rejects_missing_or_weak_verified_claims():
    requirements = {"required_acr": ["urn:company:mfa"], "required_amr": ["mfa"]}
    for claims in [{}, {"acr": "weak", "amr": ["mfa"]}, {"acr": "urn:company:mfa", "amr": ["pwd"]}, {"acr": "urn:company:mfa", "amr": "mfa"}]:
        with pytest.raises(SSOFailure):
            _verify_authentication_assurance(requirements, claims)
    _verify_authentication_assurance(requirements, {"acr": "urn:company:mfa", "amr": ["pwd", "mfa"]})


def test_scim_malformed_input_is_atomic_and_permissions_remain_provisioned(identity):
    client, app, settings, headers = scim(identity)
    admin = setup_admin(client)
    invalid = client.post('/api/scim/v2/Users', headers=headers, json={
        'userName': 'invalid@example.com', 'emails': [{'value': 123}]})
    assert invalid.status_code == 400
    assert client.get('/api/scim/v2/Users', headers=headers).json()['totalResults'] == 0
    user = client.post('/api/scim/v2/Users', headers=headers, json={
        'userName': 'managed@example.com', 'externalId': 'CaseExact'}).json()
    assert client.get('/api/scim/v2/Users', params={'filter': 'externalId eq "caseexact"'}, headers=headers).json()['totalResults'] == 0
    group = client.post('/api/scim/v2/Groups', headers=headers, json={'displayName': 'Group', 'active': True})
    assert group.status_code == 400
    assert client.patch(f'/api/scim/v2/Users/{user["id"]}', headers=headers,
        json={'Operations': [{'op': 'replace', 'path': {'bad': 'type'}, 'value': 'x'}]}).status_code == 400
    listed = client.get('/api/auth/users')
    assert listed.status_code == 200
    managed = next(item for item in listed.json()['users'] if item['email'] == 'managed@example.com')
    assert managed['permissions_source'] == 'scim'
    assert client.patch(f'/api/auth/users/{managed["id"]}', json={'permissions': {'work': {'role': 'manager', 'scope_ids': ['project-a']}}},
        headers=origin_headers(admin['csrf_token'])).status_code == 409
    unchanged = client.patch(f'/api/auth/users/{managed["id"]}', json={'name': 'Rename', 'permissions': {}},
        headers=origin_headers(admin['csrf_token']))
    assert unchanged.status_code == 200 and unchanged.json()['permissions_source'] == 'scim'


def test_mail_queue_encrypted_delivery_retry_and_expiry(identity, monkeypatch):
    from ordivant_identity.enterprise import deliver_mail
    client, app, settings = identity
    object.__setattr__(settings, "smtp_host", "local-mail-sink")
    object.__setattr__(settings, "smtp_sender", "noreply@example.com")
    object.__setattr__(settings, "smtp_starttls", False)
    admin = setup_admin(client)
    invitation = client.post("/api/auth/invitations", json={"email": "invite@example.com", "name": "Invite", "role": "member", "permissions": {}},
        headers=origin_headers(admin["csrf_token"])).json()
    assert invitation["mail_queued"]
    with app.state.session_factory() as db:
        queued = db.scalar(select(MailOutbox))
        assert invitation["invitation_code"] not in queued.payload_ciphertext
        queued_id = queued.id
    sent = []
    class Sink:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def send_message(self, message): sent.append(message)
    monkeypatch.setattr("smtplib.SMTP", Sink)
    deliver_mail(app.state.session_factory, settings)
    assert len(sent) == 1 and invitation["invitation_code"] in sent[0].get_content()
    with app.state.session_factory() as db:
        assert db.get(MailOutbox, queued_id).status == "sent"
        assert db.get(MailOutbox, queued_id).payload_ciphertext == ""
    requests = [client.post("/api/auth/request-recovery", json={"email": email}, headers=origin_headers()).json()
                for email in ["admin@example.com", "nonexistent@example.com"]]
    assert requests[0] == requests[1] == {"accepted": True}
    with app.state.session_factory() as db:
        recovery = db.scalar(select(MailOutbox).where(MailOutbox.kind == "recovery"))
        payload = __import__("json").loads(_decrypt(settings, recovery.payload_ciphertext, b"mail"))
        credential = db.scalar(select(RecoveryMailCredential))
        credential.expires_at = _now() - timedelta(seconds=1)
        db.commit()
    expired = client.post("/api/auth/recover", json={"email": "admin@example.com", "recovery_code": payload["code"], "new_password": "Synthetic replacement password 8!"}, headers=origin_headers())
    assert expired.status_code == 401


def test_audit_export_excludes_unknown_details_and_retention_is_explicit(identity):
    client, app, _ = identity
    admin = setup_admin(client)
    with app.state.session_factory() as db:
        db.add(IdentityAuditEvent(id="old-event", action="old", details={"password": "must-not-export", "kind": "test"},
            created_at=_now() - timedelta(days=400)))
        db.commit()
    output = client.get("/api/auth/audit/export")
    assert output.status_code == 200 and "must-not-export" not in output.text
    assert client.post("/api/auth/audit/retention", headers=origin_headers()).status_code == 403
    result = client.post("/api/auth/audit/retention", headers=origin_headers(admin["csrf_token"]))
    assert result.json()["deleted"] == 1


def test_audit_export_cursor_preserves_equal_timestamps(identity):
    import json
    client, app, _ = identity
    setup_admin(client)
    instant = _now() - timedelta(days=2)
    with app.state.session_factory() as db:
        for ident in ["export-a", "export-b", "export-c"]:
            db.add(IdentityAuditEvent(id=ident, action="cursor-test", details={}, created_at=instant))
        db.commit()
    first = client.get("/api/auth/audit/export", params={"limit": 2, "before": (instant + timedelta(seconds=1)).isoformat()})
    assert first.status_code == 200
    initial_ids = [json.loads(line)["id"] for line in first.text.splitlines()]
    assert initial_ids == ["export-a", "export-b"]
    second = client.get("/api/auth/audit/export", params={"limit": 2, "before": first.headers["X-Next-Before"], "before_id": first.headers["X-Next-Before-Id"]})
    assert [json.loads(line)["id"] for line in second.text.splitlines()] == ["export-c"]
    assert "no-store" in second.headers["cache-control"]
    assert client.get("/api/auth/audit/export", params={"before_id": "export-b"}).status_code == 422
