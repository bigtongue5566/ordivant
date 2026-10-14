from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text

from ordivant import planning
from ordivant.migrations import migrate_collaboration
from ordivant.models import (
    AuditEvent,
    Execution,
    OutboxEvent,
    Principal,
    ProjectField,
    ProjectRuleEvent,
    ProjectSprint,
    SavedQuery,
    Task,
    TaskWorklog,
)
from ordivant.security import new_id, now_utc
from conftest import create_task, headers


def request_headers(system, name="manager", key="planning-test"):
    return headers(system, name, key)


def create_field(api_client, system, *, key="customer", name="Customer", kind="text", required=False, options=None):
    response = api_client.post(
        f"/api/projects/{system['ids']['project']}/fields",
        json={"key": key, "name": name, "kind": kind, "required": required, "options": options or []},
        headers=request_headers(system, key=f"field-{key}"),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_task_planning_references_custom_fields_and_epic_cycles(api_client, system):
    field = create_field(api_client, system, kind="select", required=True, options=["Retail", "Enterprise"])
    foreign_sprint = api_client.post(
        f"/api/projects/{system['ids']['isolated_project']}/sprints",
        json={"name": "Isolated sprint"}, headers=request_headers(system, key="foreign-sprint"),
    ).json()
    bad_reference = api_client.post("/api/tasks", json={
        "project_id": system["ids"]["project"], "title": "Cross scope sprint", "sprint_id": foreign_sprint["id"],
    }, headers=request_headers(system, key="cross-sprint"))
    assert bad_reference.status_code == 422

    missing_required = api_client.post("/api/tasks", json={
        "project_id": system["ids"]["project"], "title": "Missing custom field", "custom_fields": {},
    }, headers=request_headers(system, key="missing-required"))
    assert missing_required.status_code == 422

    invalid_value = api_client.post("/api/tasks", json={
        "project_id": system["ids"]["project"], "title": "Invalid custom field", "custom_fields": {"customer": "Public"},
    }, headers=request_headers(system, key="invalid-field-value"))
    assert invalid_value.status_code == 422

    epic_a = api_client.post("/api/tasks", json={
        "project_id": system["ids"]["project"], "title": "Epic A", "work_type": "epic", "status": "backlog",
        "custom_fields": {"customer": "Retail"},
    }, headers=request_headers(system, key="epic-a")).json()
    epic_b = api_client.post("/api/tasks", json={
        "project_id": system["ids"]["project"], "title": "Epic B", "work_type": "epic", "status": "backlog",
        "epic_id": epic_a["id"], "custom_fields": {"customer": "Enterprise"},
    }, headers=request_headers(system, key="epic-b"))
    assert epic_b.status_code == 201, epic_b.text
    cycle = api_client.patch(f"/api/tasks/{epic_a['id']}", json={"epic_id": epic_b.json()["id"]},
        headers=request_headers(system, key="epic-cycle"))
    assert cycle.status_code == 409

    with system["factory"]() as session:
        stored = session.get(ProjectField, field["id"])
        task = session.scalar(select(Task).where(Task.id == epic_a["id"]))
        assert stored is not None and task.custom_fields_json == '{"customer":"Retail"}'


def test_sprints_are_exclusive_and_closing_does_not_complete_tasks(api_client, system):
    project_id = system["ids"]["project"]
    first = api_client.post(f"/api/projects/{project_id}/sprints", json={"name": "Sprint 1", "status": "active"},
        headers=request_headers(system, key="sprint-active-1"))
    assert first.status_code == 201, first.text
    second = api_client.post(f"/api/projects/{project_id}/sprints", json={"name": "Sprint 2", "status": "active"},
        headers=request_headers(system, key="sprint-active-2"))
    assert second.status_code == 409
    task = create_task(api_client, system, title="Sprint task", status="ready")
    close = api_client.patch(f"/api/sprints/{first.json()['id']}", json={"status": "closed"},
        headers=request_headers(system, key="sprint-close"))
    assert close.status_code == 200
    assert api_client.get(f"/api/tasks/{task['id']}", headers=headers(system, "manager")).json()["status"] == "ready"


def test_custom_stage_tracks_status_but_cannot_bypass_execution_lifecycle(api_client, system):
    project_id = system["ids"]["project"]
    ready_stage = api_client.post(f"/api/projects/{project_id}/stages", json={"name": "Queue", "category": "ready"},
        headers=request_headers(system, key="stage-ready"))
    done_stage = api_client.post(f"/api/projects/{project_id}/stages", json={"name": "Finished", "category": "done"},
        headers=request_headers(system, key="stage-done"))
    assert ready_stage.status_code == done_stage.status_code == 201
    task = api_client.post("/api/tasks", json={
        "project_id": project_id, "title": "Stage guarded task", "status": "ready", "stage_id": ready_stage.json()["id"],
    }, headers=request_headers(system, key="stage-task"))
    assert task.status_code == 201, task.text
    mismatch = api_client.patch(f"/api/tasks/{task.json()['id']}", json={"stage_id": done_stage.json()["id"]},
        headers=request_headers(system, key="stage-mismatch"))
    assert mismatch.status_code == 409
    done_status = api_client.patch(f"/api/tasks/{task.json()['id']}", json={"status": "done"},
        headers=request_headers(system, key="stage-done-status"))
    assert done_status.status_code == 422
    claim = api_client.post(f"/api/tasks/{task.json()['id']}/claim", json={}, headers=headers(system, "worker_a", "claim-stage"))
    assert claim.status_code == 200, claim.text
    assert claim.json()["task"]["status"] == "in_progress"
    assert claim.json()["task"]["stage_id"] is None


def test_rules_are_scoped_idempotent_and_recheck_creator_authority(api_client, system):
    project_id = system["ids"]["project"]
    rule_response = api_client.post(f"/api/projects/{project_id}/rules", json={
        "name": "Label new tasks", "event": "task.created", "conditions": {},
        "action": "label", "parameters": {"label": "triaged"},
    }, headers=request_headers(system, key="rule-label"))
    assert rule_response.status_code == 201, rule_response.text
    replay = api_client.post(f"/api/projects/{project_id}/rules", json={
        "name": "Label new tasks", "event": "task.created", "conditions": {},
        "action": "label", "parameters": {"label": "triaged"},
    }, headers=request_headers(system, key="rule-label"))
    assert replay.status_code == 201
    assert replay.json()["id"] == rule_response.json()["id"]

    created = api_client.post("/api/tasks", json={
        "project_id": project_id, "title": "Task from manager",
    }, headers=request_headers(system, key="rule-trigger"))
    assert created.status_code == 201, created.text
    assert "triaged" in created.json()["labels"]
    with system["factory"]() as session:
        audit = session.scalar(select(AuditEvent).where(AuditEvent.entity_id == created.json()["id"], AuditEvent.action == "task.created"))
        assert audit is not None
        planning.fire_task_rules(session, session.get(Task, created.json()["id"]), "task.created", audit.id)
        assert session.scalar(select(func.count()).select_from(ProjectRuleEvent).where(
            ProjectRuleEvent.rule_id == rule_response.json()["id"], ProjectRuleEvent.event_id == audit.id
        )) == 1
        assert session.scalar(select(func.count()).select_from(Execution).where(Execution.task_id == created.json()["id"])) == 0
        assert session.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.task_id == created.json()["id"])) == 0
        manager = session.get(Principal, system["ids"]["manager"])
        manager.role = "worker"
        session.commit()

    worker_created = api_client.post("/api/tasks", json={
        "project_id": project_id, "title": "Task after creator demotion",
    }, headers=request_headers(system, "worker_a", "rule-revoked-trigger"))
    assert worker_created.status_code == 201, worker_created.text
    assert "triaged" not in worker_created.json()["labels"]


