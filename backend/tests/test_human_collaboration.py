from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import MetaData, inspect, select
from sqlalchemy.orm import sessionmaker

from ordivant import mcp_server
from ordivant.db import Base, make_engine
from ordivant.migrations import migrate_collaboration
from ordivant.models import Agent, Artifact, AuditEvent, Execution, Principal, ProjectMembership, Task
from ordivant.security import issue_token, new_id, now_utc

from conftest import create_task, headers


@pytest.fixture
def colleagues(system):
    with system["factory"]() as session:
        for name, role, project in (
            ("alice", "worker", "project"),
            ("bob", "worker", "project"),
            ("human_reviewer", "reviewer", "project"),
            ("other_reviewer", "reviewer", "project"),
            ("human_outsider", "worker", "isolated_project"),
        ):
            person = Principal(
                id=new_id(), name=name, kind="human", role=role, active=True,
                organization_id=system["ids"]["organization"], team_id=system["ids"]["team"],
            )
            session.add(person)
            session.flush()
            session.add(ProjectMembership(id=new_id(), principal_id=person.id, project_id=system["ids"][project]))
            system["ids"][name] = person.id
            system["tokens"][name] = issue_token(session, person.id)
        session.commit()
    return system


def claim(client, system, task, person, key=None):
    response = client.post(f"/api/tasks/{task['id']}/claim", json={}, headers=headers(system, person, key))
    assert response.status_code == 200
    return response.json()


def submit(client, system, task, person, execution):
    response = client.post(
        f"/api/tasks/{task['id']}/submit",
        json={"execution_id": execution["id"], "summary": "Delivered by a coworker",
              "artifacts": [{"kind": "document", "title": "Evidence", "content": "Completed acceptance criteria"}]},
        headers=headers(system, person, f"submit-{execution['id']}"),
    )
    assert response.status_code == 200
    return response.json()


def test_no_llm_human_assignment_claim_persistence_and_independent_review(api_client, colleagues):
    system = colleagues
    task = create_task(api_client, system, assignee_principal_id=system["ids"]["alice"],
                       reviewer_principal_id=system["ids"]["human_reviewer"])
    assert task["assignee"] == {"id": system["ids"]["alice"], "principal_id": system["ids"]["alice"],
                                "name": "alice", "kind": "human"}
    assert task["assignee_id"] is None
    assert api_client.post(f"/api/tasks/{task['id']}/claim", json={}, headers=headers(system, "bob")).status_code == 403
    assert api_client.post(f"/api/tasks/{task['id']}/claim", json={}, headers=headers(system, "worker_a")).status_code == 403
    claimed = claim(api_client, system, task, "alice", "human-claim")
    execution = claimed["execution"]
    assert claimed["lease_token"] is None
    assert execution["executor_kind"] == "human"
    assert execution["executor_name"] == "alice"
    assert execution["agent_id"] is None and execution["lease_expires_at"] is None
    assert execution["claimed_by_principal_id"] == system["ids"]["alice"]
    replay = api_client.post(f"/api/tasks/{task['id']}/claim", json={}, headers=headers(system, "alice", "human-claim"))
    assert replay.status_code == 200 and replay.json()["execution"]["id"] == execution["id"]
    assert replay.json()["lease_token"] is None
    with system["factory"]() as session:
        session.get(Execution, execution["id"]).started_at = now_utc() - timedelta(days=30)
        session.commit()
    # A new request/session recovers the execution without carrying any lease or LLM config.
    context = api_client.get(f"/api/tasks/{task['id']}/context", headers=headers(system, "alice")).json()
    assert context["executions"][0]["id"] == execution["id"]
    progress = api_client.post(f"/api/tasks/{task['id']}/progress", json={"execution_id": execution["id"], "progress": 75},
                               headers=headers(system, "alice"))
    assert progress.status_code == 200 and progress.json()["progress"] == 75
    for intruder in ("bob", "manager", "worker_a"):
        assert api_client.post(f"/api/tasks/{task['id']}/progress", json={"execution_id": execution["id"], "progress": 99},
                               headers=headers(system, intruder)).status_code == 409
    assert api_client.post(f"/api/tasks/{task['id']}/renew", json={"execution_id": execution["id"]},
                           headers=headers(system, "alice")).status_code == 409
    submitted = submit(api_client, system, task, "alice", execution)
    assert submitted["task"]["status"] == "in_review"
    assert api_client.post(f"/api/tasks/{task['id']}/review", json={"decision": "accept", "comment": "Wrong reviewer"},
                           headers=headers(system, "other_reviewer")).status_code == 403
    accepted = api_client.post(f"/api/tasks/{task['id']}/review", json={"decision": "accept", "comment": "Evidence verified"},
                               headers=headers(system, "human_reviewer"))
    assert accepted.status_code == 200 and accepted.json()["task"]["status"] == "done"
    with system["factory"]() as session:
        assert session.get(Execution, execution["id"]).submitted_by_principal_id == system["ids"]["alice"]
        assert session.scalar(select(AuditEvent).where(AuditEvent.entity_id == task["id"],
                              AuditEvent.action == "task.review.accept")).actor_id == system["ids"]["human_reviewer"]


