from __future__ import annotations

from copy import deepcopy

import pytest
from sqlalchemy import select

from conftest import auth
from ordivant_code import service
from ordivant_code.db import SessionLocal
from ordivant_code.errors import DomainError
from ordivant_code.models import (
    AuditEvent,
    OperationIntent,
    Principal,
    Project,
    PullRequest,
    PullRequestComment,
    PullRequestReview,
    Repository,
)
from ordivant_code.security import new_id, now_utc


class GiteaPullStub:
    def __init__(self, *, number: int, head_sha: str = "a" * 40, state: str = "open"):
        self.item = {
            "number": number,
            "title": "Collaborative PR",
            "body": "Upstream description",
            "state": state,
            "head": {"ref": "topic", "sha": head_sha},
            "base": {"ref": "main", "sha": "b" * 40},
            "html_url": f"http://127.0.0.1:3001/demo/repo/pulls/{number}",
            "created_at": "2026-10-10T00:00:00Z",
            "updated_at": "2026-10-10T00:00:00Z",
            "user": {"id": 9001, "login": "unknown-upstream-user"},
        }
        self.calls = 0

    def pull(self, owner, repo, number):
        self.calls += 1
        assert number == self.item["number"]
        return deepcopy(self.item)


def _stub(monkeypatch, number: int, *, head_sha: str = "a" * 40, state: str = "open"):
    client = GiteaPullStub(number=number, head_sha=head_sha, state=state)
    monkeypatch.setattr(service, "_gitea", lambda: client)
    return client


def _url(repository_id: str, number: int) -> str:
    return f"/api/repositories/{repository_id}/pulls/{number}"


def test_human_and_agent_share_comments_reviews_idempotency_and_audit(api, credentials, repository, monkeypatch):
    remote = _stub(monkeypatch, 311)
    base = _url(repository["id"], 311)
    human_headers = {**auth(credentials["manager_token"]), "Idempotency-Key": "human-comment-311"}
    agent_headers = {**auth(credentials["writer_token"]), "Idempotency-Key": "agent-comment-311"}

    human_comment = api.post(f"{base}/comments", headers=human_headers, json={"body": "Human finding"})
    human_replay = api.post(f"{base}/comments", headers=human_headers, json={"body": "Human finding"})
    assert human_comment.status_code == 200
    assert human_comment.json()["author"]["kind"] == "human"
    assert human_replay.json()["id"] == human_comment.json()["id"]
    assert api.post(f"{base}/comments", headers=human_headers, json={"body": "Changed body"}).status_code == 409

    agent_comment = api.post(f"{base}/comments", headers=agent_headers, json={"body": "Agent finding"})
    assert agent_comment.status_code == 200
    assert agent_comment.json()["author"]["kind"] == "agent"

    human_review = api.post(
        f"{base}/reviews",
        headers={**auth(credentials["manager_token"]), "Idempotency-Key": "human-review-311"},
        json={"decision": "approve", "comment": "Looks good", "expected_head_sha": "a" * 40},
    )
    agent_review_headers = {**auth(credentials["writer_token"]), "Idempotency-Key": "agent-review-311"}
    agent_review = api.post(
        f"{base}/reviews", headers=agent_review_headers,
        json={"decision": "request_changes", "comment": "Fix the edge case", "expected_head_sha": "a" * 40},
    )
    agent_review_replay = api.post(
        f"{base}/reviews", headers=agent_review_headers,
        json={"decision": "request_changes", "comment": "Fix the edge case", "expected_head_sha": "a" * 40},
    )
    assert human_review.status_code == agent_review.status_code == 200
    assert human_review.json()["author"]["kind"] == "human"
    assert agent_review.json()["author"]["kind"] == "agent"
    assert agent_review_replay.json()["id"] == agent_review.json()["id"]

    context = api.get(f"{base}/collaboration", headers=auth(credentials["reader_token"]))
    assert context.status_code == 200
    body = context.json()
    assert body["head_sha"] == "a" * 40
    assert body["proposer"] is None
    assert [item["body"] for item in body["comments"]] == ["Human finding", "Agent finding"]
    assert {item["decision"] for item in body["reviews"]} == {"approve", "request_changes"}
    assert all(item["is_current"] for item in body["reviews"])
    assert remote.calls >= 5

    with SessionLocal() as session:
        assert len(session.scalars(select(PullRequestComment).where(
            PullRequestComment.pull_request_id == body["pull_request_id"],
        )).all()) == 2
        assert len(session.scalars(select(PullRequestReview).where(
            PullRequestReview.pull_request_id == body["pull_request_id"],
        )).all()) == 2
        actions = session.scalars(select(AuditEvent.action).where(
            AuditEvent.project_id == repository["project_id"],
            AuditEvent.entity_id.in_([
                human_comment.json()["id"], agent_comment.json()["id"],
                human_review.json()["id"], agent_review.json()["id"],
            ]),
        )).all()
        assert actions.count("code.pull_request_comment_added") == 2
        assert actions.count("code.pull_request_review_recorded") == 2