def test_ready_rule_only_moves_backlog_tasks_to_ready(api_client, system):
    project_id = system["ids"]["project"]
    rule = api_client.post(f"/api/projects/{project_id}/rules", json={
        "name": "Ready backlog tasks", "event": "task.created", "action": "ready",
    }, headers=request_headers(system, key="rule-ready"))
    assert rule.status_code == 201, rule.text
    backlog = api_client.post("/api/tasks", json={
        "project_id": project_id, "title": "Auto-ready backlog", "status": "backlog",
    }, headers=request_headers(system, key="rule-ready-backlog"))
    assert backlog.status_code == 201, backlog.text
    assert backlog.json()["status"] == "ready"

    with system["factory"]() as session:
        task = session.get(Task, backlog.json()["id"])
        task.status = "done"
        planning.fire_task_rules(session, task, "task.created", "already-complete-event")
        assert task.status == "done"


def test_forms_require_project_membership_and_create_backlog_tasks(api_client, system):
    create_field(api_client, system, key="impact", name="Impact", kind="text", required=True)
    project_id = system["ids"]["project"]
    form = api_client.post(f"/api/projects/{project_id}/forms", json={
        "name": "Bug report", "work_type": "bug", "fields": ["impact"],
    }, headers=request_headers(system, key="create-form"))
    assert form.status_code == 201, form.text
    assert api_client.get(f"/api/forms/{form.json()['id']}").status_code == 401
    missing = api_client.post(f"/api/forms/{form.json()['id']}/submit", json={"title": "Missing impact"},
        headers=request_headers(system, "worker_a", "form-missing"))
    assert missing.status_code == 422
    submitted = api_client.post(f"/api/forms/{form.json()['id']}/submit", json={
        "title": "Submitted bug", "description": "Issue details", "custom_fields": {"impact": "checkout"},
    }, headers=request_headers(system, "worker_a", "form-submit"))
    assert submitted.status_code == 201, submitted.text
    assert submitted.json()["status"] == "backlog"
    assert submitted.json()["work_type"] == "bug"
    assert submitted.json()["custom_fields"] == {"impact": "checkout"}
    assert api_client.get(f"/api/forms/{form.json()['id']}", headers=headers(system, "outsider")).status_code == 404


