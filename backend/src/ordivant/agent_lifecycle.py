"""Retire Agents without deleting collaboration or execution evidence."""
from __future__ import annotations

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from . import service
from .db import Base
from .errors import conflict, not_found
from .models import (
    Agent, AuthToken, Execution, Principal, ProjectMembership, ProjectRule,
    OutboxEvent, RunMirror, Task, Team, WorkflowDefinition, WorkflowSchedule,
)


def managed_agent(session: Session, actor: Principal, agent_id: str) -> tuple[Agent, Principal, list[str]]:
    service.require_role(actor, service.ACTIVE_ROLES)
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise not_found("找不到 Agent")
    agent = service._lock_agent(session, agent)
    if agent.team_id:
        team = session.get(Team, agent.team_id)
        if team is None or team.organization_id != actor.organization_id:
            raise not_found("找不到 Agent")
    principal = session.get(Principal, agent.principal_id)
    if principal is None or principal.organization_id != actor.organization_id:
        raise not_found("找不到 Agent")
    project_ids = service.principal_projects(session, principal.id)
    # Retirement affects the identity across ALL its projects, not just the current view.
    for project_id in project_ids:
        service.require_project(session, actor, project_id)
    return agent, principal, project_ids


def _references(value, ids: set[str]) -> bool:
    if isinstance(value, list):
        return any(_references(item, ids) for item in value)
    if isinstance(value, dict):
        return any(
            (key in {"agent_id", "reviewer_id", "assignee_id", "assignee_principal_id"} and isinstance(item, str) and item in ids)
            or _references(item, ids)
            for key, item in value.items()
        )
    return False


def _automation_references(session: Session, agent: Agent, *, enabled_only: bool):
    ids = {agent.id, agent.principal_id}
    workflows = select(WorkflowDefinition)
    if enabled_only:
        workflows = workflows.join(WorkflowSchedule).where(WorkflowSchedule.enabled.is_(True))
    for workflow in session.scalars(workflows):
        if _references(service._loads(workflow.steps_json, []), ids):
            yield workflow
    rules = select(ProjectRule)
    if enabled_only:
        rules = rules.where(ProjectRule.enabled.is_(True))
    for rule in session.scalars(rules):
        if _references(service._loads(rule.parameters_json, {}), ids):
            yield rule


def _require_idle(session: Session, agent: Agent) -> None:
    ids = {agent.id, agent.principal_id}
    unfinished = select(Task.id).where(
        Task.status.not_in({"done", "cancelled"}),
        or_(Task.assignee_id == agent.id, Task.reviewer_id == agent.id,
            Task.assignee_principal_id.in_(ids), Task.reviewer_principal_id.in_(ids)),
    )
    running = select(Execution.id).where(Execution.agent_id == agent.id, Execution.status == "running")
    queued = select(OutboxEvent.id).where(OutboxEvent.agent_id == agent.id, OutboxEvent.status.in_({"pending", "claimed"}))
    runs = select(RunMirror.id).where(RunMirror.agent_id == agent.id, RunMirror.status.not_in({"done", "failed", "aborted"}))
    if any(session.scalar(query.limit(1)) for query in (unfinished, running, queued, runs)):
        raise conflict("agent_has_active_work", "Agent 仍有未結束的任務或執行，請先停止執行並完成交接。")
    if next(_automation_references(session, agent, enabled_only=True), None) is not None:
        raise conflict("agent_in_active_automation", "Agent 仍被啟用中的規則或排程使用，請先停用或改派。")


def _has_history(session: Session, agent: Agent) -> bool:
    # These are owned configuration/credentials, not business history.
    owned = {"agents", "auth_tokens", "project_memberships", "agent_model_configs", "agent_execution_settings"}
    for table in Base.metadata.sorted_tables:
        if table.name in owned:
            continue
        references = []
        for column in table.columns:
            for key in column.foreign_keys:
                if key.target_fullname == "agents.id":
                    references.append(column == agent.id)
                elif key.target_fullname == "principals.id":
                    references.append(column == agent.principal_id)
            # Shared collaboration records intentionally use product-local identity ids
            # without FKs, but must still prevent removal of their author/recipient.
            if table.name.startswith("collaboration_") and column.name in {"actor_id", "principal_id"}:
                references.append(column == agent.principal_id)
        if references and session.scalar(select(1).select_from(table).where(or_(*references)).limit(1)):
            return True
    return next(_automation_references(session, agent, enabled_only=False), None) is not None


def archive_agent(session: Session, actor: Principal, agent_id: str) -> dict:
    agent, principal, project_ids = managed_agent(session, actor, agent_id)
    if agent.status != "archived":
        _require_idle(session, agent)
        agent.status = "archived"
        principal.active = False
        session.execute(update(AuthToken).where(
            AuthToken.principal_id == principal.id, AuthToken.revoked_at.is_(None),
        ).values(revoked_at=service.now_utc()))
        for project_id in project_ids:
            service.add_audit(session, actor, "agent.archived", "agent", agent.id, project_id, {"name": agent.name})
        session.flush()
    return service.agent_json(session, agent)


def delete_agent(session: Session, actor: Principal, agent_id: str) -> dict:
    agent, principal, project_ids = managed_agent(session, actor, agent_id)
    _require_idle(session, agent)
    if _has_history(session, agent):
        raise conflict("agent_has_history", "Agent 已有使用紀錄或設定引用，無法永久刪除；請改用封存。")
    result = {"id": agent.id, "deleted": True, "organization_id": principal.organization_id, "project_ids": project_ids}
    for project_id in project_ids:
        service.add_audit(session, actor, "agent.deleted", "agent", agent.id, project_id, {"name": agent.name})
    session.execute(delete(AuthToken).where(AuthToken.principal_id == principal.id))
    session.execute(delete(ProjectMembership).where(ProjectMembership.principal_id == principal.id))
    session.delete(agent)  # Owned model/execution settings cascade in the database.
    session.flush()
    session.delete(principal)
    session.flush()
    return result