def test_human_release_allows_coworker_to_take_over_and_fences_old_work(api_client, colleagues):
    system = colleagues
    task = create_task(api_client, system)
    first = claim(api_client, system, task, "alice")["execution"]
    unchanged = api_client.patch(f"/api/tasks/{task['id']}", json={"assignee_principal_id": system["ids"]["alice"],
                                  "assignee_id": None, "description": "Updated specification"}, headers=headers(system, "manager"))
    assert unchanged.status_code == 200
    changed = api_client.patch(f"/api/tasks/{task['id']}", json={"assignee_principal_id": system["ids"]["bob"]},
                               headers=headers(system, "manager"))
    assert changed.status_code == 409
    released = api_client.post(f"/api/tasks/{task['id']}/release", json={"execution_id": first["id"], "handoff": "Ready for Bob"},
                               headers=headers(system, "alice"))
    assert released.status_code == 200 and released.json()["assignee_principal_id"] is None
    second = claim(api_client, system, task, "bob")["execution"]
    assert second["id"] != first["id"]
    assert api_client.post(f"/api/tasks/{task['id']}/progress", json={"execution_id": first["id"], "progress": 99},
                           headers=headers(system, "alice")).status_code == 409
    context = api_client.get(f"/api/tasks/{task['id']}/context", headers=headers(system, "bob")).json()
    assert context["task"]["handoff"] == "Ready for Bob" and len(context["executions"]) == 2


def test_human_claim_race_and_human_agent_claim_race_have_one_execution(api_client, colleagues):
    for contenders in (("alice", "bob"), ("alice", "worker_a")):
        task = create_task(api_client, colleagues)
        def attempt(name):
            return api_client.post(f"/api/tasks/{task['id']}/claim", json={}, headers=headers(colleagues, name)).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(attempt, contenders))
        assert statuses.count(200) == 1 and all(value in {200, 403, 409} for value in statuses)
        with colleagues["factory"]() as session:
            executions = session.scalars(select(Execution).where(Execution.task_id == task["id"])).all()
            assert len(executions) == 1
            agent = session.get(Agent, executions[0].agent_id) if executions[0].agent_id else None
            if agent:
                # Make the agent available before this test's next independent race.
                agent.status = "available"
                session.commit()


def test_scoped_participants_assignments_and_agent_lease_cannot_be_bypassed(api_client, colleagues):
    system = colleagues
    participants = api_client.get(f"/api/projects/{system['ids']['project']}/participants", headers=headers(system, "alice"))
    assert participants.status_code == 200
    assert {item["kind"] for item in participants.json()} == {"human", "agent"}
    assert not any(item["id"] == system["ids"]["human_outsider"] for item in participants.json())
    assert api_client.get(f"/api/projects/{system['ids']['isolated_project']}/participants", headers=headers(system, "alice")).status_code == 404
    for fields in (
        {"assignee_principal_id": system["ids"]["human_outsider"]},
        {"assignee_principal_id": system["ids"]["alice"], "assignee_id": system["agents"]["worker-a"]},
        {"assignee_principal_id": system["ids"]["manager"], "reviewer_principal_id": system["ids"]["manager"]},
    ):
        response = api_client.post("/api/tasks", json={"project_id": system["ids"]["project"], "title": "Forbidden assignment", **fields},
                                   headers=headers(system, "manager"))
        assert response.status_code in {403, 422}
    agent_task = create_task(api_client, system, assignee_id=system["agents"]["worker-a"])
    agent_claim = claim(api_client, system, agent_task, "worker_a")
    assert agent_claim["lease_token"] and agent_claim["execution"]["executor_kind"] == "agent"
    # Nullable request token supports humans but never removes an agent's fencing requirement.
    missing_token = api_client.post(f"/api/tasks/{agent_task['id']}/progress", json={"execution_id": agent_claim["execution"]["id"], "progress": 80},
                                    headers=headers(system, "worker_a"))
    assert missing_token.status_code == 409
    human_task = create_task(api_client, system, assignee_principal_id=system["ids"]["alice"])
    dispatched = api_client.post(f"/api/tasks/{human_task['id']}/dispatch", json={"agent_id": system["agents"]["worker-b"]},
                                 headers=headers(system, "manager"))
    assert dispatched.status_code == 409 and dispatched.json()["detail"]["code"] == "human_assigned_task"