def test_csv_import_is_atomic_bounded_and_export_neutralizes_formulas(api_client, system):
    project_id = system["ids"]["project"]
    foreign_response = api_client.post("/api/tasks", json={
        "project_id": system["ids"]["isolated_project"], "title": "Foreign epic", "work_type": "epic", "status": "backlog",
    }, headers=request_headers(system, key="foreign-epic"))
    assert foreign_response.status_code == 201, foreign_response.text
    foreign = foreign_response.json()
    before = len(api_client.get("/api/tasks", params={"project_id": project_id}, headers=headers(system, "manager")).json())
    invalid_csv = "title,work_type,epic_id\nValid row,task,\nCross scope,story," + foreign["id"] + "\n"
    response = api_client.post(f"/api/projects/{project_id}/tasks/import", json={"csv": invalid_csv},
        headers=request_headers(system, key="csv-atomic"))
    assert response.status_code == 200, response.text
    assert response.json()["created"] == [] and response.json()["errors"]
    after = len(api_client.get("/api/tasks", params={"project_id": project_id}, headers=headers(system, "manager")).json())
    assert after == before

    good_csv = "title,work_type,priority,status\nImported task,story,high,backlog\n"
    imported = api_client.post(f"/api/projects/{project_id}/tasks/import", json={"csv": good_csv},
        headers=request_headers(system, key="csv-good"))
    assert imported.status_code == 200 and len(imported.json()["created"]) == 1
    create_task(api_client, system, title="=HYPERLINK(\"https://example.invalid\")", description="\t=SUM(1,1)")
    exported = api_client.get(f"/api/projects/{project_id}/tasks/export", headers=headers(system, "manager"))
    assert exported.status_code == 200 and "text/csv" in exported.headers["content-type"]
    assert "'=HYPERLINK" in exported.text
    assert "'\t=SUM" in exported.text
    assert api_client.post(f"/api/projects/{project_id}/tasks/import", json={"csv": "title\n" + "x\n" * 1001},
        headers=request_headers(system, key="csv-row-limit")).status_code == 422


def test_task_filters_reorder_and_saved_queries_are_actor_owned(api_client, system):
    project_id = system["ids"]["project"]
    first = api_client.post("/api/tasks", json={"project_id": project_id, "title": "Rank late", "rank": 20, "work_type": "bug"},
        headers=request_headers(system, key="rank-late")).json()
    second = api_client.post("/api/tasks", json={"project_id": project_id, "title": "Rank early", "rank": 10, "work_type": "story"},
        headers=request_headers(system, key="rank-early")).json()
    filtered = api_client.get("/api/tasks", params={"project_id": project_id, "work_type": "bug"}, headers=headers(system, "manager"))
    assert filtered.status_code == 200 and all(item["work_type"] == "bug" for item in filtered.json())
    reordered = api_client.post(f"/api/projects/{project_id}/reorder", json={"task_ids": [first["id"], second["id"]]},
        headers=request_headers(system, key="reorder"))
    assert reordered.status_code == 200
    assert reordered.json()[0]["rank"] == 0 and reordered.json()[1]["rank"] == 1
    cross_scope = api_client.post(f"/api/projects/{project_id}/reorder", json={"task_ids": [first["id"], "missing"]},
        headers=request_headers(system, key="reorder-invalid"))
    assert cross_scope.status_code == 422

    query = api_client.post("/api/saved-queries", json={"name": "My bugs", "project_id": project_id,
        "filters": {"work_type": "bug", "overdue": True}}, headers=request_headers(system, key="query-create"))
    assert query.status_code == 201
    assert len(api_client.get("/api/saved-queries", headers=headers(system, "manager")).json()) == 1
    assert api_client.get("/api/saved-queries", headers=headers(system, "worker_a")).json() == []
    assert api_client.delete(f"/api/saved-queries/{query.json()['id']}", headers=request_headers(system, "worker_a", "query-delete-other")).status_code == 403
    assert api_client.delete(f"/api/saved-queries/{query.json()['id']}", headers=request_headers(system, "manager", "query-delete-own")).status_code == 200


