import base64
from sqlalchemy import select
from conftest import create_task, headers
from ordivant.models import ProjectMembership
from ordivant.collaboration_models import CollaborationAttachment, CollaborationNotification


def test_attachment_replay_scope_and_safe_download(api_client, system):
    task = create_task(api_client, system)
    path = f"/api/collaboration/task/{task['id']}"
    payload = {"filename": "team-notes.html", "content_base64": base64.b64encode(b"<script>alert(1)</script>").decode()}
    first = api_client.post(path + "/attachments", json=payload, headers=headers(system, "worker_a", "upload-once"))
    assert first.status_code == 201, first.text
    replay = api_client.post(path + "/attachments", json=payload, headers=headers(system, "worker_a", "upload-once"))
    assert replay.json()["id"] == first.json()["id"]
    changed = api_client.post(path + "/attachments", json={**payload, "filename": "other.html"}, headers=headers(system, "worker_a", "upload-once"))
    assert changed.status_code == 409
    assert api_client.post(path + "/attachments", json={**payload, "filename": "../escape"}, headers=headers(system, "worker_a", "bad-path")).status_code == 422
    attachment_id = first.json()["id"]
    download = f"/api/collaboration/attachments/{attachment_id}/download"
    assert api_client.get(download, headers=headers(system, "outsider")).status_code == 404
    response = api_client.get(download, headers=headers(system, "worker_a"))
    assert response.content == b"<script>alert(1)</script>"
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["x-content-type-options"] == "nosniff"
    with system["factory"]() as db:
        assert len(db.scalars(select(CollaborationAttachment)).all()) == 1


def test_mentions_subscription_notifications_recheck_revoked_scope(api_client, system):
    task = create_task(api_client, system)
    path = f"/api/collaboration/task/{task['id']}"
    follow = api_client.post(path + "/subscription", json={"subscribed": True}, headers=headers(system, "worker_b", "follow"))
    assert follow.status_code == 200
    people = api_client.get(path + "/participants", headers=headers(system, "worker_a")).json()
    assert all(person["id"] != system["ids"]["outsider"] for person in people)
    outsider = system["ids"]["outsider"]
    assert api_client.post(path + "/discussion", json={"body": "Out of scope", "mention_ids": [outsider]}, headers=headers(system, "worker_a", "invalid-mention")).status_code == 422
    sent = api_client.post(path + "/discussion", json={"body": "Please inspect this draft", "mention_ids": [system["ids"]["reviewer"]]}, headers=headers(system, "worker_a", "mention"))
    assert sent.status_code == 201
    for role in ("worker_b", "reviewer"):
        notices = api_client.get("/api/collaboration/notifications", headers=headers(system, role)).json()
        assert len(notices) == 1 and notices[0]["body"] == "Please inspect this draft"
        if role == "worker_b":
            recipient_notice = notices[0]["id"]
    assert api_client.post(f"/api/collaboration/notifications/{recipient_notice}/read", headers=headers(system, "reviewer", "wrong-owner")).status_code == 404
    with system["factory"]() as db:
        membership = db.scalar(select(ProjectMembership).where(ProjectMembership.project_id == task["project_id"], ProjectMembership.principal_id == system["ids"]["worker_b"]))
        db.delete(membership)
        db.commit()
    assert api_client.get("/api/collaboration/notifications", headers=headers(system, "worker_b")).json() == []
    assert api_client.get(path + "/discussion", headers=headers(system, "worker_b")).status_code == 404


def test_task_updates_notify_once_in_business_transaction(api_client, system):
    task = create_task(api_client, system)
    path = f"/api/collaboration/task/{task['id']}"
    api_client.post(path + "/subscription", json={"subscribed": True}, headers=headers(system, "worker_a", "follow-task"))
    for _ in range(2):
        changed = api_client.patch(f"/api/tasks/{task['id']}", json={"description": "Updated acceptance"}, headers=headers(system, "manager", "edit-once"))
        assert changed.status_code == 200
    notifications = api_client.get("/api/collaboration/notifications", headers=headers(system, "worker_a")).json()
    assert len(notifications) == 1 and notifications[0]["event"] == "task.updated"
