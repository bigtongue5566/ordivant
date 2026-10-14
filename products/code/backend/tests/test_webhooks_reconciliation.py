from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from sqlalchemy import select

from conftest import auth
from ordivant_code.config import GiteaConfig
from ordivant_code.db import SessionLocal
from ordivant_code.errors import DomainError
from ordivant_code.models import AuditEvent, CheckReceipt, PullRequest
from ordivant_code.schemas import CheckCreate, FileCommit, PullRequestCreate
from ordivant_code.security import new_id
from ordivant_code import service
from ordivant_code.collaboration_models import CollaborationNotification, CollaborationSubscription


def test_webhook_signature_delivery_dedupe_and_binding(repository):
    config = GiteaConfig("http://127.0.0.1:3001", "upstream-secret", "hook-secret")
    body_object = {
        "repository": {
            "full_name": f"{repository['owner']}/{repository['name']}",
            "owner": {"login": repository["owner"]},
            "name": repository["name"],
        },
        "sha": "d" * 40,
        "context": "agent-review",
        "state": "success",
        "description": "Agent-reported result",
    }
    body = json.dumps(body_object, separators=(",", ":")).encode()
    signature = hmac.new(config.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    with SessionLocal() as session:
        with pytest.raises(DomainError) as forged:
            service.process_webhook(session, body, "0" * 64, "delivery-security-test", "status", config)
        assert forged.value.status_code == 401
        accepted = service.process_webhook(session, body, signature, "delivery-security-test", "status", config)
        duplicate = service.process_webhook(session, body, signature, "delivery-security-test", "status", config)
        assert accepted == {"received": True, "duplicate": False}
        assert duplicate == {"received": True, "duplicate": True}
        changed = body.replace(b"Agent-reported result", b"different body")
        changed_signature = hmac.new(config.webhook_secret.encode(), changed, hashlib.sha256).hexdigest()
        with pytest.raises(DomainError) as replay:
            service.process_webhook(session, changed, changed_signature, "delivery-security-test", "status", config)
        assert replay.value.status_code == 409
        receipt = session.scalar(select(CheckReceipt).where(CheckReceipt.commit_sha == "d" * 40))
        assert receipt is not None and receipt.source == "gitea_webhook"
        events = session.scalars(select(AuditEvent).where(AuditEvent.project_id == repository["project_id"])).all()
        matching = next(event for event in events if event.action == "code.gitea_status" and event.data.get("delivery_id") == "delivery-security-test")
        assert "Agent-reported result" not in json.dumps(matching.data)
        assert "upstream-secret" not in json.dumps(matching.data)


def test_pull_webhook_emits_to_local_pull_uuid_without_changing_audit_identity(repository, credentials):
    config = GiteaConfig("http://127.0.0.1:3001", "upstream-secret", "hook-secret")
    number = 37
    body_object = {
        "repository": {
            "full_name": f"{repository['owner']}/{repository['name']}",
            "owner": {"login": repository["owner"]},
            "name": repository["name"],
        },
        "pull_request": {
            "number": number,
            "title": "Webhook collaboration event",
            "body": "",
            "state": "open",
            "head": {"ref": "topic", "sha": "a" * 40},
            "base": {"ref": "main", "sha": "b" * 40},
            "html_url": "http://127.0.0.1:3001/demo/pulls/37",
            "created_at": "2026-10-14T00:00:00Z",
            "updated_at": "2026-10-14T00:00:00Z",
        },
    }
    body = json.dumps(body_object, separators=(",", ":")).encode()
    signature = hmac.new(config.webhook_secret.encode(), body, hashlib.sha256).hexdigest()

    with SessionLocal() as session:
        service.process_webhook(session, body, signature, "delivery-pull-bridge", "pull_request", config)
        pull = session.scalar(select(PullRequest).where(
            PullRequest.repository_id == repository["id"], PullRequest.number == number,
        ))
        assert pull is not None
        session.add(CollaborationSubscription(
            id=new_id(), resource_kind="pull", resource_id=pull.id, principal_id=credentials["manager_id"],
        ))
        session.commit()

    # A later delivery reaches the local PR subscribers while retaining the upstream number in audit history.
    body_object["pull_request"]["title"] = "Webhook collaboration event updated"
    body = json.dumps(body_object, separators=(",", ":")).encode()
    signature = hmac.new(config.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    with SessionLocal() as session:
        service.process_webhook(session, body, signature, "delivery-pull-bridge-2", "pull_request", config)
        pull = session.scalar(select(PullRequest).where(
            PullRequest.repository_id == repository["id"], PullRequest.number == number,
        ))
        webhook_audit = session.scalar(select(AuditEvent).where(
            AuditEvent.action == "code.gitea_pull_request",
            AuditEvent.data["delivery_id"].as_string() == "delivery-pull-bridge-2",
        ))
        notification = session.scalar(select(CollaborationNotification).where(
            CollaborationNotification.resource_kind == "pull",
            CollaborationNotification.resource_id == pull.id,
            CollaborationNotification.event_id == webhook_audit.id,
        ))
        assert webhook_audit.entity_id == str(number)
        assert webhook_audit.data["repository_id"] == repository["id"]
        assert webhook_audit.data["pull_number"] == number
        assert notification is not None
        assert notification.principal_id == credentials["manager_id"]
        assert notification.actor_id is None
        session.commit()


class CommitResponseLost:
    def __init__(self):
        self.commit_attempts = 0
        self.commit_message = ""
        self.content = None

    def branch(self, owner, repo, name):
        return {"name": name, "commit": {"id": "c" * 40}}

    def file(self, owner, repo, path, ref):
        if not self.commit_message:
            raise DomainError(404, "gitea_resource_not_found", "missing")
        return {"sha": "f" * 40}

    def commits_for_path(self, owner, repo, path, branch):
        if not self.commit_message:
            raise DomainError(404, "gitea_resource_not_found", "no file history yet")
        return [{"sha": "a" * 40, "commit": {"message": self.commit_message}}]

    def commit_file(self, owner, repo, *, path, branch, content, message, sha):
        self.commit_attempts += 1
        self.commit_message = message
        self.content = content
        raise DomainError(502, "gitea_unavailable", "simulated lost response")


class PullResponseLost:
    def __init__(self):
        self.create_attempts = 0
        self.items = []

    def pulls(self, owner, repo):
        return self.items

    def create_pull(self, owner, repo, *, head, base, title, body):
        self.create_attempts += 1
        self.items.append({
            "number": 12, "title": title, "body": body, "state": "open",
            "head": {"ref": head, "sha": "b" * 40}, "base": {"ref": base, "sha": "c" * 40},
            "html_url": "http://127.0.0.1:3001/demo/repo/pulls/12",
            "created_at": "2026-10-06T00:00:00Z", "updated_at": "2026-10-06T00:00:00Z",
        })
        raise DomainError(502, "gitea_unavailable", "simulated lost response")


class CheckResponseLost:
    def __init__(self):
        self.create_attempts = 0
        self.items = []

    def statuses(self, owner, repo, sha):
        return self.items

    def create_status(self, owner, repo, *, sha, context, state, description, target_url):
        self.create_attempts += 1
        self.items.append({"description": description, "id": 123})
        raise DomainError(502, "gitea_unavailable", "simulated lost response")


def test_lost_file_commit_response_reconciles_without_second_commit(repository, credentials, monkeypatch):
    client = CommitResponseLost()
    monkeypatch.setattr(service, "_gitea", lambda: client)
    route = f"/api/repositories/{repository['id']}/files"
    key = f"lost-file-{new_id()}"
    exact_content = "  leading indentation\nsecond line\n"
    payload = FileCommit(branch="main", path="docs/readme.md", content=exact_content, commit_message="Add doc")
    assert payload.content == exact_content
    with SessionLocal() as session:
        principal = session.get(service.Principal, credentials["writer_id"])
        with pytest.raises(DomainError) as lost:
            service.commit_file(session, principal, repository["id"], route, key, payload)
        assert lost.value.status_code == 502
    with SessionLocal() as session:
        principal = session.get(service.Principal, credentials["writer_id"])
        result = service.commit_file(session, principal, repository["id"], route, key, payload)
        duplicate = service.commit_file(session, principal, repository["id"], route, key, payload)
    assert result["commit_sha"] == "a" * 40
    assert result == duplicate
    assert client.commit_attempts == 1
    assert client.content == exact_content


def test_file_history_404_is_only_empty_for_new_file(repository, credentials, monkeypatch):
    class ExistingFileHistoryMissing:
        def branch(self, owner, repo, name):
            return {"name": name, "commit": {"id": "c" * 40}}

        def file(self, owner, repo, path, ref):
            return {"sha": "f" * 40}

        def commits_for_path(self, owner, repo, path, branch):
            raise DomainError(404, "gitea_resource_not_found", "path history missing")

    client = ExistingFileHistoryMissing()
    monkeypatch.setattr(service, "_gitea", lambda: client)
    route = f"/api/repositories/{repository['id']}/files"
    with SessionLocal() as session:
        principal = session.get(service.Principal, credentials["writer_id"])
        with pytest.raises(DomainError) as history_missing:
            service.commit_file(
                session, principal, repository["id"], route, f"update-{new_id()}",
                FileCommit(branch="main", path="existing.txt", content="new", commit_message="Update", expected_sha="f" * 40),
            )
        assert history_missing.value.status_code == 404


def test_lost_pull_response_reconciles_by_intent_marker(repository, credentials, monkeypatch):
    client = PullResponseLost()
    monkeypatch.setattr(service, "_gitea", lambda: client)
    route = f"/api/repositories/{repository['id']}/pulls"
    key = f"lost-pr-{new_id()}"
    payload = PullRequestCreate(head="topic", title="Review this", body="Evidence")
    with SessionLocal() as session:
        principal = session.get(service.Principal, credentials["writer_id"])
        with pytest.raises(DomainError) as lost:
            service.create_pull(session, principal, repository["id"], route, key, payload)
        assert lost.value.status_code == 502
    with SessionLocal() as session:
        principal = session.get(service.Principal, credentials["writer_id"])
        result = service.create_pull(session, principal, repository["id"], route, key, payload)
        duplicate = service.create_pull(session, principal, repository["id"], route, key, payload)
        count = session.scalar(select(PullRequest).where(PullRequest.repository_id == repository["id"]))
        assert count is not None
    assert result["number"] == 12
    assert result["body"] == "Evidence"
    assert duplicate == result
    assert client.create_attempts == 1


def test_lost_status_response_reconciles_and_keeps_agent_reported_label(repository, credentials, monkeypatch):
    client = CheckResponseLost()
    monkeypatch.setattr(service, "_gitea", lambda: client)
    route = f"/api/repositories/{repository['id']}/checks"
    key = f"lost-check-{new_id()}"
    payload = CheckCreate(commit_sha="e" * 40, context="agent.review", state="success", description="Reviewed")
    with SessionLocal() as session:
        principal = session.get(service.Principal, credentials["writer_id"])
        with pytest.raises(DomainError):
            service.report_check(session, principal, repository["id"], route, key, payload)
    with SessionLocal() as session:
        principal = session.get(service.Principal, credentials["writer_id"])
        result = service.report_check(session, principal, repository["id"], route, key, payload)
        stored = session.scalar(select(CheckReceipt).where(CheckReceipt.id == result["id"]))
    assert result["source"] == "agent_reported"
    assert stored is not None and stored.source == "agent_reported"
    assert client.create_attempts == 1
