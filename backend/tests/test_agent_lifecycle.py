from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from sqlalchemy import func, select

from conftest import create_task, headers
from ordivant import mcp_server
from ordivant.collaboration_models import CollaborationSubscription
from ordivant.models import (
    Agent, AgentExecutionSetting, AuthToken, AuditEvent, Execution,
    Organization, Principal, ProjectMembership, Task,
)
from ordivant.security import new_id, now_utc


def retire(client, system, agent_id, operation="archive", *, key="retire-once", actor="manager"):
    return client.request(
        "POST" if operation == "archive" else "DELETE",
        f"/api/agents/{agent_id}" + ("/archive" if operation == "archive" else ""),
        headers=headers(system, actor, key),
    )


def test_unused_agent_delete_cleans_credentials_settings_and_replays(api_client, system):
    payload = {
        "name": "Unused Agent", "role": "worker", "runtime": "pi",
        "project_ids": [system["ids"]["project"]], "execution_config": {"instructions": "Synthetic test"},
    }
    created = api_client.post("/api/agents", json=payload, headers=headers(system, "manager", "create-unused"))
    assert created.status_code == 201, created.text
    agent = created.json()
    deleted = retire(api_client, system, agent["id"], "delete")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] is True
    assert retire(api_client, system, agent["id"], "delete").json() == deleted.json()
    assert api_client.get("/api/me", headers={"Authorization": f"Bearer {agent['token']}"}).status_code == 401
    with system["factory"]() as db:
        assert db.get(Agent, agent["id"]) is None
        assert db.get(Principal, agent["principal_id"]) is None
        assert db.get(AgentExecutionSetting, agent["id"]) is None
        assert db.scalar(select(AuthToken.id).where(AuthToken.principal_id == agent["principal_id"])) is None
        assert db.scalar(select(ProjectMembership.id).where(ProjectMembership.principal_id == agent["principal_id"])) is None
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "agent.deleted")) == 1
    # The original create receipt must not recreate a deleted Agent or issue credentials.
    assert "token" not in deleted.json()
    assert api_client.post("/api/agents", json=payload, headers=headers(system, "manager", "create-unused")).status_code == 404


def test_archived_agent_create_replay_cannot_issue_new_credentials(api_client, system):
    payload = {"name": "Retired Agent", "role": "worker", "runtime": "pi", "project_ids": [system["ids"]["project"]]}
    created = api_client.post("/api/agents", json=payload, headers=headers(system, "manager", "create-retired"))
    assert created.status_code == 201, created.text
    agent = created.json()
    assert retire(api_client, system, agent["id"]).status_code == 200
    replay = api_client.post("/api/agents", json=payload, headers=headers(system, "manager", "create-retired"))
    assert replay.status_code == 409, replay.text
    assert replay.json()["detail"]["code"] == "agent_archived"
    with system["factory"]() as db:
        tokens = list(db.scalars(select(AuthToken).where(AuthToken.principal_id == agent["principal_id"])))
        assert len(tokens) == 1
        assert tokens[0].revoked_at is not None


def test_archive_preserves_completed_evidence_and_revokes_tokens(api_client, system):
    agent_id = system["agents"]["worker-a"]
    task = create_task(api_client, system, assignee_id=agent_id, reviewer_id=system["agents"]["reviewer-c"])
    claim = api_client.post(f"/api/tasks/{task['id']}/claim", json={}, headers=headers(system, "worker_a")).json()
    submitted = api_client.post(f"/api/tasks/{task['id']}/submit", json={
        "execution_id": claim["execution"]["id"], "lease_token": claim["lease_token"],
        "summary": "Synthetic completed work", "artifacts": [{"kind": "summary", "title": "Evidence", "content": "Verified fixture"}],
    }, headers=headers(system, "worker_a"))
    assert submitted.status_code == 200, submitted.text
    accepted = api_client.post(f"/api/tasks/{task['id']}/review", json={"decision": "accept", "comment": "Independent fixture review"}, headers=headers(system, "reviewer"))
    assert accepted.status_code == 200, accepted.text
    archived = retire(api_client, system, agent_id)
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"
    assert "token" not in archived.json()
    assert retire(api_client, system, agent_id).json() == archived.json()
    assert retire(api_client, system, agent_id, key="second-archive").status_code == 200
    assert retire(api_client, system, agent_id, "delete").json()["detail"]["code"] == "agent_has_history"
    context = api_client.get(f"/api/tasks/{task['id']}/context", headers=headers(system, "manager")).json()
    assert context["task"]["status"] == "done"
    assert context["task"]["assignee"]["name"] == "worker-a"
    assert context["executions"][0]["executor_name"] == "worker-a"
    assert context["artifacts"][0]["content"] == "Verified fixture"
    assert api_client.get("/api/me", headers=headers(system, "worker_a")).status_code == 401
    with system["factory"]() as db:
        assert not db.get(Principal, system["ids"]["worker_a"]).active
        assert all(token.revoked_at for token in db.scalars(select(AuthToken).where(AuthToken.principal_id == system["ids"]["worker_a"])))
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "agent.archived")) == 1


