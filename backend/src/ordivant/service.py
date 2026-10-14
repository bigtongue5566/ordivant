from __future__ import annotations

import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .errors import DomainError, bad_request, conflict, forbidden, not_found
from .models import (
    Agent,
    Artifact,
    AuditEvent,
    Execution,
    Message,
    OutboxEvent,
    Principal,
    Project,
    ProjectMembership,
    RunMirror,
    Task,
    TaskDependency,
    Team,
)
from .model_settings import (
    agent_model_config,
    effective_agent_model_config,
    revoke_runtime_credential,
    set_agent_model_config,
    validate_effective_agent_model_config,
)
from .execution_settings import (
    agent_execution_settings,
    dispatch_execution_snapshot,
    set_agent_execution_settings,
    template_definition_for_agent,
)
from .security import hash_secret, new_id, new_secret, now_utc, principal_projects

TASK_STATES = {"backlog", "ready", "in_progress", "blocked", "in_review", "done", "cancelled"}
ACTIVE_ROLES = {"admin", "manager"}


def _loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _set_task_status(task: Task, status: str) -> None:
    if task.status != status:
        task.status = status
        task.stage_id = None


def project_json(project: Project) -> dict:
    return {
        "id": project.id,
        "key": project.key,
        "name": project.name,
        "description": project.description,
        "organization_id": project.organization_id,
        "team_id": project.team_id,
        "budget_usd": project.budget_usd,
        "created_at": _iso(project.created_at),
    }


def agent_json(session: Session, agent: Agent) -> dict:
    project_ids = list(
        session.scalars(
            select(ProjectMembership.project_id)
            .join(Principal, Principal.id == ProjectMembership.principal_id)
            .where(Principal.id == agent.principal_id)
            .order_by(ProjectMembership.project_id)
        )
    )
    return {
        "id": agent.id,
        "principal_id": agent.principal_id,
        "name": agent.name,
        "role": agent.role,
        "team_id": agent.team_id,
        "capabilities": _loads(agent.capabilities_json, []),
        "project_ids": project_ids,
        "status": agent.status,
        "runtime": agent.runtime,
        "model": agent.model,
        "model_config": agent_model_config(session, agent),
        "effective_model_config": effective_agent_model_config(session, agent),
        "execution_config": agent_execution_settings(session, agent)[0],
        "template_id": agent_execution_settings(session, agent)[1],
        "created_at": _iso(agent.created_at),
    }


def task_json(session: Session, task: Task) -> dict:
    dependency_ids = list(
        session.scalars(select(TaskDependency.dependency_id).where(TaskDependency.task_id == task.id))
    )
    return {
        "id": task.id,
        "key": task.key,
        "project_id": task.project_id,
        "title": task.title,
        "description": task.description,
        "goal": task.goal,
        "inputs": task.inputs,
        "scope": task.scope,
        "constraints": task.constraints,
        "acceptance_criteria": _loads(task.acceptance_criteria_json, []),
        "priority": task.priority,
        "status": task.status,
        "assignee_id": task.assignee_id,
        "assignee_principal_id": task.assignee_principal_id,
        "assignee": participant_reference(session, task.assignee_id, task.assignee_principal_id),
        "reviewer_id": task.reviewer_id,
        "reviewer_principal_id": task.reviewer_principal_id,
        "reviewer": participant_reference(session, task.reviewer_id, task.reviewer_principal_id),
        "parent_task_id": task.parent_task_id,
        "dependency_ids": dependency_ids,
        "labels": _loads(task.labels_json, []),
        "blocked_reason": task.blocked_reason,
        "progress": task.progress,
        "handoff": task.handoff,
        "budget_usd": task.budget_usd,
        "work_type": task.work_type,
        "epic_id": task.epic_id,
        "due_at": _iso(task.due_at),
        "start_at": _iso(task.start_at),
        "sprint_id": task.sprint_id,
        "milestone_id": task.milestone_id,
        "estimate_points": task.estimate_points,
        "rank": task.rank,
        "stage_id": task.stage_id,
        "custom_fields": _loads(task.custom_fields_json, {}),
        "created_at": _iso(task.created_at),
        "updated_at": _iso(task.updated_at),
    }


def execution_json(execution: Execution, session: Session) -> dict:
    operator = session.get(Principal, execution.claimed_by_principal_id)
    agent = session.get(Agent, execution.agent_id) if execution.agent_id else None
    return {
        "id": execution.id,
        "task_id": execution.task_id,
        "agent_id": execution.agent_id,
        "executor_id": execution.agent_id or execution.claimed_by_principal_id,
        "executor_kind": "agent" if execution.agent_id else "human",
        "executor_name": agent.name if agent else operator.name if operator else "",
        "claimed_by_principal_id": execution.claimed_by_principal_id,
        "submitted_by_principal_id": execution.submitted_by_principal_id,
        "status": execution.status,
        "lease_expires_at": _iso(execution.lease_expires_at),
        "started_at": _iso(execution.started_at),
        "finished_at": _iso(execution.finished_at),
        "progress": execution.progress,
        "summary": execution.summary,
        "cost_usd": execution.cost_usd,
        "cost_source": execution.cost_source,
    }


def artifact_json(artifact: Artifact) -> dict:
    return {
        "id": artifact.id,
        "task_id": artifact.task_id,
        "execution_id": artifact.execution_id,
        "kind": artifact.kind,
        "title": artifact.title,
        "uri": artifact.uri,
        "content": artifact.content,
        "created_at": _iso(artifact.created_at),
    }


def message_json(message: Message) -> dict:
    return {
        "id": message.id,
        "project_id": message.project_id,
        "task_id": message.task_id,
        "sender_id": message.sender_id,
        "recipient_id": message.recipient_id,
        "kind": message.kind,
        "body": message.body,
        "reply_to_id": message.reply_to_id,
        "status": message.status,
        "created_at": _iso(message.created_at),
    }


def event_json(event: AuditEvent) -> dict:
    return {
        "id": event.id,
        "project_id": event.project_id,
        "actor_id": event.actor_id,
        "action": event.action,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "data": _loads(event.data_json, {}),
        "created_at": _iso(event.created_at),
    }


def outbox_json(event: OutboxEvent, delivery_token: str | None = None) -> dict:
    value = {
        "id": event.id,
        "project_id": event.project_id,
        "task_id": event.task_id,
        "agent_id": event.agent_id,
        "type": event.type,
        "payload": _loads(event.payload_json, {}),
        "status": event.status,
        "created_at": _iso(event.created_at),
    }
    if delivery_token is not None:
        value.update(delivery_token=delivery_token, attempts=event.attempts)
    return value


def add_audit(
    session: Session,
    actor: Principal,
    action: str,
    entity_type: str,
    entity_id: str,
    project_id: str | None,
    data: dict | None = None,
) -> AuditEvent:
    # Callers pass identifiers and outcomes only; bearer and lease secrets are never audit fields.
    item = AuditEvent(
        id=new_id(),
        project_id=project_id,
        actor_id=actor.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        data_json=_json(data or {}),
        created_at=now_utc(),
    )
    session.add(item)
    if entity_type == "task":
        task = session.get(Task, entity_id)
        if task is not None:
            from .collaboration import emit

            mentions = [task.assignee_principal_id] if task.assignee_principal_id else []
            emit(session, "task", entity_id, item.id, actor.id, action, mentions=mentions)
    return item


def require_role(actor: Principal, roles: set[str]) -> None:
    if actor.role not in roles:
        raise forbidden()


