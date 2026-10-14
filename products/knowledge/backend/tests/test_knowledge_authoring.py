from __future__ import annotations

import base64

from pycrdt import Doc, Text
from sqlalchemy import inspect, text

from ordivant_knowledge.db import make_engine, migrate_schema

from conftest import auth, client_for


def create_document(client, writer: str, space_id: str, title: str, body: str, *, parent_id: str | None = None) -> dict:
    response = client.post(
        "/api/documents",
        headers=auth(writer, f"create-{title.lower().replace(' ', '-')}-{parent_id or 'root'}"),
        json={
            "space_id": space_id,
            "title": title,
            "body": body,
            "parent_id": parent_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_parent_tree_enforces_space_and_prevents_cycles_and_archive_hides(system):
    bootstrap = system["bootstrap"]
    writer = bootstrap["writer_token"]
    manager = bootstrap["manager_token"]
    primary = bootstrap["primary_scope_id"]
    isolated = bootstrap["isolated_scope_id"]
    with client_for(system) as client:
        root = create_document(client, writer, primary, "Tree root", "Root body.")
        root_id = root["document"]["id"]
        child = create_document(client, writer, primary, "Tree child", "Child body.", parent_id=root_id)
        child_id = child["document"]["id"]
        other_space = create_document(client, manager, isolated, "Other space parent", "Separate space body.")
        other_space_id = other_space["document"]["id"]
        assert child["document"]["parent_id"] == root_id

        cross_space = client.post(
            "/api/documents",
            headers=auth(manager, "create-cross-space-parent"),
            json={"space_id": primary, "parent_id": other_space_id, "title": "Invalid", "body": "body"},
        )
        assert cross_space.status_code == 404
        hidden_space = client.post(
            "/api/documents",
            headers=auth(writer, "create-other-space-parent"),
            json={"space_id": isolated, "parent_id": root_id, "title": "Invalid", "body": "body"},
        )
        assert hidden_space.status_code == 404

        cycle = client.patch(
            f"/api/documents/{root_id}/organization",
            headers=auth(writer, "make-document-cycle"),
            json={"parent_id": child_id},
        )
        assert cycle.status_code == 409
        assert cycle.json()["detail"]["code"] == "document_tree_cycle"

        assert client.patch(
            f"/api/documents/{root_id}/organization",
            headers=auth(writer, "archive-root-with-child"),
            json={"archived": True},
        ).json()["detail"]["code"] == "document_has_children"

        archived = client.patch(
            f"/api/documents/{child_id}/organization",
            headers=auth(writer, "archive-child"),
            json={"archived": True},
        )
        assert archived.status_code == 200
        visible_ids = {item["id"] for item in client.get("/api/documents", params={"space_id": primary}, headers=auth(writer)).json()}
        all_ids = {item["id"] for item in client.get("/api/documents", params={"space_id": primary, "include_archived": True}, headers=auth(writer)).json()}
        assert child_id not in visible_ids
        assert {root_id, child_id} <= all_ids


def test_comments_quotes_replies_reader_permissions_and_templates(system):
    bootstrap = system["bootstrap"]
    writer = bootstrap["writer_token"]
    reader = bootstrap["reader_token"]
    primary = bootstrap["primary_scope_id"]
    with client_for(system) as client:
        document = create_document(client, writer, primary, "Comments", "Quoted phrase lives here.")
        document_id = document["document"]["id"]
        comment_path = f"/api/documents/{document_id}/comments"

        assert client.get(comment_path, headers=auth(reader)).json() == []
        denied = client.post(comment_path, headers=auth(reader), json={"body": "Reader cannot write."})
        assert denied.status_code == 403

        created = client.post(
            comment_path,
            headers=auth(writer, "create-comment-with-quote"),
            json={
                "body": "<script>alert('x')</script> plain text stays inert",
                "anchor": {"quote": "Quoted phrase", "start": 0, "end": 13, "version": 1},
            },
        )
        assert created.status_code == 201, created.text
        parent = created.json()
        assert parent["body"].startswith("<script>")
        assert parent["anchor"] == {"quote": "Quoted phrase", "start": 0, "end": 13, "version": 1}
        assert parent["anchor_stale"] is False

        reply = client.post(
            comment_path,
            headers=auth(writer, "reply-to-comment"),
            json={"body": "Reply body", "parent_id": parent["id"]},
        )
        assert reply.status_code == 201, reply.text
        assert reply.json()["parent_id"] == parent["id"]
        assert len(client.get(comment_path, headers=auth(reader)).json()) == 2

        denied_resolve = client.patch(
            f"/api/document-comments/{parent['id']}", headers=auth(reader), json={"resolved": True}
        )
        assert denied_resolve.status_code == 403
        resolved = client.patch(
            f"/api/document-comments/{parent['id']}", headers=auth(writer, "resolve-comment"), json={"resolved": True}
        )
        assert resolved.status_code == 200
        assert resolved.json()["resolved"] is True

        templates_path = f"/api/spaces/{primary}/templates"
        builtins = client.get(templates_path, headers=auth(reader))
        assert builtins.status_code == 200
        assert {item["id"] for item in builtins.json()} >= {"builtin:prd", "builtin:meeting", "builtin:adr", "builtin:sop"}
        custom = client.post(
            templates_path,
            headers=auth(writer, "create-custom-template"),
            json={"name": "Incident review", "description": "Post-incident review", "body": "# Incident\n"},
        )
        assert custom.status_code == 201, custom.text
        reader_templates = client.get(templates_path, headers=auth(reader)).json()
        assert any(item["id"] == custom.json()["id"] for item in reader_templates)
        denied_template = client.post(
            templates_path,
            headers=auth(reader),
            json={"name": "Forbidden", "body": "# No"},
        )
        assert denied_template.status_code == 403


def test_version_diff_restore_is_immutable_compare_and_swap_and_preserves_shared_draft(system):
    bootstrap = system["bootstrap"]
    writer = bootstrap["writer_token"]
    primary = bootstrap["primary_scope_id"]
    with client_for(system) as client:
        document = create_document(client, writer, primary, "Restore target", "Original published body.")
        document_id = document["document"]["id"]
        published = client.post(
            f"/api/documents/{document_id}/versions",
            headers=auth(writer, "publish-second-version"),
            json={"expected_version": 1, "title": "Changed title", "body": "Changed published body.", "change_summary": "Change body."},
        )
        assert published.status_code == 201, published.text
        diff = client.get(
            f"/api/documents/{document_id}/diff",
            params={"from_version": 1, "to_version": 2},
            headers=auth(writer),
        )
        assert diff.status_code == 200
        assert diff.json()["title_changed"] is True
        assert diff.json()["from_title"] == "Restore target"
        assert diff.json()["to_title"] == "Changed title"
        assert "-Original published body." in diff.json()["diff"]
        assert "+Changed published body." in diff.json()["diff"]

        restored = client.post(
            f"/api/documents/{document_id}/restore",
            headers=auth(writer, "restore-version-one"),
            json={"version": 1, "expected_current_version": 2, "change_summary": "Restore checked content."},
        )
        assert restored.status_code == 201, restored.text
        assert restored.json()["version"] == 3
        assert restored.json()["body"] == "Original published body."
        assert len(client.get(f"/api/documents/{document_id}/versions", headers=auth(writer)).json()) == 3
        stale = client.post(
            f"/api/documents/{document_id}/restore",
            headers=auth(writer, "restore-stale-version"),
            json={"version": 1, "expected_current_version": 2},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "stale_version"

        draft_document = create_document(client, writer, primary, "Draft guard", "Published before draft.")
        draft_id = draft_document["document"]["id"]
        draft = client.get(f"/api/documents/{draft_id}/draft", headers=auth(writer)).json()
        doc = Doc()
        doc.apply_update(base64.b64decode(draft["update"], validate=True))
        text_value = doc.get("body", type=Text)
        text_value += " uncommitted collaboration change"
        update = base64.b64encode(doc.get_update()).decode("ascii")
        changed = client.post(
            f"/api/documents/{draft_id}/draft/updates",
            headers=auth(writer, "update-unpublished-draft"),
            json={"update": update},
        )
        assert changed.status_code == 200, changed.text
        blocked = client.post(
            f"/api/documents/{draft_id}/restore",
            headers=auth(writer, "restore-would-overwrite-draft"),
            json={"version": 1, "expected_current_version": 1},
        )
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "draft_has_unpublished_changes"
        current = client.get(f"/api/documents/{draft_id}", headers=auth(writer)).json()
        assert current["document"]["current_version"] == 1
        assert current["version"]["body"] == "Published before draft."
        assert len(client.get(f"/api/documents/{draft_id}/versions", headers=auth(writer)).json()) == 1


def test_additive_migration_preserves_legacy_document_rows(tmp_path):
    database_file = tmp_path / "legacy-knowledge.sqlite3"
    engine = make_engine(f"sqlite:///{database_file.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE documents ("
            "id VARCHAR(36) PRIMARY KEY, space_id VARCHAR(80) NOT NULL, title VARCHAR(300) NOT NULL, "
            "summary TEXT NOT NULL, tags JSON NOT NULL, current_version INTEGER NOT NULL, "
            "created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO documents (id,space_id,title,summary,tags,current_version,created_at,updated_at) "
            "VALUES ('legacy-id','legacy-space','Legacy title','Legacy summary','[]',4,'then','then')"
        ))

    migrate_schema(engine)
    with engine.connect() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("documents")}
        row = connection.execute(text("SELECT id,title,summary,current_version,parent_id,archived FROM documents WHERE id='legacy-id'")).one()
        indexes = {index["name"] for index in inspect(connection).get_indexes("documents")}
    assert {"parent_id", "archived"} <= columns
    assert row == ("legacy-id", "Legacy title", "Legacy summary", 4, None, False)
    assert "ix_documents_parent" in indexes
    engine.dispose()