def test_worklogs_are_actor_attributed_and_report_observed_time(api_client, system):
    task = create_task(api_client, system, title="Owned worklog", assignee_id=system["agents"]["worker-a"])
    started_at = (datetime.now(UTC) - timedelta(minutes=50)).isoformat()
    added = api_client.post(f"/api/tasks/{task['id']}/worklogs", json={"minutes": 45, "started_at": started_at, "description": "Observed effort"},
        headers=request_headers(system, "worker_a", "worklog-add"))
    assert added.status_code == 201, added.text
    assert added.json()["principal_id"] == system["ids"]["worker_a"]
    denied = api_client.post(f"/api/tasks/{task['id']}/worklogs", json={"minutes": 10, "started_at": started_at},
        headers=request_headers(system, "reviewer", "worklog-other"))
    assert denied.status_code == 403
    reports = api_client.get(f"/api/projects/{system['ids']['project']}/reports", headers=headers(system, "manager"))
    assert reports.status_code == 200
    assert reports.json()["worklogs"] == {"entries": 1, "observed_minutes": 45}
    with system["factory"]() as session:
        stored = session.scalar(select(TaskWorklog).where(TaskWorklog.task_id == task["id"]))
        assert stored is not None and stored.principal_id == system["ids"]["worker_a"]


def test_legacy_task_schema_migration_is_additive_and_repeatable(tmp_path):
    from ordivant.db import make_engine

    engine = make_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE tasks (id VARCHAR(36) PRIMARY KEY, key VARCHAR(40), project_id VARCHAR(36), title VARCHAR(300), status VARCHAR(20), created_at TIMESTAMP, updated_at TIMESTAMP)")
        connection.exec_driver_sql("CREATE TABLE executions (id VARCHAR(36) PRIMARY KEY, agent_id VARCHAR(36), lease_expires_at TIMESTAMP)")
        connection.exec_driver_sql("INSERT INTO tasks (id, key, project_id, title, status, created_at, updated_at) VALUES ('task-1', 'OLD-1', 'project-1', 'preserve me', 'backlog', '2026-10-01', '2026-10-01')")
    migrate_collaboration(engine)
    migrate_collaboration(engine)
    with engine.connect() as connection:
        columns = {item[1] for item in connection.exec_driver_sql("PRAGMA table_info(tasks)")}
        row = connection.execute(text("SELECT title, work_type, rank, custom_fields_json FROM tasks WHERE id='task-1'")).one()
    assert {"assignee_principal_id", "reviewer_principal_id", "work_type", "epic_id", "due_at", "start_at", "sprint_id", "milestone_id", "estimate_points", "rank", "stage_id", "custom_fields_json"} <= columns
    assert tuple(row) == ("preserve me", "task", 0.0, "{}")
    engine.dispose()


def test_capacity_is_explicit_scoped_and_authorized_before_replay(api_client, system):
    project_id = system['ids']['project']
    path = f'/api/projects/{project_id}/capacity'
    report = api_client.get(f'/api/projects/{project_id}/reports', headers=headers(system, 'manager')).json()
    assert all(row['weekly_minutes'] is None and row['utilization_percent'] is None for row in report['capacity'])
    body = {'principal_id': system['ids']['worker_a'], 'weekly_minutes': 1200}
    assert api_client.post(path, json=body, headers=headers(system, 'worker_a', 'capacity-denied')).status_code == 403
    assert api_client.post(path, json={**body, 'principal_id': system['ids']['outsider']},
        headers=headers(system, 'manager', 'capacity-foreign')).status_code == 404
    result = api_client.post(path, json=body, headers=headers(system, 'manager', 'capacity-set'))
    assert result.status_code == 200, result.text
    assert api_client.post(path, json=body, headers=headers(system, 'manager', 'capacity-set')).json() == result.json()
    report = api_client.get(f'/api/projects/{project_id}/reports', headers=headers(system, 'manager')).json()
    row = next(item for item in report['capacity'] if item['principal_id'] == body['principal_id'])
    assert row['weekly_minutes'] == 1200 and row['utilization_percent'] == 0
    with system['factory']() as session:
        from ordivant.models import ProjectMembership
        membership = session.scalar(select(ProjectMembership).where(ProjectMembership.project_id == project_id,
            ProjectMembership.principal_id == system['ids']['manager']))
        session.delete(membership)
        session.commit()
    assert api_client.post(path, json=body, headers=headers(system, 'manager', 'capacity-set')).status_code == 404


