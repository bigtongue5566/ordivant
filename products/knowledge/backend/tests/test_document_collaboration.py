from __future__ import annotations

import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from pycrdt import Doc, Text
from starlette.websockets import WebSocketDisconnect

from ordivant_knowledge import collaboration, drafts, identity
from ordivant_knowledge.errors import DomainError
from ordivant_knowledge.main import create_app
from ordivant_knowledge.models import CollaborationPresence, Document, DocumentDraft, Principal, SpaceMembership
from sqlalchemy import func, select

from conftest import auth, client_for


def create_document(system) -> str:
    bootstrap = system["bootstrap"]
    with client_for(system) as client:
        response = client.post(
            "/api/documents",
            headers=auth(bootstrap["writer_token"], "create-collaborative-document"),
            json={
                "space_id": bootstrap["primary_scope_id"],
                "title": "Shared draft",
                "body": "Published base.",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()["document"]["id"]


def make_update(encoded_state: str, suffix: str) -> str:
    doc = Doc()
    doc.apply_update(base64.b64decode(encoded_state, validate=True))
    text = doc.get("body", type=Text)
    text += suffix
    return base64.b64encode(doc.get_update()).decode("ascii")


def configure_identity(monkeypatch, system, *, role="writer", scope_ids=None, introspect=None):
    monkeypatch.setenv("ORDIVANT_AUTH_ORIGINS", "https://suite.example")
    monkeypatch.setattr(identity, "identity_configured", lambda: True)
    monkeypatch.setattr(identity, "_configuration", lambda: ("ordivant_session", "http://identity.test", "synthetic-service-token"))
    bootstrap = system["bootstrap"]
    user = {
        "id": "knowledge-collaboration-human",
        "name": "Human Collaborator",
        "active": True,
        "role": "member",
        "permissions": {
            "knowledge": {
                "role": role,
                "scope_ids": list(scope_ids if scope_ids is not None else [bootstrap["primary_scope_id"]]),
            }
        },
    }

    async def default_introspect(_identity_url, _service_token, session_token):
        assert session_token == "synthetic-session"
        return user, "synthetic-csrf"

    monkeypatch.setattr(identity, "_introspect", introspect or default_introspect)
    return user


def open_collaboration(client: TestClient, document_id: str):
    client.cookies.set("ordivant_session", "synthetic-session")
    return client.websocket_connect(
        f"/api/documents/{document_id}/collaborate",
        headers={"Origin": "https://suite.example"},
    )


def authenticate_socket(socket) -> dict[str, object]:
    socket.send_json({"type": "authenticate", "csrf_token": "synthetic-csrf"})
    result = socket.receive_json()
    assert result["type"] == "sync", result
    return result


def test_concurrent_crdt_updates_guard_legacy_publish_and_publish_by_revision(system):
    document_id = create_document(system)
    bootstrap = system["bootstrap"]
    writer = bootstrap["writer_token"]
    with client_for(system) as client:
        initial = client.get(f"/api/documents/{document_id}/draft", headers=auth(writer))
        assert initial.status_code == 200, initial.text
        assert initial.json()["body"] == "Published base."
        assert initial.json()["revision"] == initial.json()["published_revision"] == 0
        branches = [make_update(initial.json()["update"], " Writer A."), make_update(initial.json()["update"], " Writer B.")]

    barrier = Barrier(2)

    def apply_update(index: int):
        with client_for(system) as client:
            barrier.wait(timeout=10)
            return client.post(
                f"/api/documents/{document_id}/draft/updates",
                headers=auth(writer, f"collaborative-update-{index}"),
                json={"update": branches[index]},
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(apply_update, [0, 1]))
    assert [response.status_code for response in responses] == [200, 200]
    with client_for(system) as client:
        draft_response = client.get(f"/api/documents/{document_id}/draft", headers=auth(writer))
        assert draft_response.status_code == 200
        draft = draft_response.json()
        assert "Writer A." in draft["body"]
        assert "Writer B." in draft["body"]
        assert draft["revision"] == 2

        old_publish = client.post(
            f"/api/documents/{document_id}/versions",
            headers=auth(writer, "legacy-publish-cannot-overwrite-draft"),
            json={
                "expected_version": 1,
                "body": "This would discard shared edits.",
                "change_summary": "Must be rejected.",
            },
        )
        assert old_publish.status_code == 409
        assert old_publish.json()["detail"]["code"] == "draft_has_unpublished_changes"

        stale = client.post(
            f"/api/documents/{document_id}/draft/publish",
            headers=auth(writer, "stale-draft-publish"),
            json={"expected_revision": 1, "change_summary": "Stale editor publish."},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "stale_draft_revision"

        body = {"expected_revision": 2, "change_summary": "Publish merged team edits."}
        published = client.post(
            f"/api/documents/{document_id}/draft/publish",
            headers=auth(writer, "publish-merged-draft"),
            json=body,
        )
        assert published.status_code == 201, published.text
        assert published.json()["version"] == 2
        assert "Writer A." in published.json()["body"]
        assert "Writer B." in published.json()["body"]
        replay = client.post(
            f"/api/documents/{document_id}/draft/publish",
            headers=auth(writer, "publish-merged-draft"),
            json=body,
        )
        assert replay.status_code == 201
        assert replay.json() == published.json()

        final_draft = client.get(f"/api/documents/{document_id}/draft", headers=auth(writer)).json()
        assert final_draft["base_version"] == 2
        assert final_draft["revision"] == final_draft["published_revision"] == 3
        versions = client.get(f"/api/documents/{document_id}/versions", headers=auth(writer)).json()
        assert [item["version"] for item in versions] == [2, 1]
        assert client.get(f"/api/documents/{document_id}/draft", headers=auth(bootstrap["reader_token"])).status_code == 200
        assert client.post(
            f"/api/documents/{document_id}/draft/updates",
            headers=auth(bootstrap["reader_token"]),
            json={"update": branches[0]},
        ).status_code == 403
        with system["app"].state.session_factory() as session:
            membership = session.scalar(
                select(SpaceMembership).where(
                    SpaceMembership.principal_id == bootstrap["reader_id"],
                    SpaceMembership.space_id == bootstrap["primary_scope_id"],
                )
            )
            assert membership is not None
            session.delete(membership)
            session.add(
                SpaceMembership(
                    id=f"{bootstrap['reader_id']}:{bootstrap['isolated_scope_id']}",
                    principal_id=bootstrap["reader_id"],
                    space_id=bootstrap["isolated_scope_id"],
                )
            )
            session.commit()
        assert client.get(
            f"/api/documents/{document_id}/draft", headers=auth(bootstrap["reader_token"])
        ).status_code == 404


def test_draft_updates_are_idempotent_and_invalid_updates_do_not_commit(system):
    document_id = create_document(system)
    bootstrap = system["bootstrap"]
    writer = bootstrap["writer_token"]
    with client_for(system) as client:
        state = client.get(f"/api/documents/{document_id}/draft", headers=auth(writer)).json()
        update = make_update(state["update"], " Replay once.")
        first = client.post(
            f"/api/documents/{document_id}/draft/updates",
            headers=auth(writer, "idempotent-draft-update"),
            json={"update": update},
        )
        replay = client.post(
            f"/api/documents/{document_id}/draft/updates",
            headers=auth(writer, "idempotent-draft-update"),
            json={"update": update},
        )
        assert first.status_code == replay.status_code == 200
        assert replay.json() == first.json()

        changed = make_update(state["update"], " Different payload.")
        conflict = client.post(
            f"/api/documents/{document_id}/draft/updates",
            headers=auth(writer, "idempotent-draft-update"),
            json={"update": changed},
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "idempotency_conflict"

        malformed = client.post(
            f"/api/documents/{document_id}/draft/updates",
            headers=auth(writer, "malformed-draft-update"),
            json={"update": base64.b64encode(b"not a Yjs update").decode("ascii")},
        )
        assert malformed.status_code == 422
        assert malformed.json()["detail"]["code"] == "invalid_draft_update"
        latest = client.get(f"/api/documents/{document_id}/draft", headers=auth(writer)).json()
        assert latest["revision"] == 1
        assert "Replay once." in latest["body"]


def test_draft_update_rate_limit_is_shared_by_rest_clients(system, monkeypatch):
    document_id = create_document(system)
    bootstrap = system["bootstrap"]
    monkeypatch.setattr(drafts, "MAX_DRAFT_UPDATES_PER_WINDOW", 1)
    with client_for(system) as client:
        initial = client.get(f"/api/documents/{document_id}/draft", headers=auth(bootstrap["writer_token"])).json()
        first = client.post(
            f"/api/documents/{document_id}/draft/updates",
            headers=auth(bootstrap["writer_token"], "quota-first-update"),
            json={"update": make_update(initial["update"], " First update.")},
        )
        assert first.status_code == 200
        exceeded = client.post(
            f"/api/documents/{document_id}/draft/updates",
            headers=auth(bootstrap["writer_token"], "quota-second-update"),
            json={"update": make_update(initial["update"], " Second update.")},
        )
        assert exceeded.status_code == 429
        assert exceeded.json()["detail"]["code"] == "rate_limited"
        final = client.get(f"/api/documents/{document_id}/draft", headers=auth(bootstrap["writer_token"])).json()
        assert final["revision"] == 1
        assert "First update." in final["body"]
        assert "Second update." not in final["body"]


def test_shared_draft_update_survives_app_restart(system):
    document_id = create_document(system)
    bootstrap = system["bootstrap"]
    writer = bootstrap["writer_token"]
    with client_for(system) as client:
        state = client.get(f"/api/documents/{document_id}/draft", headers=auth(writer)).json()
        update = make_update(state["update"], " Persisted collaboration.")
        response = client.post(
            f"/api/documents/{document_id}/draft/updates",
            headers=auth(writer, "restart-safe-draft-update"),
            json={"update": update},
        )
        assert response.status_code == 200
        before = response.json()

    restarted_app = create_app(system["database_url"], mode="development")
    with TestClient(restarted_app, client=("127.0.0.1", 50921)) as restarted:
        after = restarted.get(f"/api/documents/{document_id}/draft", headers=auth(writer))
        assert after.status_code == 200
        assert after.json() == before
    restarted_app.state.engine.dispose()


def test_clean_legacy_publish_rebases_live_crdt_without_dropping_offline_update(system):
    document_id = create_document(system)
    writer = system["bootstrap"]["writer_token"]
    with client_for(system) as client:
        initial = client.get(f"/api/documents/{document_id}/draft", headers=auth(writer)).json()
        offline_update = make_update(initial["update"], " Offline teammate edit.")
        published = client.post(
            f"/api/documents/{document_id}/versions",
            headers=auth(writer, "publish-clean-legacy-version"),
            json={
                "expected_version": 1,
                "body": "Published replacement.",
                "change_summary": "Legacy version publish with a clean draft.",
            },
        )
        assert published.status_code == 201, published.text
        rebased = client.get(f"/api/documents/{document_id}/draft", headers=auth(writer)).json()
        assert rebased["base_version"] == 2
        assert rebased["revision"] == rebased["published_revision"] == 1
        assert rebased["body"] == "Published replacement."

        offline = client.post(
            f"/api/documents/{document_id}/draft/updates",
            headers=auth(writer, "merge-offline-edit-after-legacy-publish"),
            json={"update": offline_update},
        )
        assert offline.status_code == 200, offline.text
        assert "Published replacement." in offline.json()["body"]
        assert "Offline teammate edit." in offline.json()["body"]


def test_websocket_auth_ack_reconnect_retry_and_presence(system, monkeypatch):
    document_id = create_document(system)
    configure_identity(monkeypatch, system)
    writer = system["bootstrap"]["writer_token"]
    with client_for(system) as client:
        with open_collaboration(client, document_id) as socket:
            sync = authenticate_socket(socket)
            participant = sync["participants"][0]
            with system["app"].state.session_factory() as session:
                local_principal = session.scalar(select(Principal).where(Principal.name == "Human Collaborator"))
                assert local_principal is not None
            assert participant == {
                "id": local_principal.id,
                "name": "Human Collaborator",
                "kind": "human",
            }
            update = make_update(sync["draft"]["update"], " WebSocket edit.")
            socket.send_json({"type": "update", "request_id": "ws-edit-1", "update": update})
            ack = socket.receive_json()
            assert ack["type"] == "ack"
            assert ack["request_id"] == "ws-edit-1"
            assert "WebSocket edit." in ack["draft"]["body"]
            persisted = client.get(f"/api/documents/{document_id}/draft", headers=auth(writer)).json()
            assert persisted == ack["draft"]

        with open_collaboration(client, document_id) as socket:
            reconnect = authenticate_socket(socket)
            assert reconnect["draft"]["revision"] == 1
            assert "WebSocket edit." in reconnect["draft"]["body"]
            socket.send_json({"type": "update", "request_id": "ws-edit-1", "update": update})
            replay = socket.receive_json()
            assert replay["type"] == "ack"
            assert replay["draft"]["revision"] == 1
            changed = make_update(reconnect["draft"]["update"], " Changed retry payload.")
            socket.send_json({"type": "update", "request_id": "ws-edit-1", "update": changed})
            conflict = socket.receive_json()
            assert conflict["type"] == "error"
            assert conflict["code"] == "request_id_conflict"

        with system["app"].state.session_factory() as session:
            assert session.scalar(
                select(func.count()).select_from(CollaborationPresence).where(CollaborationPresence.document_id == document_id)
            ) == 0
            draft = session.get(DocumentDraft, document_id)
            assert draft is not None
            assert draft.revision == 1


def test_websocket_requires_allowed_origin_cookie_csrf_and_writer_scope(system, monkeypatch):
    document_id = create_document(system)
    configure_identity(monkeypatch, system)
    with client_for(system) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                f"/api/documents/{document_id}/collaborate",
                headers={"Origin": "https://evil.example"},
            ):
                pass

        with client.websocket_connect(
            f"/api/documents/{document_id}/collaborate",
            headers={"Origin": "https://suite.example"},
        ) as socket:
            socket.send_json({"type": "authenticate", "csrf_token": "synthetic-csrf"})
            error = socket.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "unauthenticated"

        with open_collaboration(client, document_id) as socket:
            socket.send_json({"type": "authenticate", "csrf_token": "wrong"})
            error = socket.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "csrf_failed"

        user = configure_identity(monkeypatch, system, role="reader")
        with open_collaboration(client, document_id) as socket:
            sync = authenticate_socket(socket)
            update = make_update(sync["draft"]["update"], " Unauthorized edit.")
            socket.send_json({"type": "update", "request_id": "reader-update", "update": update})
            error = socket.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "forbidden"

        user["permissions"]["knowledge"]["scope_ids"] = [system["bootstrap"]["isolated_scope_id"]]
        with open_collaboration(client, document_id) as socket:
            socket.send_json({"type": "authenticate", "csrf_token": "synthetic-csrf"})
            error = socket.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "not_found"

        user["permissions"]["knowledge"]["scope_ids"] = [system["bootstrap"]["primary_scope_id"]]
        with system["app"].state.session_factory() as session:
            draft = session.get(DocumentDraft, document_id)
            assert draft is not None
            assert draft.revision == 0


def test_websocket_periodically_revalidates_session_and_scope(system, monkeypatch):
    document_id = create_document(system)
    auth_calls = {"count": 0}

    async def expires_after_initial(_identity_url, _service_token, session_token):
        assert session_token == "synthetic-session"
        auth_calls["count"] += 1
        if auth_calls["count"] > 1:
            raise DomainError(401, "unauthenticated", "Identity session expired")
        return (
            {
                "id": "knowledge-collaboration-human",
                "name": "Human Collaborator",
                "active": True,
                "role": "member",
                "permissions": {
                    "knowledge": {
                        "role": "writer",
                        "scope_ids": [system["bootstrap"]["primary_scope_id"]],
                    }
                },
            },
            "synthetic-csrf",
        )

    configure_identity(monkeypatch, system, introspect=expires_after_initial)
    monkeypatch.setattr(collaboration, "REAUTH_SECONDS", 0.01)
    monkeypatch.setattr(collaboration, "DB_POLL_SECONDS", 0.01)
    with client_for(system) as client:
        with open_collaboration(client, document_id) as socket:
            authenticate_socket(socket)
            error = socket.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "unauthenticated"


def test_websocket_closes_after_periodic_scope_revocation(system, monkeypatch):
    document_id = create_document(system)
    user = configure_identity(monkeypatch, system)
    monkeypatch.setattr(collaboration, "REAUTH_SECONDS", 0.01)
    monkeypatch.setattr(collaboration, "DB_POLL_SECONDS", 0.01)
    with client_for(system) as client:
        with open_collaboration(client, document_id) as socket:
            authenticate_socket(socket)
            user["permissions"]["knowledge"]["scope_ids"] = []
            error = socket.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "not_found"


def test_websocket_reads_updates_written_by_another_app_process(system, monkeypatch):
    document_id = create_document(system)
    configure_identity(monkeypatch, system)
    writer = system["bootstrap"]["writer_token"]
    second_app = create_app(system["database_url"], mode="development")
    with client_for(system) as browser:
        with open_collaboration(browser, document_id) as socket:
            initial = authenticate_socket(socket)
            with TestClient(second_app, client=("127.0.0.1", 50923)) as other_process:
                update = make_update(initial["draft"]["update"], " Written by another process.")
                changed = other_process.post(
                    f"/api/documents/{document_id}/draft/updates",
                    headers=auth(writer, "other-process-draft-update"),
                    json={"update": update},
                )
                assert changed.status_code == 200, changed.text
            sync = socket.receive_json()
            assert sync["type"] == "sync"
            assert "Written by another process." in sync["draft"]["body"]
            assert sync["draft"]["revision"] == 1
    second_app.state.engine.dispose()


def test_document_draft_scope_publication_is_atomic(system):
    document_id = create_document(system)
    bootstrap = system["bootstrap"]
    with client_for(system) as client:
        draft = client.get(f"/api/documents/{document_id}/draft", headers=auth(bootstrap["writer_token"])).json()
        update = make_update(draft["update"], " Draft authored by human.")
        changed = client.post(
            f"/api/documents/{document_id}/draft/updates",
            headers=auth(bootstrap["writer_token"], "publish-audited-update"),
            json={"update": update},
        )
        assert changed.status_code == 200
        published = client.post(
            f"/api/documents/{document_id}/draft/publish",
            headers=auth(bootstrap["manager_token"], "manager-publish-draft"),
            json={"expected_revision": 1, "change_summary": "Manager reviewed the shared draft."},
        )
        assert published.status_code == 201
        assert published.json()["version"] == 2
        assert hashlib.sha256(published.json()["body"].encode("utf-8")).hexdigest() == published.json()["content_sha256"]

        events = client.get("/api/events", params={"space_id": bootstrap["primary_scope_id"]}, headers=auth(bootstrap["manager_token"]))
        edit_event = next(item for item in events.json() if item["action"] == "knowledge.document.draft_updated")
        publish_event = next(item for item in events.json() if item["action"] == "knowledge.document.draft_published")
        assert edit_event["data"]["actor_kind"] == "agent"
        assert publish_event["data"]["actor_kind"] == "human"
        assert publish_event["data"]["revision"] == 2


@pytest.mark.parametrize("operation", ["update", "poll"])
def test_websocket_rechecks_local_membership_before_periodic_reauth(system, monkeypatch, operation):
    document_id = create_document(system)
    configure_identity(monkeypatch, system)
    writer = system["bootstrap"]["writer_token"]
    monkeypatch.setattr(collaboration, "REAUTH_SECONDS", 3600)
    monkeypatch.setattr(collaboration, "DB_POLL_SECONDS", 5 if operation == "update" else 0.01)

    with client_for(system) as client:
        with open_collaboration(client, document_id) as socket:
            sync = authenticate_socket(socket)
            with system["app"].state.session_factory() as session:
                principal = session.scalar(select(Principal).where(Principal.name == "Human Collaborator"))
                assert principal is not None
                membership = session.scalar(
                    select(SpaceMembership).where(
                        SpaceMembership.principal_id == principal.id,
                        SpaceMembership.space_id == system["bootstrap"]["primary_scope_id"],
                    )
                )
                assert membership is not None
                session.delete(membership)
                session.commit()

            if operation == "update":
                socket.send_json({
                    "type": "update",
                    "request_id": "membership-revoked-update",
                    "update": make_update(sync["draft"]["update"], " Must be denied."),
                })
            error = socket.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "not_found"

        with system["app"].state.session_factory() as session:
            draft = session.get(DocumentDraft, document_id)
            assert draft is not None
            assert draft.revision == 0


@pytest.mark.parametrize(
    ("principal_change", "expected_code"),
    [("reader", "forbidden"), ("inactive", "not_found")],
)
def test_websocket_cannot_write_after_local_principal_change(system, monkeypatch, principal_change, expected_code):
    document_id = create_document(system)
    configure_identity(monkeypatch, system)
    monkeypatch.setattr(collaboration, "REAUTH_SECONDS", 3600)
    monkeypatch.setattr(collaboration, "DB_POLL_SECONDS", 5)

    with client_for(system) as client:
        with open_collaboration(client, document_id) as socket:
            sync = authenticate_socket(socket)
            with system["app"].state.session_factory() as session:
                principal = session.scalar(select(Principal).where(Principal.name == "Human Collaborator"))
                assert principal is not None
                if principal_change == "reader":
                    principal.role = "reader"
                else:
                    principal.active = False
                session.commit()

            socket.send_json({
                "type": "update",
                "request_id": f"principal-{principal_change}-update",
                "update": make_update(sync["draft"]["update"], " Must be denied."),
            })
            error = socket.receive_json()
            assert error["type"] == "error"
            assert error["code"] == expected_code

    with system["app"].state.session_factory() as session:
        draft = session.get(DocumentDraft, document_id)
        assert draft is not None
        assert draft.revision == 0


@pytest.mark.parametrize("operation", ["update", "publish"])
def test_draft_mutations_recheck_role_after_draft_lock(system, monkeypatch, operation):
    document_id = create_document(system)
    bootstrap = system["bootstrap"]
    writer = bootstrap["writer_token"]
    with client_for(system) as client:
        initial = client.get(f"/api/documents/{document_id}/draft", headers=auth(writer)).json()
        original_ensure_draft = drafts._ensure_draft

        def downgrade_after_draft_lock(session, document):
            draft = original_ensure_draft(session, document)
            principal = session.get(Principal, bootstrap["writer_id"])
            assert principal is not None
            principal.role = "reader"
            session.flush()
            return draft

        monkeypatch.setattr(drafts, "_ensure_draft", downgrade_after_draft_lock)
        if operation == "update":
            response = client.post(
                f"/api/documents/{document_id}/draft/updates",
                headers=auth(writer, "role-changed-after-draft-lock-update"),
                json={"update": make_update(initial["update"], " Must not commit.")},
            )
        else:
            response = client.post(
                f"/api/documents/{document_id}/draft/publish",
                headers=auth(writer, "role-changed-after-draft-lock-publish"),
                json={"expected_revision": 0, "change_summary": "Must not publish."},
            )
        assert response.status_code == 403, response.text

    with system["app"].state.session_factory() as session:
        draft = session.get(DocumentDraft, document_id)
        principal = session.get(Principal, bootstrap["writer_id"])
        document = session.get(Document, document_id)
        assert draft is not None and principal is not None and document is not None
        assert draft.revision == 0
        assert principal.role == "writer"
        assert document.current_version == 1
