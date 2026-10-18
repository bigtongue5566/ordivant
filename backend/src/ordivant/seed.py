from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import select

from .agent_presets import ensure_builtin_agent_templates
from .config import data_dir
from .db import Base, SessionLocal, engine
from .models import (
    Agent,
    Artifact,
    AuditEvent,
    AuthToken,
    Execution,
    Message,
    Organization,
    Principal,
    Project,
    ProjectMembership,
    Task,
    TaskDependency,
    Team,
)
from .security import hash_secret, issue_token, new_id, new_secret, now_utc
from .service import _json


def _ensure_membership(session, project_id: str, principal_id: str) -> None:
    exists = session.scalar(
        select(ProjectMembership).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.principal_id == principal_id,
        )
    )
    if exists is None:
        session.add(ProjectMembership(id=new_id(), project_id=project_id, principal_id=principal_id))


def _token_for(session, principal_id: str, existing_token: str | None) -> str:
    if existing_token:
        stored = session.scalar(select(AuthToken).where(AuthToken.token_hash == hash_secret(existing_token)))
        if stored and stored.principal_id == principal_id and stored.revoked_at is None:
            return existing_token
    return issue_token(session, principal_id)


def _ensure_task(session, project: Project, key: str, fields: dict) -> Task:
    task = session.scalar(select(Task).where(Task.key == key))
    if task:
        if task.project_id != project.id:
            raise RuntimeError(f"seed task key {key} belongs to another project")
        return task
    now = now_utc()
    task = Task(
        id=new_id(),
        key=key,
        project_id=project.id,
        title=fields["title"],
        description=fields.get("description", ""),
        goal=fields.get("goal", ""),
        inputs="",
        scope=fields.get("scope", ""),
        constraints="",
        acceptance_criteria_json=_json(fields.get("acceptance_criteria", [])),
        priority=fields.get("priority", "medium"),
        status=fields["status"],
        assignee_id=fields.get("assignee_id"),
        reviewer_id=fields.get("reviewer_id"),
        parent_task_id=None,
        labels_json=_json(["demo", "seed"]),
        blocked_reason=fields.get("blocked_reason"),
        progress=fields.get("progress", 0),
        handoff=None,
        budget_usd=fields.get("budget_usd", 10),
        created_at=now,
        updated_at=now,
    )
    session.add(task)
    session.flush()
    return task


def _ensure_execution(
    session,
    task: Task,
    agent: Agent,
    principal: Principal,
    status: str,
    *,
    summary: str,
    progress: int,
    finished: bool,
    submitted_by: str | None = None,
) -> Execution:
    execution = session.scalar(
        select(Execution).where(Execution.task_id == task.id).order_by(Execution.started_at.desc())
    )
    if execution:
        return execution
    now = now_utc()
    execution = Execution(
        id=new_id(),
        task_id=task.id,
        agent_id=agent.id,
        claimed_by_principal_id=principal.id,
        submitted_by_principal_id=submitted_by,
        status=status,
        lease_token_hash=hash_secret(new_secret("seed-lease")) if status == "running" else None,
        lease_expires_at=now - timedelta(seconds=1) if status == "running" else now,
        started_at=now - timedelta(minutes=5),
        finished_at=now if finished else None,
        progress=progress,
        summary=summary,
        cost_usd=0,
        cost_source="self_reported",
    )
    session.add(execution)
    session.flush()
    return execution


def _ensure_artifact(session, task: Task, execution: Execution, title: str, content: str) -> None:
    if session.scalar(select(Artifact).where(Artifact.task_id == task.id, Artifact.title == title)):
        return
    session.add(
        Artifact(
            id=new_id(),
            task_id=task.id,
            execution_id=execution.id,
            kind="summary",
            title=title,
            uri=None,
            content=content,
            created_at=now_utc(),
        )
    )