def test_cycle_time_includes_rework_and_independent_review_wait(api_client, system):
    task = create_task(api_client, system, title='Observed review cycle')
    started = now_utc() - timedelta(hours=5)
    with system['factory']() as session:
        first = Execution(id=new_id(), task_id=task['id'], agent_id=system['agents']['worker-a'],
            claimed_by_principal_id=system['ids']['worker_a'], submitted_by_principal_id=system['ids']['worker_a'],
            status='rejected', started_at=started, finished_at=started + timedelta(hours=1))
        accepted = Execution(id=new_id(), task_id=task['id'], agent_id=system['agents']['worker-a'],
            claimed_by_principal_id=system['ids']['worker_a'], submitted_by_principal_id=system['ids']['worker_a'],
            status='accepted', started_at=started + timedelta(hours=2), finished_at=started + timedelta(hours=3))
        session.add_all([first, accepted])
        session.flush()
        session.add(AuditEvent(id=new_id(), project_id=system['ids']['project'], actor_id=system['ids']['reviewer'],
            action='task.review.accept', entity_type='task', entity_id=task['id'],
            data_json=__import__('json').dumps({'execution_id': accepted.id}), created_at=started + timedelta(hours=4)))
        session.commit()
    report = api_client.get(f'/api/projects/{system["ids"]["project"]}/reports', headers=headers(system, 'manager')).json()
    assert report['cycle_time']['samples'] == 1
    assert report['cycle_time']['average_seconds'] == 4 * 3600


def test_filtered_reorder_preserves_hidden_slots_without_duplicate_ranks(api_client, system):
    created = []
    for index in range(4):
        result = api_client.post('/api/tasks', json={'project_id': system['ids']['project'], 'title': f'Rank {index}', 'rank': index},
            headers=headers(system, 'manager', f'filtered-rank-{index}'))
        assert result.status_code == 201, result.text
        created.append(result.json())
    result = api_client.post(f'/api/projects/{system["ids"]["project"]}/reorder',
        json={'task_ids': [created[3]['id'], created[1]['id']]}, headers=headers(system, 'manager', 'subset-order'))
    assert result.status_code == 200
    rows = api_client.get('/api/tasks', params={'project_id': system['ids']['project']}, headers=headers(system, 'manager')).json()
    assert [row['id'] for row in rows] == [created[0]['id'], created[3]['id'], created[2]['id'], created[1]['id']]
    assert len({row['rank'] for row in rows}) == 4



def test_epic_partial_patch_preserves_type_and_validates_combined_dates(api_client, system):
    project_id = system["ids"]["project"]
    epic = api_client.post("/api/tasks", json={"project_id": project_id, "title": "Parent epic", "work_type": "epic", "status": "backlog",
        "start_at": "2026-10-15T00:00:00Z", "due_at": "2026-10-18T00:00:00Z"}, headers=request_headers(system, key="partial-epic")).json()
    child = api_client.post("/api/tasks", json={"project_id": project_id, "title": "Child", "epic_id": epic["id"], "status": "backlog"},
        headers=request_headers(system, key="partial-child"))
    assert child.status_code == 201
    edited = api_client.patch(f"/api/tasks/{epic['id']}", json={"estimate_points": 8}, headers=request_headers(system, key="partial-epic-points"))
    assert edited.status_code == 200, edited.text
    assert edited.json()["work_type"] == "epic" and edited.json()["estimate_points"] == 8
    invalid = api_client.patch(f"/api/tasks/{epic['id']}", json={"due_at": "2026-10-14T00:00:00Z"}, headers=request_headers(system, key="partial-invalid-date"))
    assert invalid.status_code == 422
    assert api_client.get(f"/api/tasks/{epic['id']}", headers=headers(system, "manager")).json()["due_at"].startswith("2026-10-18")


@pytest.mark.parametrize("content", ['title,description\n"unfinished,notes', '"unfinished header', 'title,title\nfirst,second'])
def test_malformed_csv_is_rejected_without_partial_writes(api_client, system, content):
    project_id = system["ids"]["project"]
    before = api_client.get("/api/tasks", params={"project_id": project_id}, headers=headers(system, "manager")).json()
    result = api_client.post(f"/api/projects/{project_id}/tasks/import", json={"csv": content}, headers=request_headers(system, key="malformed-csv"))
    assert result.status_code == 422
    after = api_client.get("/api/tasks", params={"project_id": project_id}, headers=headers(system, "manager")).json()
    assert len(after) == len(before)
