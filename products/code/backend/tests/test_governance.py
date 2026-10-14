from __future__ import annotations

from copy import deepcopy

from sqlalchemy import select

from conftest import auth
from ordivant_code import governance, service
from ordivant_code.config import GiteaConfig
from ordivant_code.db import SessionLocal
from ordivant_code.errors import DomainError
from ordivant_code.models import CheckReceipt, Project, PullRequest, Repository
from ordivant_code.security import new_id, now_utc

HEAD = "a" * 40
DIFF = """diff --git a/src/example.py b/src/example.py
index 1234567..abcdef0 100644
--- a/src/example.py
+++ b/src/example.py
@@ -1,2 +1,3 @@
 unchanged = True
-value = 1
+value = 2
+extra = 3
"""


class InlineGitea:
    def __init__(self):
        self.head_sha = HEAD
        self.diff = DIFF
        self.diff_calls = 0

    def pull(self, owner, repo, number):
        return {
            "number": number, "title": "Inline review", "body": "", "state": "open", "mergeable": True,
            "head": {"ref": "topic", "sha": self.head_sha}, "base": {"ref": "main", "sha": "b" * 40},
            "html_url": f"http://127.0.0.1:3001/{owner}/{repo}/pulls/{number}",
            "created_at": "2026-10-14T00:00:00Z", "updated_at": "2026-10-14T00:00:00Z",
        }

    def pull_diff(self, owner, repo, number):
        self.diff_calls += 1
        return self.diff


def test_parse_unified_diff_tracks_exact_path_side_and_lines():
    result = governance.parse_unified_diff(DIFF)
    assert result["src/example.py"]["LEFT"] == {1, 2}
    assert result["src/example.py"]["RIGHT"] == {1, 2, 3}


def test_search_and_resource_resolution_are_scope_limited(api, credentials, repository):
    title = f"isolated-marker-{new_id()[:8]}"
    with SessionLocal() as session:
        visible = PullRequest(
            id=new_id(), repository_id=repository["id"], number=501, title=title, body="visible PR",
            state="open", head="topic", base="main", web_url="http://127.0.0.1/pr/501", head_sha=HEAD,
            source_refs=[], created_at=now_utc(), updated_at=now_utc(),
        )
        isolated_project = session.scalar(select(Project).where(Project.scope_id == credentials["isolated_scope_id"]))
        hidden_repo = Repository(
            id=new_id(), project_id=isolated_project.id, provider="gitea", owner="demo-owner",
            name=f"hidden-{new_id()[:8]}", default_branch="main", web_url="http://127.0.0.1/hidden",
            clone_url="http://127.0.0.1/hidden.git", created_at=now_utc(),
        )
        session.add(hidden_repo)
        session.flush()
        hidden = PullRequest(
            id=new_id(), repository_id=hidden_repo.id, number=501, title=title, body="must not leak",
            state="open", head="topic", base="main", web_url="http://127.0.0.1/hidden/501", head_sha=HEAD,
            source_refs=[], created_at=now_utc(), updated_at=now_utc(),
        )
        session.add_all([visible, hidden])
        session.commit()
        visible_id, hidden_id = visible.id, hidden.id

    headers = auth(credentials["writer_token"])
    matches = api.get(f"/api/search?q={title}", headers=headers)
    assert matches.status_code == 200
    assert matches.json() == [{
        "id": visible_id, "resource_kind": "pull", "title": f"PR #501 · {title}",
        "excerpt": "visible PR", "source": "code_index",
    }]
    resolved = api.get(f"/api/resources/pull/{visible_id}", headers=headers)
    assert resolved.status_code == 200
    assert resolved.json() == {
        "resource_kind": "pull", "id": visible_id, "project_id": repository["project_id"],
        "repository_id": repository["id"], "pull_number": 501,
    }
    assert api.get(f"/api/resources/pull/{hidden_id}", headers=headers).status_code == 404


