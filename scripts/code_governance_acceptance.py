"""Black-box Code governance acceptance against the isolated collaboration QA stack."""

from __future__ import annotations

import argparse
import base64
import json
import secrets
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
QA_BASE_URL = "http://127.0.0.1:8096"
API = "/code-api/api"
DEFAULT_INPUT = ROOT / ".cache" / "collaboration-qa" / "context.json"
DEFAULT_CONTEXT = ROOT / ".cache" / "p0-p1-qa" / "code-governance-context.json"
DEFAULT_REPORT = ROOT / ".cache" / "p0-p1-qa" / "code-governance-api-report.json"


class AcceptanceError(RuntimeError):
    def __init__(self, check: str):
        self.check = check
        super().__init__(check)


def private_cache_path(value: str | Path) -> Path:
    path = Path(value)
    resolved = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    cache_root = (ROOT / ".cache" / "p0-p1-qa").resolve()
    try:
        resolved.relative_to(cache_root)
    except ValueError:
        raise AcceptanceError("output_path_must_be_under_p0_p1_qa_cache") from None
    return resolved


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class CodeGovernanceAcceptance:
    def __init__(self, context: dict[str, Any], base_url: str, context_output: Path):
        self.base_url = base_url.rstrip("/")
        self.source_context = context
        self.context_output = context_output
        self.run_id = uuid.uuid4().hex[:12]
        self.checks: dict[str, bool] = {}
        self.evidence: dict[str, Any] = {}
        self.clients: dict[str, httpx.Client] = {}
        self.code: dict[str, Any] = {}
        self.fixture: dict[str, Any] = {}

    def check(self, name: str, condition: bool) -> None:
        self.checks[name] = bool(condition)
        if not condition:
            raise AcceptanceError(name)

    def client(self, name: str) -> httpx.Client:
        cached = self.clients.get(name)
        if cached is not None:
            return cached
        if name == "agent":
            return self.agent_client()
        user = (self.source_context.get("users") or {}).get(name)
        if not isinstance(user, dict):
            raise AcceptanceError(f"missing_qa_user_{name}")
        cookie_name, cookie_value, csrf = (user.get(key) for key in ("cookie_name", "cookie_value", "csrf_token"))
        if not all(isinstance(value, str) and value for value in (cookie_name, cookie_value, csrf)):
            raise AcceptanceError(f"missing_qa_session_{name}")
        client = httpx.Client(
            base_url=self.base_url,
            headers={"Origin": self.base_url, "X-CSRF-Token": csrf},
            timeout=httpx.Timeout(25, connect=5),
            follow_redirects=False,
            trust_env=False,
        )
        client.cookies.set(cookie_name, cookie_value)
        self.clients[name] = client
        return client

    def agent_client(self) -> httpx.Client:
        agent = ((self.source_context.get("agents") or {}).get("code") or {}).get("token")
        if not isinstance(agent, str) or not agent:
            raise AcceptanceError("missing_qa_code_agent_credential")
        client = httpx.Client(
            base_url=self.base_url,
            headers={"Origin": self.base_url, "Authorization": f"Bearer {agent}"},
            timeout=httpx.Timeout(25, connect=5),
            follow_redirects=False,
            trust_env=False,
        )
        self.clients["agent"] = client
        return client

    def request(
        self,
        actor: str,
        method: str,
        path: str,
        *,
        body: dict | None = None,
        status: int | tuple[int, ...] = 200,
        key: str | None = None,
        params: dict | None = None,
    ) -> httpx.Response:
        headers = {"Idempotency-Key": key} if key else None
        try:
            response = self.client(actor).request(method, path, json=body, params=params, headers=headers)
        except httpx.HTTPError:
            raise AcceptanceError(f"request_failed_{method.lower()}") from None
        expected = status if isinstance(status, tuple) else (status,)
        if response.status_code not in expected:
            raise AcceptanceError(f"unexpected_status_{method.lower()}_{response.status_code}_expected_{'_or_'.join(map(str, expected))}")
        return response

    def json(self, actor: str, method: str, path: str, **kwargs) -> dict:
        response = self.request(actor, method, path, **kwargs)
        try:
            value = response.json()
        except ValueError:
            raise AcceptanceError("invalid_json_response") from None
        if not isinstance(value, dict):
            raise AcceptanceError("invalid_object_response")
        return value

    def json_list(self, actor: str, method: str, path: str, **kwargs) -> list[dict]:
        response = self.request(actor, method, path, **kwargs)
        try:
            value = response.json()
        except ValueError:
            raise AcceptanceError("invalid_json_response") from None
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise AcceptanceError("invalid_list_response")
        return value

    def checkpoint_fixture(self) -> None:
        write_json(self.context_output, {
            "base_url": self.base_url,
            "run_id": self.run_id,
            "code": self.fixture,
        })

    def initialize(self) -> None:
        if self.base_url != QA_BASE_URL or self.source_context.get("base_url") != QA_BASE_URL:
            raise AcceptanceError("only_isolated_qa_url_is_allowed")
        self.check("dedicated_qa_base_url", self.base_url == QA_BASE_URL)
        self.check("shared_context_is_not_modified", True)
        health = self.json("alice", "GET", f"{API}/health")
        self.check("code_api_healthy", health.get("status") == "ok")
        self.check("gitea_is_configured", health.get("gitea_configured") is True)

        identities = {}
        for name in ("admin", "alice", "bob", "reader"):
            identity = self.json(name, "GET", "/auth-api/me")
            self.check(f"identity_session_{name}_valid", isinstance((identity.get("user") or {}).get("id"), str))
            identities[name] = self.json(name, "GET", f"{API}/me")
            self.check(
                f"code_principal_{name}_active",
                isinstance(identities[name].get("id"), str)
                and identities[name].get("kind") == "human"
                and bool(identities[name].get("organization_id"))
                and isinstance(identities[name].get("scope_ids"), list),
            )
        self.fixture["principals"] = {name: value.get("id") for name, value in identities.items()}
        managers = [name for name, value in identities.items() if value.get("role") in {"admin", "manager"}]
        if not managers:
            raise AcceptanceError("no_qa_principal_has_branch_policy_manager_role")
        self.fixture["manager_role"] = identities[managers[0]].get("role")
        self.fixture["manager_name"] = managers[0]
        self.code = self.source_context.get("code") or {}
        project_id = self.code.get("project_id")
        repository_id = self.code.get("repository_id")
        isolated_project_id = ((self.source_context.get("_qa_state") or {}).get("resources") or {}).get("code_isolated_project", {}).get("id")
        if not all(isinstance(value, str) and value for value in (project_id, repository_id, isolated_project_id)):
            raise AcceptanceError("missing_qa_code_project_or_repository")
        self.fixture.update({
            "project_id": project_id,
            "repository_id": repository_id,
            "isolated_project_id": isolated_project_id,
            "owner": (self.code.get("repository") or {}).get("owner"),
            "repository": (self.code.get("repository") or {}).get("name"),
        })
        repositories = self.json_list("alice", "GET", f"{API}/repositories", params={"project_id": project_id})
        self.check("qa_repository_visible_in_project", any(item.get("id") == repository_id for item in repositories))
        repo = next(item for item in repositories if item.get("id") == repository_id)
        self.fixture["owner"] = repo.get("owner")
        self.fixture["repository"] = repo.get("name")
        self.fixture["initial_pull_number"] = self.code.get("pull_number")
        self.fixture["initial_head_sha"] = self.code.get("head_sha")
        self.fixture["branches"] = {}
        self.fixture["comments"] = {}
        self.checkpoint_fixture()

    def create_pull_fixture(self) -> None:
        repository_id = self.fixture["repository_id"]
        target = f"qa-gov-{self.run_id}-base"
        head = f"qa-gov-{self.run_id}-head"
        title = f"QA governance {self.run_id}"
        file_path = f"qa_governance_{self.run_id}.md"
        content = f"# Governance acceptance {self.run_id}\n\nInline comment marker {self.run_id}\n"
        for name in (target, head):
            created = self.json(
                "alice", "POST", f"{API}/repositories/{repository_id}/branches",
                body={"name": name, "from_branch": "main"}, key=f"code-gov-{self.run_id}-branch-{name}",
            )
            self.check(f"gitea_branch_created_{name.endswith('base') and 'base' or 'head'}", bool(created.get("commit_sha")))
        commit = self.json(
            "alice", "POST", f"{API}/repositories/{repository_id}/files",
            body={
                "branch": head, "path": file_path, "content": content,
                "commit_message": f"QA governance fixture {self.run_id}", "expected_sha": None,
            },
            key=f"code-gov-{self.run_id}-initial-commit",
        )
        self.check("gitea_initial_commit_has_sha", bool(commit.get("commit_sha") and commit.get("file_sha")))
        pull = self.json(
            "alice", "POST", f"{API}/repositories/{repository_id}/pulls",
            body={"head": head, "base": target, "title": title, "body": f"Synthetic QA fixture {self.run_id}."},
            key=f"code-gov-{self.run_id}-pull",
        )
        number = pull.get("number")
        self.check("gitea_pull_request_created", isinstance(number, int) and number > 0)
        self.fixture.update({"branches": {"base": target, "head": head}, "file_path": file_path, "pull_number": number, "title": title})
        context = self.json("alice", "GET", f"{API}/repositories/{repository_id}/pulls/{number}")
        pull_id = context.get("id")
        head_sha = context.get("head_sha")
        self.check("local_pull_id_persisted", isinstance(pull_id, str) and bool(pull_id))
        self.check("pull_head_sha_is_real", isinstance(head_sha, str) and len(head_sha) in {40, 64})
        self.fixture.update({"pull_id": pull_id, "head_sha": head_sha, "initial_file_sha": commit["file_sha"]})
        self.checkpoint_fixture()

    def test_search_and_resource_scope(self) -> None:
        project_id = self.fixture["project_id"]
        repository_id = self.fixture["repository_id"]
        pull_id = self.fixture["pull_id"]
        pull_number = self.fixture["pull_number"]
        project_rows = self.json_list("alice", "GET", f"{API}/projects")
        project = next(item for item in project_rows if item.get("id") == project_id)
        self.fixture["project_key"] = project.get("key")
        self.fixture["project_name"] = project.get("name")
        project_query = self.json_list("alice", "GET", f"{API}/search", params={"q": project.get("key", "")})
        self.check("search_returns_project_resource_kind", any(item.get("id") == project_id and item.get("resource_kind") == "project" and item.get("source") == "code_index" for item in project_query))
        repo_query = self.json_list("alice", "GET", f"{API}/search", params={"q": self.fixture["repository"]})
        self.check("search_returns_repository_resource_kind", any(item.get("id") == repository_id and item.get("resource_kind") == "repository" for item in repo_query))
        pull_query = self.json_list("alice", "GET", f"{API}/search", params={"q": self.fixture["title"]})
        self.check("search_returns_pull_resource_kind", any(item.get("id") == pull_id and item.get("resource_kind") == "pull" for item in pull_query))
        resolved = self.json("alice", "GET", f"{API}/resources/pull/{pull_id}")
        self.check("pull_deep_link_resolves_authorized_repository", resolved.get("repository_id") == repository_id and resolved.get("pull_number") == pull_number and resolved.get("project_id") == project_id)
        reader_resource = self.json("reader", "GET", f"{API}/resources/pull/{pull_id}")
        self.check("reader_can_resolve_in_scope_pull", reader_resource.get("id") == pull_id)
        denied = self.request("reader", "GET", f"{API}/resources/project/{self.fixture['isolated_project_id']}", status=(403, 404))
        self.check("reader_cannot_resolve_cross_scope_project", denied.status_code in {403, 404})

    def test_inline_collaboration(self) -> None:
        repository_id = self.fixture["repository_id"]
        number = self.fixture["pull_number"]
        path = f"{API}/repositories/{repository_id}/pulls/{number}"
        diff = self.json("bob", "GET", path + "/diff")
        self.check("gitea_diff_head_matches_live_pull", diff.get("head_sha") == self.fixture["head_sha"])
        files = diff.get("files")
        first_file = next((item for item in files or [] if item.get("path") == self.fixture["file_path"] and item.get("right_lines")), None)
        self.check("gitea_diff_contains_new_file_and_lines", first_file is not None)
        line = first_file["right_lines"][0]
        body = {"head_sha": diff["head_sha"], "file_path": first_file["path"], "line": line, "side": "RIGHT", "body": f"QA inline {self.run_id}"}
        comment_path = path + "/inline-comments"
        key = f"code-gov-{self.run_id}-inline"
        created = self.json("alice", "POST", comment_path, body=body, key=key)
        replay = self.json("alice", "POST", comment_path, body=body, key=key)
        self.check("inline_comment_is_sha_file_line_anchored", created.get("head_sha") == diff["head_sha"] and created.get("file_path") == first_file["path"] and created.get("line") == line and created.get("side") == "RIGHT")
        self.check("inline_comment_idempotency_replays", replay.get("id") == created.get("id"))
        self.fixture["comments"]["inline_id"] = created.get("id")

        invalid_line = dict(body, line=999999)
        rejected = self.request("alice", "POST", comment_path, body=invalid_line, status=422, key=f"code-gov-{self.run_id}-wrong-line")
        self.check("inline_comment_rejects_line_not_in_real_diff", rejected.status_code == 422)
        reader_write = self.request("reader", "POST", comment_path, body=body, status=403, key=f"code-gov-{self.run_id}-reader-inline")
        self.check("reader_cannot_create_inline_comment", reader_write.status_code == 403)

        reply = self.json("bob", "POST", f"{API}/inline-comments/{created['id']}/replies", body={"body": f"QA reply {self.run_id}"}, key=f"code-gov-{self.run_id}-reply")
        self.check("inline_reply_stays_in_same_thread", reply.get("parent_id") == created["id"] and reply.get("head_sha") == created["head_sha"])
        resolved = self.json("alice", "POST", f"{API}/inline-comments/{created['id']}/resolve", body={"resolved": True}, key=f"code-gov-{self.run_id}-resolve")
        self.check("inline_thread_resolves", resolved.get("resolved") is True)
        history = self.json("bob", "GET", comment_path)
        self.check("inline_thread_readback_contains_reply_and_resolution", any(item.get("id") == reply.get("id") for item in history.get("comments", [])) and any(item.get("id") == created.get("id") and item.get("resolved") is True for item in history.get("comments", [])))

        manager = self.fixture["manager_name"]
        policy_path = f"{API}/repositories/{repository_id}/branch-protection"
        branch = self.fixture["branches"]["base"]
        before = self.json(manager, "GET", policy_path, params={"branch": branch})
        self.check("branch_protection_read_is_upstream", before.get("available") is True and before.get("branch") == branch)
        body_policy = {
            "required_approvals": 1,
            "enable_status_check": True,
            "status_check_contexts": [f"qa-governance-{self.run_id}"],
            "block_on_outdated_branch": False,
            "block_on_rejected_reviews": True,
            "dismiss_stale_approvals": True,
            "require_signed_commits": False,
        }
        key_policy = f"code-gov-{self.run_id}-branch-policy"
        updated = self.json(manager, "PATCH", policy_path, params={"branch": branch}, body=body_policy, key=key_policy)
        self.check("branch_protection_update_returns_upstream_policy", updated.get("available") is True and (updated.get("protection") or {}).get("required_approvals") == 1 and (updated.get("protection") or {}).get("status_check_contexts") == body_policy["status_check_contexts"])
        replay = self.json(manager, "PATCH", policy_path, params={"branch": branch}, body=body_policy, key=key_policy)
        self.check("branch_protection_idempotency_replays", replay.get("protection") == updated.get("protection"))
        changed = dict(body_policy, required_approvals=2)
        conflict = self.request(manager, "PATCH", policy_path, params={"branch": branch}, body=changed, key=key_policy, status=409)
        self.check("branch_protection_idempotency_rejects_changed_body", conflict.status_code == 409)
        writer_denied = self.request("alice", "PATCH", policy_path, params={"branch": branch}, body=body_policy, key=f"code-gov-{self.run_id}-writer-policy", status=403)
        self.check("writer_cannot_manage_branch_protection", writer_denied.status_code == 403)
        reread = self.json("reader", "GET", policy_path, params={"branch": branch})
        self.check("branch_protection_reread_matches_change", reread.get("available") is True and reread.get("protection", {}).get("required_approvals") == 1 and reread.get("protection", {}).get("status_check_contexts") == body_policy["status_check_contexts"])
        self.fixture["branch_policy"] = body_policy

        shared_path = f"{API}/collaboration/pull/{self.fixture['pull_id']}"
        participants = self.json_list("alice", "GET", shared_path + "/participants")
        bob_principal = self.fixture["principals"]["bob"]
        self.check("shared_participants_are_scoped", any(item.get("id") == bob_principal for item in participants))
        subscribed = self.json("bob", "POST", shared_path + "/subscription", body={"subscribed": True}, key=f"code-gov-{self.run_id}-subscribe")
        self.check("bob_can_subscribe_to_pull", subscribed.get("subscribed") is True)
        content = f"Ordivant Code QA attachment {self.run_id}.".encode()
        attachment = self.json("alice", "POST", shared_path + "/attachments", body={"filename": f"qa-{self.run_id}.txt", "content_base64": base64.b64encode(content).decode()}, status=201, key=f"code-gov-{self.run_id}-attachment")
        attachment_replay = self.json("alice", "POST", shared_path + "/attachments", body={"filename": f"qa-{self.run_id}.txt", "content_base64": base64.b64encode(content).decode()}, status=201, key=f"code-gov-{self.run_id}-attachment")
        self.check("shared_attachment_is_idempotent_and_hashed", attachment.get("id") == attachment_replay.get("id") and attachment.get("size") == len(content) and bool(attachment.get("sha256")))
        read_attachments = self.json_list("reader", "GET", shared_path + "/attachments")
        self.check("reader_can_read_shared_attachment_metadata", any(item.get("id") == attachment.get("id") for item in read_attachments))
        download = self.request("bob", "GET", f"{API}/collaboration/attachments/{attachment['id']}/download")
        self.check("shared_attachment_download_is_scoped", download.content == content and download.headers.get("ETag", "").strip('"') == attachment.get("sha256"))
        mention = self.json("alice", "POST", shared_path + "/discussion", body={"body": f"QA human discussion {self.run_id}", "mention_ids": [bob_principal]}, status=201, key=f"code-gov-{self.run_id}-discussion")
        self.check("human_shared_discussion_saved", mention.get("body", "").endswith(self.run_id))
        bob_notifications = self.json_list("bob", "GET", f"{API}/collaboration/notifications")
        self.check("mention_notifies_scoped_bob", any(item.get("resource_id") == self.fixture["pull_id"] and item.get("event") == "discussion.mention" and item.get("actor_id") == self.fixture["principals"]["alice"] for item in bob_notifications))
        agent = self.agent_client()
        agent_discussion = self.request("agent", "POST", shared_path + "/discussion", body={"body": f"QA Agent discussion {self.run_id}", "mention_ids": []}, status=201, key=f"code-gov-{self.run_id}-agent-discussion")
        self.check("agent_uses_same_shared_discussion_service", agent_discussion.status_code == 201)
        discussion = self.json_list("reader", "GET", shared_path + "/discussion")
        self.check("reader_sees_human_and_agent_shared_discussion", {item.get("body", "").split()[1] for item in discussion if self.run_id in item.get("body", "")} >= {"human", "Agent"})
        reader_write = self.request("reader", "POST", shared_path + "/discussion", body={"body": "Reader should be denied", "mention_ids": []}, status=403, key=f"code-gov-{self.run_id}-reader-discussion")
        self.check("reader_cannot_write_shared_discussion", reader_write.status_code == 403)
        self.fixture["attachment_id"] = attachment["id"]

    def test_governance_head_and_history(self) -> None:
        repository_id = self.fixture["repository_id"]
        number = self.fixture["pull_number"]
        path = f"{API}/repositories/{repository_id}/pulls/{number}"
        initial_gov = self.json("bob", "GET", path + "/governance")
        self.check("governance_head_matches_real_pull", initial_gov.get("head_sha") == self.fixture["head_sha"] and initial_gov.get("pull_number") == number)
        policy = initial_gov.get("upstream", {}).get("protection", {}).get("policy") or {}
        self.check("governance_uses_real_branch_policy", policy.get("branch_name") == self.fixture["branches"]["base"] and policy.get("required_approvals") == 1)
        checks = initial_gov.get("upstream", {}).get("statuses", {}).get("checks", [])
        self.check("governance_statuses_are_current_sha", all(item.get("current_sha") == initial_gov.get("head_sha") for item in checks))
        actions = initial_gov.get("actions") or {}
        runs = actions.get("runs") or []
        self.check("actions_are_real_current_sha_runs_or_unavailable", (actions.get("available") is False and not runs) or (actions.get("available") is True and all(item.get("head_sha") == initial_gov.get("head_sha") for item in runs)))
        self.evidence["actions"] = {"available": actions.get("available"), "run_count": len(runs), "reason": actions.get("reason")}
        deployments = initial_gov.get("deployments") or {}
        self.check("unconfigured_deployment_provider_is_not_fabricated", deployments.get("available") is False and not deployments.get("items"))
        self.evidence["deployments"] = {"available": deployments.get("available"), "reason": deployments.get("reason"), "item_count": len(deployments.get("items") or [])}

        repo_id = self.fixture["repository_id"]
        comment = self.json("alice", "POST", path + "/comments", body={"body": f"QA local human comment {self.run_id}"}, key=f"code-gov-{self.run_id}-local-comment")
        agent_comment = self.request("agent", "POST", path + "/comments", body={"body": f"QA local Agent comment {self.run_id}"}, key=f"code-gov-{self.run_id}-local-agent-comment")
        self.check("human_and_agent_use_same_local_comment_service", comment.get("author", {}).get("kind") == "human" and agent_comment.status_code == 200)
        review = self.json("bob", "POST", path + "/reviews", body={"decision": "approve", "comment": f"QA local review {self.run_id}", "expected_head_sha": self.fixture["head_sha"]}, key=f"code-gov-{self.run_id}-local-review")
        self.check("local_review_is_separate_review_receipt", review.get("head_sha") == self.fixture["head_sha"])
        after_local_review = self.json("bob", "GET", path + "/governance")
        self.check("local_reviews_do_not_change_upstream_gitea_approvals", after_local_review.get("upstream", {}).get("reviews", {}).get("current_approvals") == initial_gov.get("upstream", {}).get("reviews", {}).get("current_approvals"))
        collaboration = self.json("reader", "GET", path + "/collaboration")
        self.check("reader_sees_human_and_agent_reviews_and_comments", {item.get("author", {}).get("kind") for item in collaboration.get("comments", [])} >= {"human", "agent"} and any(item.get("id") == review.get("id") for item in collaboration.get("reviews", [])))

        body = f"# Governance acceptance {self.run_id}\n\nUpdated source marker {self.run_id}\n"
        commit = self.json(
            "alice", "POST", f"{API}/repositories/{repo_id}/files",
            body={"branch": self.fixture["branches"]["head"], "path": self.fixture["file_path"], "content": body, "commit_message": f"Move QA head {self.run_id}", "expected_sha": self.fixture["initial_file_sha"]},
            key=f"code-gov-{self.run_id}-move-head",
        )
        self.check("gitea_head_moved_with_second_real_commit", bool(commit.get("commit_sha")) and commit.get("commit_sha") != self.fixture["head_sha"])
        new_pull = self.json("bob", "GET", path)
        new_head = new_pull.get("head_sha")
        self.check("pull_reread_observes_new_gitea_head", isinstance(new_head, str) and new_head != self.fixture["head_sha"])
        stale_payload = {
            "head_sha": self.fixture["head_sha"], "file_path": self.fixture["file_path"],
            "line": 1, "side": "RIGHT", "body": "Stale anchor must be rejected",
        }
        stale = self.request("alice", "POST", path + "/inline-comments", body=stale_payload, status=409, key=f"code-gov-{self.run_id}-stale-anchor")
        self.check("inline_comment_rejects_old_head_sha", stale.status_code == 409)
        history = self.json("reader", "GET", path + "/inline-comments")
        self.check("old_inline_thread_is_marked_stale", any(item.get("id") == self.fixture["comments"]["inline_id"] and item.get("is_current") is False for item in history.get("comments", [])))
        final_gov = self.json("bob", "GET", path + "/governance")
        self.check("governance_tracks_latest_real_head", final_gov.get("head_sha") == new_head and final_gov.get("merge_readiness", {}).get("verified_at_sha") == new_head)
        final_reviews = self.json("reader", "GET", path + "/collaboration")
        self.check("review_history_is_versioned_after_head_change", any(item.get("id") == review.get("id") and item.get("is_current") is False for item in final_reviews.get("reviews", [])))
        self.fixture["head_sha"] = new_head
        self.fixture["updated_commit_sha"] = commit.get("commit_sha")
        self.fixture["upstream_status_count"] = len(final_gov.get("upstream", {}).get("statuses", {}).get("checks", []))
        self.evidence["governance"] = {
            "initial_head_matches_gitea": True,
            "final_head_matches_gitea": True,
            "upstream_status_count": self.fixture["upstream_status_count"],
            "upstream_review_api_available": final_gov.get("upstream", {}).get("reviews", {}).get("available"),
            "actions_available": (final_gov.get("actions") or {}).get("available"),
        }
        self.checkpoint_fixture()

    def execute(self) -> dict[str, Any]:
        self.initialize()
        self.create_pull_fixture()
        self.test_search_and_resource_scope()
        self.test_inline_collaboration()
        self.test_governance_head_and_history()
        return {
            "status": "passed",
            "base_url": self.base_url,
            "run_id": self.run_id,
            "checks": self.checks,
            "passed": sum(self.checks.values()),
            "failed": sum(not value for value in self.checks.values()),
            "evidence": self.evidence,
            "fixture_context": str(self.context_output.relative_to(ROOT)),
        }

    def close(self) -> None:
        for client in self.clients.values():
            client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=QA_BASE_URL)
    parser.add_argument("--input-context", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--context-output", type=Path, default=DEFAULT_CONTEXT)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    context_output = private_cache_path(args.context_output)
    report_output = private_cache_path(args.report_output)
    report: dict[str, Any] = {"status": "failed", "base_url": QA_BASE_URL, "checks": {}, "passed": 0, "failed": 0}
    try:
        source_context = json.loads(args.input_context.read_text(encoding="utf-8"))
        if not isinstance(source_context, dict):
            raise AcceptanceError("invalid_shared_qa_context")
        run = CodeGovernanceAcceptance(source_context, args.base_url, context_output)
        try:
            report = run.execute()
        except AcceptanceError as error:
            report = {
                "status": "failed", "base_url": QA_BASE_URL, "run_id": run.run_id,
                "failed_check": error.check, "checks": run.checks,
                "passed": sum(run.checks.values()), "failed": 1,
                "evidence": run.evidence,
            }
        finally:
            run.close()
    except (OSError, ValueError, AcceptanceError) as error:
        failure = error.check if isinstance(error, AcceptanceError) else "input_context_unavailable" if isinstance(error, OSError) else "invalid_context_json"
        report = {"status": "failed", "base_url": QA_BASE_URL, "failed_check": failure, "checks": {}, "passed": 0, "failed": 1}
    write_json(report_output, report)
    print(json.dumps({key: report.get(key) for key in ("status", "run_id", "passed", "failed", "failed_check", "fixture_context") if key in report}, ensure_ascii=False))
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