def test_verified_creator_can_comment_but_cannot_approve_own_pull(api, credentials, repository, monkeypatch):
    _stub(monkeypatch, 312)
    base = _url(repository["id"], 312)
    assert api.get(f"{base}/collaboration", headers=auth(credentials["manager_token"])).status_code == 200
    with SessionLocal() as session:
        pull = session.scalar(select(PullRequest).where(
            PullRequest.repository_id == repository["id"], PullRequest.number == 312,
        ))
        session.add(AuditEvent(
            id=new_id(), project_id=repository["project_id"], actor_id=credentials["manager_id"],
            action="code.pull_request_created", entity_type="pull_request", entity_id=pull.id,
            data={}, created_at=now_utc(),
        ))
        session.commit()

    context = api.get(f"{base}/collaboration", headers=auth(credentials["reader_token"]))
    assert context.json()["proposer"] == {
        "id": credentials["manager_id"], "name": "code-demo-manager", "kind": "human",
    }
    rejected = api.post(
        f"{base}/reviews",
        headers={**auth(credentials["manager_token"]), "Idempotency-Key": "self-review"},
        json={"decision": "approve", "comment": "", "expected_head_sha": "a" * 40},
    )
    assert rejected.status_code == 403
    assert rejected.json()["detail"]["code"] == "self_review_forbidden"

    comment = api.post(
        f"{base}/reviews",
        headers={**auth(credentials["manager_token"]), "Idempotency-Key": "self-comment-312"},
        json={"decision": "comment", "comment": "One question", "expected_head_sha": "a" * 40},
    )
    assert comment.status_code == 200
    assert comment.json()["decision"] == "comment"