def test_inline_comments_validate_current_diff_and_preserve_thread_scope(api, credentials, repository, monkeypatch):
    remote = InlineGitea()
    monkeypatch.setattr(service, "_gitea", lambda: remote)
    path = f"/api/repositories/{repository['id']}/pulls/601/inline-comments"
    headers = {**auth(credentials["writer_token"]), "Idempotency-Key": "inline-601"}
    payload = {"head_sha": HEAD, "file_path": "src/example.py", "line": 2, "side": "RIGHT", "body": "Check this change"}

    created = api.post(path, headers=headers, json=payload)
    replay = api.post(path, headers=headers, json=payload)
    assert created.status_code == 200
    assert replay.json()["id"] == created.json()["id"]
    assert created.json()["is_current"] is True
    assert created.json()["parent_id"] is None

    changed_key = {**headers, "Idempotency-Key": "inline-601-changed"}
    assert api.post(path, headers=changed_key, json={**payload, "line": 40}).json()["detail"]["code"] == "inline_location_not_in_diff"
    stale = api.post(path, headers={**headers, "Idempotency-Key": "inline-601-stale"}, json={**payload, "head_sha": "c" * 40})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_pull_request_head"

    reader = api.post(path, headers={**auth(credentials["reader_token"]), "Idempotency-Key": "inline-reader"}, json=payload)
    assert reader.status_code == 403

    comment_id = created.json()["id"]
    reply = api.post(
        f"/api/inline-comments/{comment_id}/replies",
        headers={**auth(credentials["manager_token"]), "Idempotency-Key": "inline-reply"},
        json={"body": "Resolved by updating the code"},
    )
    assert reply.status_code == 200
    assert reply.json()["parent_id"] == comment_id
    assert reply.json()["file_path"] == payload["file_path"]

    resolved = api.post(
        f"/api/inline-comments/{comment_id}/resolve",
        headers={**auth(credentials["manager_token"]), "Idempotency-Key": "inline-resolve"},
        json={"resolved": True},
    )
    assert resolved.status_code == 200
    assert resolved.json()["resolved"] is True

    remote.head_sha = "d" * 40
    history = api.get(path, headers=auth(credentials["reader_token"]))
    assert history.status_code == 200
    assert all(item["is_current"] is False for item in history.json()["comments"])
    assert remote.diff_calls >= 2


class GovernanceGitea:
    def __init__(self, *, policy=True, actions=True):
        self.policy = policy
        self.actions = actions
        self.last_update = None
        self.updated_policy = None
        self.behind_by = 0
        self.reviews = [{"state": "APPROVED", "commit_id": HEAD, "user": {"login": "upstream-reviewer"}}]
        self.commits = [{"commit": {"verification": {"verified": True}}}]

    def pull(self, owner, repo, number):
        return {
            "number": number, "title": "Governance PR", "body": "", "state": "open", "mergeable": True,
            "head": {"ref": "topic", "sha": HEAD}, "base": {"ref": "main", "sha": "b" * 40},
            "html_url": "http://gitea.example.test/demo/repo/pulls/701",
            "created_at": "2026-10-14T00:00:00Z", "updated_at": "2026-10-14T00:00:00Z",
        }

    def branch(self, owner, repo, branch):
        return {"name": branch}

    def branch_protections(self, owner, repo):
        if not self.policy:
            raise DomainError(501, "gitea_feature_unavailable", "unsupported")
        if self.updated_policy:
            return [self.updated_policy]
        return [{
            "branch_name": "main", "required_approvals": 1, "enable_status_check": True,
            "status_check_contexts": ["lint"], "block_on_outdated_branch": True,
            "block_on_rejected_reviews": True, "dismiss_stale_approvals": True,
            "require_signed_commits": False, "enable_push": False,
        }]

    def pull_reviews(self, owner, repo, number):
        return self.reviews

    def pull_commits(self, owner, repo, number):
        return self.commits

    def compare(self, owner, repo, base, head):
        return {"behind_by": self.behind_by, "ahead_by": 2}

    def statuses(self, owner, repo, sha):
        return [
            {"context": "lint", "state": "success", "sha": HEAD},
            {"context": "lint", "state": "failure", "sha": "d" * 40},
        ]

    def actions_runs(self, owner, repo, sha):
        if not self.actions:
            raise DomainError(501, "gitea_feature_unavailable", "unsupported")
        return {"total_count": 1, "workflow_runs": [{
            "id": 81, "name": "build", "head_sha": HEAD, "status": "completed", "conclusion": "success",
            "html_url": "http://gitea.example.test/demo/repo/actions/runs/81",
        }]}

    def actions_jobs(self, owner, repo, run_id):
        return {"jobs": [{"id": 82, "name": "unit", "status": "completed", "conclusion": "success"}]}

    def actions_artifacts(self, owner, repo, run_id):
        return {"artifacts": [{
            "id": 83, "name": "bundle", "size_in_bytes": 42, "expired": False,
            "url": "https://attacker.invalid/download/83",
        }]}

    def update_branch_protection(self, owner, repo, branch, *, exists, data):
        self.last_update = {"branch": branch, "exists": exists, "data": deepcopy(data)}
        self.updated_policy = {**(self.branch_protections(owner, repo)[0] if self.policy and not self.updated_policy else {}), "branch_name": branch, **data}
        return self.updated_policy