def require_project(session: Session, actor: Principal, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None or project.organization_id != actor.organization_id:
        raise not_found()
    if project_id not in principal_projects(session, actor.id):
        raise not_found()
    return project


def task_for_actor(session: Session, actor: Principal, task_id: str) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise not_found()
    require_project(session, actor, task.project_id)
    return task


def _lock_task(session: Session, task: Task) -> Task:
    if session.bind and session.bind.dialect.name != "sqlite":
        locked = session.scalar(
            select(Task)
            .where(Task.id == task.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked is None:
            raise not_found()
        return locked
    return task


def _lock_agent(session: Session, agent: Agent) -> Agent:
    if session.bind and session.bind.dialect.name != "sqlite":
        locked = session.scalar(
            select(Agent)
            .where(Agent.id == agent.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked is None:
            raise not_found("找不到 agent")
        return locked
    return agent


def agent_for_task(session: Session, actor: Principal, agent_id: str, project_id: str) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise not_found("找不到 agent")
    principal = session.get(Principal, agent.principal_id)
    if principal is None or not principal.active or principal.organization_id != actor.organization_id or project_id not in principal_projects(session, principal.id):
        raise forbidden("agent 沒有此專案的存取權")
    return agent


def human_for_task(session: Session, actor: Principal, principal_id: str, project_id: str, *, reviewer: bool = False) -> Principal:
    target = session.get(Principal, principal_id)
    roles = {"admin", "manager", "reviewer"} if reviewer else {"admin", "manager", "worker"}
    if target is None or target.kind != "human" or not target.active or target.organization_id != actor.organization_id:
        raise not_found("找不到可指派的人員")
    if project_id not in principal_projects(session, target.id) or target.role not in roles:
        raise forbidden("人員沒有此專案的所需角色或存取權")
    return target


def participant_reference(session: Session, agent_id: str | None, principal_id: str | None) -> dict | None:
    if agent_id:
        agent = session.get(Agent, agent_id)
        return {"id": agent.id, "principal_id": agent.principal_id, "name": agent.name, "kind": "agent"} if agent else None
    principal = session.get(Principal, principal_id) if principal_id else None
    return {"id": principal.id, "principal_id": principal.id, "name": principal.name, "kind": "human"} if principal else None


def list_participants(session: Session, actor: Principal, project_id: str) -> list[dict]:
    require_project(session, actor, project_id)
    result = []
    humans = session.scalars(select(Principal).join(ProjectMembership, ProjectMembership.principal_id == Principal.id).where(
        ProjectMembership.project_id == project_id, Principal.organization_id == actor.organization_id,
        Principal.kind == "human", Principal.active.is_(True),
    ).order_by(Principal.name, Principal.id))
    for principal in humans:
        result.append({**participant_reference(session, None, principal.id), "role": principal.role})
    agents = session.scalars(select(Agent).join(Principal, Principal.id == Agent.principal_id).join(
        ProjectMembership, ProjectMembership.principal_id == Principal.id,
    ).where(ProjectMembership.project_id == project_id, Principal.organization_id == actor.organization_id,
        Principal.active.is_(True), Agent.status != "disabled").order_by(Agent.name, Agent.id))
    for agent in agents:
        result.append({**participant_reference(session, agent.id, None), "role": agent.role})
    return result


def _validate_assignment(session: Session, actor: Principal, project_id: str, value: dict) -> None:
    for field, role in (("assignee_id", "worker"), ("reviewer_id", "reviewer")):
        human_field = field.replace("_id", "_principal_id")
        if value.get(field) and value.get(human_field):
            raise bad_request("assignment_conflict", "每個負責角色只能指派一位人員或 Agent")
        if value.get(field):
            agent = agent_for_task(session, actor, value[field], project_id)
            if agent.role != role or agent.status == "disabled":
                raise bad_request("invalid_agent", f"{field} 必須指定可用的 {role} agent")
        if value.get(human_field):
            human_for_task(session, actor, value[human_field], project_id, reviewer=role == "reviewer")
    assignee = participant_reference(session, value.get("assignee_id"), value.get("assignee_principal_id"))
    reviewer = participant_reference(session, value.get("reviewer_id"), value.get("reviewer_principal_id"))
    if assignee and reviewer and assignee["principal_id"] == reviewer["principal_id"]:
        raise bad_request("review_separation", "執行者與指定審查者必須不同")


def actor_agent(session: Session, actor: Principal) -> Agent | None:
    return session.scalar(select(Agent).where(Agent.principal_id == actor.id))


def has_active_task_lease(session: Session, actor: Principal, task: Task) -> bool:
    now = now_utc()
    execution = session.scalar(
        select(Execution).where(
            Execution.task_id == task.id,
            Execution.status == "running",
            Execution.claimed_by_principal_id == actor.id,
        )
    )
    return bool(execution and (execution.agent_id is None or _utc(execution.lease_expires_at) > now))


def _dependencies_done(session: Session, task_id: str) -> bool:
    dependency_ids = list(
        session.scalars(select(TaskDependency.dependency_id).where(TaskDependency.task_id == task_id))
    )
    if not dependency_ids:
        return True
    return session.scalar(
        select(func.count()).select_from(Task).where(Task.id.in_(dependency_ids), Task.status != "done")
    ) == 0


def _validate_dependencies(session: Session, project_id: str, task_id: str | None, dependency_ids: list[str]) -> None:
    if len(dependency_ids) != len(set(dependency_ids)):
        raise bad_request("duplicate_dependency", "dependency_ids 不可重複")
    if task_id and task_id in dependency_ids:
        raise conflict("dependency_cycle", "任務不可依賴自己")
    for dependency_id in dependency_ids:
        dependency = session.get(Task, dependency_id)
        if dependency is None or dependency.project_id != project_id:
            raise bad_request("invalid_dependency", "依賴任務必須存在於相同專案")
    if not task_id:
        return
    graph: dict[str, list[str]] = {}
    rows = session.execute(select(TaskDependency.task_id, TaskDependency.dependency_id)).all()
    for source, target in rows:
        graph.setdefault(source, []).append(target)
    graph[task_id] = dependency_ids

    def reaches_target(node: str, seen: set[str]) -> bool:
        if node == task_id:
            return True
        if node in seen:
            return False
        seen.add(node)
        return any(reaches_target(child, seen) for child in graph.get(node, []))

    if any(reaches_target(dependency_id, set()) for dependency_id in dependency_ids):
        raise conflict("dependency_cycle", "此依賴會形成循環")


def _task_depth(session: Session, task: Task) -> int:
    depth = 0
    current = task
    while current.parent_task_id:
        depth += 1
        current = session.get(Task, current.parent_task_id)
        if current is None:
            break
    return depth


def _validate_parent_assignment(session: Session, actor: Principal, project_id: str, parent_id: str | None) -> None:
    if not parent_id:
        return
    parent = session.get(Task, parent_id)
    if parent is None or parent.project_id != project_id:
        raise bad_request("invalid_parent", "parent_task_id 必須指向同一專案的任務")
    task_for_actor(session, actor, parent.id)
    if actor.role not in ACTIVE_ROLES and not has_active_task_lease(session, actor, parent):
        raise forbidden("只有管理者或持有有效 lease 的任務 owner 可建立子任務")
    if _task_depth(session, parent) >= 3:
        raise conflict("delegation_depth_exceeded", "子任務最多允許三層")


def _replace_dependencies(session: Session, task: Task, dependency_ids: list[str]) -> None:
    _validate_dependencies(session, task.project_id, task.id, dependency_ids)
    session.query(TaskDependency).filter(TaskDependency.task_id == task.id).delete(synchronize_session=False)
    for dependency_id in dependency_ids:
        session.add(TaskDependency(id=new_id(), task_id=task.id, dependency_id=dependency_id))


def create_project(session: Session, actor: Principal, value: dict) -> dict:
    require_role(actor, ACTIVE_ROLES)
    if value.get("team_id"):
        team = session.get(Team, value["team_id"])
        if team is None or team.organization_id != actor.organization_id:
            raise bad_request("invalid_team", "team_id 不屬於目前組織")
    project = Project(
        id=new_id(),
        key=value["key"].upper(),
        name=value["name"],
        description=value.get("description", ""),
        organization_id=actor.organization_id,
        team_id=value.get("team_id"),
        budget_usd=value.get("budget_usd", 0),
        created_at=now_utc(),
    )
    session.add(project)
    session.flush()
    session.add(ProjectMembership(id=new_id(), project_id=project.id, principal_id=actor.id))
    add_audit(session, actor, "project.created", "project", project.id, project.id, {"key": project.key})
    return project_json(project)


def list_projects(session: Session, actor: Principal) -> list[dict]:
    ids = principal_projects(session, actor.id)
    if not ids:
        return []
    projects = session.scalars(select(Project).where(Project.id.in_(ids)).order_by(Project.created_at.desc()))
    return [project_json(item) for item in projects]


def get_project_context(session: Session, actor: Principal, project_id: str) -> dict:
    project = require_project(session, actor, project_id)
    tasks = session.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.created_at.desc()))
    agents = session.scalars(
        select(Agent)
        .join(Principal, Principal.id == Agent.principal_id)
        .join(ProjectMembership, ProjectMembership.principal_id == Principal.id)
        .where(ProjectMembership.project_id == project_id)
        .order_by(Agent.name)
    )
    decisions = session.scalars(
        select(Message)
        .where(Message.project_id == project_id, Message.kind == "decision")
        .order_by(Message.created_at.desc())
    )
    return {
        "project": project_json(project),
        "tasks": [task_json(session, item) for item in tasks],
        "agents": [agent_json(session, item) for item in agents],
        "decisions": [message_json(item) for item in decisions],
    }


def _task_values(value: dict) -> dict:
    now = now_utc()
    return {
        "id": new_id(),
        "key": "",
        "project_id": value["project_id"],
        "title": value["title"],
        "description": value.get("description", ""),
        "goal": value.get("goal", ""),
        "inputs": value.get("inputs", ""),
        "scope": value.get("scope", ""),
        "constraints": value.get("constraints", ""),
        "acceptance_criteria_json": _json(value.get("acceptance_criteria", [])),
        "priority": value.get("priority", "medium"),
        "status": value.get("status", "ready"),
        "assignee_id": value.get("assignee_id"),
        "assignee_principal_id": value.get("assignee_principal_id"),
        "reviewer_id": value.get("reviewer_id"),
        "reviewer_principal_id": value.get("reviewer_principal_id"),
        "parent_task_id": value.get("parent_task_id"),
        "labels_json": _json(value.get("labels", [])),
        "blocked_reason": value.get("blocked_reason"),
        "progress": value.get("progress", 0),
        "handoff": value.get("handoff"),
        "budget_usd": value.get("budget_usd", 0),
        "work_type": value.get("work_type", "task"),
        "epic_id": value.get("epic_id"),
        "due_at": value.get("due_at"),
        "start_at": value.get("start_at"),
        "sprint_id": value.get("sprint_id"),
        "milestone_id": value.get("milestone_id"),
        "estimate_points": value.get("estimate_points"),
        "rank": value.get("rank", 0),
        "stage_id": value.get("stage_id"),
        "custom_fields_json": json.dumps(value.get("custom_fields", {}), ensure_ascii=False, separators=(",", ":")),
        "created_at": now,
        "updated_at": now,
    }


def create_task(session: Session, actor: Principal, value: dict) -> dict:
    from . import planning

    value = dict(value)
    intake_submission = value.pop("intake_submission", False)
    project = require_project(session, actor, value["project_id"])
    # Metadata and hierarchy mutations share the same project-before-task lock order.
    session.refresh(project, with_for_update=True)
    _validate_parent_assignment(session, actor, value["project_id"], value.get("parent_task_id"))
    agent = actor_agent(session, actor)
    if actor.role not in ACTIVE_ROLES and not intake_submission:
        if actor.kind != "agent" or actor.role != "worker" or value.get("assignee_id") not in {None, agent.id if agent else None}:
            raise forbidden()
        if value.get("status", "ready") not in {"backlog", "ready"}:
            raise bad_request("invalid_initial_status", "新任務只能從 backlog 或 ready 開始")
    if intake_submission and (value.get("assignee_id") or value.get("assignee_principal_id") or value.get("reviewer_id") or value.get("reviewer_principal_id") or value.get("status") != "backlog"):
        raise bad_request("invalid_intake_task", "表單只能建立未指派的 backlog 任務")
    if actor.role not in ACTIVE_ROLES and not intake_submission and value.get("assignee_principal_id"):
        raise forbidden("只有管理者可指派其他人員")
    _validate_assignment(session, actor, value["project_id"], value)
    dependencies = value.get("dependency_ids", [])
    _validate_dependencies(session, value["project_id"], None, dependencies)
    planning_values = {key: value[key] for key in planning.PLANNING_FIELDS if key in value}
    planning_values.setdefault("custom_fields", {})
    planning.validate_task_metadata(
        session, actor, value["project_id"], planning_values, current_status=value.get("status", "ready"),
        planning_edit=bool(planning.PLANNING_FIELDS.intersection(value)) and not intake_submission,
    )
    value.update(planning_values)
    task = Task(**_task_values(value))
    task.key = f"{session.get(Project, task.project_id).key}-{task.id.replace('-', '')[:8].upper()}"
    session.add(task)
    session.flush()
    for dependency_id in dependencies:
        session.add(TaskDependency(id=new_id(), task_id=task.id, dependency_id=dependency_id))
    session.flush()
    if dependencies and not _dependencies_done(session, task.id) and task.status == "ready":
        _set_task_status(task, "blocked")
        task.blocked_reason = "dependencies_pending"
    event = add_audit(session, actor, "task.created", "task", task.id, task.project_id, {"key": task.key, "status": task.status})
    planning.fire_task_rules(session, task, "task.created", event.id)
    session.flush()
    return task_json(session, task)


def list_tasks(
    session: Session,
    actor: Principal,
    project_id: str | None = None,
    status: str | None = None,
    query: str | None = None,
    ready_only: bool = False,
    work_type: str | None = None,
    sprint_id: str | None = None,
    milestone_id: str | None = None,
    assignee_principal_id: str | None = None,
    overdue: bool = False,
) -> list[dict]:
    ids = principal_projects(session, actor.id)
    stmt = select(Task).where(Task.project_id.in_(ids))
    if project_id:
        require_project(session, actor, project_id)
        stmt = stmt.where(Task.project_id == project_id)
    if status:
        if status not in TASK_STATES:
            raise bad_request("invalid_status", "status 不合法")
        stmt = stmt.where(Task.status == status)
    if work_type:
        if work_type not in {"task", "story", "bug", "epic"}:
            raise bad_request("invalid_work_type", "work_type 不合法")
        stmt = stmt.where(Task.work_type == work_type)
    if sprint_id:
        stmt = stmt.where(Task.sprint_id == sprint_id)
    if milestone_id:
        stmt = stmt.where(Task.milestone_id == milestone_id)
    if assignee_principal_id:
        stmt = stmt.where(Task.assignee_principal_id == assignee_principal_id)
    if overdue:
        stmt = stmt.where(Task.due_at.is_not(None), Task.due_at < now_utc(), Task.status.not_in({"done", "cancelled"}))
    if ready_only:
        now = now_utc()
        expired_task_ids = select(Execution.task_id).where(
            Execution.status == "running", Execution.lease_expires_at <= now
        )
        stmt = stmt.where(or_(Task.status == "ready", Task.id.in_(expired_task_ids)))
    if query:
        like = f"%{query.strip()}%"
        stmt = stmt.where(or_(Task.title.ilike(like), Task.key.ilike(like), Task.description.ilike(like)))
    stmt = stmt.order_by(Task.rank.asc(), Task.created_at.asc())
    result = []
    for item in session.scalars(stmt):
        value = task_json(session, item)
        if ready_only and item.status == "in_progress":
            value["status"] = "ready"
        result.append(value)
    return result


def patch_task(session: Session, actor: Principal, task_id: str, patch: dict) -> dict:
    from . import planning

    task = task_for_actor(session, actor, task_id)
    project = require_project(session, actor, task.project_id)
    session.refresh(project, with_for_update=True)
    task = _lock_task(session, task)
    if task.status in {"in_progress", "in_review"} and actor.role not in ACTIVE_ROLES:
        raise forbidden()
    if actor.role not in ACTIVE_ROLES:
        raise forbidden()
    values = {
        key: value
        for key, value in patch.items()
        if value is not None or key in {
            "assignee_id", "reviewer_id", "assignee_principal_id", "reviewer_principal_id", "epic_id", "due_at",
            "start_at", "sprint_id", "milestone_id", "estimate_points", "stage_id", "custom_fields",
        }
    }
    if not values:
        return task_json(session, task)
    assignment_fields = {"assignee_id", "reviewer_id", "assignee_principal_id", "reviewer_principal_id"}
    if assignment_fields.intersection(values):
        assignment = {name: getattr(task, name) for name in assignment_fields}
        assignment.update({name: value for name, value in values.items() if name in assignment_fields})
        for field in ("assignee_id", "reviewer_id"):
            human_field = field.replace("_id", "_principal_id")
            if values.get(field) and human_field not in values:
                assignment[human_field] = values[human_field] = None
            if values.get(human_field) and field not in values:
                assignment[field] = values[field] = None
        if task.status in {"in_progress", "in_review"} and any(
            assignment[name] != getattr(task, name) for name in ("assignee_id", "assignee_principal_id")
        ):
            raise conflict("active_assignment", "進行中任務需先交接或釋出才能變更負責者")
        _validate_assignment(session, actor, task.project_id, assignment)
    if "status" in values:
        allowed = (task.status == "backlog" and values["status"] == "ready") or values["status"] == "cancelled"
        if not allowed:
            raise conflict("guarded_transition", "此狀態只能透過受控任務操作變更")
        if values["status"] == "ready" and not _dependencies_done(session, task.id):
            raise conflict("dependencies_pending", "依賴尚未完成")
        if values["status"] == "cancelled":
            from .runs import stop_task_runs

            stop_task_runs(session, actor, task)
            for execution in session.scalars(
                select(Execution).where(Execution.task_id == task.id, Execution.status == "running")
            ):
                execution.status = "released"
                execution.finished_at = now_utc()
                execution.lease_token_hash = None
                agent = session.get(Agent, execution.agent_id) if execution.agent_id else None
                if agent and agent.status == "busy":
                    agent.status = "available"
                add_audit(session, actor, "execution.released", "execution", execution.id, task.project_id, {"reason": "task_cancelled"})
        _set_task_status(task, values.pop("status"))
    if "dependency_ids" in values:
        _replace_dependencies(session, task, values.pop("dependency_ids"))
        if task.status not in {"in_progress", "in_review", "done", "cancelled"}:
            if _dependencies_done(session, task.id):
                _set_task_status(task, "ready" if task.status == "blocked" and task.blocked_reason == "dependencies_pending" else task.status)
                if task.blocked_reason == "dependencies_pending":
                    task.blocked_reason = None
            elif task.status == "ready":
                _set_task_status(task, "blocked")
                task.blocked_reason = "dependencies_pending"
    if "assignee_id" in values and values["assignee_id"]:
        agent = agent_for_task(session, actor, values["assignee_id"], task.project_id)
        if agent.role != "worker" or agent.status == "disabled":
            raise bad_request("invalid_assignee", "assignee 必須是可用的 worker agent")
    if "reviewer_id" in values and values["reviewer_id"]:
        agent = agent_for_task(session, actor, values["reviewer_id"], task.project_id)
        if agent.role != "reviewer" or agent.status == "disabled":
            raise bad_request("invalid_reviewer", "reviewer_id 必須是可用的 reviewer agent")
    planning_values = {key: values.pop(key) for key in list(values) if key in planning.PLANNING_FIELDS}
    if planning_values:
        if "custom_fields" in planning_values and planning_values["custom_fields"] is None:
            planning_values["custom_fields"] = {}
        planning.validate_task_metadata(
            session, actor, task.project_id, planning_values, current_status=values.get("status", task.status), task_id=task.id
        )
        planning.set_task_metadata(task, planning_values)
    mappings = {
        "acceptance_criteria": "acceptance_criteria_json",
        "labels": "labels_json",
    }
    for key, value in values.items():
        setattr(task, mappings.get(key, key), _json(value) if key in mappings else value)
    task.updated_at = now_utc()
    event = add_audit(session, actor, "task.updated", "task", task.id, task.project_id, {"fields": sorted(patch)})
    planning.fire_task_rules(session, task, "task.updated", event.id)
    session.flush()
    return task_json(session, task)


def get_task_context(session: Session, actor: Principal, task_id: str) -> dict:
    task = task_for_actor(session, actor, task_id)
    executions = session.scalars(select(Execution).where(Execution.task_id == task.id).order_by(Execution.started_at.desc()))
    artifacts = session.scalars(select(Artifact).where(Artifact.task_id == task.id).order_by(Artifact.created_at))
    messages = session.scalars(select(Message).where(Message.task_id == task.id).order_by(Message.created_at))
    events = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.project_id == task.project_id, AuditEvent.entity_id == task.id)
        .order_by(AuditEvent.created_at.desc())
    )
    dependencies = session.scalars(
        select(Task).join(TaskDependency, TaskDependency.dependency_id == Task.id).where(TaskDependency.task_id == task.id)
    )
    return {
        "task": task_json(session, task),
        "executions": [execution_json(item, session) for item in executions],
        "artifacts": [artifact_json(item) for item in artifacts],
        "messages": [message_json(item) for item in messages],
        "events": [event_json(item) for item in events],
        "dependencies": [task_json(session, item) for item in dependencies],
    }


def list_executions(session: Session, actor: Principal, task_id: str) -> list[dict]:
    task = task_for_actor(session, actor, task_id)
    return [
        execution_json(item, session)
        for item in session.scalars(
            select(Execution).where(Execution.task_id == task.id).order_by(Execution.started_at.desc())
        )
    ]


def _close_expired(session: Session, task: Task) -> None:
    now = now_utc()
    for execution in session.scalars(
        select(Execution).where(Execution.task_id == task.id, Execution.status == "running")
    ):
        if execution.agent_id and _utc(execution.lease_expires_at) <= now:
            execution.status = "expired"
            execution.finished_at = now
            execution.lease_token_hash = None
            agent = session.get(Agent, execution.agent_id)
            if agent and agent.status == "busy":
                agent.status = "available"
            _set_task_status(task, "ready" if _dependencies_done(session, task.id) else "blocked")
            task.blocked_reason = None if task.status == "ready" else "dependencies_pending"
            task.updated_at = now
            add_audit(session, execution_actor(session, execution), "execution.expired", "execution", execution.id, task.project_id, {"task_id": task.id})


def execution_actor(session: Session, execution: Execution) -> Principal:
    actor = session.get(Principal, execution.claimed_by_principal_id)
    if actor is None:
        raise DomainError(500, "internal_error", "execution actor missing")
    return actor


def claim_task(session: Session, actor: Principal, task_id: str, value: dict) -> dict:
    task = task_for_actor(session, actor, task_id)
    # PostgreSQL serializes claims on the task row; SQLite relies on the conditional update below.
    if session.bind and session.bind.dialect.name != "sqlite":
        task = _lock_task(session, task)
    _close_expired(session, task)
    session.flush()
    agent = actor_agent(session, actor)
    if actor.kind == "runtime":
        raise forbidden("runtime credential 不可代替 agent 領取任務")
    human_work = actor.kind == "human" and not value.get("agent_id")
    claimed_agent = None
    if human_work:
        require_role(actor, {"admin", "manager", "worker"})
        if task.assignee_id or (task.assignee_principal_id and task.assignee_principal_id != actor.id):
            raise forbidden("只能認領未指派或指派給自己的任務")
        if task.reviewer_principal_id == actor.id:
            raise bad_request("review_separation", "指定審查者不可認領同一任務")
        if session.scalar(select(OutboxEvent.id).where(OutboxEvent.task_id == task.id, OutboxEvent.status.in_(["pending", "claimed"]))):
            raise conflict("dispatch_pending", "任務已派發給 Agent，需先停止派發")
        agent_id = None
    elif agent:
        agent_id = agent.id
    elif actor.role in ACTIVE_ROLES:
        agent_id = value.get("agent_id")
        if not agent_id:
            raise bad_request("agent_required", "human claim 必須提供 agent_id")
    else:
        raise forbidden("只有 worker agent 或具管理權的 human 可 claim")
    if value.get("agent_id") and agent and value["agent_id"] != agent.id:
        raise forbidden("agent 不可冒用其他 agent 身分")
    if not human_work:
        if task.assignee_principal_id:
            raise forbidden("此任務已指派給人員")
        claimed_agent = _lock_agent(session, agent_for_task(session, actor, agent_id, task.project_id))
        if claimed_agent.role != "worker" or claimed_agent.status != "available":
            raise conflict("agent_unavailable", "agent 目前不可執行任務")
        if task.assignee_id and task.assignee_id != claimed_agent.id:
            raise forbidden("此任務已指派給其他 agent")
    if task.status != "ready":
        raise conflict("task_not_ready", "任務目前不可領取")
    if not _dependencies_done(session, task.id):
        _set_task_status(task, "blocked")
        task.blocked_reason = "dependencies_pending"
        raise conflict("dependencies_pending", "任務依賴尚未完成")
    now = now_utc()
    claim_values = {"status": "in_progress", "stage_id": None, "blocked_reason": None, "updated_at": now}
    if human_work:
        claim_values["assignee_principal_id"] = actor.id
    result = session.execute(
        update(Task)
        .where(
            Task.id == task.id,
            Task.status == "ready",
            Task.assignee_id == task.assignee_id,
            Task.assignee_principal_id == task.assignee_principal_id,
        )
        .values(**claim_values)
    )
    if result.rowcount != 1:
        raise conflict("task_claimed", "任務已被其他執行者領取")
    token = None if human_work else new_secret("lease")
    execution = Execution(
        id=new_id(),
        task_id=task.id,
        agent_id=claimed_agent.id if claimed_agent else None,
        claimed_by_principal_id=actor.id,
        status="running",
        lease_token_hash=hash_secret(token) if token else None,
        lease_expires_at=None if human_work else now + timedelta(seconds=value.get("lease_seconds", 300)),
        started_at=now,
        progress=0,
        cost_usd=0,
        cost_source="self_reported",
    )
    session.add(execution)
    if claimed_agent:
        claimed_agent.status = "busy"
    _set_task_status(task, "in_progress")
    task.updated_at = now
    add_audit(session, actor, "task.claimed", "task", task.id, task.project_id, {"execution_id": execution.id, "agent_id": execution.agent_id, "executor_kind": "human" if human_work else "agent"})
    session.flush()
    return {"task": task_json(session, task), "execution": execution_json(execution, session), "lease_token": token}


def _leased_execution(
    session: Session,
    actor: Principal,
    task: Task,
    execution_id: str,
    lease_token: str | None,
) -> Execution:
    task = _lock_task(session, task)
    if session.bind and session.bind.dialect.name != "sqlite":
        execution = session.scalar(
            select(Execution)
            .where(Execution.id == execution_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    else:
        execution = session.get(Execution, execution_id)
    if execution is None or execution.task_id != task.id:
        raise not_found("找不到 execution")
    if execution.status != "running" or execution.claimed_by_principal_id != actor.id:
        raise conflict("lease_invalid", "execution lease 已失效或不屬於目前 actor")
    if execution.agent_id is None:
        if actor.kind != "human":
            raise forbidden("只有實際執行的人員可更新此任務")
        require_role(actor, {"admin", "manager", "worker"})
        return execution
    if _utc(execution.lease_expires_at) <= now_utc():
        execution.status = "expired"
        execution.finished_at = now_utc()
        execution.lease_token_hash = None
        _set_task_status(task, "ready" if _dependencies_done(session, task.id) else "blocked")
        task.blocked_reason = None if task.status == "ready" else "dependencies_pending"
        task.updated_at = now_utc()
        agent = session.get(Agent, execution.agent_id)
        if agent and agent.status == "busy":
            agent.status = "available"
        add_audit(session, actor, "execution.expired", "execution", execution.id, task.project_id, {"task_id": task.id})
        raise conflict("lease_expired", "execution lease 已過期")
    if not lease_token or not execution.lease_token_hash or not hmac.compare_digest(execution.lease_token_hash, hash_secret(lease_token)):
        raise conflict("lease_invalid", "lease token 無效")
    return execution


def renew_lease(session: Session, actor: Principal, task_id: str, value: dict) -> dict:
    task = task_for_actor(session, actor, task_id)
    execution = _leased_execution(session, actor, task, value["execution_id"], value["lease_token"])
    if execution.agent_id is None:
        raise conflict("human_work_has_no_lease", "人員工作不需要續期租約")
    token = new_secret("lease")
    now = now_utc()
    execution.lease_token_hash = hash_secret(token)
    execution.lease_expires_at = now + timedelta(seconds=value.get("lease_seconds", 300))
    task.updated_at = now
    add_audit(session, actor, "execution.renewed", "execution", execution.id, task.project_id, {"lease_expires_at": _iso(execution.lease_expires_at)})
    session.flush()
    return {"task": task_json(session, task), "execution": execution_json(execution, session), "lease_token": token}


def report_progress(session: Session, actor: Principal, task_id: str, value: dict) -> dict:
    task = task_for_actor(session, actor, task_id)
    execution = _leased_execution(session, actor, task, value["execution_id"], value.get("lease_token"))
    progress = value["progress"]
    execution.progress = progress
    task.progress = progress
    if value.get("summary") is not None:
        execution.summary = value["summary"]
    if value.get("cost_usd") is not None:
        execution.cost_usd = value["cost_usd"]
        execution.cost_source = "self_reported"
    task.updated_at = now_utc()
    add_audit(session, actor, "task.progress", "task", task.id, task.project_id, {"progress": progress, "execution_id": execution.id})
    session.flush()
    return task_json(session, task)


def _finish_execution(session: Session, task: Task, execution: Execution, status: str) -> None:
    now = now_utc()
    execution.status = status
    execution.finished_at = now
    execution.lease_token_hash = None
    agent = session.get(Agent, execution.agent_id) if execution.agent_id else None
    if agent and agent.status == "busy":
        agent.status = "available"
    task.updated_at = now


def block_task(session: Session, actor: Principal, task_id: str, value: dict) -> dict:
    task = task_for_actor(session, actor, task_id)
    execution = _leased_execution(session, actor, task, value["execution_id"], value.get("lease_token"))
    _finish_execution(session, task, execution, "released")
    _set_task_status(task, "blocked")
    task.blocked_reason = value["reason"]
    task.handoff = value.get("handoff")
    add_audit(session, actor, "task.blocked", "task", task.id, task.project_id, {"execution_id": execution.id, "reason": value["reason"]})
    session.flush()
    return task_json(session, task)


def release_task(session: Session, actor: Principal, task_id: str, value: dict) -> dict:
    task = task_for_actor(session, actor, task_id)
    execution = _leased_execution(session, actor, task, value["execution_id"], value.get("lease_token"))
    _finish_execution(session, task, execution, "released")
    _set_task_status(task, "ready")
    task.blocked_reason = None
    task.handoff = value["handoff"]
    task.progress = 0
    if execution.agent_id is None:
        task.assignee_principal_id = None
    add_audit(session, actor, "task.released", "task", task.id, task.project_id, {"execution_id": execution.id})
    session.flush()
    return task_json(session, task)


def unblock_task(session: Session, actor: Principal, task_id: str) -> dict:
    task = task_for_actor(session, actor, task_id)
    require_role(actor, ACTIVE_ROLES)
    if task.status != "blocked":
        raise conflict("task_not_blocked", "只有 blocked 任務可解除")
    if not _dependencies_done(session, task.id):
        raise conflict("dependencies_pending", "仍有未完成的依賴")
    _set_task_status(task, "ready")
    task.blocked_reason = None
    task.updated_at = now_utc()
    add_audit(session, actor, "task.unblocked", "task", task.id, task.project_id, {})
    session.flush()
    return task_json(session, task)


def submit_result(session: Session, actor: Principal, task_id: str, value: dict) -> dict:
    task = task_for_actor(session, actor, task_id)
    execution = _leased_execution(session, actor, task, value["execution_id"], value.get("lease_token"))
    now = now_utc()
    execution.status = "submitted"
    execution.finished_at = now
    execution.progress = 100
    execution.summary = value["summary"]
    execution.cost_usd = value.get("cost_usd", 0)
    execution.cost_source = "self_reported"
    execution.submitted_by_principal_id = actor.id
    execution.lease_token_hash = None
    task.progress = 100
    _set_task_status(task, "in_review")
    task.blocked_reason = None
    task.updated_at = now
    for entry in value["artifacts"]:
        session.add(
            Artifact(
                id=new_id(),
                task_id=task.id,
                execution_id=execution.id,
                kind=entry["kind"],
                title=entry["title"],
                uri=entry.get("uri"),
                content=entry.get("content"),
                created_at=now,
            )
        )
    agent = session.get(Agent, execution.agent_id) if execution.agent_id else None
    if agent and agent.status == "busy":
        agent.status = "available"
    add_audit(session, actor, "task.submitted", "task", task.id, task.project_id, {"execution_id": execution.id, "artifact_count": len(value["artifacts"])})
    session.flush()
    return get_task_context(session, actor, task.id)


def review_result(session: Session, actor: Principal, task_id: str, value: dict) -> dict:
    task = _lock_task(session, task_for_actor(session, actor, task_id))
    if task.status != "in_review":
        raise conflict("task_not_in_review", "任務目前沒有待審核結果")
    require_role(actor, {"reviewer", "manager", "admin"})
    submitted = session.scalar(
        select(Execution)
        .where(Execution.task_id == task.id, Execution.status == "submitted")
        .order_by(Execution.finished_at.desc())
    )
    if submitted is None:
        raise conflict("submission_missing", "找不到待審核的執行紀錄")
    reviewer_agent = actor_agent(session, actor)
    if task.reviewer_principal_id and actor.id != task.reviewer_principal_id:
        raise forbidden("此任務指定了其他人員審查")
    if task.reviewer_id:
        if actor.role != "admin" and (reviewer_agent is None or reviewer_agent.id != task.reviewer_id):
            raise forbidden("此任務指定了其他 reviewer")
    if actor.id == submitted.submitted_by_principal_id or (reviewer_agent and reviewer_agent.id == submitted.agent_id):
        raise forbidden("執行者不可審核自己的結果")
    accepted = value["decision"] == "accept"
    submitted.status = "accepted" if accepted else "rejected"
    if accepted:
        _set_task_status(task, "done")
        task.blocked_reason = None
        session.flush()
        for successor in session.scalars(
            select(Task).join(TaskDependency, TaskDependency.task_id == Task.id).where(TaskDependency.dependency_id == task.id)
        ):
            if successor.status == "blocked" and successor.blocked_reason == "dependencies_pending" and _dependencies_done(session, successor.id):
                _set_task_status(successor, "ready")
                successor.blocked_reason = None
                successor.updated_at = now_utc()
                add_audit(session, actor, "task.unblocked", "task", successor.id, successor.project_id, {"dependency_id": task.id})
    else:
        _set_task_status(task, "ready" if _dependencies_done(session, task.id) else "blocked")
        task.blocked_reason = None if task.status == "ready" else "dependencies_pending"
        task.progress = 0
    task.updated_at = now_utc()
    add_audit(session, actor, f"task.review.{value['decision']}", "task", task.id, task.project_id, {"execution_id": submitted.id, "comment": value["comment"]})
    session.flush()
    return get_task_context(session, actor, task.id)


def create_agent(session: Session, actor: Principal, value: dict) -> dict:
    require_role(actor, ACTIVE_ROLES)
    project_ids = list(dict.fromkeys(value["project_ids"]))
    if not project_ids:
        raise bad_request("project_required", "agent 至少需要一個專案範圍")
    projects = [require_project(session, actor, project_id) for project_id in project_ids]
    team_id = value.get("team_id")
    if team_id:
        team = session.get(Team, team_id)
        if team is None or team.organization_id != actor.organization_id:
            raise bad_request("invalid_team", "team_id 不屬於目前組織")
    template_id = value.get("template_id")
    template = template_definition_for_agent(session, actor, template_id) if template_id else {}
    role = value.get("role") or template.get("role")
    if role not in {"worker", "reviewer"}:
        raise bad_request("agent_role_required", "Agent role 必須是 worker 或 reviewer")
    capabilities = value.get("capabilities")
    if capabilities is None:
        capabilities = template.get("capabilities", [])
    execution_config = value.get("execution_config")
    if execution_config is None:
        execution_config = {
            "instructions": template.get("instructions", ""),
            "tool_connection_ids": template.get("tool_connection_ids", []),
            "sandbox_profile_id": template.get("sandbox_profile_id"),
            "limits": template.get("limits", {"max_turns": 20, "timeout_seconds": 600}),
        }
    model_config = value.get("model_config")
    if model_config is None and template:
        model_config = template.get("model_config")
    principal = Principal(
        id=new_id(),
        name=value["name"],
        kind="agent",
        role=role,
        organization_id=actor.organization_id,
        team_id=team_id,
        active=True,
    )
    agent = Agent(
        id=new_id(),
        principal_id=principal.id,
        name=value["name"],
        role=role,
        team_id=team_id,
        capabilities_json=_json(capabilities),
        status="available",
        runtime=value.get("runtime", "external"),
        model=value.get("model"),
        created_at=now_utc(),
    )
    session.add(principal)
    session.flush()
    session.add(agent)
    set_agent_model_config(session, actor, agent, model_config)
    set_agent_execution_settings(session, agent, project_ids, execution_config, template_id)
    for project in projects:
        session.add(ProjectMembership(id=new_id(), project_id=project.id, principal_id=principal.id))
    token = new_secret()
    from .models import AuthToken

    session.add(AuthToken(id=new_id(), principal_id=principal.id, token_hash=hash_secret(token), created_at=now_utc()))
    add_audit(session, actor, "agent.created", "agent", agent.id, projects[0].id, {"role": agent.role, "project_ids": project_ids})
    session.flush()
    result = agent_json(session, agent)
    result["token"] = token
    return result


def list_agents(session: Session, actor: Principal, project_id: str | None = None) -> list[dict]:
    ids = principal_projects(session, actor.id)
    if project_id:
        require_project(session, actor, project_id)
        ids = [project_id]
    if not ids:
        return []
    agents = session.scalars(
        select(Agent)
        .join(Principal, Principal.id == Agent.principal_id)
        .join(ProjectMembership, ProjectMembership.principal_id == Principal.id)
        .where(ProjectMembership.project_id.in_(ids))
        .distinct()
        .order_by(Agent.name)
    )
    return [agent_json(session, item) for item in agents]


def patch_agent(session: Session, actor: Principal, agent_id: str, patch: dict) -> dict:
    require_role(actor, ACTIVE_ROLES)
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise not_found("找不到 agent")
    if agent.team_id:
        team = session.get(Team, agent.team_id)
        if team is None or team.organization_id != actor.organization_id:
            raise not_found("找不到 agent")
    principal = session.get(Principal, agent.principal_id)
    if principal is None or principal.organization_id != actor.organization_id:
        raise not_found("找不到 agent")
    project_ids = principal_projects(session, principal.id)
    for project_id in project_ids:
        require_project(session, actor, project_id)
    model_config_present = "model_config" in patch
    execution_config_present = "execution_config" in patch
    template_id_present = "template_id" in patch
    values = {key: value for key, value in patch.items() if value is not None and key not in {"model_config", "execution_config", "template_id"}}
    template = template_definition_for_agent(session, actor, patch["template_id"]) if template_id_present and patch["template_id"] else {}
    if template and "role" not in values:
        values["role"] = template["role"]
    if template and "capabilities" not in values:
        values["capabilities"] = template.get("capabilities", [])
    if "name" in values:
        agent.name = values["name"]
        principal.name = values["name"]
    if "capabilities" in values:
        agent.capabilities_json = _json(values["capabilities"])
    if "role" in values:
        agent.role = values["role"]
        principal.role = values["role"]
    if "status" in values:
        is_running = bool(session.scalar(
            select(func.count()).select_from(Execution).where(Execution.agent_id == agent.id, Execution.status == "running")
        ))
        if is_running:
            raise conflict("agent_busy", "執行中的 agent 不可變更狀態")
        agent.status = values["status"]
        principal.active = values["status"] != "disabled"
    if "runtime" in values:
        agent.runtime = values["runtime"]
    if "model" in values:
        agent.model = values["model"]
    if model_config_present:
        set_agent_model_config(session, actor, agent, patch["model_config"])
    elif template_id_present and template:
        set_agent_model_config(session, actor, agent, template.get("model_config"))
    if execution_config_present or template_id_present:
        selected_template_id = patch.get("template_id") if template_id_present else agent_execution_settings(session, agent)[1]
        selected_config = patch.get("execution_config") if execution_config_present else None
        if selected_config is None and template:
            selected_config = {
                "instructions": template.get("instructions", ""),
                "tool_connection_ids": template.get("tool_connection_ids", []),
                "sandbox_profile_id": template.get("sandbox_profile_id"),
                "limits": template.get("limits", {"max_turns": 20, "timeout_seconds": 600}),
            }
        if selected_config is None and execution_config_present:
            selected_config = {}
        if selected_config is not None:
            set_agent_execution_settings(session, agent, project_ids, selected_config, selected_template_id)
        elif template_id_present:
            current_config, _ = agent_execution_settings(session, agent)
            set_agent_execution_settings(session, agent, project_ids, current_config, None)
    fields = sorted(values)
    if model_config_present:
        fields.append("model_config")
    elif template_id_present and template:
        fields.append("model_config")
    if execution_config_present or template_id_present:
        fields.extend(key for key, present in (("execution_config", execution_config_present), ("template_id", template_id_present)) if present)
    add_audit(session, actor, "agent.updated", "agent", agent.id, project_ids[0] if project_ids else None, {"fields": fields})
    session.flush()
    return agent_json(session, agent)


def _resolve_principal(session: Session, identifier: str) -> Principal | None:
    principal = session.get(Principal, identifier)
    if principal:
        return principal
    agent = session.get(Agent, identifier)
    return session.get(Principal, agent.principal_id) if agent else None


def create_message(session: Session, actor: Principal, value: dict) -> dict:
    require_project(session, actor, value["project_id"])
    task_id = value.get("task_id")
    if task_id:
        task = session.get(Task, task_id)
        if task is None or task.project_id != value["project_id"]:
            raise not_found("任務不屬於此專案")
    recipient = _resolve_principal(session, value["recipient_id"]) if value.get("recipient_id") else None
    if value.get("recipient_id") and recipient is None:
        raise not_found("找不到收件者")
    reply_to = session.get(Message, value["reply_to_id"]) if value.get("reply_to_id") else None
    if value.get("reply_to_id") and reply_to is None:
        raise not_found("找不到欲回覆的訊息")
    if reply_to:
        if reply_to.project_id != value["project_id"] or reply_to.task_id != task_id:
            raise bad_request("reply_scope_mismatch", "回覆必須位於相同專案與任務")
        if reply_to.recipient_id and reply_to.recipient_id != actor.id:
            raise forbidden("只有指定收件者可回覆")
        if recipient is None:
            recipient = session.get(Principal, reply_to.sender_id)
        if value["kind"] != "reply":
            raise bad_request("invalid_reply_kind", "回覆訊息 kind 必須是 reply")
    if recipient:
        if recipient.id == actor.id:
            raise bad_request("self_message", "不可傳送訊息給自己")
        if not recipient.active or recipient.kind == "runtime" or recipient.organization_id != actor.organization_id or value["project_id"] not in principal_projects(session, recipient.id):
            raise forbidden("寄件者與收件者必須共同有此專案權限")
    message = Message(
        id=new_id(),
        project_id=value["project_id"],
        task_id=task_id,
        sender_id=actor.id,
        recipient_id=recipient.id if recipient else None,
        kind=value["kind"],
        body=value["body"],
        reply_to_id=reply_to.id if reply_to else None,
        status="delivered",
        created_at=now_utc(),
    )
    session.add(message)
    if reply_to:
        reply_to.status = "completed"
    add_audit(session, actor, "message.sent", "message", message.id, message.project_id, {"kind": message.kind, "task_id": message.task_id, "recipient_id": message.recipient_id})
    session.flush()
    return message_json(message)


def list_messages(
    session: Session,
    actor: Principal,
    project_id: str | None = None,
    task_id: str | None = None,
    inbox: bool = False,
) -> list[dict]:
    project_ids = principal_projects(session, actor.id)
    stmt = select(Message).where(Message.project_id.in_(project_ids))
    if project_id:
        require_project(session, actor, project_id)
        stmt = stmt.where(Message.project_id == project_id)
    if task_id:
        task = task_for_actor(session, actor, task_id)
        stmt = stmt.where(Message.task_id == task.id)
    if inbox:
        stmt = stmt.where(Message.recipient_id == actor.id)
    elif actor.role not in ACTIVE_ROLES:
        stmt = stmt.where(or_(Message.sender_id == actor.id, Message.recipient_id == actor.id))
    stmt = stmt.order_by(Message.created_at.desc())
    return [message_json(item) for item in session.scalars(stmt)]


def acknowledge_message(session: Session, actor: Principal, message_id: str, status: str) -> dict:
    message = session.get(Message, message_id)
    if message is None:
        raise not_found("找不到訊息")
    require_project(session, actor, message.project_id)
    if message.recipient_id != actor.id and actor.role not in ACTIVE_ROLES:
        raise forbidden("只有收件者可確認訊息")
    if message.status == "completed" and status == "accepted":
        return message_json(message)
    message.status = status
    add_audit(session, actor, "message.acknowledged", "message", message.id, message.project_id, {"status": status})
    session.flush()
    return message_json(message)


def delegate_task(session: Session, actor: Principal, task_id: str, value: dict) -> dict:
    parent = _lock_task(session, task_for_actor(session, actor, task_id))
    if actor.role not in ACTIVE_ROLES and not has_active_task_lease(session, actor, parent):
        raise forbidden("只有管理者或持有有效 lease 的任務 owner 可 delegate")
    agent_id, human_id = value.get("agent_id"), value.get("assignee_principal_id")
    if bool(agent_id) == bool(human_id):
        raise bad_request("delegate_target_required", "委派需選擇一位人員或 Agent")
    if human_id:
        target = human_for_task(session, actor, human_id, parent.project_id)
        recipient_id = target.id
    else:
        target = agent_for_task(session, actor, agent_id, parent.project_id)
        if target.role != "worker" or target.status in {"disabled", "offline"}:
            raise bad_request("invalid_delegate", "delegate 對象必須是可用的 worker agent")
        recipient_id = target.principal_id
    if _task_depth(session, parent) >= 3:
        raise conflict("delegation_depth_exceeded", "子任務最多允許三層")
    child_value = {
        "project_id": parent.project_id,
        "title": value["title"],
        "description": value.get("description", ""),
        "goal": value["goal"],
        "inputs": value.get("inputs", ""),
        "scope": value.get("scope", ""),
        "constraints": value.get("constraints", ""),
        "acceptance_criteria": value.get("acceptance_criteria", []),
        "priority": value.get("priority", "medium"),
        "assignee_id": agent_id,
        "assignee_principal_id": human_id,
        "reviewer_id": parent.reviewer_id,
        "reviewer_principal_id": parent.reviewer_principal_id,
        "parent_task_id": parent.id,
        "budget_usd": value.get("budget_usd", 0),
        "status": "ready",
    }
    _validate_assignment(session, actor, parent.project_id, child_value)
    child = Task(**_task_values(child_value))
    child.key = f"{session.get(Project, child.project_id).key}-{child.id.replace('-', '')[:8].upper()}"
    session.add(child)
    session.flush()
    message = Message(
        id=new_id(),
        project_id=parent.project_id,
        task_id=parent.id,
        sender_id=actor.id,
        recipient_id=recipient_id,
        kind="handoff",
        body=f"Delegated task {child.key}: {child.title}",
        reply_to_id=None,
        status="delivered",
        created_at=now_utc(),
    )
    session.add(message)
    add_audit(session, actor, "task.delegated", "task", child.id, child.project_id, {"parent_task_id": parent.id, "agent_id": agent_id, "assignee_principal_id": human_id})
    add_audit(session, actor, "message.sent", "message", message.id, parent.project_id, {"kind": "handoff", "task_id": parent.id, "recipient_id": recipient_id})
    session.flush()
    return task_json(session, child)


def _admit_runtime_project(session: Session, project: Project) -> None:
    runtime_principals = session.scalars(
        select(Principal).where(
            Principal.kind == "runtime",
            Principal.organization_id == project.organization_id,
            Principal.active.is_(True),
        )
    )
    for runtime_principal in runtime_principals:
        membership = session.scalar(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project.id,
                ProjectMembership.principal_id == runtime_principal.id,
            )
        )
        if membership is None:
            session.add(ProjectMembership(id=new_id(), project_id=project.id, principal_id=runtime_principal.id))


def _create_dispatch(session: Session, actor: Principal, task: Task, agent: Agent, *, retry_of: str | None = None) -> dict:
    task = _lock_task(session, task)
    if task.assignee_principal_id:
        raise conflict("human_assigned_task", "人員負責的任務不可派發給 Pi Agent")
    if task.assignee_id and task.assignee_id != agent.id:
        raise forbidden("此任務已指派給其他 Agent")
    agent = _lock_agent(session, agent)
    agent_principal = session.get(Principal, agent.principal_id)
    project = session.get(Project, task.project_id)
    if agent_principal is None or project is None or agent_principal.organization_id != project.organization_id:
        raise forbidden("agent 與任務必須屬於相同組織")
    if agent.runtime != "pi":
        raise bad_request("runtime_required", "只有 Pi runtime agent 可 dispatch")
    if agent.status in {"disabled", "offline"}:
        raise conflict("agent_unavailable", "Agent 目前不可執行任務")
    if task.status != "ready" or not _dependencies_done(session, task.id):
        raise conflict("task_not_ready", "任務尚未 ready 或依賴未完成")
    existing = session.scalar(
        select(OutboxEvent).where(
            OutboxEvent.task_id == task.id,
            or_(
                OutboxEvent.status == "pending",
                and_(OutboxEvent.status == "claimed", OutboxEvent.claim_expires_at > now_utc()),
            ),
        )
    )
    if existing:
        raise conflict("dispatch_outstanding", "此任務已有尚未完成的 dispatch")
    active_agent_run = session.scalar(
        select(OutboxEvent.id).where(
            OutboxEvent.agent_id == agent.id,
            or_(
                OutboxEvent.status == "pending",
                and_(OutboxEvent.status == "claimed", OutboxEvent.claim_expires_at > now_utc()),
            ),
        ).limit(1)
    )
    active_execution = session.scalar(
        select(Execution.id).where(Execution.agent_id == agent.id, Execution.status == "running").limit(1)
    )
    if active_agent_run or active_execution:
        raise conflict("agent_busy", "此 Agent 已有執行中的工作")
    model_config = validate_effective_agent_model_config(session, agent)
    execution_config, template_id, sandbox_profile = dispatch_execution_snapshot(session, agent, task.project_id)
    event = OutboxEvent(
        id=new_id(),
        project_id=task.project_id,
        task_id=task.id,
        agent_id=agent.id,
        type="run_task",
        payload_json=_json(
            {
                "task_id": task.id,
                "agent_id": agent.id,
                "task_key": task.key,
                "model_config": model_config,
                "execution_mode": "configured" if model_config else "demo",
                "execution_config": execution_config,
                "template_id": template_id,
                "sandbox_profile": sandbox_profile,
            }
        ),
        status="pending",
        attempts=0,
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    session.add(event)
    session.add(
        RunMirror(
            id=event.id,
            project_id=task.project_id,
            task_id=task.id,
            agent_id=agent.id,
            execution_id=None,
            template_id_snapshot=template_id,
            status="queued",
            desired_action=None,
            control_revision=0,
            retry_of=retry_of,
            mode=None,
            model_config_json=_json(model_config) if model_config else None,
            execution_config_json=_json(execution_config),
            tool_connections_json=_json(execution_config["tool_connection_ids"]),
            sandbox_profile_json=_json(sandbox_profile) if sandbox_profile else None,
            last_sync_sequence=0,
            last_sync_hash=None,
            created_at=now_utc(),
            updated_at=now_utc(),
            started_at=None,
            finished_at=None,
        )
    )
    from .tool_connections import snapshot_tool_connections

    snapshot_tool_connections(session, event.id, task.project_id, execution_config["tool_connection_ids"])
    _admit_runtime_project(session, project)
    add_audit(session, actor, "task.dispatched", "outbox", event.id, task.project_id, {"task_id": task.id, "agent_id": agent.id})
    session.flush()
    return outbox_json(event)


def dispatch_task(session: Session, actor: Principal, task_id: str, agent_id: str) -> dict:
    task = _lock_task(session, task_for_actor(session, actor, task_id))
    if actor.role not in ACTIVE_ROLES and not has_active_task_lease(session, actor, task):
        raise forbidden("只有管理者或持有有效 lease 的任務 owner 可 dispatch")
    if task.assignee_principal_id:
        raise conflict("human_assigned_task", "人員任務需先明確改指派為 Agent 才能派發")
    agent = agent_for_task(session, actor, agent_id, task.project_id)
    return _create_dispatch(session, actor, task, agent)


def dispatch_workflow_step(
    session: Session,
    actor: Principal,
    instance,
    step_run,
    agent_id: str,
) -> dict:
    if actor.kind != "runtime" or not actor.active:
        raise forbidden("只有 runtime 可 dispatch Workflow step")
    if instance.project_id not in principal_projects(session, actor.id):
        raise not_found("找不到 workflow instance")
    task = session.get(Task, step_run.task_id)
    if task is None or task.project_id != instance.project_id or task.status != "ready" or not _dependencies_done(session, task.id):
        raise conflict("workflow_step_not_ready", "Workflow step 尚未滿足 dispatch 條件")
    agent = agent_for_task(session, actor, agent_id, instance.project_id)
    if agent.runtime != "pi" or agent.role != "worker" or agent.status != "available":
        raise conflict("agent_unavailable", "Workflow Agent 目前不可執行任務")
    result = _create_dispatch(session, actor, task, agent)
    step_run.run_id = result["id"]
    return result


def claim_outbox(session: Session, actor: Principal, worker_id: str, limit: int) -> list[dict]:
    if actor.kind != "runtime" and actor.role != "admin":
        raise forbidden("只有 runtime 或 admin 可領取 outbox")
    now = now_utc()
    control_blocked = select(RunMirror.id).where(
        RunMirror.id == OutboxEvent.id,
        RunMirror.desired_action.in_(["pause", "stop"]),
    )
    stmt = select(OutboxEvent).where(
        or_(
            and_(OutboxEvent.status == "pending", ~control_blocked.exists()),
            and_(OutboxEvent.status == "claimed", OutboxEvent.claim_expires_at <= now),
        )
    )
    if actor.kind == "runtime":
        project_ids = principal_projects(session, actor.id)
        stmt = stmt.where(OutboxEvent.project_id.in_(project_ids))
    if session.bind and session.bind.dialect.name != "sqlite":
        stmt = stmt.with_for_update(skip_locked=True)
    candidates = list(session.scalars(stmt.order_by(OutboxEvent.created_at).limit(limit)))
    result = []
    for event in candidates:
        token = new_secret("delivery")
        eligible = or_(
            OutboxEvent.status == "pending",
            and_(OutboxEvent.status == "claimed", OutboxEvent.claim_expires_at <= now),
        )
        changed = session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event.id, eligible)
            .execution_options(synchronize_session=False)
            .values(
                status="claimed",
                worker_id=worker_id,
                delivery_token_hash=hash_secret(token),
                claim_expires_at=now + timedelta(seconds=60),
                attempts=OutboxEvent.attempts + 1,
                updated_at=now,
            )
        )
        if changed.rowcount == 1:
            session.refresh(event)
            result.append(outbox_json(event, token))
    return result


def acknowledge_outbox(session: Session, actor: Principal, event_id: str, value: dict) -> dict:
    event = session.get(OutboxEvent, event_id)
    if event is None:
        raise not_found("找不到 outbox event")
    if actor.kind != "runtime" and actor.role != "admin":
        raise forbidden()
    if actor.kind == "runtime" and event.project_id not in principal_projects(session, actor.id):
        raise not_found()
    if event.status != "claimed" or event.worker_id != value["worker_id"]:
        raise conflict("delivery_lease_invalid", "outbox ownership 已變更")
    if event.claim_expires_at and _utc(event.claim_expires_at) <= now_utc():
        raise conflict("delivery_lease_expired", "outbox claim 已過期")
    if not event.delivery_token_hash or not hmac.compare_digest(event.delivery_token_hash, hash_secret(value["delivery_token"])):
        raise conflict("delivery_token_invalid", "delivery token 無效")
    event.status = value["status"]
    event.error = value.get("error") if value["status"] == "failed" else None
    event.delivery_token_hash = None
    event.claim_expires_at = None
    event.updated_at = now_utc()
    run = session.get(RunMirror, event.id)
    if run is not None and run.desired_action == "stop":
        run.status = "aborted"
        run.desired_action = None
        run.finished_at = now_utc()
        run.error = None
        run.updated_at = now_utc()
        from .runs import _append_event, _clean_text

        _append_event(session, run, "status", {"to": "aborted", "reason": "stop_acknowledged"})
    elif run is not None and value["status"] == "failed" and run.status not in {"done", "failed", "aborted"}:
        run.status = "failed"
        run.error = _clean_text(value.get("error") or "Runtime delivery failed.")
        run.finished_at = now_utc()
        run.updated_at = now_utc()
        from .runs import _append_event, _clean_text

        _append_event(session, run, "status", {"to": "failed", "reason": run.error})
    if run is not None:
        agent = session.get(Agent, event.agent_id)
        still_running = session.scalar(
            select(Execution.id).where(Execution.agent_id == event.agent_id, Execution.status == "running").limit(1)
        )
        if agent and not still_running:
            agent.status = "available"
    revoke_runtime_credential(session, event.id, event.agent_id)
    add_audit(session, actor, f"outbox.{event.status}", "outbox", event.id, event.project_id, {"attempts": event.attempts, "task_id": event.task_id})
    session.flush()
    return outbox_json(event)


def list_events(session: Session, actor: Principal, project_id: str | None, task_id: str | None) -> list[dict]:
    project_ids = principal_projects(session, actor.id)
    stmt = select(AuditEvent).where(
        or_(AuditEvent.project_id.in_(project_ids), and_(AuditEvent.project_id.is_(None), AuditEvent.actor_id == actor.id))
    )
    if project_id:
        require_project(session, actor, project_id)
        stmt = stmt.where(AuditEvent.project_id == project_id)
    if task_id:
        task = task_for_actor(session, actor, task_id)
        stmt = stmt.where(AuditEvent.project_id == task.project_id, AuditEvent.entity_id == task.id)
    stmt = stmt.order_by(AuditEvent.created_at.desc()).limit(200)
    return [event_json(item) for item in session.scalars(stmt)]


def overview(session: Session, actor: Principal, project_id: str | None) -> dict:
    if project_id:
        require_project(session, actor, project_id)
        project_ids = [project_id]
    else:
        project_ids = principal_projects(session, actor.id)
    counts = {key: 0 for key in ("total", "ready", "in_progress", "blocked", "in_review", "done")}
    task_rows = list(session.scalars(select(Task).where(Task.project_id.in_(project_ids)))) if project_ids else []
    counts["total"] = len(task_rows)
    for task in task_rows:
        if task.status in counts:
            counts[task.status] += 1
    agent_rows = list(
        session.scalars(
            select(Agent)
            .join(Principal, Principal.id == Agent.principal_id)
            .join(ProjectMembership, ProjectMembership.principal_id == Principal.id)
            .where(ProjectMembership.project_id.in_(project_ids))
            .distinct()
        )
    ) if project_ids else []
    all_executions = session.scalars(
        select(Execution).join(Task, Task.id == Execution.task_id).where(Task.project_id.in_(project_ids))
    ) if project_ids else []
    budget = session.scalar(select(func.sum(Project.budget_usd)).where(Project.id.in_(project_ids))) or 0
    audit = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.project_id.in_(project_ids))
        .order_by(AuditEvent.created_at.desc())
        .limit(20)
    ) if project_ids else []
    return {
        "counts": counts,
        "agents": {
            "total": len(agent_rows),
            "available": sum(1 for item in agent_rows if item.status == "available"),
            "busy": sum(1 for item in agent_rows if item.status == "busy"),
        },
        "cost_usd": round(sum(item.cost_usd for item in all_executions), 6),
        "budget_usd": float(budget),
        "activity": [event_json(item) for item in audit],
    }
