"""Black-box acceptance for human and Agent collaboration in the isolated QA Compose stack.

This script refuses every target except the dedicated local QA project. It creates
synthetic accounts only when Identity reports that initial setup is still required.
Passwords, invitations, cookies, CSRF tokens, and bearer tokens never enter logs or
the sanitized report. Browser-session material is written only to the ignored QA
context file for a later UI or restart check.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import re
import secrets
import subprocess
import sys
import uuid
from dataclasses import dataclass
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import websockets
from pycrdt import Doc, Text


ROOT = Path(__file__).resolve().parents[1]
QA_BASE_URL = "http://127.0.0.1:8096"
QA_COMPOSE_PROJECT = "ordivant-collaboration-qa-20261014"
QA_CONTEXT = ROOT / ".cache" / "collaboration-qa" / "context.json"
QA_REPORT = ROOT / ".cache" / "collaboration-qa" / "api-report.json"


class AcceptanceError(RuntimeError):
    """An expected QA precondition or collaboration assertion failed."""


@dataclass
class SessionClient:
    client: httpx.Client
    cookie_name: str
    cookie_value: str
    csrf_token: str
    identity_user_id: str
    principal_id: str | None = None


class CollaborationAcceptance:
    def __init__(self, base_url: str, compose_project: str):
        self.base_url = base_url.rstrip("/")
        self.compose_project = compose_project
        self.run_id = uuid.uuid4().hex[:10]
        self.checks: dict[str, bool] = {}
        self.phase = "preflight"
        self.clients: list[httpx.Client] = []
        self.users: dict[str, SessionClient] = {}
        self.resources: dict[str, Any] = {}
        self.agents: dict[str, dict[str, str]] = {}
        self.context: dict[str, Any] | None = None
        self.context_path: Path | None = None
        self.completed_phases: set[str] = set()
        self.evidence: dict[str, Any] = {}
        self.admin: SessionClient | None = None

    def check(self, name: str, condition: bool) -> None:
        self.checks[name] = bool(condition)
        if not condition:
            raise AcceptanceError(f"{name} failed")

    def new_client(self) -> httpx.Client:
        client = httpx.Client(
            base_url=self.base_url,
            headers={"Origin": self.base_url},
            timeout=httpx.Timeout(25, connect=5),
            follow_redirects=False,
            trust_env=False,
        )
        self.clients.append(client)
        return client

    @staticmethod
    def _headers(*, idempotency_key: str | None = None, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = dict(extra or {})
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def request(
        self,
        client: httpx.Client,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        expected: int = 200,
        key: str | None = None,
        params: dict[str, Any] | None = None,
        label: str | None = None,
    ) -> httpx.Response:
        if key is None and method.upper() not in {"GET", "HEAD"} and label:
            operation = re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-")[:100]
            key = f"qa-{self.run_id}-{operation}"
        try:
            response = client.request(
                method,
                path,
                json=body,
                params=params,
                headers=self._headers(idempotency_key=key or (str(uuid.uuid4()) if method.upper() not in {"GET", "HEAD"} else None)),
            )
        except httpx.HTTPError:
            raise AcceptanceError(f"{label or method + ' ' + path}: request failed") from None
        if response.status_code != expected:
            raise AcceptanceError(f"{label or method + ' ' + path}: HTTP {response.status_code}, expected {expected}")
        return response

    def json_request(self, *args, **kwargs) -> dict[str, Any]:
        response = self.request(*args, **kwargs)
        try:
            payload = response.json()
        except ValueError:
            raise AcceptanceError("API returned invalid JSON") from None
        if not isinstance(payload, dict):
            raise AcceptanceError("API returned an unexpected JSON shape")
        return payload

    def identity_cookie(self, client: httpx.Client, response: httpx.Response) -> tuple[str, str]:
        raw_cookie = response.headers.get("set-cookie", "")
        parsed = SimpleCookie()
        parsed.load(raw_cookie)
        if not parsed:
            raise AcceptanceError("Identity did not issue an HTTP session cookie")
        cookie_name = next(iter(parsed.keys()))
        cookie_value = client.cookies.get(cookie_name)
        if not cookie_value:
            raise AcceptanceError("Identity session cookie was not retained")
        return cookie_name, cookie_value

    def identity_session(self, client: httpx.Client, response: httpx.Response) -> SessionClient:
        try:
            data = response.json()
            csrf_token = data["csrf_token"]
            user_id = data["user"]["id"]
        except (ValueError, KeyError, TypeError):
            raise AcceptanceError("Identity returned an incomplete session") from None
        if not isinstance(csrf_token, str) or not isinstance(user_id, str):
            raise AcceptanceError("Identity returned an invalid session")
        cookie_name, cookie_value = self.identity_cookie(client, response)
        client.headers["X-CSRF-Token"] = csrf_token
        return SessionClient(client, cookie_name, cookie_value, csrf_token, user_id)

    def checkpoint(self, *, completed: bool = False) -> None:
        if completed:
            self.completed_phases.add(self.phase)
        if self.context_path is not None and self.users:
            _write_json(self.context_path, self.make_context())

    def restore_context(self, context: dict[str, Any]) -> None:
        if context.get("base_url") != self.base_url or context.get("run_id") is None:
            raise AcceptanceError("Saved QA context belongs to another run or base URL")
        self.run_id = str(context["run_id"])
        state = context.get("_qa_state") if isinstance(context.get("_qa_state"), dict) else {}
        resources = state.get("resources", {})
        if isinstance(resources, dict):
            self.resources = resources
        completed = state.get("completed_phases", [])
        if isinstance(completed, list):
            self.completed_phases = {item for item in completed if isinstance(item, str)}
        self.phase = state.get("phase") if isinstance(state.get("phase"), str) else "preflight"
        checks = state.get("checks", {})
        if isinstance(checks, dict):
            self.checks.update({key: value for key, value in checks.items() if isinstance(key, str) and isinstance(value, bool)})
        for product, credential in (context.get("agents") or {}).items():
            if isinstance(credential, dict) and isinstance(credential.get("id"), str) and isinstance(credential.get("token"), str):
                self.agents[product] = {key: credential[key] for key in ("id", "token") if key in credential}
                if "principal_id" in credential and isinstance(credential["principal_id"], str):
                    self.agents[product]["principal_id"] = credential["principal_id"]
        for name, entry in (context.get("users") or {}).items():
            if name not in {"admin", "alice", "bob", "reader"} or not isinstance(entry, dict):
                continue
            values = [entry.get(key) for key in ("cookie_name", "cookie_value", "csrf_token")]
            if not all(isinstance(value, str) and value for value in values):
                continue
            client = self.new_client()
            client.cookies.set(entry["cookie_name"], entry["cookie_value"])
            client.headers["X-CSRF-Token"] = entry["csrf_token"]
            self.users[name] = SessionClient(
                client=client,
                cookie_name=entry["cookie_name"],
                cookie_value=entry["cookie_value"],
                csrf_token=entry["csrf_token"],
                identity_user_id="",
                principal_id=entry.get("principal_id") if isinstance(entry.get("principal_id"), str) else None,
            )
        self.admin = self.users.get("admin")

    def setup_identity(self) -> SessionClient:
        if self.admin is not None:
            response = self.request(self.admin.client, "GET", "/auth-api/me", label="Resume QA administrator session")
            if response.status_code != 200:
                raise AcceptanceError("Saved QA administrator session is no longer valid")
            return self.admin
        anonymous = self.new_client()
        status = self.json_request(anonymous, "GET", "/auth-api/status", label="Identity setup status")
        self.check("identity_requires_initial_setup", status.get("setup_required") is True)
        if status.get("setup_required") is not True:
            raise AcceptanceError("Identity is already initialized; refusing to log in or modify an existing account")

        admin_client = self.new_client()
        password = secrets.token_urlsafe(48)
        email = f"collab-admin-{self.run_id}@example.com"
        response = self.request(
            admin_client,
            "POST",
            "/auth-api/setup",
            body={"name": f"QA Admin {self.run_id}", "email": email, "password": password},
            expected=201,
            label="Identity synthetic QA setup",
        )
        admin = self.identity_session(admin_client, response)
        self.users["admin"] = admin
        self.admin = admin
        self.checkpoint()
        del password
        return admin

    def create_resource(self, client: httpx.Client, path: str, body: dict[str, Any], *, expected: int, label: str) -> dict[str, Any]:
        data = self.json_request(client, "POST", path, body=body, expected=expected, label=label)
        resource = data
        if not isinstance(resource.get("id"), str) and isinstance(data.get("document"), dict):
            resource = data["document"]
        if not isinstance(resource.get("id"), str) or not resource["id"]:
            raise AcceptanceError(f"{label}: resource id missing")
        return data

    def create_scopes(self) -> None:
        assert self.admin is not None
        suffix = self.run_id
        admin = self.admin.client
        self.phase = "create_scopes"
        self.resources["work_project"] = self.create_resource(
            admin,
            "/api/projects",
            {"key": f"qa{suffix}", "name": f"QA Collaboration {suffix}", "description": "Synthetic collaboration acceptance."},
            expected=201,
            label="Work project creation",
        )
        self.resources["work_isolated_project"] = self.create_resource(
            admin,
            "/api/projects",
            {"key": f"qi{suffix}", "name": f"QA Isolated Work {suffix}", "description": "Synthetic isolated scope."},
            expected=201,
            label="Work isolated project creation",
        )
        self.resources["knowledge_space"] = self.create_resource(
            admin,
            "/knowledge-api/api/spaces",
            {"key": f"qa{suffix}", "name": f"QA Collaboration {suffix}", "description": "Synthetic collaboration acceptance."},
            expected=201,
            label="Knowledge space creation",
        )
        self.resources["knowledge_isolated_space"] = self.create_resource(
            admin,
            "/knowledge-api/api/spaces",
            {"key": f"qi{suffix}", "name": f"QA Isolated Knowledge {suffix}", "description": "Synthetic isolated scope."},
            expected=201,
            label="Knowledge isolated space creation",
        )
        self.resources["code_project"] = self.create_resource(
            admin,
            "/code-api/api/projects",
            {"key": f"qa{suffix}", "name": f"QA Collaboration {suffix}", "description": "Synthetic collaboration acceptance."},
            expected=200,
            label="Code project creation",
        )
        self.resources["code_isolated_project"] = self.create_resource(
            admin,
            "/code-api/api/projects",
            {"key": f"qi{suffix}", "name": f"QA Isolated Code {suffix}", "description": "Synthetic isolated scope."},
            expected=200,
            label="Code isolated project creation",
        )
        self.checkpoint(completed=True)

    def invite_and_accept(self, role: str, permissions: dict[str, Any]) -> SessionClient:
        if role in self.users:
            return self.users[role]
        assert self.admin is not None
        name = f"QA {role.title()} {self.run_id}"
        email = f"collab-{role}-{self.run_id}@example.com"
        invite = self.json_request(
            self.admin.client,
            "POST",
            "/auth-api/invitations",
            body={"name": name, "email": email, "role": "member", "permissions": permissions},
            expected=201,
            label=f"Identity {role} invitation",
        )
        invitation_code = invite.get("invitation_code")
        if not isinstance(invitation_code, str) or not invitation_code:
            raise AcceptanceError(f"Identity {role} invitation did not return a code")
        member_client = self.new_client()
        password = secrets.token_urlsafe(48)
        accepted = self.request(
            member_client,
            "POST",
            "/auth-api/accept-invitation",
            body={"invitation_code": invitation_code, "password": password},
            expected=201,
            label=f"Identity {role} acceptance",
        )
        session = self.identity_session(member_client, accepted)
        del password, invitation_code
        self.users[role] = session
        self.checkpoint()
        return session

    def create_users(self) -> None:
        assert self.admin is not None
        work_id = self.resources["work_project"]["id"]
        work_isolated_id = self.resources["work_isolated_project"]["id"]
        knowledge_id = self.resources["knowledge_space"]["id"]
        code_id = self.resources["code_project"]["id"]
        code_isolated_id = self.resources["code_isolated_project"]["id"]

        self.phase = "invite_users"
        self.invite_and_accept(
            "alice",
            {
                "work": {"role": "worker", "scope_ids": [work_id]},
                "knowledge": {"role": "writer", "scope_ids": [knowledge_id]},
                "code": {"role": "writer", "scope_ids": [code_id]},
            },
        )
        self.invite_and_accept(
            "bob",
            {
                "work": {"role": "manager", "scope_ids": [work_id]},
                "knowledge": {"role": "writer", "scope_ids": [knowledge_id]},
                "code": {"role": "writer", "scope_ids": [code_id]},
            },
        )
        self.invite_and_accept(
            "reader",
            {
                "work": {"role": "worker", "scope_ids": [work_isolated_id]},
                "knowledge": {"role": "reader", "scope_ids": [knowledge_id]},
                "code": {"role": "reader", "scope_ids": [code_id]},
            },
        )
        self.checkpoint(completed=True)

    def work_directory_and_tasks(self) -> None:
        assert self.admin is not None
        self.phase = "work_directory"
        project_id = self.resources["work_project"]["id"]
        participants = self.request(
            self.admin.client,
            "GET",
            f"/api/projects/{project_id}/participants",
            label="Work registered participant directory",
        ).json()
        if not isinstance(participants, list):
            raise AcceptanceError("Work participants response was invalid")

        def participant_for(name: str, existing_id: str | None) -> dict[str, Any]:
            matches = [
                item for item in participants
                if item.get("kind") == "human"
                and (
                    (existing_id is not None and (item.get("principal_id") or item.get("id")) == existing_id)
                    or (existing_id is None and item.get("name") == name)
                )
            ]
            if len(matches) != 1:
                raise AcceptanceError(f"Work directory did not resolve exactly one {name} participant")
            return matches[0]

        alice_name = f"QA Alice {self.run_id}"
        bob_name = f"QA Bob {self.run_id}"
        saved_alice_id = self.users["alice"].principal_id
        saved_bob_id = self.users["bob"].principal_id
        alice = participant_for(alice_name, saved_alice_id)
        bob = participant_for(bob_name, saved_bob_id)
        alice_id = alice.get("principal_id") or alice.get("id")
        bob_id = bob.get("principal_id") or bob.get("id")
        if not isinstance(alice_id, str) or not isinstance(bob_id, str):
            raise AcceptanceError("Work directory returned invalid principal ids")
        self.users["alice"].principal_id = alice_id
        self.users["bob"].principal_id = bob_id
        self.users["admin"].principal_id = self.json_request(self.admin.client, "GET", "/api/me", label="Work admin principal").get("id")
        self.check("work_directory_resolves_registered_coworkers", True)

        first_task = self.create_resource(
            self.admin.client,
            "/api/tasks",
            {
                "project_id": project_id,
                "title": f"QA {self.run_id} Alice assigned and reviewed task",
                "goal": "Verify a human can own, submit, and receive independent review of work without a model.",
                "acceptance_criteria": ["Human claim has no agent lease", "Independent reviewer accepts evidence"],
                "assignee_principal_id": alice_id,
                "reviewer_principal_id": bob_id,
                "priority": "medium",
            },
            expected=201,
            label="Work assigned task creation",
        )
        self.resources["browser_task"] = first_task
        self.checkpoint()

        alice_client = self.users["alice"].client
        alice_me = self.json_request(alice_client, "GET", "/api/me", label="Alice first Work login")
        self.check("work_assignee_principal_matches_first_work_login", alice_me.get("id") == alice_id)
        self.resources["alice"] = alice_me

        self.phase = "work_human_lifecycle"
        task_id = first_task["id"]
        claim = self.json_request(
            alice_client,
            "POST",
            f"/api/tasks/{task_id}/claim",
            body={},
            label="Alice human task claim",
        )
        execution = claim.get("execution") or {}
        self.check(
            "human_claim_has_no_agent_or_lease",
            execution.get("agent_id") is None and claim.get("lease_token") is None and execution.get("executor_kind") == "human",
        )
        execution_id = execution.get("id")
        if not isinstance(execution_id, str):
            raise AcceptanceError("Human claim did not return an execution id")
        self.request(
            alice_client,
            "POST",
            f"/api/tasks/{task_id}/progress",
            body={"execution_id": execution_id, "progress": 60, "summary": "QA human progress update."},
            label="Alice progress update",
        )
        submitted = self.json_request(
            alice_client,
            "POST",
            f"/api/tasks/{task_id}/submit",
            body={
                "execution_id": execution_id,
                "summary": "QA Alice completed the assigned work.",
                "artifacts": [{"kind": "summary", "title": "QA evidence", "content": f"Human evidence {self.run_id}."}],
            },
            label="Alice task submission",
        )
        self.check("human_submission_enters_independent_review", submitted.get("task", {}).get("status") == "in_review")
        self.request(
            alice_client,
            "POST",
            f"/api/tasks/{task_id}/review",
            body={"decision": "accept", "comment": "Self-review must be denied."},
            expected=403,
            label="Work self-review rejection",
        )
        self.check("work_self_review_denied", True)
        reviewed = self.json_request(
            self.users["bob"].client,
            "POST",
            f"/api/tasks/{task_id}/review",
            body={"decision": "accept", "comment": "Independent QA review passed."},
            label="Bob independent Work review",
        )
        self.check("independent_reviewer_accepts", reviewed.get("task", {}).get("status") == "done")
        context = self.json_request(alice_client, "GET", f"/api/tasks/{task_id}/context", label="Work audit context")
        actions = {event.get("action") for event in context.get("events", []) if isinstance(event, dict)}
        self.check("work_audit_contains_collaboration_lifecycle", {"task.created", "task.claimed", "task.submitted", "task.review.accept"}.issubset(actions))

        self.phase = "work_handoff"
        handoff_task = self.create_resource(
            self.admin.client,
            "/api/tasks",
            {
                "project_id": project_id,
                "title": f"QA {self.run_id} release and reassign",
                "goal": "Verify release clears the first worker and permits a manager to assign the next coworker.",
                "acceptance_criteria": ["Alice releases", "Bob claims after manager reassigns"],
                "assignee_principal_id": alice_id,
            },
            expected=201,
            label="Work release task creation",
        )
        alice_claim = self.json_request(alice_client, "POST", f"/api/tasks/{handoff_task['id']}/claim", body={}, label="Alice handoff task claim")
        alice_execution_id = alice_claim["execution"]["id"]
        released = self.json_request(
            alice_client,
            "POST",
            f"/api/tasks/{handoff_task['id']}/release",
            body={"execution_id": alice_execution_id, "handoff": "QA handoff to Bob."},
            label="Alice release",
        )
        self.check("work_release_returns_task_to_ready", released.get("status") == "ready" and released.get("assignee_principal_id") is None)
        self.request(
            self.admin.client,
            "PATCH",
            f"/api/tasks/{handoff_task['id']}",
            body={"assignee_principal_id": bob_id},
            label="Manager reassigns released task to Bob",
        )
        bob_claim = self.json_request(self.users["bob"].client, "POST", f"/api/tasks/{handoff_task['id']}/claim", body={}, label="Bob claim after handoff")
        self.check("work_handoff_claimed_by_next_coworker", (bob_claim.get("execution") or {}).get("executor_id") == bob_id)
        bob_execution_id = bob_claim["execution"]["id"]
        self.request(
            self.users["bob"].client,
            "POST",
            f"/api/tasks/{handoff_task['id']}/submit",
            body={
                "execution_id": bob_execution_id,
                "summary": "QA Bob completed the handed-off work.",
                "artifacts": [{"kind": "summary", "title": "QA handoff evidence", "content": f"Bob evidence {self.run_id}."}],
            },
            label="Bob handed-off task submission",
        )
        admin_review = self.json_request(
            self.admin.client,
            "POST",
            f"/api/tasks/{handoff_task['id']}/review",
            body={"decision": "accept", "comment": "Independent admin review passed."},
            label="Admin review of handed-off task",
        )
        self.check("reassigned_work_reviewed", admin_review.get("task", {}).get("status") == "done")

        self.phase = "work_agent_collaboration"
        work_agent = self.agents.get("work")
        if work_agent is None:
            work_agent = self.json_request(
                self.admin.client,
                "POST",
                "/api/agents",
                body={"name": f"QA Work Agent {self.run_id}", "role": "worker", "project_ids": [project_id], "runtime": "external"},
                expected=201,
                label="Work external Agent creation without model configuration",
            )
            if not isinstance(work_agent.get("id"), str) or not isinstance(work_agent.get("principal_id"), str) or not isinstance(work_agent.get("token"), str):
                raise AcceptanceError("Work did not return the synthetic external Agent credential")
            self.agents["work"] = {"id": work_agent["id"], "principal_id": work_agent["principal_id"], "token": work_agent["token"]}
            self.checkpoint()

        parent_task = self.create_resource(
            self.admin.client,
            "/api/tasks",
            {
                "project_id": project_id,
                "title": f"QA {self.run_id} human and Agent delegation",
                "goal": "Verify a human owner can delegate to an external Agent and exchange messages without LLM execution.",
                "acceptance_criteria": ["Agent child task is independently reviewed", "Agent message is visible to the human"],
                "assignee_principal_id": alice_id,
                "reviewer_principal_id": bob_id,
            },
            expected=201,
            label="Work delegation parent creation",
        )
        parent_claim = self.json_request(alice_client, "POST", f"/api/tasks/{parent_task['id']}/claim", body={}, label="Alice delegation parent claim")
        parent_execution_id = parent_claim["execution"]["id"]
        message = self.json_request(
            alice_client,
            "POST",
            "/api/messages",
            body={
                "project_id": project_id,
                "task_id": parent_task["id"],
                "recipient_id": self.agents["work"]["id"],
                "kind": "question",
                "body": f"QA human-to-Agent question {self.run_id}.",
            },
            expected=201,
            label="Human to Agent Work message",
        )
        agent_headers = {"Authorization": f"Bearer {self.agents['work']['token']}"}
        agent_client = self.new_client()
        agent_client.headers.update(agent_headers)
        inbox = self.request(agent_client, "GET", "/api/messages", params={"project_id": project_id, "inbox": "true"}, label="Agent Work inbox").json()
        self.check("work_agent_receives_human_message", any(item.get("id") == message.get("id") for item in inbox if isinstance(item, dict)))
        self.request(
            agent_client,
            "POST",
            "/api/messages",
            body={
                "project_id": project_id,
                "task_id": parent_task["id"],
                "recipient_id": alice_id,
                "kind": "reply",
                "body": f"QA Agent-to-human response {self.run_id}.",
                "reply_to_id": message["id"],
            },
            expected=201,
            label="Agent to human Work reply",
        )
        conversation = self.request(alice_client, "GET", "/api/messages", params={"project_id": project_id, "task_id": parent_task["id"]}, label="Human and Agent Work conversation").json()
        self.check("work_human_agent_messages_share_conversation", len(conversation) >= 2)

        child = self.create_resource(
            alice_client,
            f"/api/tasks/{parent_task['id']}/delegate",
            {
                "agent_id": self.agents["work"]["id"],
                "title": f"QA {self.run_id} delegated Agent child",
                "goal": "Return a deterministic no-LLM task artifact.",
                "acceptance_criteria": ["Agent completes task through REST"],
            },
            expected=201,
            label="Human delegates Work child task to Agent",
        )
        agent_claim = self.json_request(agent_client, "POST", f"/api/tasks/{child['id']}/claim", body={}, label="External Agent claims delegated task")
        agent_execution = agent_claim.get("execution") or {}
        agent_execution_id = agent_execution.get("id")
        agent_lease = agent_claim.get("lease_token")
        if not isinstance(agent_execution_id, str) or not isinstance(agent_lease, str):
            raise AcceptanceError("Agent claim did not return its execution lease")
        self.request(
            agent_client,
            "POST",
            f"/api/tasks/{child['id']}/progress",
            body={"execution_id": agent_execution_id, "lease_token": agent_lease, "progress": 80, "summary": "QA external Agent progress."},
            label="Agent progress update",
        )
        self.request(
            agent_client,
            "POST",
            f"/api/tasks/{child['id']}/submit",
            body={
                "execution_id": agent_execution_id,
                "lease_token": agent_lease,
                "summary": "QA external Agent completed without invoking an LLM.",
                "artifacts": [{"kind": "summary", "title": "Agent evidence", "content": f"Agent evidence {self.run_id}."}],
            },
            label="Agent child submission",
        )
        child_review = self.json_request(
            self.users["bob"].client,
            "POST",
            f"/api/tasks/{child['id']}/review",
            body={"decision": "accept", "comment": "Independent review of the Agent artifact passed."},
            label="Bob independently reviews Agent child",
        )
        self.check("work_human_delegates_agent_without_llm", child_review.get("task", {}).get("status") == "done")
        parent_submission = self.request(
            alice_client,
            "POST",
            f"/api/tasks/{parent_task['id']}/submit",
            body={
                "execution_id": parent_execution_id,
                "summary": "QA Alice coordinated the delegated Agent work.",
                "artifacts": [{"kind": "summary", "title": "Coordination evidence", "content": f"Coordination {self.run_id}."}],
            },
            label="Alice parent task submission",
        ).json()
        self.check("work_parent_task_submitted_after_agent_child", parent_submission.get("task", {}).get("status") == "in_review")
        parent_review = self.json_request(
            self.users["bob"].client,
            "POST",
            f"/api/tasks/{parent_task['id']}/review",
            body={"decision": "accept", "comment": "Independent review of delegated collaboration passed."},
            label="Bob reviews human delegation parent",
        )
        self.check("work_delegation_parent_independently_reviewed", parent_review.get("task", {}).get("status") == "done")

        isolated_task = self.create_resource(
            self.admin.client,
            "/api/tasks",
            {
                "project_id": self.resources["work_isolated_project"]["id"],
                "title": f"QA {self.run_id} isolated Work task",
                "goal": "Exercise project scope isolation.",
            },
            expected=201,
            label="Work isolated task creation",
        )
        reader_denial = self.users["reader"].client.get(f"/api/tasks/{task_id}")
        self.check("work_cross_project_task_denied", reader_denial.status_code in {403, 404})
        reader_allowed = self.request(self.users["reader"].client, "GET", f"/api/tasks/{isolated_task['id']}", label="Reader Work task in assigned scope")
        self.check("work_reader_scope_is_project_specific", reader_allowed.status_code == 200)
        self.resources["work_parent_task"] = parent_task
        self.resources["work_handoff_task"] = handoff_task
        self.phase = "work_collaboration"
        self.checkpoint(completed=True)

    def work_claim_race(self, task_id: str) -> None:
        self.phase = "work_claim_race"
        claim_path = f"/api/tasks/{task_id}/claim"
        claim_names = ("alice", "bob")
        claim_keys = {name: f"qa-{self.run_id}-claim-race-{name}" for name in claim_names}

        def claim_as(name: str) -> tuple[str, httpx.Response]:
            user = self.users[name]
            response = user.client.post(
                claim_path,
                json={},
                headers={"Idempotency-Key": claim_keys[name]},
            )
            return name, response

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(claim_as, name) for name in claim_names]
                responses = dict(future.result(timeout=30) for future in futures)
        except Exception:
            raise AcceptanceError("Concurrent human claim requests failed") from None

        statuses = {name: response.status_code for name, response in responses.items()}
        winners = [name for name, response in responses.items() if response.status_code == 200]
        race_evidence: dict[str, Any] = {"task_id": task_id, "claim_statuses": statuses, "different_idempotency_keys": len(set(claim_keys.values())) == 2}
        self.evidence["claim_race"] = race_evidence

        valid_denials = [name for name, response in responses.items() if response.status_code in {403, 409}]
        one_winner_and_denial = len(winners) == 1 and len(valid_denials) == 1
        if len(winners) != 1:
            self.check("claim_race_has_one_200_and_one_403_or_409", one_winner_and_denial)
            return

        winner_name = winners[0]
        loser_name = next(name for name in claim_names if name != winner_name)
        try:
            claim_payload = responses[winner_name].json()
        except ValueError:
            raise AcceptanceError("Winning claim returned invalid JSON") from None
        execution = claim_payload.get("execution") if isinstance(claim_payload, dict) else None
        if not isinstance(execution, dict) or not isinstance(execution.get("id"), str):
            raise AcceptanceError("Winning claim did not return an execution")

        execution_id = execution["id"]
        winner_client = self.users[winner_name].client
        loser_client = self.users[loser_name].client
        before_rows = self.request(
            winner_client,
            "GET",
            f"/api/tasks/{task_id}/executions",
            label="Read claim race execution before loser write",
        ).json()
        before = next((item for item in before_rows if isinstance(item, dict) and item.get("id") == execution_id), None) if isinstance(before_rows, list) else None
        if before is None:
            raise AcceptanceError("Winning execution was not persisted in PostgreSQL")

        progress_response = loser_client.post(
            f"/api/tasks/{task_id}/progress",
            json={"execution_id": execution_id, "progress": 99, "summary": f"Forbidden loser update {self.run_id}."},
            headers={"Idempotency-Key": f"qa-{self.run_id}-claim-race-loser-progress"},
        )
        after_rows = self.request(
            winner_client,
            "GET",
            f"/api/tasks/{task_id}/executions",
            label="Read claim race execution after loser write",
        ).json()
        after = next((item for item in after_rows if isinstance(item, dict) and item.get("id") == execution_id), None) if isinstance(after_rows, list) else None
        task_after = self.json_request(winner_client, "GET", f"/api/tasks/{task_id}", label="Read claim race task after loser write")

        race_evidence.update({
            "winner": winner_name,
            "loser": loser_name,
            "execution_id": execution_id,
            "persisted_execution_count_before_loser_write": len(before_rows) if isinstance(before_rows, list) else None,
            "winner_executor_kind": execution.get("executor_kind"),
            "winner_has_lease": claim_payload.get("lease_token") is not None,
            "loser_progress_status": progress_response.status_code,
            "progress_before": before.get("progress"),
            "progress_after": after.get("progress") if after else None,
            "summary_after": after.get("summary") if after else None,
            "task_progress_after": task_after.get("progress"),
        })
        invariants = {
            "claim_race_uses_distinct_idempotency_keys": len(set(claim_keys.values())) == 2,
            "claim_race_has_one_200_and_one_403_or_409": one_winner_and_denial and responses[loser_name].status_code in {403, 409},
            "claim_race_persists_exactly_one_execution": isinstance(before_rows, list) and len(before_rows) == 1,
            "claim_race_winner_is_human_without_lease": execution.get("executor_kind") == "human" and execution.get("agent_id") is None and claim_payload.get("lease_token") is None,
            "claim_race_loser_cannot_write_execution": progress_response.status_code in {403, 409},
            "claim_race_loser_write_leaves_execution_unchanged": (
                after is not None
                and after.get("progress") == before.get("progress")
                and after.get("summary") == before.get("summary")
                and task_after.get("progress") == before.get("progress")
            ),
        }
        self.checks.update(invariants)
        if not all(invariants.values()):
            raise AcceptanceError("Concurrent claim invariants failed")

    def verify_work_postgres(self) -> None:
        code = "from sqlalchemy.engine.url import make_url; from ordivant.config import database_url; print(make_url(database_url()).get_backend_name())"
        command = [
            "docker", "compose",
            "--project-directory", str(ROOT),
            "--project-name", self.compose_project,
            "--file", str(ROOT / "compose.yaml"),
            "exec", "-T", "work-api", "python", "-c", code,
        ]
        try:
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise AcceptanceError("Could not verify the QA Work database backend") from None
        if result.returncode != 0:
            raise AcceptanceError("Could not verify the QA Work database backend")
        backend = result.stdout.strip()
        self.evidence["database_backend"] = backend
        self.check("claim_race_uses_postgresql", backend == "postgresql")

    def provision_scoped_agent(self, product: str, resource_id: str) -> dict[str, str]:
        if product == "knowledge":
            container = "knowledge-api"
            code = r'''import json, sys
from ordivant_knowledge.config import get_settings
from ordivant_knowledge.db import make_engine, session_factory
from ordivant_knowledge.models import KnowledgeSpace, Principal, SpaceMembership
from ordivant_knowledge.security import issue_token, new_id, now_iso
engine = make_engine(get_settings().database_url)
factory = session_factory(engine)
with factory() as session:
    space = session.get(KnowledgeSpace, sys.argv[1])
    if space is None:
        raise SystemExit(2)
    principal = session.query(Principal).join(SpaceMembership, SpaceMembership.principal_id == Principal.id).filter(
        Principal.name == sys.argv[2], Principal.kind == "agent", Principal.organization_id == space.organization_id,
        SpaceMembership.space_id == space.id,
    ).one_or_none()
    if principal is None:
        principal_id = new_id()
        principal = Principal(id=principal_id, name=sys.argv[2], kind="agent", role="writer", organization_id=space.organization_id, active=True)
        session.add(principal)
        session.flush()
        session.add(SpaceMembership(id=new_id(), principal_id=principal_id, space_id=space.id))
    token = issue_token(session, principal.id)
    session.commit()
    print(json.dumps({"id": principal.id, "token": token}))
engine.dispose()
'''
        elif product == "code":
            container = "code-api"
            code = r'''import json, sys
from ordivant_code.db import SessionLocal
from ordivant_code.models import Principal, Project, ScopeMembership
from ordivant_code.security import issue_token, new_id, now_utc
with SessionLocal() as session:
    project = session.get(Project, sys.argv[1])
    if project is None:
        raise SystemExit(2)
    principal = session.query(Principal).join(ScopeMembership, ScopeMembership.principal_id == Principal.id).filter(
        Principal.name == sys.argv[2], Principal.kind == "agent", Principal.organization_id == project.organization_id,
        ScopeMembership.scope_id == project.scope_id,
    ).one_or_none()
    if principal is None:
        principal_id = new_id()
        principal = Principal(id=principal_id, organization_id=project.organization_id, name=sys.argv[2], kind="agent", role="writer", active=True, created_at=now_utc())
        session.add(principal)
        session.flush()
        session.add(ScopeMembership(id=new_id(), principal_id=principal_id, scope_id=project.scope_id, role="writer"))
    token = issue_token(session, principal.id)
    session.commit()
    print(json.dumps({"id": principal.id, "token": token}))
'''
        else:
            raise AcceptanceError("Unsupported machine Agent product")

        command = [
            "docker",
            "compose",
            "--project-directory",
            str(ROOT),
            "--project-name",
            self.compose_project,
            "--file",
            str(ROOT / "compose.yaml"),
            "exec",
            "-T",
            container,
            "python",
            "-c",
            code,
            resource_id,
            f"QA {product.title()} Agent {self.run_id}",
        ]
        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=45,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise AcceptanceError(f"Could not provision the QA-scoped {product.title()} Agent") from None
        if result.returncode != 0:
            raise AcceptanceError(f"Could not provision the QA-scoped {product.title()} Agent")
        try:
            payload = json.loads(result.stdout)
        except (ValueError, TypeError):
            raise AcceptanceError(f"Could not read the QA-scoped {product.title()} Agent credential") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("id"), str) or not isinstance(payload.get("token"), str):
            raise AcceptanceError(f"Invalid QA-scoped {product.title()} Agent credential")
        return {"id": payload["id"], "token": payload["token"]}

    def create_knowledge_document(self) -> None:
        assert self.admin is not None
        self.phase = "knowledge_document"
        marker = f"QA-COLLAB-{self.run_id}"
        document = self.create_resource(
            self.admin.client,
            "/knowledge-api/api/documents",
            {
                "space_id": self.resources["knowledge_space"]["id"],
                "title": f"QA shared draft {self.run_id}",
                "summary": "Synthetic multi-editor acceptance document.",
                "body": f"{marker} initial shared content.",
                "change_summary": "Initial QA version.",
            },
            expected=201,
            label="Knowledge collaboration document creation",
        )
        self.resources["knowledge_document"] = document["document"]["id"]
        isolated = self.create_resource(
            self.admin.client,
            "/knowledge-api/api/documents",
            {
                "space_id": self.resources["knowledge_isolated_space"]["id"],
                "title": f"QA isolated document {self.run_id}",
                "body": f"Isolated {marker}.",
                "change_summary": "Initial isolated QA version.",
            },
            expected=201,
            label="Knowledge isolated document creation",
        )
        self.resources["knowledge_isolated_document"] = isolated["document"]["id"]
        self.users["reader"].principal_id = self.json_request(self.users["reader"].client, "GET", "/knowledge-api/me", label="Knowledge reader principal").get("id")
        if "knowledge" not in self.agents:
            self.agents["knowledge"] = self.provision_scoped_agent("knowledge", self.resources["knowledge_space"]["id"])
        self.checkpoint()

    @staticmethod
    def _doc_delta(encoded_state: str, suffix: str) -> str:
        doc = Doc()
        try:
            doc.apply_update(base64.b64decode(encoded_state, validate=True))
            text = doc.get("body", type=Text)
            state = doc.get_state()
            text += suffix
            return base64.b64encode(doc.get_update(state)).decode("ascii")
        except Exception:
            raise AcceptanceError("Could not create a valid synthetic Yjs v1 update") from None

    @staticmethod
    async def _receive_until(socket, predicate, *, label: str, timeout: float = 20, allow_error: bool = False) -> dict[str, Any]:
        async def receive() -> dict[str, Any]:
            while True:
                try:
                    raw = await socket.recv()
                    message = json.loads(raw)
                except Exception:
                    raise AcceptanceError(f"{label}: WebSocket response failed") from None
                if not isinstance(message, dict):
                    raise AcceptanceError(f"{label}: WebSocket returned an invalid message")
                if message.get("type") == "error" and not allow_error:
                    raise AcceptanceError(f"{label}: collaboration error {message.get('code', 'unknown')}")
                if predicate(message):
                    return message

        try:
            return await asyncio.wait_for(receive(), timeout=timeout)
        except asyncio.TimeoutError:
            raise AcceptanceError(f"{label}: timed out waiting for WebSocket response") from None

    async def _open_human_socket(self, user: SessionClient, document_id: str, *, label: str):
        url = self.base_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        url += f"/knowledge-api/api/documents/{document_id}/collaborate"
        socket = await websockets.connect(
            url,
            additional_headers={
                "Origin": self.base_url,
                "Cookie": f"{user.cookie_name}={user.cookie_value}",
            },
            open_timeout=15,
            close_timeout=5,
        )
        await socket.send(json.dumps({"type": "authenticate", "csrf_token": user.csrf_token}))
        sync = await self._receive_until(socket, lambda item: item.get("type") == "sync", label=label)
        if not isinstance(sync.get("draft"), dict):
            await socket.close()
            raise AcceptanceError(f"{label}: sync response did not include the draft")
        return socket, sync

    async def _socket_update(self, socket, update: str, request_id: str, *, label: str) -> dict[str, Any]:
        await socket.send(json.dumps({"type": "update", "update": update, "request_id": request_id}))
        ack = await self._receive_until(
            socket,
            lambda item: item.get("type") == "ack" and item.get("request_id") == request_id,
            label=label,
        )
        return ack

    async def knowledge_websocket_collaboration(self) -> None:
        document_id = self.resources["knowledge_document"]
        alice = self.users["alice"]
        bob = self.users["bob"]
        alice_socket = bob_socket = None
        self.phase = "knowledge_websocket_collaboration"
        try:
            alice_socket, alice_sync = await self._open_human_socket(alice, document_id, label="Alice Knowledge WebSocket authentication")
            bob_socket, bob_sync = await self._open_human_socket(bob, document_id, label="Bob Knowledge WebSocket authentication")
            participants = bob_sync.get("participants", [])
            names = {item.get("name") for item in participants if isinstance(item, dict)}
            self.check(
                "knowledge_presence_uses_authenticated_human_identity",
                f"QA Alice {self.run_id}" in names and f"QA Bob {self.run_id}" in names,
            )
            initial_state = alice_sync["draft"]["update"]
            self.check("knowledge_two_humans_share_same_initial_draft", bob_sync["draft"].get("revision") == alice_sync["draft"].get("revision"))

            alice_delta = self._doc_delta(initial_state, f"\nAlice WebSocket {self.run_id}.")
            bob_delta = self._doc_delta(initial_state, f"\nBob concurrent WebSocket {self.run_id}.")
            offline_delta = self._doc_delta(initial_state, f"\nBob offline reconnect {self.run_id}.")
            agent_delta = self._doc_delta(initial_state, f"\nAgent REST {self.run_id}.")

            attempt_id = uuid.uuid4().hex
            first = await self._socket_update(alice_socket, alice_delta, f"alice-{self.run_id}-{attempt_id}", label="Alice collaborative update")
            second = await self._socket_update(bob_socket, bob_delta, f"bob-{self.run_id}-{attempt_id}", label="Bob concurrent update")
            self.check("knowledge_websocket_ack_after_persisted_human_updates", first["draft"].get("revision", 0) >= 1 and second["draft"].get("revision", 0) >= 2)

            agent_client = self.new_client()
            agent_client.headers["Authorization"] = f"Bearer {self.agents['knowledge']['token']}"
            rest_update = self.json_request(
                agent_client,
                "POST",
                f"/knowledge-api/api/documents/{document_id}/draft/updates",
                body={"update": agent_delta},
                key=f"qa-knowledge-rest-{self.run_id}-{uuid.uuid4().hex}",
                label="Knowledge Agent REST draft update",
            )
            self.check("knowledge_agent_rest_edits_shared_yjs_draft", rest_update.get("body", "").find(f"Agent REST {self.run_id}.") >= 0)

            await bob_socket.close()
            bob_socket = None
            await alice_socket.close()
            alice_socket = None
            bob_socket, reconnect_sync = await self._open_human_socket(bob, document_id, label="Bob Knowledge reconnect")
            self.check("knowledge_reconnect_receives_current_server_state", reconnect_sync["draft"].get("revision", 0) >= 3)
            offline_ack = await self._socket_update(
                bob_socket,
                offline_delta,
                f"bob-offline-{self.run_id}-{uuid.uuid4().hex}",
                label="Bob offline update remerge",
            )
            self.check("knowledge_offline_yjs_update_remerges_after_reconnect", f"Bob offline reconnect {self.run_id}." in offline_ack["draft"].get("body", ""))
        finally:
            for socket in (alice_socket, bob_socket):
                if socket is not None:
                    try:
                        await socket.close()
                    except Exception:
                        pass

        alice_client = self.users["alice"].client
        draft = self.json_request(alice_client, "GET", f"/knowledge-api/api/documents/{document_id}/draft", label="Knowledge merged draft read")
        expected_markers = [
            f"Alice WebSocket {self.run_id}.",
            f"Bob concurrent WebSocket {self.run_id}.",
            f"Agent REST {self.run_id}.",
            f"Bob offline reconnect {self.run_id}.",
        ]
        self.check("knowledge_all_human_agent_and_offline_edits_are_merged", all(marker in draft.get("body", "") for marker in expected_markers))

        reader = self.users["reader"].client
        denied_update = reader.post(
            f"/knowledge-api/api/documents/{document_id}/draft/updates",
            json={"update": self._doc_delta(draft["update"], f"\nReader forbidden {self.run_id}.")},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        self.check("knowledge_reader_cannot_write_shared_draft", denied_update.status_code == 403)
        denied_scope = reader.get(f"/knowledge-api/api/documents/{self.resources['knowledge_isolated_document']}/draft")
        self.check("knowledge_reader_cannot_read_unassigned_space", denied_scope.status_code in {403, 404})

        published = self.json_request(
            alice_client,
            "POST",
            f"/knowledge-api/api/documents/{document_id}/draft/publish",
            body={"expected_revision": draft["revision"], "change_summary": "Publish merged synthetic QA collaboration."},
            expected=201,
            key=f"qa-knowledge-publish-{self.run_id}-{uuid.uuid4().hex}",
            label="Publish merged Knowledge draft",
        )
        self.check("knowledge_publish_preserves_merged_version", all(marker in published.get("body", "") for marker in expected_markers))
        versions = self.request(alice_client, "GET", f"/knowledge-api/api/documents/{document_id}/versions", label="Knowledge immutable versions").json()
        self.check("knowledge_publish_adds_immutable_version", any(item.get("version") == published.get("version") for item in versions if isinstance(item, dict)))
        self.resources["knowledge_revision"] = draft["revision"]
        self.phase = "knowledge_collaboration"
        self.checkpoint(completed=True)

        reader_socket, sync = await self._open_human_socket(self.users["reader"], document_id, label="Knowledge reader WebSocket")
        try:
            invalid_write = self._doc_delta(sync["draft"]["update"], f"\nReader WebSocket forbidden {self.run_id}.")
            request_id = f"reader-forbidden-{self.run_id}"
            await reader_socket.send(json.dumps({"type": "update", "update": invalid_write, "request_id": request_id}))
            denial = await self._receive_until(
                reader_socket,
                lambda item: item.get("type") == "error",
                label="Knowledge reader WebSocket write denial",
                allow_error=True,
            )
            self.check("knowledge_reader_cannot_write_over_websocket", denial.get("code") == "forbidden")
        finally:
            await reader_socket.close()

    def code_collaboration(self) -> None:
        assert self.admin is not None
        self.phase = "code_gitea_collaboration"
        project_id = self.resources["code_project"]["id"]
        alice = self.users["alice"].client
        bob = self.users["bob"].client
        repo = self.create_resource(
            alice,
            "/code-api/api/repositories",
            {"project_id": project_id, "name": f"qa-{self.run_id}", "description": "Synthetic Gitea-backed collaboration acceptance.", "private": True},
            expected=200,
            label="Gitea repository creation through Code API",
        )
        repository_id = repo["id"]
        branch_name = f"qa/{self.run_id}/head"
        self.json_request(
            alice,
            "POST",
            f"/code-api/api/repositories/{repository_id}/branches",
            body={"name": branch_name, "from_branch": "main"},
            label="Gitea QA branch creation",
        )
        file_path = f"qa-collaboration-{self.run_id}.txt"
        initial_commit = self.json_request(
            alice,
            "POST",
            f"/code-api/api/repositories/{repository_id}/files",
            body={"branch": branch_name, "path": file_path, "content": f"Initial {self.run_id}.\n", "commit_message": "Add QA collaboration evidence", "expected_sha": None},
            label="Gitea QA initial commit",
        )
        self.check("code_repository_has_real_gitea_commit", bool(initial_commit.get("commit_sha")) and bool(initial_commit.get("file_sha")))
        pull = self.create_resource(
            alice,
            f"/code-api/api/repositories/{repository_id}/pulls",
            {"head": branch_name, "base": "main", "title": f"QA collaboration {self.run_id}", "body": "Synthetic local collaboration acceptance."},
            expected=200,
            label="Gitea pull request creation",
        )
        pull_number = pull.get("number")
        if not isinstance(pull_number, int):
            raise AcceptanceError("Code API did not return a pull request number")
        collaboration_path = f"/code-api/api/repositories/{repository_id}/pulls/{pull_number}/collaboration"
        initial = self.json_request(bob, "GET", collaboration_path, label="Code live pull collaboration read")
        head_sha = initial.get("head_sha")
        if not isinstance(head_sha, str) or len(head_sha) < 40:
            raise AcceptanceError("Code API did not return the actual Gitea pull request head")
        original_head_sha = self.resources.get("code_initial_head_sha")
        if not isinstance(original_head_sha, str):
            original_head_sha = head_sha
            self.resources["code_initial_head_sha"] = original_head_sha
        self.resources["code_repository"] = repo
        self.resources["code_pull_number"] = pull_number
        self.checkpoint()
        alice_user = self.json_request(alice, "GET", "/code-api/api/me", label="Code Alice writer identity")
        proposer = initial.get("proposer") or {}
        self.check("code_pull_proposer_is_verified_human_creator", proposer.get("id") == alice_user.get("id") and proposer.get("kind") == "human")

        self.phase = "code_local_discussion_and_review"
        comment_path = f"/code-api/api/repositories/{repository_id}/pulls/{pull_number}/comments"
        comment_key = f"qa-human-comment-{self.run_id}"
        comment_body = f"QA Alice review discussion {self.run_id}."
        first_comment = self.json_request(alice, "POST", comment_path, body={"body": comment_body}, key=comment_key, label="Code Alice PR comment")
        replay = self.json_request(alice, "POST", comment_path, body={"body": comment_body}, key=comment_key, label="Code Alice idempotent PR comment replay")
        self.check("code_comment_idempotency_replays_same_receipt", first_comment.get("id") == replay.get("id"))
        changed = self.request(alice, "POST", comment_path, body={"body": f"Changed {self.run_id}."}, key=comment_key, expected=409, label="Code idempotency body conflict")
        self.check("code_comment_idempotency_rejects_changed_body", changed.status_code == 409)

        agent = self.agents.get("code")
        if agent is None:
            agent = self.provision_scoped_agent("code", project_id)
            self.agents["code"] = agent
            self.checkpoint()
        agent_client = self.new_client()
        agent_client.headers["Authorization"] = f"Bearer {agent['token']}"
        agent_comment = self.json_request(
            agent_client,
            "POST",
            comment_path,
            body={"body": f"QA Code Agent comment {self.run_id}."},
            label="Code Agent PR comment",
        )
        self.check("code_agent_comment_uses_same_collaboration_service", agent_comment.get("author", {}).get("kind") == "agent")

        alice_self_review = self.request(
            alice,
            "POST",
            f"/code-api/api/repositories/{repository_id}/pulls/{pull_number}/reviews",
            body={"decision": "approve", "comment": "Self-review must be denied.", "expected_head_sha": head_sha},
            expected=403,
            label="Code proposer self-approval rejection",
        )
        self.check("code_proposer_cannot_approve_own_pull", alice_self_review.status_code == 403)

        old_review = self.json_request(
            bob,
            "POST",
            f"/code-api/api/repositories/{repository_id}/pulls/{pull_number}/reviews",
            body={"decision": "request_changes", "comment": "Record review on the original head.", "expected_head_sha": original_head_sha},
            label="Bob original-head review",
        )
        second_commit = self.json_request(
            alice,
            "POST",
            f"/code-api/api/repositories/{repository_id}/files",
            body={
                "branch": branch_name,
                "path": file_path,
                "content": f"Updated {self.run_id}.\n",
                "commit_message": "Update QA collaboration evidence",
                "expected_sha": initial_commit["file_sha"],
            },
            label="Gitea QA head movement commit",
        )
        self.check("code_gitea_head_moved_after_commit", second_commit.get("commit_sha") != initial_commit.get("commit_sha"))
        refreshed = self.json_request(bob, "GET", collaboration_path, label="Code collaboration after Gitea head move")
        new_head = refreshed.get("head_sha")
        if not isinstance(new_head, str) or new_head == head_sha:
            raise AcceptanceError("Code collaboration did not observe the live Gitea head change")

        stale = self.request(
            bob,
            "POST",
            f"/code-api/api/repositories/{repository_id}/pulls/{pull_number}/reviews",
            body={"decision": "approve", "comment": "Stale approval must be rejected.", "expected_head_sha": original_head_sha},
            expected=409,
            label="Code stale review rejection",
        )
        self.check("code_stale_head_review_rejected", stale.status_code == 409)
        current_review = self.json_request(
            bob,
            "POST",
            f"/code-api/api/repositories/{repository_id}/pulls/{pull_number}/reviews",
            body={"decision": "approve", "comment": "Review of the current Gitea head passed.", "expected_head_sha": new_head},
            label="Bob current-head review",
        )
        self.check("code_current_head_review_saved", current_review.get("head_sha") == new_head)
        final = self.json_request(bob, "GET", collaboration_path, label="Code review history read")
        reviews = final.get("reviews", [])
        self.check(
            "code_review_history_marks_old_stale_and_current",
            any(item.get("id") == old_review.get("id") and item.get("is_current") is False for item in reviews)
            and any(item.get("id") == current_review.get("id") and item.get("is_current") is True for item in reviews),
        )
        self.check("code_local_comments_include_human_and_agent", {item.get("author", {}).get("kind") for item in final.get("comments", [])} >= {"human", "agent"})

        reader = self.users["reader"].client
        reader_comment = reader.post(comment_path, json={"body": f"Forbidden reader {self.run_id}."}, headers={"Idempotency-Key": str(uuid.uuid4())})
        self.check("code_reader_cannot_write_comments", reader_comment.status_code == 403)
        isolated_project = self.resources["code_isolated_project"]["id"]
        isolated_read = reader.get(f"/code-api/api/projects/{isolated_project}")
        self.check("code_reader_cannot_read_unassigned_project", isolated_read.status_code in {403, 404})

        self.resources["code_repository"] = repo
        self.resources["code_pull_number"] = pull_number
        self.resources["code_head_sha"] = new_head
        self.phase = "code_collaboration"
        self.checkpoint(completed=True)

    def make_context(self) -> dict[str, Any]:
        def session_entry(name: str) -> dict[str, Any]:
            user = self.users[name]
            return {
                "cookie_name": user.cookie_name,
                "cookie_value": user.cookie_value,
                "csrf_token": user.csrf_token,
                "principal_id": user.principal_id,
            }

        def resource_id(name: str) -> str | None:
            value = self.resources.get(name)
            if isinstance(value, dict):
                value = value.get("id")
            return value if isinstance(value, str) and value else None

        def safe_resource(value: Any) -> dict[str, Any] | None:
            if not isinstance(value, dict):
                return None
            result = {key: value[key] for key in ("id", "title", "key") if isinstance(value.get(key), (str, int))}
            return result or None

        context: dict[str, Any] = {
            "base_url": self.base_url,
            "run_id": self.run_id,
            "users": {name: session_entry(name) for name in ("admin", "alice", "bob", "reader") if name in self.users},
        }
        work: dict[str, Any] = {}
        if project_id := resource_id("work_project"):
            work["project_id"] = project_id
        task = safe_resource(self.resources.get("browser_task"))
        if task:
            work.update({
                "browser_task_id": task["id"],
                "assignee_id": self.users.get("alice").principal_id if self.users.get("alice") else None,
                "reviewer_id": self.users.get("bob").principal_id if self.users.get("bob") else None,
                "task_title": task.get("title"),
                "task_key": task.get("key"),
            })
        if work:
            context["work"] = work

        knowledge: dict[str, Any] = {}
        if space_id := resource_id("knowledge_space"):
            knowledge["space_id"] = space_id
        if document_id := resource_id("knowledge_document"):
            knowledge["document_id"] = document_id
        if knowledge:
            context["knowledge"] = knowledge

        code: dict[str, Any] = {}
        if project_id := resource_id("code_project"):
            code["project_id"] = project_id
        raw_repo = self.resources.get("code_repository")
        repo = safe_resource(raw_repo)
        if repo:
            code["repository_id"] = repo["id"]
            if isinstance(raw_repo, dict):
                code["repository"] = {key: raw_repo[key] for key in ("owner", "name") if isinstance(raw_repo.get(key), str)}
        pull_number = self.resources.get("code_pull_number")
        if isinstance(pull_number, int):
            code["pull_number"] = pull_number
        if isinstance(self.resources.get("code_head_sha"), str):
            code["head_sha"] = self.resources["code_head_sha"]
        if code:
            context["code"] = code

        safe_resources: dict[str, Any] = {}
        for key in (
            "work_project", "work_isolated_project", "browser_task", "work_handoff_task", "work_parent_task",
            "knowledge_space", "knowledge_isolated_space", "code_project", "code_isolated_project", "code_repository",
        ):
            value = safe_resource(self.resources.get(key))
            if value:
                safe_resources[key] = value
        for key in ("knowledge_document", "knowledge_isolated_document", "knowledge_revision", "code_pull_number", "code_head_sha", "code_initial_head_sha"):
            value = self.resources.get(key)
            if isinstance(value, (str, int)):
                safe_resources[key] = value
        context["agents"] = self.agents
        context["_qa_state"] = {
            "phase": self.phase,
            "completed_phases": sorted(self.completed_phases),
            "checks": self.checks,
            "resources": safe_resources,
        }
        return context

    def execute(self) -> dict[str, Any]:
        self.setup_identity()
        if "create_scopes" not in self.completed_phases:
            self.create_scopes()
        if "invite_users" not in self.completed_phases:
            self.create_users()
        if not self.completed_phases.intersection({"work_collaboration", "work_agent_collaboration"}):
            self.work_directory_and_tasks()
        else:
            self.check("resume_work_phase_already_completed", True)
        if "knowledge_collaboration" not in self.completed_phases:
            self.create_knowledge_document()
            asyncio.run(self.knowledge_websocket_collaboration())
        else:
            self.check("resume_knowledge_phase_already_completed", True)
        if "code_collaboration" not in self.completed_phases and "code_local_discussion_and_review" not in self.completed_phases:
            self.code_collaboration()
        else:
            self.check("resume_code_phase_already_completed", True)
        assert self.admin is not None
        model_settings = self.json_request(self.admin.client, "GET", "/api/model-settings", label="Verify no LLM is configured")
        self.check("collaboration_operates_without_configured_llm", model_settings.get("providers") == [] and model_settings.get("default") is None)
        self.context = self.make_context()
        return self.context

    def verify_saved_context(self, context: dict[str, Any]) -> None:
        if context.get("base_url") != self.base_url:
            raise AcceptanceError("Saved context belongs to a different base URL")
        users = context.get("users")
        work = context.get("work")
        knowledge = context.get("knowledge")
        code = context.get("code")
        if not all(isinstance(value, dict) for value in (users, work, knowledge, code)):
            raise AcceptanceError("Saved context is missing a collaboration resource")
        for name in ("admin", "alice", "bob", "reader"):
            entry = users.get(name)
            if not isinstance(entry, dict) or not all(isinstance(entry.get(key), str) and entry[key] for key in ("cookie_name", "cookie_value", "csrf_token")):
                raise AcceptanceError("Saved QA context is missing a browser session")

        self.phase = "verify_saved_sessions_after_restart"
        clients: dict[str, httpx.Client] = {}
        for name in ("admin", "alice", "bob", "reader"):
            entry = users[name]
            client = self.new_client()
            client.cookies.set(entry["cookie_name"], entry["cookie_value"])
            clients[name] = client
            identity = self.json_request(client, "GET", "/auth-api/me", label=f"Persisted {name} Identity session")
            self.check(f"restart_identity_session_{name}", (identity.get("user") or {}).get("id") is not None)

        task_id = work.get("browser_task_id")
        document_id = knowledge.get("document_id")
        repository_id = code.get("repository_id")
        pull_number = code.get("pull_number")
        if not all((isinstance(task_id, str), isinstance(document_id, str), isinstance(repository_id, str), isinstance(pull_number, int))):
            raise AcceptanceError("Saved context resource IDs are invalid")
        task = self.json_request(clients["alice"], "GET", f"/api/tasks/{task_id}", label="Persisted Work task after restart")
        self.check("restart_work_task_persisted", task.get("id") == task_id)
        draft = self.json_request(clients["alice"], "GET", f"/knowledge-api/api/documents/{document_id}/draft", label="Persisted Knowledge draft after restart")
        self.check("restart_knowledge_collaboration_persisted", "QA-COLLAB-" in draft.get("body", ""))
        collaboration = self.json_request(
            clients["bob"],
            "GET",
            f"/code-api/api/repositories/{repository_id}/pulls/{pull_number}/collaboration",
            label="Persisted Code collaboration after restart",
        )
        self.check("restart_code_collaboration_persisted", collaboration.get("pull_request_id") is not None and bool(collaboration.get("head_sha")))
        self.resources = {"work_task": task_id, "knowledge_document": document_id, "code_repository": repository_id, "code_pull_number": pull_number}


def _safe_output_path(value: str, *, label: str) -> Path:
    base = (ROOT / ".cache" / "collaboration-qa").resolve()
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    resolved = candidate.resolve()
    if resolved == base or base not in resolved.parents:
        raise AcceptanceError(f"{label} must be inside .cache/collaboration-qa")
    return resolved


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sanitized_report(run: CollaborationAcceptance, status: str, failure: Exception | None = None) -> dict[str, Any]:
    resource_ids: dict[str, Any] = {}
    for key in ("work_project", "work_isolated_project", "browser_task", "work_parent_task", "knowledge_space", "knowledge_document", "code_project", "code_repository", "code_pull_number"):
        value = run.resources.get(key)
        if isinstance(value, dict):
            if isinstance(value.get("id"), str):
                report_key = "work_browser_task" if key == "browser_task" else key
                resource_ids[report_key] = value["id"]
        elif isinstance(value, (str, int)):
            resource_ids[key] = value
    report: dict[str, Any] = {
        "status": status,
        "base_url": run.base_url,
        "compose_project": run.compose_project,
        "run_id": run.run_id,
        "phase": run.phase,
        "checks": run.checks,
        "resource_ids": resource_ids,
        "check_count": len(run.checks),
    }
    if run.evidence:
        report["evidence"] = run.evidence
    if failure is not None:
        report["failure"] = str(failure) if isinstance(failure, AcceptanceError) else type(failure).__name__
    return report


def _validate_target(base_url: str, compose_project: str) -> None:
    parsed = urlsplit(base_url)
    if (
        base_url.rstrip("/") != QA_BASE_URL
        or parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port != 8096
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise AcceptanceError("Only the dedicated local collaboration QA URL is allowed")
    if compose_project != QA_COMPOSE_PROJECT:
        raise AcceptanceError("Only the dedicated collaboration QA Compose project is allowed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=QA_BASE_URL)
    parser.add_argument("--project", "--compose-project", dest="compose_project", default=QA_COMPOSE_PROJECT)
    parser.add_argument("--context-output", default=str(QA_CONTEXT.relative_to(ROOT)))
    parser.add_argument("--report-output")
    parser.add_argument("--verify-context", action="store_true", help="Read saved QA sessions and verify persisted resources after a service restart")
    parser.add_argument("--resume", action="store_true", help="Resume a prior synthetic QA run using its saved context and sessions")
    parser.add_argument("--work-only", action="store_true", help="Run a fresh Work-only round trip from a saved QA context without writing that context")
    parser.add_argument("--work-claim-race-only", action="store_true", help="Run concurrent human claim acceptance from a saved QA context without modifying that context")
    parser.add_argument("--context-input", default=str(QA_CONTEXT.relative_to(ROOT)))
    args = parser.parse_args(argv)
    run = CollaborationAcceptance(args.base_url, args.compose_project)
    context_restored = False
    try:
        _validate_target(args.base_url, args.compose_project)
        if sum((args.resume, args.verify_context, args.work_only, args.work_claim_race_only)) > 1:
            raise AcceptanceError("--resume, --verify-context, --work-only, and --work-claim-race-only are mutually exclusive")
        default_report = "work-report.json" if args.work_only else "work-race-report.json" if args.work_claim_race_only else "api-report.json"
        report_value = args.report_output or str((ROOT / ".cache" / "collaboration-qa" / default_report).relative_to(ROOT))
        report_path = _safe_output_path(report_value, label="Report output")
        context_path = _safe_output_path(args.context_output, label="Context output")
        if report_path == context_path:
            raise AcceptanceError("Context and report must use separate files")
        run.context_path = None if args.verify_context or args.work_only or args.work_claim_race_only else context_path

        if args.verify_context:
            source_path = _safe_output_path(args.context_input, label="Context input")
            try:
                context = json.loads(source_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise AcceptanceError("Could not read the saved QA context") from None
            if not isinstance(context, dict):
                raise AcceptanceError("Saved QA context is invalid")
            run.verify_saved_context(context)
        elif args.work_claim_race_only:
            source_path = _safe_output_path(args.context_input, label="Context input")
            try:
                saved_context = json.loads(source_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise AcceptanceError("Could not read the saved QA context") from None
            if not isinstance(saved_context, dict):
                raise AcceptanceError("Saved QA context is invalid")
            run.restore_context(saved_context)
            context_restored = True
            run.run_id = uuid.uuid4().hex[:10]
            run.checks.clear()
            run.completed_phases.clear()
            run.evidence.clear()
            alice_principal_id = run.users.get("alice").principal_id if run.users.get("alice") else None
            if run.admin is None or not isinstance(run.resources.get("work_project"), dict) or not isinstance(alice_principal_id, str) or not alice_principal_id:
                raise AcceptanceError("Saved QA context is missing Work resources")
            project_id = run.resources["work_project"]["id"]
            run.verify_work_postgres()

            participants = run.request(
                run.admin.client,
                "GET",
                f"/api/projects/{project_id}/participants",
                label="Work claim race project participants",
            ).json()
            if not isinstance(participants, list):
                raise AcceptanceError("Work participants response was invalid")

            def participant_for(name: str) -> dict[str, Any]:
                user = run.users.get(name)
                principal_id = user.principal_id if user else None
                matches = [
                    item for item in participants
                    if isinstance(item, dict)
                    and item.get("kind") == "human"
                    and isinstance(principal_id, str)
                    and item.get("principal_id") == principal_id
                ]
                if len(matches) != 1:
                    raise AcceptanceError(f"Work claim race did not resolve exactly one {name} participant")
                return matches[0]

            claim_roles = {"admin", "manager", "worker"}
            claimant_roles: dict[str, str] = {}
            for name in ("alice", "bob"):
                role = participant_for(name).get("role")
                if not isinstance(role, str) or role not in claim_roles:
                    raise AcceptanceError(f"Work claim race participant {name} does not have a claim-capable role")
                claimant_roles[name] = role
            run.check("claim_race_both_claimers_have_claim_capable_roles", True)
            run.evidence["claim_race_claimant_roles"] = claimant_roles

            admin_me = run.json_request(run.admin.client, "GET", "/api/me", label="Work claim race independent reviewer")
            reviewer_id = admin_me.get("id")
            if not isinstance(reviewer_id, str) or not reviewer_id or reviewer_id in {alice_principal_id, run.users["bob"].principal_id}:
                raise AcceptanceError("Work claim race reviewer is not independent of the contenders")
            run.admin.principal_id = reviewer_id
            reviewer = participant_for("admin")
            if reviewer.get("principal_id") != reviewer_id:
                raise AcceptanceError("Work claim race reviewer is not a project participant")
            run.check("claim_race_reviewer_is_independent_of_both_claimers", True)

            race_task = run.create_resource(
                run.admin.client,
                "/api/tasks",
                {
                    "project_id": project_id,
                    "title": f"QA {run.run_id} concurrent human claim race",
                    "goal": "Prove PostgreSQL permits exactly one concurrent human claim and fences the losing actor from that execution.",
                    "acceptance_criteria": ["Exactly one claim succeeds", "Losing actor cannot update winner execution"],
                    "reviewer_principal_id": reviewer_id,
                },
                expected=201,
                label="Work unassigned claim race task creation",
            )
            race_task_precondition = (
                race_task.get("status") == "ready"
                and race_task.get("assignee_principal_id") is None
                and race_task.get("assignee_id") is None
                and race_task.get("reviewer_principal_id") == reviewer_id
            )
            run.evidence["claim_race_precondition"] = {
                "task_id": race_task.get("id"),
                "status": race_task.get("status"),
                "unassigned": race_task.get("assignee_principal_id") is None and race_task.get("assignee_id") is None,
                "independent_reviewer": race_task.get("reviewer_principal_id") == reviewer_id,
            }
            run.check("claim_race_starts_ready_unassigned_with_independent_reviewer", race_task_precondition)
            run.resources["work_race_task"] = race_task
            run.work_claim_race(race_task["id"])
            context = None
        elif args.work_only:
            source_path = _safe_output_path(args.context_input, label="Context input")
            try:
                saved_context = json.loads(source_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise AcceptanceError("Could not read the saved QA context") from None
            if not isinstance(saved_context, dict):
                raise AcceptanceError("Saved QA context is invalid")
            run.restore_context(saved_context)
            context_restored = True
            run.run_id = uuid.uuid4().hex[:10]
            run.checks.clear()
            run.completed_phases.clear()
            if run.admin is None or "work_project" not in run.resources:
                raise AcceptanceError("Saved QA context is missing the Work administrator or project")
            run.work_directory_and_tasks()
            model_settings = run.json_request(run.admin.client, "GET", "/api/model-settings", label="Verify Work collaboration without configured LLM")
            run.check("work_round_trip_operates_without_configured_llm", model_settings.get("providers") == [] and model_settings.get("default") is None)
            context = None
        elif args.resume:
            source_path = _safe_output_path(args.context_input, label="Context input")
            try:
                context = json.loads(source_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise AcceptanceError("Could not read the saved QA context") from None
            if not isinstance(context, dict):
                raise AcceptanceError("Saved QA context is invalid")
            run.restore_context(context)
            context_restored = True
            try:
                prior_report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                prior_report = None
            if isinstance(prior_report, dict) and prior_report.get("run_id") == run.run_id:
                prior_checks = prior_report.get("checks")
                if isinstance(prior_checks, dict):
                    run.checks.update({key: value for key, value in prior_checks.items() if isinstance(key, str) and isinstance(value, bool)})
            context = run.execute()
        else:
            context = run.execute()
        if not args.verify_context and not args.work_only and not args.work_claim_race_only:
            _write_json(context_path, context)

        report = _sanitized_report(run, "passed")
        _write_json(report_path, report)
        print(f"COLLABORATION_ACCEPTANCE_PASSED checks={len(run.checks)} report={report_path}")
        return 0
    except Exception as error:
        report_path = None
        try:
            if run.context_path is not None and run.users and (not args.resume or context_restored):
                run.checkpoint()
            report_path = _safe_output_path(args.report_output, label="Report output")
            _write_json(report_path, _sanitized_report(run, "failed", error))
        except Exception:
            pass
        if isinstance(error, AcceptanceError):
            print(f"COLLABORATION_ACCEPTANCE_FAILED phase={run.phase}: {error}")
        else:
            print(f"COLLABORATION_ACCEPTANCE_FAILED phase={run.phase}: {type(error).__name__}")
        return 1
    finally:
        for client in run.clients:
            try:
                client.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