class NewBranchProtectionGitea:
    def __init__(self, *, readback=True):
        self.readback = readback
        self.policy = None
        self.update_calls = []

    def branch(self, owner, repo, branch):
        return {"name": branch}

    def branch_protections(self, owner, repo):
        return [self.policy] if self.readback and self.policy is not None else []

    def update_branch_protection(self, owner, repo, branch, *, exists, data):
        self.update_calls.append({"branch": branch, "exists": exists, "data": deepcopy(data)})
        self.policy = {"branch_name": branch, **data}
        return self.policy


def test_governance_uses_only_current_upstream_evidence_and_real_actions(repository, credentials, monkeypatch):
    client = GovernanceGitea()
    config = GiteaConfig("http://gitea.example.test", "server-token", "hook-secret")
    monkeypatch.setattr(governance, "load_gitea_config", lambda: config)
    monkeypatch.setattr(governance, "GiteaClient", lambda _: client)
    with SessionLocal() as session:
        pull = PullRequest(
            id=new_id(), repository_id=repository["id"], number=701, title="Governance PR", body="",
            state="open", head="topic", base="main", web_url="http://gitea.example.test/pull/701",
            head_sha=HEAD, source_refs=[], created_at=now_utc(), updated_at=now_utc(),
        )
        session.add(pull)
        session.add(CheckReceipt(
            id=new_id(), repository_id=repository["id"], commit_sha=HEAD, context="lint", state="failure",
            description="Agent-reported only", target_url=None, source="agent_reported", actor_id=None,
            created_at=now_utc(),
        ))
        session.commit()
        result = governance.pull_governance(
            session,
            session.get(service.Principal, credentials["manager_id"]),
            repository["id"],
            701,
        )
        assert result["head_sha"] == HEAD
        assert result["upstream"]["reviews"]["current_approvals"] == ["upstream-reviewer"]
        assert result["upstream"]["statuses"]["required"] == [{"context": "lint", "state": "success", "current_sha": HEAD}]
        assert result["upstream"]["branch_sync"] == {"available": True, "behind_by": 0}
        assert result["merge_readiness"] == {"ready": True, "blockers": [], "verified_at_sha": HEAD}
        assert result["actions"]["available"] is True
        assert result["actions"]["runs"][0]["jobs"][0]["name"] == "unit"
        assert result["actions"]["runs"][0]["artifacts"][0]["html_url"] is None
        assert result["deployments"]["available"] is False


def test_branch_protection_requires_manager_and_returns_upstream_policy(api, credentials, repository, monkeypatch):
    client = GovernanceGitea()
    config = GiteaConfig("http://gitea.example.test", "server-token", "hook-secret")
    monkeypatch.setattr(governance, "load_gitea_config", lambda: config)
    monkeypatch.setattr(governance, "GiteaClient", lambda _: client)
    url = f"/api/repositories/{repository['id']}/branch-protection?branch=main"
    denied = api.patch(url, headers={**auth(credentials["writer_token"]), "Idempotency-Key": "policy-writer"}, json={"required_approvals": 2})
    assert denied.status_code == 403

    changed = api.patch(
        url,
        headers={**auth(credentials["manager_token"]), "Idempotency-Key": "policy-manager"},
        json={"required_approvals": 2, "enable_status_check": True, "status_check_contexts": ["lint"]},
    )
    assert changed.status_code == 200
    assert changed.json()["protection"]["required_approvals"] == 2
    assert client.last_update["branch"] == "main"
    assert client.last_update["exists"] is True
    assert client.last_update["data"] == {
        "required_approvals": 2, "enable_status_check": True,
        "status_check_contexts": ["lint"], "branch_name": "main",
    }
    assert changed.json()["protection"]["require_signed_commits"] is False
    assert changed.json()["protection"]["enable_push"] is False
    current = api.get(url, headers=auth(credentials["reader_token"]))
    assert current.status_code == 200
    assert current.json()["protection"]["required_approvals"] == 2


def test_sparse_branch_protection_create_replay_uses_original_request_hash(api, credentials, repository, monkeypatch):
    client = NewBranchProtectionGitea()
    config = GiteaConfig("http://gitea.example.test", "server-token", "hook-secret")
    monkeypatch.setattr(governance, "load_gitea_config", lambda: config)
    monkeypatch.setattr(governance, "GiteaClient", lambda _: client)
    url = f"/api/repositories/{repository['id']}/branch-protection?branch=release"
    headers = {**auth(credentials["manager_token"]), "Idempotency-Key": "sparse-protection-create"}

    created = api.patch(url, headers=headers, json={"required_approvals": 2})
    replay = api.patch(url, headers=headers, json={"required_approvals": 2})

    assert created.status_code == 200
    assert replay.status_code == 200
    assert replay.json() == created.json()
    assert len(client.update_calls) == 1
    assert client.update_calls[0] == {
        "branch": "release", "exists": False, "data": {
            "required_approvals": 2,
            "enable_status_check": False,
            "status_check_contexts": [],
            "block_on_outdated_branch": False,
            "block_on_rejected_reviews": False,
            "dismiss_stale_approvals": False,
            "require_signed_commits": False,
            "branch_name": "release",
        },
    }
    assert created.json()["protection"]["required_approvals"] == 2


