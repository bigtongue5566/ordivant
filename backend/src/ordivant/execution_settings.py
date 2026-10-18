from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .agent_presets import builtin_key_for_template
from .errors import DomainError, bad_request, conflict, not_found
from .model_settings import validate_model_selection
from .models import (
    Agent,
    AgentExecutionSetting,
    AgentTemplate,
    Principal,
    SandboxProfile,
    ToolConnection,
)
from .security import new_id, now_utc, principal_projects

DEFAULT_EXECUTION_CONFIG = {
    "instructions": "",
    "tool_connection_ids": [],
    "sandbox_profile_id": None,
    "limits": {"max_turns": 20, "timeout_seconds": 600},
}


def _loads(value: str | None, default):
    try:
        return json.loads(value) if value is not None else default
    except (TypeError, json.JSONDecodeError):
        return default


def _canonical_execution_config(value: dict | None) -> dict:
    config = {**DEFAULT_EXECUTION_CONFIG, **(value or {})}
    config["limits"] = {**DEFAULT_EXECUTION_CONFIG["limits"], **(config.get("limits") or {})}
    config["tool_connection_ids"] = list(dict.fromkeys(config.get("tool_connection_ids") or []))
    return config


def _definition(value: dict) -> dict:
    definition = dict(value)
    definition["capabilities"] = list(dict.fromkeys(definition.get("capabilities") or []))
    definition["tool_connection_ids"] = list(dict.fromkeys(definition.get("tool_connection_ids") or []))
    definition["limits"] = {**DEFAULT_EXECUTION_CONFIG["limits"], **(definition.get("limits") or {})}
    if "model_selection" in definition and "model_config" not in definition:
        definition["model_config"] = definition.pop("model_selection")
    return definition


def _validate_bindings(session: Session, project_ids: set[str], tool_ids: list[str], sandbox_id: str | None) -> None:
    from .tool_connections import validate_connection_for_projects

    for connection_id in tool_ids:
        validate_connection_for_projects(session, connection_id, project_ids, require_enabled=True)
    if sandbox_id:
        profile = session.get(SandboxProfile, sandbox_id)
        if profile is None or profile.project_id not in project_ids or not profile.enabled:
            raise bad_request("sandbox_profile_scope", "Sandbox profile 不屬於可用的 Agent project scope")


def agent_execution_settings(session: Session, agent: Agent) -> tuple[dict, str | None]:
    row = session.get(AgentExecutionSetting, agent.id)
    if row is None:
        return _canonical_execution_config(None), None
    return _canonical_execution_config(_loads(row.config_json, {})), row.template_id


def set_agent_execution_settings(
    session: Session,
    agent: Agent,
    project_ids: list[str],
    config: dict | None,
    template_id: str | None,
) -> None:
    canonical = _canonical_execution_config(config)
    _validate_bindings(session, set(project_ids), canonical["tool_connection_ids"], canonical["sandbox_profile_id"])
    row = session.get(AgentExecutionSetting, agent.id)
    if row is None:
        row = AgentExecutionSetting(agent_id=agent.id, config_json="{}", template_id=None, updated_at=now_utc())
        session.add(row)
    row.config_json = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"))
    row.template_id = template_id
    row.updated_at = now_utc()


def validate_agent_execution_config(
    session: Session,
    agent: Agent,
    project_id: str,
) -> tuple[dict, str | None]:
    config, template_id = agent_execution_settings(session, agent)
    project_ids = set(principal_projects(session, agent.principal_id))
    if project_id not in project_ids:
        raise DomainError(404, "not_found", "找不到 Agent project scope")
    # Validate every persisted binding against the Agent's full current scope first. Then
    # only dispatch bindings owned by the executing project; an Agent may span projects,
    # but a run must never inherit another project's tool or sandbox configuration.
    _validate_bindings(session, project_ids, config["tool_connection_ids"], config["sandbox_profile_id"])
    config["tool_connection_ids"] = [
        connection_id
        for connection_id in config["tool_connection_ids"]
        if session.get(ToolConnection, connection_id).project_id == project_id
    ]
    profile_id = config.get("sandbox_profile_id")
    profile = session.get(SandboxProfile, profile_id) if profile_id else None
    if profile is not None and profile.project_id != project_id:
        config["sandbox_profile_id"] = None
    return config, template_id