def seed() -> dict:
    Base.metadata.create_all(bind=engine)
    output_dir = data_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    bootstrap_path = output_dir / "bootstrap.json"
    previous = {}
    if bootstrap_path.exists():
        try:
            previous = json.loads(bootstrap_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}

    with SessionLocal() as session:
        organization = session.scalar(select(Organization).where(Organization.name == "Ordivant Demo Organization"))
        if organization is None:
            organization = Organization(id=new_id(), name="Ordivant Demo Organization", created_at=now_utc())
            session.add(organization)
            session.flush()
            ensure_builtin_agent_templates(session, organization.id)

        teams: dict[str, Team] = {}
        for name in ("Engineering", "Operations"):
            team = session.scalar(select(Team).where(Team.organization_id == organization.id, Team.name == name))
            if team is None:
                team = Team(id=new_id(), organization_id=organization.id, name=name, created_at=now_utc())
                session.add(team)
                session.flush()
            teams[name] = team

        manager = session.scalar(
            select(Principal).where(
                Principal.organization_id == organization.id,
                Principal.kind == "human",
                Principal.name == "manager",
            )
        )
        if manager is None:
            manager = Principal(
                id=new_id(),
                name="manager",
                kind="human",
                role="manager",
                organization_id=organization.id,
                team_id=teams["Engineering"].id,
                active=True,
            )
            session.add(manager)
            session.flush()

        runtime_principal = session.scalar(
            select(Principal).where(
                Principal.organization_id == organization.id,
                Principal.kind == "runtime",
                Principal.name == "runtime",
            )
        )
        if runtime_principal is None:
            runtime_principal = Principal(
                id=new_id(),
                name="runtime",
                kind="runtime",
                role="manager",
                organization_id=organization.id,
                team_id=teams["Operations"].id,
                active=True,
            )
            session.add(runtime_principal)
            session.flush()

        project = session.scalar(select(Project).where(Project.organization_id == organization.id, Project.key == "ORD"))
        if project is None:
            project = Project(
                id=new_id(),
                key="ORD",
                name="Ordivant 示範 Agent Workspace (DEMO)",
                description="DEMO / 示範資料：供本機操作與驗收使用，不代表正式部署資料。",
                organization_id=organization.id,
                team_id=teams["Engineering"].id,
                budget_usd=250,
                created_at=now_utc(),
            )
            session.add(project)
            session.flush()

        isolated_project = session.scalar(
            select(Project).where(Project.organization_id == organization.id, Project.key == "ISO")
        )
        if isolated_project is None:
            isolated_project = Project(
                id=new_id(),
                key="ISO",
                name="Scoped Access Demonstration",
                description="Second project used to demonstrate project membership isolation.",
                organization_id=organization.id,
                team_id=teams["Operations"].id,
                budget_usd=50,
                created_at=now_utc(),
            )
            session.add(isolated_project)
            session.flush()
        _ensure_membership(session, project.id, manager.id)
        _ensure_membership(session, isolated_project.id, manager.id)
        _ensure_membership(session, project.id, runtime_principal.id)

        agent_specs = {
            "planner": ("worker", "Engineering", [project.id], ["planning", "decomposition"], "pi", "demo"),
            "builder": ("worker", "Engineering", [project.id], ["implementation", "testing"], "pi", "demo"),
            "analyst": ("worker", "Operations", [project.id, isolated_project.id], ["research", "analysis"], "external", None),
            "reviewer": ("reviewer", "Operations", [project.id], ["acceptance_review"], "external", None),
        }
        agents: dict[str, Agent] = {}
        principals: dict[str, Principal] = {}
        for name, (role, team_name, project_ids, capabilities, runtime, model) in agent_specs.items():
            principal = session.scalar(
                select(Principal).where(
                    Principal.organization_id == organization.id,
                    Principal.kind == "agent",
                    Principal.name == name,
                )
            )
            if principal is None:
                principal = Principal(
                    id=new_id(),
                    name=name,
                    kind="agent",
                    role=role,
                    organization_id=organization.id,
                    team_id=teams[team_name].id,
                    active=True,
                )
                session.add(principal)
                session.flush()
            agent = session.scalar(select(Agent).where(Agent.principal_id == principal.id))
            if agent is None:
                agent = Agent(
                    id=new_id(),
                    principal_id=principal.id,
                    name=name,
                    role=role,
                    team_id=teams[team_name].id,
                    capabilities_json=_json(capabilities),
                    status="available",
                    runtime=runtime,
                    model=model,
                    created_at=now_utc(),
                )
                session.add(agent)
                session.flush()
            for project_id in project_ids:
                _ensure_membership(session, project_id, principal.id)
            agents[name] = agent
            principals[name] = principal

        now = now_utc()
        done_task = _ensure_task(
            session,
            project,
            "ORD-001",
            {
                "title": "建立 agent workspace 基礎規格",
                "description": "整理角色、專案範圍與 API 邊界。",
                "goal": "形成可供實作的 workspace 規格。",
                "acceptance_criteria": ["專案角色已列明", "核心 API 已有契約"],
                "status": "done",
                "assignee_id": agents["planner"].id,
                "reviewer_id": agents["reviewer"].id,
                "progress": 100,
            },
        )
        running_task = _ensure_task(
            session,
            project,
            "ORD-002",
            {
                "title": "檢查 local pilot 的資料隔離",
                "description": "示範執行中的工作及逾期 lease 回復。",
                "goal": "確認每個 agent 只看到授權專案。",
                "acceptance_criteria": ["第二專案無跨界讀取", "逾期執行能重新領取"],
                "status": "in_progress",
                "assignee_id": agents["analyst"].id,
                "reviewer_id": agents["reviewer"].id,
                "progress": 40,
            },
        )
        review_task = _ensure_task(
            session,
            project,
            "ORD-003",
            {
                "title": "審查操作手冊初稿",
                "description": "準備一份可由 reviewer 獨立檢查的證據。",
                "goal": "驗證提交與審核分離。",
                "acceptance_criteria": ["提交包含證據", "reviewer 與提交者不同"],
                "status": "in_review",
                "assignee_id": agents["planner"].id,
                "reviewer_id": agents["reviewer"].id,
                "progress": 100,
            },
        )
        ready_task = _ensure_task(
            session,
            project,
            "ORD-004",
            {
                "title": "實作協作收件匣與回覆",
                "description": "展示 help request 與回覆的往返流程。",
                "goal": "讓 agent 在任務中向同專案成員求助。",
                "acceptance_criteria": ["收件者可讀取 inbox", "reply 完成原問題"],
                "status": "ready",
                "assignee_id": agents["builder"].id,
                "reviewer_id": agents["reviewer"].id,
            },
        )
        blocked_task = _ensure_task(
            session,
            project,
            "ORD-005",
            {
                "title": "整理協作流程驗收紀錄",
                "description": "等待收件匣與回覆流程完成。",
                "goal": "建立可重現的協作驗收證據。",
                "acceptance_criteria": ["前置協作工作完成", "提供驗收摘要"],
                "status": "blocked",
                "blocked_reason": "dependencies_pending",
                "assignee_id": agents["builder"].id,
                "reviewer_id": agents["reviewer"].id,
            },
        )
        for task_id, dependency_id in ((ready_task.id, done_task.id), (blocked_task.id, ready_task.id)):
            existing = session.scalar(
                select(TaskDependency).where(
                    TaskDependency.task_id == task_id,
                    TaskDependency.dependency_id == dependency_id,
                )
            )
            if existing is None:
                session.add(TaskDependency(id=new_id(), task_id=task_id, dependency_id=dependency_id))

        done_execution = _ensure_execution(
            session,
            done_task,
            agents["planner"],
            principals["planner"],
            "accepted",
            summary="規格與 API 邊界已經過 reviewer 接受。",
            progress=100,
            finished=True,
        )
        _ensure_artifact(session, done_task, done_execution, "已接受的 workspace 規格", "Demo evidence: project scope and API boundaries were reviewed.")
        _ensure_execution(
            session,
            running_task,
            agents["analyst"],
            principals["analyst"],
            "running",
            summary="正在檢查專案成員與隔離範圍。此示範 lease 已逾期，可由 authorized agent 重新領取。",
            progress=40,
            finished=False,
        )
        review_execution = _ensure_execution(
            session,
            review_task,
            agents["planner"],
            principals["planner"],
            "submitted",
            summary="操作手冊草稿已附上可檢查的內容證據。",
            progress=100,
            finished=True,
            submitted_by=principals["planner"].id,
        )
        _ensure_artifact(session, review_task, review_execution, "操作手冊初稿", "Demo evidence: setup, run, and scoped credential workflow.")
        for name, task in (("ORD-001", done_task), ("ORD-002", running_task), ("ORD-003", review_task), ("ORD-004", ready_task), ("ORD-005", blocked_task)):
            if session.scalar(
                select(AuditEvent).where(AuditEvent.project_id == project.id, AuditEvent.entity_id == task.id, AuditEvent.action == "seed.demo")
            ) is None:
                session.add(
                    AuditEvent(
                        id=new_id(),
                        project_id=project.id,
                        actor_id=manager.id,
                        action="seed.demo",
                        entity_type="task",
                        entity_id=task.id,
                        data_json=_json({"seed_key": name, "label": "DEMO"}),
                        created_at=now,
                    )
                )

        help_message = session.scalar(
            select(Message).where(Message.project_id == project.id, Message.task_id == ready_task.id, Message.kind == "help_request")
        )
        if help_message is None:
            help_message = Message(
                id=new_id(),
                project_id=project.id,
                task_id=ready_task.id,
                sender_id=principals["planner"].id,
                recipient_id=principals["analyst"].id,
                kind="help_request",
                body="請協助確認收件匣回覆需要哪些跨 actor 權限檢查。",
                reply_to_id=None,
                status="completed",
                created_at=now,
            )
            session.add(help_message)
            session.flush()
            session.add(
                Message(
                    id=new_id(),
                    project_id=project.id,
                    task_id=ready_task.id,
                    sender_id=principals["analyst"].id,
                    recipient_id=principals["planner"].id,
                    kind="reply",
                    body="已確認：寄件者與收件者都必須具有同一專案授權。",
                    reply_to_id=help_message.id,
                    status="delivered",
                    created_at=now + timedelta(seconds=1),
                )
            )
        if session.scalar(select(Message).where(Message.project_id == project.id, Message.kind == "decision")) is None:
            session.add(
                Message(
                    id=new_id(),
                    project_id=project.id,
                    task_id=ready_task.id,
                    sender_id=manager.id,
                    recipient_id=None,
                    kind="decision",
                    body="DEMO decision: task results require evidence and an independent reviewer.",
                    reply_to_id=None,
                    status="delivered",
                    created_at=now,
                )
            )

        bootstrap = {
            "manager_token": _token_for(session, manager.id, previous.get("manager_token")),
            "runtime_token": _token_for(session, runtime_principal.id, previous.get("runtime_token")),
            "agents": {},
            "project_id": project.id,
            "isolated_project_id": isolated_project.id,
        }
        previous_agents = previous.get("agents", {})
        for name, agent in agents.items():
            bootstrap["agents"][name] = {
                "id": agent.id,
                "principal_id": agent.principal_id,
                "token": _token_for(session, agent.principal_id, previous_agents.get(name, {}).get("token")),
            }
        session.commit()

    temporary = bootstrap_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(bootstrap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(bootstrap_path)
    return {"path": str(bootstrap_path), "project_id": bootstrap["project_id"], "isolated_project_id": bootstrap["isolated_project_id"]}


def main() -> None:
    result = seed()
    print(f"Ordivant demo seed ready: {result['path']}")
    print(f"Project IDs: {result['project_id']}, {result['isolated_project_id']}")


if __name__ == "__main__":
    main()