def test_branch_protection_requires_actual_upstream_readback(api, credentials, repository, monkeypatch):
    client = NewBranchProtectionGitea(readback=False)
    config = GiteaConfig("http://gitea.example.test", "server-token", "hook-secret")
    monkeypatch.setattr(governance, "load_gitea_config", lambda: config)
    monkeypatch.setattr(governance, "GiteaClient", lambda _: client)
    url = f"/api/repositories/{repository['id']}/branch-protection?branch=release"

    response = api.patch(
        url,
        headers={**auth(credentials["manager_token"]), "Idempotency-Key": "unverified-protection-create"},
        json={"required_approvals": 1},
    )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "gitea_invalid_response"
    assert len(client.update_calls) == 1


def test_governance_reports_actions_and_protection_unavailable_without_fabrication(repository, monkeypatch):
    client = GovernanceGitea(policy=False, actions=False)
    config = GiteaConfig("http://gitea.example.test", "server-token", "hook-secret")
    monkeypatch.setattr(governance, "load_gitea_config", lambda: config)
    monkeypatch.setattr(governance, "GiteaClient", lambda _: client)
    with SessionLocal() as session:
        pull = PullRequest(
            id=new_id(), repository_id=repository["id"], number=702, title="Unverifiable PR", body="",
            state="open", head="topic", base="main", web_url="http://gitea.example.test/pull/702",
            head_sha=HEAD, source_refs=[], created_at=now_utc(), updated_at=now_utc(),
        )
        session.add(pull)
        session.commit()
        manager = session.query(service.Principal).filter_by(name="code-demo-manager").one()
        result = governance.pull_governance(session, manager, repository["id"], 702)
        assert result["upstream"]["protection"]["available"] is False
        assert result["actions"] == {"available": False, "reason": "unsupported_by_gitea", "runs": []}
        assert result["merge_readiness"]["ready"] is None


def test_merge_readiness_honors_outdated_branch_rejected_reviews_and_signed_commit_policy(repository, monkeypatch):
    client = GovernanceGitea()
    client.behind_by = 3
    client.reviews = [
        {"state": "APPROVED", "commit_id": HEAD, "submitted_at": "2026-10-14T01:00:00Z", "user": {"login": "reviewer"}},
        {"state": "CHANGES_REQUESTED", "commit_id": HEAD, "submitted_at": "2026-10-14T02:00:00Z", "user": {"login": "reviewer"}},
    ]
    client.commits = [
        {"commit": {"verification": {"verified": True}}},
        {"commit": {"verification": {"verified": False}}},
    ]
    client.branch_protections = lambda owner, repo: [{
        "branch_name": "main", "required_approvals": 1, "enable_status_check": True,
        "status_check_contexts": ["lint"], "block_on_outdated_branch": True,
        "block_on_rejected_reviews": True, "dismiss_stale_approvals": True,
        "require_signed_commits": True,
    }]
    config = GiteaConfig("http://gitea.example.test", "server-token", "hook-secret")
    monkeypatch.setattr(governance, "load_gitea_config", lambda: config)
    monkeypatch.setattr(governance, "GiteaClient", lambda _: client)
    with SessionLocal() as session:
        pull = PullRequest(
            id=new_id(), repository_id=repository["id"], number=703, title="Policy enforcement", body="",
            state="open", head="topic", base="main", web_url="http://gitea.example.test/pull/703",
            head_sha=HEAD, source_refs=[], created_at=now_utc(), updated_at=now_utc(),
        )
        session.add(pull)
        session.commit()
        manager = session.query(service.Principal).filter_by(name="code-demo-manager").one()
        result = governance.pull_governance(session, manager, repository["id"], 703)
    assert result["merge_readiness"]["ready"] is False
    assert {"pull_branch_outdated", "upstream_review_changes_requested", "pull_commits_unsigned"}.issubset(result["merge_readiness"]["blockers"])
    assert result["upstream"]["commit_signatures"] == {"available": True, "all_signed": False, "unverified_count": 1}