def test_archive_hidden_from_directory_context_assignments_and_counts(api_client, system):
    agent_id = system["agents"]["worker-a"]
    before = api_client.get("/api/overview", headers=headers(system, "manager")).json()["agents"]["total"]
    assert retire(api_client, system, agent_id).status_code == 200
    assert agent_id not in {a["id"] for a in api_client.get("/api/agents", headers=headers(system, "manager")).json()}
    assert agent_id in {a["id"] for a in api_client.get("/api/agents?include_archived=true", headers=headers(system, "manager")).json()}
    context = api_client.get(f"/api/projects/{system['ids']['project']}/context", headers=headers(system, "manager")).json()
    assert agent_id not in {a["id"] for a in context["agents"]}
    participants = api_client.get(f"/api/projects/{system['ids']['project']}/participants", headers=headers(system, "manager")).json()
    assert agent_id not in {a["id"] for a in participants}
    assert api_client.get("/api/overview", headers=headers(system, "manager")).json()["agents"]["total"] == before - 1
    changed = api_client.patch(f"/api/agents/{agent_id}", json={"status": "available"}, headers=headers(system, "manager"))
    assert changed.status_code == 409
    assigned = api_client.post("/api/tasks", json={"project_id": system["ids"]["project"], "title": "Invalid new work", "assignee_id": agent_id}, headers=headers(system, "manager"))
    assert assigned.status_code == 409


def test_disable_then_reenable_restores_identity_participation_and_claims(api_client, system):
    agent_id = system["agents"]["worker-a"]
    task = create_task(api_client, system)
    path = f"/api/agents/{agent_id}"
    disabled = api_client.patch(path, json={"status": "disabled"}, headers=headers(system, "manager", "disable"))
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["status"] == "disabled"
    assert api_client.get("/api/me", headers=headers(system, "worker_a")).status_code == 401
    participants_path = f"/api/projects/{system['ids']['project']}/participants"
    assert agent_id not in {a["id"] for a in api_client.get(participants_path, headers=headers(system, "manager")).json()}
    enabled = api_client.patch(path, json={"status": "available"}, headers=headers(system, "manager", "reenable"))
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["status"] == "available"
    assert api_client.patch(path, json={"status": "available"}, headers=headers(system, "manager", "reenable")).json() == enabled.json()
    with system["factory"]() as db:
        assert db.get(Principal, system["ids"]["worker_a"]).active
    assert api_client.get("/api/me", headers=headers(system, "worker_a")).status_code == 200
    assert agent_id in {a["id"] for a in api_client.get(participants_path, headers=headers(system, "manager")).json()}
    claim = api_client.post(f"/api/tasks/{task['id']}/claim", json={}, headers=headers(system, "worker_a"))
    assert claim.status_code == 200, claim.text
    assert claim.json()["execution"]["agent_id"] == agent_id


@pytest.mark.parametrize("actor", ["worker_b", "runtime"])
def test_reenable_requires_management_permission(api_client, system, actor):
    path = f"/api/agents/{system['agents']['worker-a']}"
    assert api_client.patch(path, json={"status": "disabled"}, headers=headers(system, "manager", "disable")).status_code == 200
    denied = api_client.patch(path, json={"status": "available"}, headers=headers(system, actor, "unauthorized-enable"))
    assert denied.status_code == 403, denied.text
    with system["factory"]() as db:
        assert db.get(Agent, system["agents"]["worker-a"]).status == "disabled"
        assert not db.get(Principal, system["ids"]["worker_a"]).active