def _template_definition(session: Session, actor: Principal, value: dict) -> dict:
    definition = _definition(value)
    project_ids = set(principal_projects(session, actor.id))
    _validate_bindings(session, project_ids, definition["tool_connection_ids"], definition["sandbox_profile_id"])
    if definition.get("model_config") is not None:
        definition["model_config"] = validate_model_selection(session, actor.organization_id, definition["model_config"])
    return definition


def template_json(template: AgentTemplate) -> dict:
    return {
        "id": template.id,
        "key": template.key,
        "version": template.version,
        "name": template.name,
        "description": template.description,
        "builtin_key": builtin_key_for_template(template),
        "definition": _loads(template.definition_json, {}),
        "created_at": template.created_at.isoformat().replace("+00:00", "Z"),
    }


def _template_references_visible(session: Session, actor: Principal, template: AgentTemplate) -> bool:
    definition = _loads(template.definition_json, {})
    try:
        _validate_bindings(
            session,
            set(principal_projects(session, actor.id)),
            definition.get("tool_connection_ids", []),
            definition.get("sandbox_profile_id"),
        )
    except DomainError:
        return False
    return True


def list_agent_templates(session: Session, actor: Principal) -> list[dict]:
    rows = session.scalars(
        select(AgentTemplate)
        .where(AgentTemplate.organization_id == actor.organization_id)
        .order_by(AgentTemplate.key, AgentTemplate.version.desc())
    )
    return [template_json(row) for row in rows if _template_references_visible(session, actor, row)]


def get_agent_template(session: Session, actor: Principal, template_id: str) -> AgentTemplate:
    row = session.get(AgentTemplate, template_id)
    if row is None or row.organization_id != actor.organization_id or not _template_references_visible(session, actor, row):
        raise not_found("找不到 Agent template")
    return row


def create_agent_template(session: Session, actor: Principal, value: dict) -> dict:
    from .service import require_role

    require_role(actor, {"admin", "manager"})
    existing = session.scalar(
        select(AgentTemplate.id).where(
            AgentTemplate.organization_id == actor.organization_id,
            AgentTemplate.key == value["key"],
        )
    )
    if existing:
        raise conflict("agent_template_exists", "Agent template key 已存在")
    definition = _template_definition(session, actor, value["definition"])
    row = AgentTemplate(
        id=new_id(),
        organization_id=actor.organization_id,
        key=value["key"],
        version=1,
        name=value["name"],
        description=value.get("description", ""),
        definition_json=json.dumps(definition, ensure_ascii=False, separators=(",", ":")),
        created_at=now_utc(),
    )
    session.add(row)
    session.flush()
    return template_json(row)


def create_agent_template_version(session: Session, actor: Principal, template_id: str, value: dict) -> dict:
    from .service import require_role

    require_role(actor, {"admin", "manager"})
    current = get_agent_template(session, actor, template_id)
    definition = _template_definition(session, actor, value["definition"])
    session.scalar(
        select(AgentTemplate.id)
        .where(AgentTemplate.organization_id == actor.organization_id, AgentTemplate.key == current.key)
        .with_for_update()
    )
    version = session.scalar(
        select(func.max(AgentTemplate.version)).where(
            AgentTemplate.organization_id == actor.organization_id,
            AgentTemplate.key == current.key,
        )
    ) or 0
    row = AgentTemplate(
        id=new_id(),
        organization_id=actor.organization_id,
        key=current.key,
        version=version + 1,
        name=value["name"],
        description=value.get("description", ""),
        definition_json=json.dumps(definition, ensure_ascii=False, separators=(",", ":")),
        created_at=now_utc(),
    )
    session.add(row)
    session.flush()
    return template_json(row)


def template_definition_for_agent(session: Session, actor: Principal, template_id: str) -> dict:
    return _loads(get_agent_template(session, actor, template_id).definition_json, {})


def dispatch_execution_snapshot(session: Session, agent: Agent, project_id: str) -> tuple[dict, str | None, dict | None]:
    config, template_id = validate_agent_execution_config(session, agent, project_id)
    sandbox_profile = None
    if config["sandbox_profile_id"]:
        profile = session.get(SandboxProfile, config["sandbox_profile_id"])
        sandbox_profile = {
            "id": profile.id,
            "project_id": profile.project_id,
            "name": profile.name,
            "limits": _loads(profile.limits_json, {}),
        }
    return config, template_id, sandbox_profile