def test_human_agent_messages_delegation_and_self_review_denial(api_client, colleagues):
    system = colleagues
    parent = create_task(api_client, system, reviewer_principal_id=system["ids"]["human_reviewer"])
    claim(api_client, system, parent, "alice")
    child = api_client.post(f"/api/tasks/{parent['id']}/delegate", json={"assignee_principal_id": system["ids"]["bob"],
                            "title": "Human child", "goal": "Prepare evidence"}, headers=headers(system, "alice", "human-delegate"))
    assert child.status_code == 201 and child.json()["assignee"]["kind"] == "human"
    assert child.json()["reviewer_principal_id"] == system["ids"]["human_reviewer"]
    inbox = api_client.get("/api/messages", params={"inbox": "true"}, headers=headers(system, "bob")).json()
    assert any(child.json()["key"] in item["body"] for item in inbox)
    human_help = api_client.post("/api/messages", json={"project_id": system["ids"]["project"], "task_id": parent["id"],
                                  "recipient_id": system["ids"]["alice"], "kind": "help_request", "body": "Agent asks coworker"},
                                 headers=headers(system, "worker_a"))
    assert human_help.status_code == 201
    agent_help = api_client.post("/api/messages", json={"project_id": system["ids"]["project"], "task_id": parent["id"],
                                  "recipient_id": system["ids"]["worker_b"], "kind": "help_request", "body": "Coworker asks agent"},
                                 headers=headers(system, "alice"))
    assert agent_help.status_code == 201
    hidden_recipient = api_client.post("/api/messages", json={"project_id": system["ids"]["project"],
                                       "recipient_id": system["ids"]["human_outsider"], "kind": "question", "body": "Do not deliver"},
                                      headers=headers(system, "alice"))
    assert hidden_recipient.status_code == 403
    self_task = create_task(api_client, system)
    own_execution = claim(api_client, system, self_task, "manager")["execution"]
    submit(api_client, system, self_task, "manager", own_execution)
    assert api_client.post(f"/api/tasks/{self_task['id']}/review", json={"decision": "accept", "comment": "Self approval"},
                           headers=headers(system, "manager")).status_code == 403


def test_mcp_coworker_directory_and_delegation_use_same_rest_service(monkeypatch):
    calls = []
    async def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"ok": True}
    monkeypatch.setattr(mcp_server, "_request", request)
    asyncio.run(mcp_server.list_project_participants("project"))
    asyncio.run(mcp_server.delegate_task(task_id="parent", assignee_principal_id="coworker", title="Child", goal="Goal", acceptance_criteria=[]))
    assert calls[0][1] == "/api/projects/project/participants"
    assert calls[1][1] == "/api/tasks/parent/delegate"
    assert calls[1][2]["body"]["assignee_principal_id"] == "coworker"
    assert calls[1][2]["body"]["agent_id"] is None


def test_legacy_sqlite_upgrade_preserves_agent_evidence_and_enables_human_work(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    legacy = MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(legacy)
    tasks = legacy.tables["tasks"]
    tasks.indexes = {index for index in tasks.indexes if not any(column.name.endswith("_principal_id") for column in index.columns)}
    for name in ("assignee_principal_id", "reviewer_principal_id"):
        column = tasks.c[name]
        for constraint in list(tasks.foreign_key_constraints):
            if name in constraint.columns:
                tasks.constraints.discard(constraint)
                tasks.foreign_keys.difference_update(constraint.elements)
        tasks._columns.remove(column)
    for name in ("agent_id", "lease_expires_at"):
        legacy.tables["executions"].c[name].nullable = False
    legacy.create_all(engine)
    now = now_utc()
    with engine.begin() as conn:
        conn.execute(legacy.tables["organizations"].insert().values(id="org", name="Existing organization", created_at=now))
        conn.execute(legacy.tables["principals"].insert(), [
            {"id": "worker", "name": "Old agent", "kind": "agent", "role": "worker", "organization_id": "org", "active": True},
            {"id": "human", "name": "New coworker", "kind": "human", "role": "worker", "organization_id": "org", "active": True},
        ])
        conn.execute(legacy.tables["agents"].insert().values(id="agent", principal_id="worker", name="Old agent", role="worker", created_at=now))
        conn.execute(legacy.tables["projects"].insert().values(id="project", key="OLD", name="Legacy project", organization_id="org", created_at=now))
        conn.execute(tasks.insert().values(id="task", project_id="project", key="OLD-1", title="Old work", status="in_progress", created_at=now, updated_at=now))
        conn.execute(legacy.tables["executions"].insert().values(id="execution", task_id="task", agent_id="agent", claimed_by_principal_id="worker",
                     status="running", lease_token_hash="old-fencing-hash", lease_expires_at=now + timedelta(hours=1), started_at=now))
        conn.execute(legacy.tables["artifacts"].insert().values(id="evidence", task_id="task", execution_id="execution", kind="document",
                     title="Old evidence", content="Must survive", created_at=now))
    migrate_collaboration(engine)
    migrate_collaboration(engine)  # Safe restart/repeated deployment.
    assert {item["name"] for item in inspect(engine).get_columns("tasks")} >= {"assignee_principal_id", "reviewer_principal_id"}
    assert all(item["nullable"] for item in inspect(engine).get_columns("executions") if item["name"] in {"agent_id", "lease_expires_at"})
    with sessionmaker(bind=engine)() as session:
        assert session.get(Artifact, "evidence").content == "Must survive"
        assert session.get(Execution, "execution").lease_token_hash == "old-fencing-hash"
        session.add(Execution(id="human-execution", task_id="task", agent_id=None, claimed_by_principal_id="human", status="released",
                              lease_expires_at=None, started_at=now))
        session.commit()
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    engine.dispose()