@pytest.mark.parametrize("operation", ["archive", "delete"])
@pytest.mark.parametrize("status", ["backlog", "ready", "in_progress", "blocked", "in_review"])
def test_unfinished_assignment_blocks_retirement(api_client, system, operation, status):
    agent_id = system["agents"]["worker-a"]
    task = create_task(api_client, system, assignee_id=agent_id)
    with system["factory"]() as db:
        db.get(Task, task["id"]).status = status
        db.commit()
    response = retire(api_client, system, agent_id, operation)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "agent_has_active_work"
    assert api_client.get("/api/me", headers=headers(system, "worker_a")).status_code == 200


def test_pending_reviewer_assignment_blocks_archive(api_client, system):
    agent_id = system["agents"]["reviewer-c"]
    create_task(api_client, system, reviewer_id=agent_id)
    assert retire(api_client, system, agent_id).json()["detail"]["code"] == "agent_has_active_work"


def test_queued_run_blocks_retirement(api_client, system):
    agent_id = system["agents"]["worker-b"]
    task = create_task(api_client, system)
    response = api_client.post(f"/api/tasks/{task['id']}/dispatch", json={"agent_id": agent_id}, headers=headers(system, "manager"))
    assert response.status_code == 201, response.text
    for operation in ("archive", "delete"):
        assert retire(api_client, system, agent_id, operation).json()["detail"]["code"] == "agent_has_active_work"


@pytest.mark.parametrize("kind", ["workflow", "rule"])
def test_automation_references_preserved_and_enabled_references_block_archive(api_client, system, kind):
    agent_id = system["agents"]["worker-b"]
    project = system["ids"]["project"]
    if kind == "workflow":
        response = api_client.post("/api/workflows", json={
            "project_id": project, "key": "lifecycle", "name": "Lifecycle", "steps": [{"key": "one", "title": "One", "goal": "Fixture", "agent_id": agent_id}],
            "schedule": {"enabled": True, "interval_minutes": 60, "max_runs": 3},
        }, headers=headers(system, "manager", "workflow"))
        assert response.status_code == 201, response.text
        path = f"/api/workflows/{response.json()['id']}/schedule"
        disable = {"enabled": False, "interval_minutes": 60, "max_runs": 3}
        update_method = api_client.patch
    else:
        response = api_client.post(f"/api/projects/{project}/rules", json={
            "name": "Assignment fixture", "event": "task.created", "conditions": {}, "action": "assign",
            "parameters": {"assignee_principal_id": system["ids"]["worker_b"]}, "enabled": True,
        }, headers=headers(system, "manager", "rule"))
        assert response.status_code == 201, response.text
        path, disable, update_method = f"/api/rules/{response.json()['id']}", {"enabled": False}, api_client.patch
    assert retire(api_client, system, agent_id).json()["detail"]["code"] == "agent_in_active_automation"
    disabled = update_method(path, json=disable, headers=headers(system, "manager", "disable-automation"))
    assert disabled.status_code == 200, disabled.text
    assert retire(api_client, system, agent_id, "delete").json()["detail"]["code"] == "agent_has_history"
    assert retire(api_client, system, agent_id).status_code == 200
    enabled = update_method(path, json={**disable, "enabled": True}, headers=headers(system, "manager", "enable-archived"))
    assert enabled.status_code in {409, 422}, enabled.text


def test_collaboration_reference_without_foreign_key_blocks_delete(api_client, system):
    task = create_task(api_client, system)
    with system["factory"]() as db:
        subscription = CollaborationSubscription(id=new_id(), resource_kind="task", resource_id=task["id"], principal_id=system["ids"]["worker_a"])
        db.add(subscription)
        db.commit()
    agent_id = system["agents"]["worker-a"]
    assert retire(api_client, system, agent_id, "delete").json()["detail"]["code"] == "agent_has_history"
    assert retire(api_client, system, agent_id).status_code == 200