def test_review_requires_current_head_and_open_pr_except_comment(api, credentials, repository, monkeypatch):
    remote = _stub(monkeypatch, 313)
    base = _url(repository["id"], 313)
    first = api.post(
        f"{base}/reviews",
        headers={**auth(credentials["writer_token"]), "Idempotency-Key": "first-review-313"},
        json={"decision": "approve", "comment": "Initial head", "expected_head_sha": "a" * 40},
    )
    assert first.status_code == 200
    remote.item["head"]["sha"] = "c" * 40
    remote.item["state"] = "closed"
    history = api.get(f"{base}/collaboration", headers=auth(credentials["reader_token"]))
    assert history.status_code == 200
    assert history.json()["reviews"][0]["head_sha"] == "a" * 40
    assert history.json()["reviews"][0]["is_current"] is False

    stale = api.post(
        f"{base}/reviews",
        headers={**auth(credentials["writer_token"]), "Idempotency-Key": "stale-review-313"},
        json={"decision": "approve", "comment": "", "expected_head_sha": "a" * 40},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_pull_request_head"

    closed = api.post(
        f"{base}/reviews",
        headers={**auth(credentials["writer_token"]), "Idempotency-Key": "closed-review"},
        json={"decision": "approve", "comment": "", "expected_head_sha": "c" * 40},
    )
    assert closed.status_code == 409
    assert closed.json()["detail"]["code"] == "pull_request_closed"

    comment = api.post(
        f"{base}/reviews",
        headers={**auth(credentials["writer_token"]), "Idempotency-Key": "closed-comment-313"},
        json={"decision": "comment", "comment": "Follow-up only", "expected_head_sha": "c" * 40},
    )
    assert comment.status_code == 200
    assert remote.calls == 5


def test_reader_and_cross_scope_are_rejected_before_gitea(api, credentials, repository, monkeypatch):
    remote = _stub(monkeypatch, 314)
    reader = api.post(
        f"{_url(repository['id'], 314)}/comments",
        headers={**auth(credentials["reader_token"]), "Idempotency-Key": "reader-comment-314"},
        json={"body": "No write access"},
    )
    assert reader.status_code == 403
    assert remote.calls == 0

    with SessionLocal() as session:
        project = session.scalar(select(Project).where(Project.key == "code-isolated-demo"))
        isolated = Repository(
            id=new_id(), project_id=project.id, provider="gitea", owner="demo-owner",
            name=f"isolated-{new_id()[:8]}", default_branch="main", web_url="http://127.0.0.1/repo",
            clone_url="http://127.0.0.1/repo.git", created_at=now_utc(),
        )
        session.add(isolated)
        session.commit()
        isolated_id = isolated.id

    cross_scope = api.get(
        f"{_url(isolated_id, 314)}/collaboration", headers=auth(credentials["writer_token"]),
    )
    assert cross_scope.status_code == 404
    assert remote.calls == 0


def test_inactive_actor_is_rechecked_by_service(repository, credentials):
    with SessionLocal() as session:
        actor = session.get(Principal, credentials["writer_id"])
        actor.active = False
        session.commit()
        with pytest.raises(DomainError) as denied:
            service.comment_on_pull_request(
                session, actor, repository["id"], 315,
                f"{_url(repository['id'], 315)}/comments", "inactive-actor-315",
                service.PullRequestCommentCreate(body="Should not be written"),
            )
        assert denied.value.status_code == 401
    with SessionLocal() as session:
        session.get(Principal, credentials["writer_id"]).active = True
        session.commit()


def test_collaboration_requires_live_gitea_even_when_pull_is_cached(api, credentials, repository, monkeypatch):
    with SessionLocal() as session:
        pull = PullRequest(
            id=new_id(), repository_id=repository["id"], number=316, title="Cached only", body="",
            state="open", head="topic", base="main", web_url="http://127.0.0.1/cached",
            head_sha="d" * 40, source_refs=[], created_at=now_utc(), updated_at=now_utc(),
        )
        session.add(pull)
        session.commit()

    def unavailable():
        raise DomainError(502, "gitea_unavailable", "Gitea is unavailable")

    monkeypatch.setattr(service, "_gitea", unavailable)
    response = api.get(
        f"{_url(repository['id'], 316)}/collaboration", headers=auth(credentials["reader_token"]),
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "gitea_unavailable"


def test_completed_create_intent_can_identify_proposer(api, credentials, repository, monkeypatch):
    _stub(monkeypatch, 317)
    base = _url(repository["id"], 317)
    with SessionLocal() as session:
        session.add(OperationIntent(
            id=new_id(), actor_id=credentials["writer_id"], project_id=repository["project_id"],
            repository_id=repository["id"], route=f"/api/repositories/{repository['id']}/pulls",
            key="historical-pr-create", request_hash="a" * 64, kind="create_pull", request_json={},
            state="complete", lock_until=0, external_id="317", result_json={},
            created_at=now_utc(), updated_at=now_utc(),
        ))
        session.commit()
    response = api.get(f"{base}/collaboration", headers=auth(credentials["reader_token"]))
    assert response.status_code == 200
    assert response.json()["proposer"] == {
        "id": credentials["writer_id"], "name": "code-demo-writer", "kind": "agent",
    }
