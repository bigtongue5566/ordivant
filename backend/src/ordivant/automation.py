from __future__ import annotations

import json
from datetime import UTC, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .errors import bad_request, conflict, forbidden, not_found
from .models import (
    Agent,
    AuditEvent,
    Execution,
    OutboxEvent,
    Principal,
    Project,
    ProjectMembership,
    RunMirror,
    Task,
    TaskDependency,
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowSchedule,
    WorkflowStepRun,
)
from .security import new_id, now_utc, principal_projects


def _loads(value: str | None, default):
    try:
        return json.loads(value) if value is not None else default
    except (TypeError, json.JSONDecodeError):
        return default


def _iso(value):
    return value.isoformat().replace("+00:00", "Z") if value else None


def _require_manager(actor: Principal) -> None:
    if actor.kind != "human" or actor.role not in {"admin", "manager"} or not actor.active:
        raise forbidden("只有 project manager 或 admin 可管理 workflow")


def _validate_steps(session: Session, actor: Principal, project_id: str, steps: list[dict]) -> list[dict]:
    from .service import agent_for_task, require_project

    require_project(session, actor, project_id)
    if not 1 <= len(steps) <= 20:
        raise bad_request("workflow_steps_invalid", "Workflow 必須有 1 到 20 個 steps")
    by_key = {item["key"]: item for item in steps}
    if len(by_key) != len(steps):
        raise bad_request("workflow_step_duplicate", "Workflow step key 不可重複")
    for item in steps:
        missing = set(item.get("dependency_keys", [])) - set(by_key)
        if missing or item["key"] in item.get("dependency_keys", []):
            raise bad_request("workflow_dependency_invalid", "Workflow dependency key 不存在或形成自我相依")
        if item.get("agent_id"):
            agent = agent_for_task(session, actor, item["agent_id"], project_id)
            if agent.role != "worker" or agent.runtime != "pi":
                raise bad_request("workflow_agent_invalid", "Workflow agent 必須是 project scoped Pi worker")
        if item.get("reviewer_id"):
            reviewer = agent_for_task(session, actor, item["reviewer_id"], project_id)
            if reviewer.role != "reviewer":
                raise bad_request("workflow_reviewer_invalid", "Workflow reviewer 必須是 project scoped reviewer")
            if item.get("agent_id") and item["reviewer_id"] == item["agent_id"]:
                raise bad_request("workflow_self_review", "Workflow 不可指定 Agent 審查自己的結果")
    state: dict[str, int] = {}

    def visit(key: str) -> None:
        if state.get(key) == 1:
            raise bad_request("workflow_cycle", "Workflow dependency graph 不可有 cycle")
        if state.get(key) == 2:
            return
        state[key] = 1
        for dependency in by_key[key].get("dependency_keys", []):
            visit(dependency)
        state[key] = 2

    for key in by_key:
        visit(key)
    return steps


def _schedule_json(session: Session, workflow_id: str) -> dict:
    row = session.get(WorkflowSchedule, workflow_id)
    if row is None:
        return {"enabled": False, "interval_minutes": 60, "max_runs": 1, "next_run_at": None}
    return {
        "enabled": row.enabled,
        "interval_minutes": row.interval_minutes,
        "max_runs": row.max_runs,
        "next_run_at": _iso(row.next_run_at),
    }


def workflow_json(session: Session, row: WorkflowDefinition) -> dict:
    schedule = _schedule_json(session, row.id)
    return {
        "id": row.id,
        "project_id": row.project_id,
        "key": row.key,
        "version": row.version,
        "name": row.name,
        "description": row.description,
        "steps": _loads(row.steps_json, []),
        "schedule": {key: value for key, value in schedule.items() if key != "next_run_at"},
        "next_run_at": schedule["next_run_at"],
        "created_at": _iso(row.created_at),
    }