@pytest.mark.parametrize("operation", ["archive", "delete"])
def test_scope_role_and_idempotency_permissions(api_client, system, operation):
    agent_id = system["agents"]["worker-a"]
    assert retire(api_client, system, agent_id, operation, actor="worker_b").status_code == 403
    assert retire(api_client, system, agent_id, operation, actor="runtime").status_code == 403
    missing_key = api_client.request("POST" if operation == "archive" else "DELETE", f"/api/agents/{agent_id}" + ("/archive" if operation == "archive" else ""), headers=headers(system, "manager"))
    assert missing_key.status_code == 422
    with system["factory"]() as db:
        db.add(ProjectMembership(id=new_id(), principal_id=system["ids"]["worker_a"], project_id=system["ids"]["isolated_project"]))
        membership = db.scalar(select(ProjectMembership).where(ProjectMembership.principal_id == system["ids"]["manager"], ProjectMembership.project_id == system["ids"]["isolated_project"]))
        db.delete(membership)
        db.commit()
    assert retire(api_client, system, agent_id, operation).status_code == 404


@pytest.mark.parametrize("operation", ["archive", "delete"])
def test_receipt_replay_rechecks_current_project_scope(api_client, system, operation):
    agent_id = system["agents"]["worker-a"]
    assert retire(api_client, system, agent_id, operation).status_code == 200
    with system["factory"]() as db:
        membership = db.scalar(select(ProjectMembership).where(ProjectMembership.principal_id == system["ids"]["manager"], ProjectMembership.project_id == system["ids"]["project"]))
        db.delete(membership)
        db.commit()
    assert retire(api_client, system, agent_id, operation).status_code == 404


def test_other_organization_agent_is_inaccessible(api_client, system):
    with system["factory"]() as db:
        org = Organization(id=new_id(), name="Other org", created_at=now_utc())
        db.add(org)
        db.flush()
        db.get(Principal, system["ids"]["worker_a"]).organization_id = org.id
        db.commit()
    for operation in ("archive", "delete"):
        assert retire(api_client, system, system["agents"]["worker-a"], operation).status_code == 404


@pytest.mark.parametrize("operation", ["archive", "delete"])
def test_claim_and_retirement_serialize(api_client, system, operation):
    task = create_task(api_client, system)
    agent_id = system["agents"]["worker-a"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        claim = pool.submit(api_client.post, f"/api/tasks/{task['id']}/claim", json={}, headers=headers(system, "worker_a"))
        retirement = pool.submit(retire, api_client, system, agent_id, operation)
        claimed, retired = claim.result(), retirement.result()
    assert claimed.status_code == 200 or retired.status_code == 200, (claimed.text, retired.text)
    with system["factory"]() as db:
        executions = list(db.scalars(select(Execution).where(Execution.task_id == task["id"])))
        if retired.status_code == 200:
            assert claimed.status_code in {401, 403, 404, 409}
            assert not executions
        else:
            assert retired.status_code == 409
            assert len(executions) == 1
            assert db.get(Agent, agent_id).status == "busy"


def test_mcp_lifecycle_uses_same_rest_guards_and_stable_keys(api_client, system, monkeypatch):
    monkeypatch.setattr(mcp_server, "API_TOKEN", system["tokens"]["manager"])
    original_client = httpx.AsyncClient
    monkeypatch.setattr(mcp_server.httpx, "AsyncClient", lambda *a, **kw: original_client(*a, **{**kw, "transport": httpx.ASGITransport(app=api_client.app)}))

    async def run():
        agent_id = system["agents"]["worker-a"]
        archived = await mcp_server.archive_agent(agent_id, request_id="mcp-archive")
        assert archived["status"] == "archived"
        assert (await mcp_server.archive_agent(agent_id, request_id="mcp-archive"))["id"] == agent_id
        assert agent_id not in {a["id"] for a in await mcp_server.find_agents()}
        assert agent_id in {a["id"] for a in await mcp_server.find_agents(include_archived=True)}
        deleted = await mcp_server.delete_agent(agent_id, request_id="mcp-delete")
        assert deleted["deleted"] is True
        assert await mcp_server.delete_agent(agent_id, request_id="mcp-delete") == deleted

    asyncio.run(run())