def _instance_json(session: Session, row: WorkflowInstance) -> dict:
    workflow = session.get(WorkflowDefinition, row.workflow_id)
    steps = list(session.scalars(select(WorkflowStepRun).where(WorkflowStepRun.instance_id == row.id)))
    ordered = {step["key"]: index for index, step in enumerate(_loads(workflow.steps_json, []))} if workflow else {}
    steps.sort(key=lambda item: ordered.get(item.step_key, 999))
    return {
        "id": row.id,
        "workflow_id": row.workflow_id,
        "project_id": row.project_id,
        "status": row.status,
        "trigger": row.trigger,
        "inputs": row.inputs,
        "steps": [
            {"key": item.step_key, "task_id": item.task_id, "status": item.status, "run_id": item.run_id, "error": item.error}
            for item in steps
        ],
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _audit(session: Session, actor: Principal, project_id: str, action: str, entity_type: str, entity_id: str, data: dict) -> None:
    session.add(
        AuditEvent(
            id=new_id(), project_id=project_id, actor_id=actor.id, action=action,
            entity_type=entity_type, entity_id=entity_id,
            data_json=json.dumps(data, ensure_ascii=False, separators=(",", ":")), created_at=now_utc(),
        )
    )


def create_workflow(session: Session, actor: Principal, value: dict) -> dict:
    _require_manager(actor)
    steps = _validate_steps(session, actor, value["project_id"], value["steps"])
    existing = session.scalar(
        select(WorkflowDefinition.id).where(
            WorkflowDefinition.project_id == value["project_id"], WorkflowDefinition.key == value["key"]
        )
    )
    if existing:
        raise conflict("workflow_exists", "此 project 已有相同 Workflow key")
    row = WorkflowDefinition(
        id=new_id(), project_id=value["project_id"], key=value["key"], version=1,
        name=value["name"], description=value.get("description", ""),
        steps_json=json.dumps(steps, ensure_ascii=False, separators=(",", ":")),
        created_by_principal_id=actor.id, created_at=now_utc(),
    )
    schedule_value = value.get("schedule") or {"enabled": False, "interval_minutes": 60, "max_runs": 1}
    session.add(row)
    session.flush()
    from .service import _admit_runtime_project

    _admit_runtime_project(session, session.get(Project, row.project_id))
    session.add(
        WorkflowSchedule(
            workflow_id=row.id, enabled=schedule_value["enabled"], interval_minutes=schedule_value["interval_minutes"],
            max_runs=schedule_value["max_runs"], runs_created=0,
            next_run_at=now_utc() + timedelta(minutes=schedule_value["interval_minutes"]) if schedule_value["enabled"] else None,
            updated_at=now_utc(),
        )
    )
    _audit(session, actor, row.project_id, "workflow.created", "workflow", row.id, {"key": row.key, "version": row.version})
    session.flush()
    return workflow_json(session, row)


def list_workflows(session: Session, actor: Principal, project_id: str | None) -> list[dict]:
    project_ids = principal_projects(session, actor.id)
    if project_id:
        from .service import require_project

        require_project(session, actor, project_id)
        project_ids = [project_id]
    if not project_ids:
        return []
    rows = list(
        session.scalars(
            select(WorkflowDefinition).where(WorkflowDefinition.project_id.in_(project_ids)).order_by(
                WorkflowDefinition.project_id, WorkflowDefinition.key, WorkflowDefinition.version.desc()
            )
        )
    )
    return [workflow_json(session, row) for row in rows]


def _workflow_for_actor(session: Session, actor: Principal, workflow_id: str) -> WorkflowDefinition:
    stmt = select(WorkflowDefinition).where(WorkflowDefinition.id == workflow_id)
    row = session.scalar(stmt)
    if row is None:
        raise not_found("找不到 workflow")
    from .service import require_project

    require_project(session, actor, row.project_id)
    return row


def _lock_workflow_key(session: Session, workflow: WorkflowDefinition, *, skip_locked: bool = False) -> bool:
    stmt = (
        select(WorkflowDefinition.id)
        .where(
            WorkflowDefinition.project_id == workflow.project_id,
            WorkflowDefinition.key == workflow.key,
            WorkflowDefinition.version == 1,
        )
        .limit(1)
    )
    if session.bind and session.bind.dialect.name != "sqlite":
        stmt = stmt.with_for_update(skip_locked=skip_locked)
    return session.scalar(stmt) is not None


def _lock_workflow_schedule(session: Session, workflow_id: str) -> WorkflowSchedule | None:
    return session.scalar(select(WorkflowSchedule).where(WorkflowSchedule.workflow_id == workflow_id).with_for_update())


def _has_active_instance(session: Session, workflow: WorkflowDefinition) -> bool:
    return session.scalar(
        select(WorkflowInstance.id)
        .join(WorkflowDefinition, WorkflowDefinition.id == WorkflowInstance.workflow_id)
        .where(
            WorkflowDefinition.project_id == workflow.project_id,
            WorkflowDefinition.key == workflow.key,
            WorkflowInstance.status.in_(["running", "waiting"]),
        )
        .limit(1)
    ) is not None


def create_workflow_version(session: Session, actor: Principal, workflow_id: str, value: dict) -> dict:
    _require_manager(actor)
    current = _workflow_for_actor(session, actor, workflow_id)
    steps = _validate_steps(session, actor, current.project_id, value["steps"])
    if not _lock_workflow_key(session, current):
        raise not_found("找不到 workflow key")
    previous_schedule = _lock_workflow_schedule(session, current.id)
    version = session.scalar(
        select(func.max(WorkflowDefinition.version)).where(
            WorkflowDefinition.project_id == current.project_id, WorkflowDefinition.key == current.key
        )
    ) or current.version
    row = WorkflowDefinition(
        id=new_id(), project_id=current.project_id, key=current.key, version=version + 1,
        name=value["name"], description=value.get("description", ""),
        steps_json=json.dumps(steps, ensure_ascii=False, separators=(",", ":")),
        created_by_principal_id=actor.id, created_at=now_utc(),
    )
    previous_interval = previous_schedule.interval_minutes if previous_schedule else 60
    previous_max_runs = previous_schedule.max_runs if previous_schedule else 1
    session.add(row)
    session.flush()
    if previous_schedule:
        previous_schedule.enabled = False
        previous_schedule.next_run_at = None
        session.add(
            WorkflowSchedule(
                workflow_id=row.id, enabled=False, interval_minutes=previous_schedule.interval_minutes,
                max_runs=previous_schedule.max_runs, runs_created=0,
                next_run_at=None, updated_at=now_utc(),
            )
        )
    else:
        session.add(WorkflowSchedule(workflow_id=row.id, enabled=False, interval_minutes=previous_interval, max_runs=previous_max_runs, runs_created=0, next_run_at=None, updated_at=now_utc()))
    # Versions never inherit an active trigger. The schedule must be explicitly enabled on the new version.
    _audit(session, actor, row.project_id, "workflow.version_created", "workflow", row.id, {"key": row.key, "version": row.version})
    session.flush()
    return workflow_json(session, row)


def update_workflow_schedule(session: Session, actor: Principal, workflow_id: str, value: dict) -> dict:
    _require_manager(actor)
    row = _workflow_for_actor(session, actor, workflow_id)
    if not _lock_workflow_key(session, row):
        raise not_found("找不到 workflow key")
    if value["enabled"]:
        _validate_steps(session, actor, row.project_id, _loads(row.steps_json, []))
    from .service import _admit_runtime_project

    _admit_runtime_project(session, session.get(Project, row.project_id))
    schedule = _lock_workflow_schedule(session, row.id)
    if schedule is None:
        schedule = WorkflowSchedule(workflow_id=row.id, runs_created=0, updated_at=now_utc())
        session.add(schedule)
    if value["max_runs"] < schedule.runs_created:
        raise conflict("workflow_run_limit", "max_runs 不可低於已建立的 scheduled runs")
    schedule.enabled = value["enabled"] and schedule.runs_created < value["max_runs"]
    schedule.interval_minutes = value["interval_minutes"]
    schedule.max_runs = value["max_runs"]
    schedule.next_run_at = now_utc() + timedelta(minutes=schedule.interval_minutes) if schedule.enabled else None
    schedule.updated_at = now_utc()
    _audit(session, actor, row.project_id, "workflow.schedule_updated", "workflow", row.id, value)
    session.flush()
    return workflow_json(session, row)


def _topological_steps(steps: list[dict]) -> list[dict]:
    result = []
    added: set[str] = set()
    while len(result) < len(steps):
        ready = [item for item in steps if item["key"] not in added and set(item.get("dependency_keys", [])) <= added]
        if not ready:
            raise bad_request("workflow_cycle", "Workflow dependency graph 不可有 cycle")
        for item in ready:
            added.add(item["key"])
            result.append(item)
    return result


def _create_instance(session: Session, actor: Principal, workflow: WorkflowDefinition, inputs: str, trigger: str) -> WorkflowInstance:
    from . import service

    steps = _loads(workflow.steps_json, [])
    instance = WorkflowInstance(
        id=new_id(), workflow_id=workflow.id, project_id=workflow.project_id, status="running", trigger=trigger,
        inputs=inputs, created_by_principal_id=actor.id, created_at=now_utc(), updated_at=now_utc(),
    )
    session.add(instance)
    session.flush()
    task_by_key: dict[str, str] = {}
    for step in _topological_steps(steps):
        missing_references = False
        assignee_id = step.get("agent_id")
        reviewer_id = step.get("reviewer_id")
        if trigger == "schedule":
            if assignee_id and not _agent_still_valid(session, workflow.project_id, assignee_id, "worker"):
                assignee_id = None
                missing_references = True
            if reviewer_id and not _agent_still_valid(session, workflow.project_id, reviewer_id, "reviewer"):
                reviewer_id = None
                missing_references = True
        dependencies = [task_by_key[key] for key in step.get("dependency_keys", [])]
        if actor.kind == "human":
            task_data = {
                "project_id": workflow.project_id,
                "title": step["title"],
                "goal": step["goal"],
                "description": step.get("description", ""),
                "inputs": inputs,
                "acceptance_criteria": step.get("acceptance_criteria", []),
                "priority": step.get("priority", "medium"),
                "assignee_id": assignee_id,
                "reviewer_id": reviewer_id,
                "dependency_ids": dependencies,
                "labels": [f"workflow:{workflow.key}", f"workflow-instance:{instance.id}"],
            }
            task_value = service.create_task(session, actor, task_data)
            task_id = task_value["id"]
        else:
            task = Task(
                id=new_id(), key="", project_id=workflow.project_id, title=step["title"],
                description=step.get("description", ""), goal=step["goal"], inputs=inputs, scope="", constraints="",
                acceptance_criteria_json=json.dumps(step.get("acceptance_criteria", []), ensure_ascii=False),
                priority=step.get("priority", "medium"), status="ready", assignee_id=assignee_id,
                reviewer_id=reviewer_id, parent_task_id=None,
                labels_json=json.dumps([f"workflow:{workflow.key}", f"workflow-instance:{instance.id}"], ensure_ascii=False),
                blocked_reason=None, progress=0, handoff=None, budget_usd=0, created_at=now_utc(), updated_at=now_utc(),
            )
            project = session.get(Project, workflow.project_id)
            task.key = f"{project.key}-{task.id.replace('-', '')[:8].upper()}"
            session.add(task)
            session.flush()
            for dependency_id in dependencies:
                session.add(TaskDependency(id=new_id(), task_id=task.id, dependency_id=dependency_id))
            if dependencies:
                task.status = "blocked"
                task.blocked_reason = "dependencies_pending"
            service.add_audit(session, actor, "task.created", "task", task.id, task.project_id, {"key": task.key, "status": task.status})
            task_id = task.id
        if missing_references:
            step_status, error = "failed", "Configured Agent or reviewer is no longer available in this project."
        else:
            task = session.get(Task, task_id)
            step_status, error = ("waiting" if task.status in {"blocked", "ready"} else "running"), None
        task_by_key[step["key"]] = task_id
        session.add(
            WorkflowStepRun(
                id=new_id(), instance_id=instance.id, step_key=step["key"], task_id=task_id,
                status=step_status, run_id=None, error=error,
            )
        )
    if any(step.error for step in session.scalars(select(WorkflowStepRun).where(WorkflowStepRun.instance_id == instance.id))):
        instance.status = "failed"
    _audit(session, actor, workflow.project_id, "workflow.instance_started", "workflow_instance", instance.id, {"trigger": trigger, "workflow_id": workflow.id})
    session.flush()
    return instance


def _agent_still_valid(session: Session, project_id: str, agent_id: str, role: str) -> bool:
    agent = session.get(Agent, agent_id)
    if agent is None or agent.role != role or agent.status in {"disabled", "archived"}:
        return False
    return session.scalar(
        select(ProjectMembership.id).where(ProjectMembership.project_id == project_id, ProjectMembership.principal_id == agent.principal_id)
    ) is not None


def start_workflow(session: Session, actor: Principal, workflow_id: str, inputs: str) -> dict:
    _require_manager(actor)
    workflow = _workflow_for_actor(session, actor, workflow_id)
    if not _lock_workflow_key(session, workflow):
        raise not_found("找不到 workflow key")
    _lock_workflow_schedule(session, workflow.id)
    if _has_active_instance(session, workflow):
        raise conflict("workflow_active", "相同 project/key 已有執行中的 Workflow instance")
    from .service import _admit_runtime_project

    _admit_runtime_project(session, session.get(Project, workflow.project_id))
    instance = _create_instance(session, actor, workflow, inputs, "manual")
    _advance_instance(session, actor, instance)
    session.flush()
    return _instance_json(session, instance)


def get_workflow_instance(session: Session, actor: Principal, instance_id: str) -> dict:
    row = session.get(WorkflowInstance, instance_id)
    if row is None:
        raise not_found("找不到 workflow run")
    from .service import require_project

    require_project(session, actor, row.project_id)
    return _instance_json(session, row)


def list_workflow_instances(session: Session, actor: Principal, project_id: str | None) -> list[dict]:
    project_ids = principal_projects(session, actor.id)
    if project_id:
        from .service import require_project

        require_project(session, actor, project_id)
        project_ids = [project_id]
    if not project_ids:
        return []
    rows = session.scalars(
        select(WorkflowInstance).where(WorkflowInstance.project_id.in_(project_ids)).order_by(WorkflowInstance.created_at.desc()).limit(200)
    )
    return [_instance_json(session, row) for row in rows]


def _select_agent(session: Session, project_id: str, step: dict, task_id: str) -> Agent | None:
    agent_stmt = (
        select(Agent)
        .join(ProjectMembership, ProjectMembership.principal_id == Agent.principal_id)
        .where(ProjectMembership.project_id == project_id, Agent.role == "worker", Agent.runtime == "pi", Agent.status == "available")
    )
    if step.get("agent_id"):
        agent_stmt = agent_stmt.where(Agent.id == step["agent_id"])
    agents = list(session.scalars(agent_stmt.order_by(Agent.name, Agent.id)))
    requirements = set(step.get("capabilities", []))
    for agent in agents:
        capabilities = set(_loads(agent.capabilities_json, []))
        if not requirements.issubset(capabilities):
            continue
        if step.get("reviewer_id") == agent.id:
            continue
        outstanding = session.scalar(
            select(OutboxEvent.id).where(
                OutboxEvent.agent_id == agent.id,
                (OutboxEvent.status == "pending") | ((OutboxEvent.status == "claimed") & (OutboxEvent.claim_expires_at > now_utc())),
            ).limit(1)
        )
        running = session.scalar(
            select(Execution.id).where(Execution.agent_id == agent.id, Execution.status == "running").limit(1)
        )
        if outstanding or running:
            continue
        return agent
    return None


def _advance_instance(session: Session, actor: Principal, instance: WorkflowInstance) -> None:
    from . import service

    workflow = session.get(WorkflowDefinition, instance.workflow_id)
    if workflow is None:
        instance.status = "failed"
        return
    definition_steps = _loads(workflow.steps_json, [])
    step_rows = {item.step_key: item for item in session.scalars(select(WorkflowStepRun).where(WorkflowStepRun.instance_id == instance.id))}
    waiting = False
    failed = False
    for step in definition_steps:
        record = step_rows.get(step["key"])
        if record is None:
            failed = True
            continue
        if record.status in {"completed", "failed", "cancelled"}:
            failed = failed or record.status == "failed"
            continue
        task = session.get(Task, record.task_id)
        if task is None:
            record.status, record.error = "failed", "Workflow task record is missing."
            failed = True
            continue
        if task.status == "done":
            record.status, record.error = "completed", None
            continue
        if task.status in {"cancelled"}:
            record.status, record.error = "cancelled", None
            continue
        if record.run_id:
            run = session.get(RunMirror, record.run_id)
            if run and run.status in {"queued", "running", "paused"}:
                record.status = "running"
                waiting = True
                continue
            if run and run.status in {"failed", "aborted"} and task.status == "ready":
                record.status, record.error = "failed", run.error or f"Run {run.status}."
                failed = True
                continue
            if run and run.status == "done" and task.status == "ready":
                record.status = "waiting"
                waiting = True
                continue
        if task.status == "in_review":
            record.status = "running"
            waiting = True
            continue
        dep_records = [step_rows[key] for key in step.get("dependency_keys", []) if key in step_rows]
        deps_done = len(dep_records) == len(step.get("dependency_keys", [])) and all(item.status == "completed" for item in dep_records)
        if not deps_done or task.status != "ready":
            record.status = "waiting"
            waiting = True
            continue
        agent = _select_agent(session, instance.project_id, step, task.id)
        if agent is None:
            record.status = "waiting"
            waiting = True
            continue
        task.assignee_id = agent.id
        if actor.kind == "runtime":
            dispatch = service.dispatch_workflow_step(session, actor, instance, record, agent.id)
        else:
            dispatch = service.dispatch_task(session, actor, task.id, agent.id)
        record.run_id = dispatch["id"]
        record.status = "running"
    instance.updated_at = now_utc()
    if failed:
        instance.status = "failed"
    elif all(step_rows[item["key"]].status == "completed" for item in definition_steps if item["key"] in step_rows) and len(step_rows) == len(definition_steps):
        instance.status = "completed"
    elif waiting or any(row.status == "running" for row in step_rows.values()):
        instance.status = "waiting" if waiting else "running"
    session.flush()


def cancel_workflow_instance(session: Session, actor: Principal, instance_id: str) -> dict:
    _require_manager(actor)
    instance = session.get(WorkflowInstance, instance_id)
    if instance is None:
        raise not_found("找不到 workflow run")
    from .service import patch_task, require_project

    require_project(session, actor, instance.project_id)
    if instance.status in {"completed", "cancelled"}:
        return _instance_json(session, instance)
    for step in session.scalars(select(WorkflowStepRun).where(WorkflowStepRun.instance_id == instance.id)):
        task = session.get(Task, step.task_id)
        if task and task.status not in {"done", "cancelled"}:
            patch_task(session, actor, task.id, {"status": "cancelled"})
        if step.status not in {"completed", "failed"}:
            step.status = "cancelled"
    instance.status = "cancelled"
    instance.updated_at = now_utc()
    _audit(session, actor, instance.project_id, "workflow.instance_cancelled", "workflow_instance", instance.id, {})
    session.flush()
    return _instance_json(session, instance)


def _admit_due_schedules(session: Session, actor: Principal) -> int:
    if actor.kind != "runtime" or not actor.active:
        raise forbidden("只有 runtime 可執行 workflow tick")
    project_ids = set(principal_projects(session, actor.id))
    if not project_ids:
        return 0
    stmt = (
        select(WorkflowSchedule.workflow_id)
        .join(WorkflowDefinition, WorkflowDefinition.id == WorkflowSchedule.workflow_id)
        .where(
            WorkflowSchedule.enabled.is_(True), WorkflowSchedule.next_run_at <= now_utc(),
            WorkflowSchedule.runs_created < WorkflowSchedule.max_runs, WorkflowDefinition.project_id.in_(project_ids),
        )
        .order_by(WorkflowSchedule.next_run_at, WorkflowSchedule.workflow_id)
    )
    candidates = list(session.scalars(stmt.limit(50)))
    admitted = 0
    for workflow_id in candidates:
        workflow = session.get(WorkflowDefinition, workflow_id)
        if workflow is None:
            continue
        if not _lock_workflow_key(session, workflow, skip_locked=True):
            continue
        schedule = _lock_workflow_schedule(session, workflow_id)
        next_run_at = schedule.next_run_at if schedule else None
        if next_run_at is not None and next_run_at.tzinfo is None:
            next_run_at = next_run_at.replace(tzinfo=UTC)
        if (
            schedule is None
            or not schedule.enabled
            or next_run_at is None
            or next_run_at > now_utc()
            or schedule.runs_created >= schedule.max_runs
        ):
            continue
        active = _has_active_instance(session, workflow)
        next_at = now_utc() + timedelta(minutes=schedule.interval_minutes)
        if active:
            schedule.next_run_at = next_at
            schedule.updated_at = now_utc()
            continue
        instance = _create_instance(session, actor, workflow, "", "schedule")
        schedule.runs_created += 1
        schedule.next_run_at = next_at if schedule.runs_created < schedule.max_runs else None
        if schedule.runs_created >= schedule.max_runs:
            schedule.enabled = False
        schedule.updated_at = now_utc()
        _advance_instance(session, actor, instance)
        admitted += 1
    return admitted


def tick_workflows(session: Session, actor: Principal) -> dict:
    admitted = _admit_due_schedules(session, actor)
    project_ids = principal_projects(session, actor.id)
    active_stmt = (
        select(WorkflowInstance)
        .where(WorkflowInstance.project_id.in_(project_ids), WorkflowInstance.status.in_(["running", "waiting"]))
        .order_by(WorkflowInstance.created_at)
        .limit(200)
    )
    if session.bind and session.bind.dialect.name != "sqlite":
        active_stmt = active_stmt.with_for_update(skip_locked=True)
    active_instances = list(session.scalars(active_stmt))
    advanced = 0
    for instance in active_instances:
        _advance_instance(session, actor, instance)
        advanced += 1
    return {"admitted_schedules": admitted, "advanced_instances": advanced}
