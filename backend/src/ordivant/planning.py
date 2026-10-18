from __future__ import annotations

import csv
import io
import json
import math
import statistics
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .errors import bad_request, conflict, forbidden, not_found
from .models import (
    Agent,
    AuditEvent,
    Execution,
    Principal,
    ProjectCapacity,
    Project,
    ProjectField,
    ProjectIntakeForm,
    ProjectMilestone,
    ProjectMembership,
    ProjectRule,
    ProjectRuleEvent,
    ProjectSprint,
    ProjectStage,
    SavedQuery,
    Task,
    TaskWorklog,
)
from .security import new_id, now_utc

WORK_TYPES = {"task", "story", "bug", "epic"}
TASK_STATES = {"backlog", "ready", "in_progress", "blocked", "in_review", "done", "cancelled"}
PLANNING_FIELDS = {
    "work_type", "epic_id", "due_at", "start_at", "sprint_id", "milestone_id",
    "estimate_points", "rank", "stage_id", "custom_fields",
}
MAX_IMPORT_ROWS = 1000
MAX_CUSTOM_FIELDS = 100
MAX_FIELD_VALUE_LENGTH = 4000


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_manager(session: Session, actor: Principal, project_id: str) -> Project:
    from . import service

    service.require_role(actor, service.ACTIVE_ROLES)
    project = service.require_project(session, actor, project_id)
    # Serialize project configuration/quota checks across different authorized managers.
    session.refresh(project, with_for_update=True)
    return project


def _audit(session: Session, actor: Principal, action: str, entity: str, entity_id: str, project_id: str, data: dict | None = None) -> AuditEvent:
    from . import service

    return service.add_audit(session, actor, action, entity, entity_id, project_id, data)


def _record_json(item: Any, fields: dict[str, Any]) -> dict:
    return {"id": item.id, **fields}


def sprint_json(item: ProjectSprint) -> dict:
    return _record_json(item, {
        "project_id": item.project_id, "name": item.name, "goal": item.goal,
        "start_at": _iso(item.start_at), "end_at": _iso(item.end_at), "status": item.status,
    })


def milestone_json(item: ProjectMilestone) -> dict:
    return _record_json(item, {
        "project_id": item.project_id, "name": item.name, "due_at": _iso(item.due_at),
        "description": item.description, "status": item.status,
    })


def field_json(item: ProjectField) -> dict:
    return _record_json(item, {
        "project_id": item.project_id, "key": item.key, "name": item.name, "kind": item.kind,
        "required": item.required, "options": _loads(item.options_json, []), "active": item.active,
    })


def stage_json(item: ProjectStage) -> dict:
    return _record_json(item, {
        "project_id": item.project_id, "name": item.name, "category": item.category,
        "rank": item.rank, "active": item.active,
    })


def rule_json(item: ProjectRule) -> dict:
    return _record_json(item, {
        "project_id": item.project_id, "name": item.name, "event": item.event,
        "conditions": _loads(item.conditions_json, {}), "action": item.action,
        "parameters": _loads(item.parameters_json, {}), "enabled": item.enabled,
    })


def form_json(item: ProjectIntakeForm) -> dict:
    return _record_json(item, {
        "project_id": item.project_id, "name": item.name, "description": item.description,
        "work_type": item.work_type, "fields": _loads(item.fields_json, []), "active": item.active,
    })


def saved_query_json(item: SavedQuery) -> dict:
    return _record_json(item, {
        "name": item.name, "project_id": item.project_id,
        "filters": _loads(item.filters_json, {}), "created_at": _iso(item.created_at),
    })


def planning_json(session: Session, actor: Principal, project_id: str) -> dict:
    from . import service

    service.require_project(session, actor, project_id)
    return {
        "sprints": [sprint_json(item) for item in session.scalars(select(ProjectSprint).where(ProjectSprint.project_id == project_id).order_by(ProjectSprint.start_at, ProjectSprint.created_at))],
        "milestones": [milestone_json(item) for item in session.scalars(select(ProjectMilestone).where(ProjectMilestone.project_id == project_id).order_by(ProjectMilestone.due_at, ProjectMilestone.created_at))],
        "fields": [field_json(item) for item in session.scalars(select(ProjectField).where(ProjectField.project_id == project_id).order_by(ProjectField.created_at))],
        "stages": [stage_json(item) for item in session.scalars(select(ProjectStage).where(ProjectStage.project_id == project_id).order_by(ProjectStage.rank, ProjectStage.created_at))],
        "rules": [rule_json(item) for item in session.scalars(select(ProjectRule).where(ProjectRule.project_id == project_id).order_by(ProjectRule.created_at))],
        "forms": [form_json(item) for item in session.scalars(select(ProjectIntakeForm).where(ProjectIntakeForm.project_id == project_id).order_by(ProjectIntakeForm.created_at))],
    }


def _ensure_date_order(start_at: datetime | None, end_at: datetime | None) -> None:
    if start_at is not None and end_at is not None and _utc(start_at) > _utc(end_at):
        raise bad_request("invalid_date_range", "start_at 不可晚於 end_at")


def _ensure_one_active_sprint(session: Session, project_id: str, sprint_id: str | None = None) -> None:
    project_stmt = select(Project).where(Project.id == project_id)
    if session.bind and session.bind.dialect.name != "sqlite":
        session.scalar(project_stmt.with_for_update())
    active = session.scalar(select(ProjectSprint.id).where(
        ProjectSprint.project_id == project_id,
        ProjectSprint.status == "active",
        ProjectSprint.id != (sprint_id or ""),
    ).limit(1))
    if active:
        raise conflict("active_sprint_exists", "每個專案同時只能有一個進行中的 Sprint")


def create_sprint(session: Session, actor: Principal, project_id: str, value: dict) -> dict:
    _require_manager(session, actor, project_id)
    _ensure_date_order(value.get("start_at"), value.get("end_at"))
    if value.get("status") == "active":
        _ensure_one_active_sprint(session, project_id)
    now = now_utc()
    item = ProjectSprint(id=new_id(), project_id=project_id, name=value["name"], goal=value.get("goal", ""),
        start_at=_utc(value.get("start_at")), end_at=_utc(value.get("end_at")), status=value.get("status", "planned"),
        created_at=now, updated_at=now)
    session.add(item)
    _audit(session, actor, "planning.sprint_created", "sprint", item.id, project_id)
    session.flush()
    return sprint_json(item)


def patch_sprint(session: Session, actor: Principal, sprint_id: str, patch: dict) -> dict:
    item = session.get(ProjectSprint, sprint_id)
    if item is None:
        raise not_found()
    _require_manager(session, actor, item.project_id)
    values = {key: value for key, value in patch.items()
        if key in {"name", "goal", "start_at", "end_at", "status"} and (value is not None or key in {"start_at", "end_at"})}
    _ensure_date_order(values.get("start_at", item.start_at), values.get("end_at", item.end_at))
    if values.get("status") == "active" and item.status != "active":
        _ensure_one_active_sprint(session, item.project_id, item.id)
    for key, value in values.items():
        setattr(item, key, _utc(value) if key in {"start_at", "end_at"} else value)
    item.updated_at = now_utc()
    _audit(session, actor, "planning.sprint_updated", "sprint", item.id, item.project_id, {"fields": sorted(values)})
    session.flush()
    return sprint_json(item)


def create_milestone(session: Session, actor: Principal, project_id: str, value: dict) -> dict:
    _require_manager(session, actor, project_id)
    now = now_utc()
    item = ProjectMilestone(id=new_id(), project_id=project_id, name=value["name"], due_at=_utc(value.get("due_at")),
        description=value.get("description", ""), status=value.get("status", "open"), created_at=now, updated_at=now)
    session.add(item)
    _audit(session, actor, "planning.milestone_created", "milestone", item.id, project_id)
    session.flush()
    return milestone_json(item)


def patch_milestone(session: Session, actor: Principal, milestone_id: str, patch: dict) -> dict:
    item = session.get(ProjectMilestone, milestone_id)
    if item is None:
        raise not_found()
    _require_manager(session, actor, item.project_id)
    values = {key: value for key, value in patch.items()
        if key in {"name", "due_at", "description", "status"} and (value is not None or key == "due_at")}
    for key, value in values.items():
        setattr(item, key, _utc(value) if key == "due_at" else value)
    item.updated_at = now_utc()
    _audit(session, actor, "planning.milestone_updated", "milestone", item.id, item.project_id, {"fields": sorted(values)})
    session.flush()
    return milestone_json(item)


def _validate_field_definition(value: dict) -> None:
    options = value.get("options") or []
    if len(options) != len(set(options)) or any(not option or len(option) > 200 for option in options):
        raise bad_request("invalid_field_options", "欄位選項必須唯一且為 1 至 200 個字元")
    if value.get("kind") == "select" and not options:
        raise bad_request("select_options_required", "select 欄位至少需要一個選項")
    if value.get("kind") != "select" and options:
        raise bad_request("unexpected_field_options", "只有 select 欄位可設定 options")


def _field_is_used(session: Session, project_id: str, key: str) -> bool:
    for value in session.scalars(select(Task.custom_fields_json).where(Task.project_id == project_id)):
        if key in _loads(value, {}):
            return True
    return False


def create_field(session: Session, actor: Principal, project_id: str, value: dict) -> dict:
    _require_manager(session, actor, project_id)
    _validate_field_definition(value)
    if session.scalar(select(ProjectField.id).where(ProjectField.project_id == project_id, ProjectField.key == value["key"])):
        raise conflict("duplicate_field_key", "此專案已使用該欄位 key")
    if session.scalar(select(func.count()).select_from(ProjectField).where(ProjectField.project_id == project_id)) >= 100:
        raise bad_request("field_limit", "每個專案最多可建立 100 個自訂欄位")
    now = now_utc()
    item = ProjectField(id=new_id(), project_id=project_id, key=value["key"], name=value["name"], kind=value["kind"],
        required=value.get("required", False), options_json=_json(value.get("options", [])), active=value.get("active", True),
        created_at=now, updated_at=now)
    session.add(item)
    _audit(session, actor, "planning.field_created", "project_field", item.id, project_id)
    session.flush()
    return field_json(item)


def patch_field(session: Session, actor: Principal, field_id: str, patch: dict) -> dict:
    item = session.get(ProjectField, field_id)
    if item is None:
        raise not_found()
    _require_manager(session, actor, item.project_id)
    values = {key: value for key, value in patch.items()
        if key in {"key", "name", "kind", "required", "options", "active"} and value is not None}
    if "key" in values and values["key"] != item.key and _field_is_used(session, item.project_id, item.key):
        raise conflict("field_immutable", "欄位被任務使用後不可更改 key")
    if "kind" in values and values["kind"] != item.kind and _field_is_used(session, item.project_id, item.key):
        raise conflict("field_immutable", "欄位被任務使用後不可更改 kind")
    if "key" in values and values["key"] != item.key and session.scalar(select(ProjectField.id).where(
        ProjectField.project_id == item.project_id, ProjectField.key == values["key"], ProjectField.id != item.id
    )):
        raise conflict("duplicate_field_key", "此專案已使用該欄位 key")
    candidate = {"kind": values.get("kind", item.kind), "options": values.get("options", _loads(item.options_json, []))}
    _validate_field_definition(candidate)
    for key, value in values.items():
        setattr(item, "options_json" if key == "options" else key, _json(value) if key == "options" else value)
    item.updated_at = now_utc()
    _audit(session, actor, "planning.field_updated", "project_field", item.id, item.project_id, {"fields": sorted(values)})
    session.flush()
    return field_json(item)


def create_stage(session: Session, actor: Principal, project_id: str, value: dict) -> dict:
    _require_manager(session, actor, project_id)
    if session.scalar(select(ProjectStage.id).where(ProjectStage.project_id == project_id, ProjectStage.name == value["name"])):
        raise conflict("duplicate_stage_name", "此專案已存在同名階段")
    if session.scalar(select(func.count()).select_from(ProjectStage).where(ProjectStage.project_id == project_id)) >= 100:
        raise bad_request("stage_limit", "每個專案最多可建立 100 個自訂階段")
    now = now_utc()
    item = ProjectStage(id=new_id(), project_id=project_id, name=value["name"], category=value["category"],
        rank=value.get("rank", 0), active=value.get("active", True), created_at=now, updated_at=now)
    session.add(item)
    _audit(session, actor, "planning.stage_created", "project_stage", item.id, project_id)
    session.flush()
    return stage_json(item)


def patch_stage(session: Session, actor: Principal, stage_id: str, patch: dict) -> dict:
    item = session.get(ProjectStage, stage_id)
    if item is None:
        raise not_found()
    _require_manager(session, actor, item.project_id)
    values = {key: value for key, value in patch.items()
        if key in {"name", "category", "rank", "active"} and value is not None}
    if "name" in values and values["name"] != item.name and session.scalar(select(ProjectStage.id).where(
        ProjectStage.project_id == item.project_id, ProjectStage.name == values["name"], ProjectStage.id != item.id
    )):
        raise conflict("duplicate_stage_name", "此專案已存在同名階段")
    in_use = session.scalar(select(Task.id).where(Task.stage_id == item.id).limit(1)) is not None
    if in_use and values.get("category", item.category) != item.category:
        raise conflict("stage_in_use", "階段正被任務使用時不可更改 category")
    if in_use and values.get("active") is False:
        raise conflict("stage_in_use", "階段仍被任務使用，請先移動任務")
    for key, value in values.items():
        setattr(item, key, value)
    item.updated_at = now_utc()
    _audit(session, actor, "planning.stage_updated", "project_stage", item.id, item.project_id, {"fields": sorted(values)})
    session.flush()
    return stage_json(item)


def _validate_custom_fields(session: Session, project_id: str, values: dict | None) -> dict:
    values = values or {}
    if not isinstance(values, dict) or len(values) > MAX_CUSTOM_FIELDS:
        raise bad_request("invalid_custom_fields", "custom_fields 必須是最多 100 個欄位的物件")
    definitions = {item.key: item for item in session.scalars(select(ProjectField).where(
        ProjectField.project_id == project_id, ProjectField.active.is_(True)
    ))}
    unknown = set(values) - definitions.keys()
    if unknown:
        raise bad_request("unknown_custom_field", "custom_fields 包含未知或已停用欄位")
    for key, item in definitions.items():
        current = values.get(key)
        if item.required and current is None:
            raise bad_request("required_custom_field", f"缺少必要欄位：{key}")
        if current is None:
            continue
        valid = {
            "text": isinstance(current, str) and len(current) <= MAX_FIELD_VALUE_LENGTH,
            "number": isinstance(current, (int, float)) and not isinstance(current, bool) and math.isfinite(current),
            "boolean": isinstance(current, bool),
            "select": isinstance(current, str) and current in _loads(item.options_json, []),
        }[item.kind]
        if not valid:
            raise bad_request("invalid_custom_field_value", f"欄位 {key} 的值不符合 {item.kind} 定義")
    return values


def validate_task_metadata(
    session: Session, actor: Principal, project_id: str, values: dict, *, current_status: str = "ready",
    task_id: str | None = None, planning_edit: bool | None = None,
) -> dict:
    from . import service

    service.require_project(session, actor, project_id)
    supplied = PLANNING_FIELDS.intersection(values)
    if planning_edit is None:
        planning_edit = bool(supplied)
    if planning_edit and actor.role not in service.ACTIVE_ROLES:
        raise forbidden("規劃欄位僅限專案管理者編輯")
    current_task = session.get(Task, task_id) if task_id else None
    work_type = values.get("work_type", current_task.work_type if current_task else "task")
    if work_type not in WORK_TYPES:
        raise bad_request("invalid_work_type", "work_type 不合法")
    if task_id and work_type != "epic" and session.scalar(select(Task.id).where(Task.epic_id == task_id).limit(1)):
        raise conflict("epic_in_use", "仍有任務使用此 Epic，不能改為其他 work_type")
    epic_id = values.get("epic_id")
    if epic_id:
        epic = session.get(Task, epic_id, populate_existing=True)
        if epic is None or epic.project_id != project_id or epic.work_type != "epic":
            raise bad_request("invalid_epic", "epic_id 必須指向相同專案的 Epic")
        if task_id and epic.id == task_id:
            raise conflict("epic_cycle", "Epic 不可指派給自己")
        seen = set()
        current = epic
        while current is not None:
            if current.id in seen or (task_id and current.id == task_id):
                raise conflict("epic_cycle", "Epic 關係不可形成循環")
            seen.add(current.id)
            current = session.get(Task, current.epic_id, populate_existing=True) if current.epic_id else None
    for key, model in (("sprint_id", ProjectSprint), ("milestone_id", ProjectMilestone)):
        resource_id = values.get(key)
        if resource_id:
            resource = session.get(model, resource_id)
            if resource is None or resource.project_id != project_id:
                raise bad_request("invalid_planning_reference", f"{key} 必須屬於相同專案")
    if values.get("stage_id"):
        stage = session.get(ProjectStage, values["stage_id"])
        status = values.get("status", current_status)
        if stage is None or stage.project_id != project_id or not stage.active:
            raise bad_request("invalid_stage", "stage_id 必須指向相同專案的啟用階段")
        if stage.category != status:
            raise conflict("stage_status_mismatch", "階段 category 必須符合任務目前 status")
    rank = values.get("rank")
    if rank is not None and not math.isfinite(rank):
        raise bad_request("invalid_rank", "rank 必須是有限數字")
    points = values.get("estimate_points")
    if points is not None and (not math.isfinite(points) or points < 0):
        raise bad_request("invalid_estimate", "estimate_points 必須是非負有限數字")
    _ensure_date_order(values.get("start_at", current_task.start_at if current_task else None),
                       values.get("due_at", current_task.due_at if current_task else None))
    if "custom_fields" in values:
        values["custom_fields"] = _validate_custom_fields(session, project_id, values["custom_fields"])
    return values


def set_task_metadata(task: Task, values: dict) -> None:
    for key in PLANNING_FIELDS.intersection(values):
        value = values[key]
        setattr(task, "custom_fields_json" if key == "custom_fields" else key, _json(value) if key == "custom_fields" else _utc(value) if key in {"due_at", "start_at"} else value)


def _rule_matches(rule: ProjectRule, task: Task) -> bool:
    conditions = _loads(rule.conditions_json, {})
    if "work_type" in conditions and task.work_type != conditions["work_type"]:
        return False
    if "priority" in conditions and task.priority != conditions["priority"]:
        return False
    if "status" in conditions and task.status != conditions["status"]:
        return False
    if "label" in conditions and conditions["label"] not in _loads(task.labels_json, []):
        return False
    return True


def _rule_assignee_valid(session: Session, project_id: str, principal_id: str) -> bool:
    principal = session.get(Principal, principal_id)
    if principal is None or not principal.active or principal.role != "worker":
        return False
    if session.scalar(select(ProjectMembership.id).where(ProjectMembership.project_id == project_id, ProjectMembership.principal_id == principal_id)) is None:
        return False
    agent = session.scalar(select(Agent).where(Agent.principal_id == principal_id))
    if agent is not None:
        from .service import _lock_agent

        agent = _lock_agent(session, agent)
    return agent is None or (agent.role == "worker" and agent.status not in {"disabled", "archived"})


def _validate_rule(session: Session, project_id: str, actor: Principal, value: dict) -> dict:
    from . import service

    event = value.get("event")
    if event not in {"task.created", "task.updated"}:
        raise bad_request("invalid_rule_event", "event 不合法")
    conditions = value.get("conditions", {}) or {}
    if set(conditions) - {"work_type", "priority", "status", "label"}:
        raise bad_request("invalid_rule_conditions", "rule conditions 包含未知欄位")
    if "work_type" in conditions and conditions["work_type"] not in WORK_TYPES:
        raise bad_request("invalid_rule_conditions", "work_type 條件不合法")
    if "priority" in conditions and conditions["priority"] not in {"urgent", "high", "medium", "low"}:
        raise bad_request("invalid_rule_conditions", "priority 條件不合法")
    if "status" in conditions and conditions["status"] not in TASK_STATES:
        raise bad_request("invalid_rule_conditions", "status 條件不合法")
    if "label" in conditions and (not isinstance(conditions["label"], str) or not conditions["label"] or len(conditions["label"]) > 100):
        raise bad_request("invalid_rule_conditions", "label 條件不合法")
    action = value.get("action")
    params = value.get("parameters", {}) or {}
    if action == "label":
        label = params.get("label")
        if set(params) != {"label"} or not isinstance(label, str) or not label or len(label) > 100:
            raise bad_request("invalid_rule_parameters", "label action 需要 parameters.label")
    elif action == "assign":
        principal_id = params.get("assignee_principal_id")
        if set(params) != {"assignee_principal_id"} or not isinstance(principal_id, str) or not _rule_assignee_valid(session, project_id, principal_id):
            raise bad_request("invalid_rule_assignee", "assign action 必須指定此專案內啟用的 worker")
    elif action == "ready":
        if params:
            raise bad_request("invalid_rule_parameters", "ready action 不接受 parameters")
    else:
        raise bad_request("invalid_rule_action", "action 不合法")
    return {**value, "event": event, "conditions": conditions, "action": action, "parameters": params,
        "enabled": value.get("enabled", True)}


def create_rule(session: Session, actor: Principal, project_id: str, value: dict) -> dict:
    _require_manager(session, actor, project_id)
    value = _validate_rule(session, project_id, actor, value)
    now = now_utc()
    item = ProjectRule(id=new_id(), project_id=project_id, creator_principal_id=actor.id, name=value["name"], event=value["event"],
        conditions_json=_json(value["conditions"]), action=value["action"], parameters_json=_json(value["parameters"]),
        enabled=value["enabled"], created_at=now, updated_at=now)
    session.add(item)
    _audit(session, actor, "planning.rule_created", "project_rule", item.id, project_id)
    session.flush()
    return rule_json(item)


def patch_rule(session: Session, actor: Principal, rule_id: str, patch: dict) -> dict:
    item = session.get(ProjectRule, rule_id)
    if item is None:
        raise not_found()
    _require_manager(session, actor, item.project_id)
    value = {"name": item.name, "event": item.event, "conditions": _loads(item.conditions_json, {}),
        "action": item.action, "parameters": _loads(item.parameters_json, {}), "enabled": item.enabled}
    value.update({key: val for key, val in patch.items() if key in value and val is not None})
    value = _validate_rule(session, item.project_id, actor, value)
    item.name = value["name"]
    item.event = value["event"]
    item.conditions_json = _json(value["conditions"])
    item.action = value["action"]
    item.parameters_json = _json(value["parameters"])
    item.enabled = value["enabled"]
    item.updated_at = now_utc()
    _audit(session, actor, "planning.rule_updated", "project_rule", item.id, item.project_id, {"fields": sorted(patch)})
    session.flush()
    return rule_json(item)


def fire_task_rules(session: Session, task: Task, event: str, event_id: str) -> None:
    """Apply rules once for an audit event; actions never emit another rule event."""
    rules = list(session.scalars(select(ProjectRule).where(
        ProjectRule.project_id == task.project_id, ProjectRule.event == event
    ).order_by(ProjectRule.created_at, ProjectRule.id)))
    for rule in rules:
        if session.scalar(select(ProjectRuleEvent.id).where(ProjectRuleEvent.rule_id == rule.id, ProjectRuleEvent.event_id == event_id)):
            continue
        session.add(ProjectRuleEvent(id=new_id(), rule_id=rule.id, event_id=event_id, created_at=now_utc()))
        session.flush()
        if not rule.enabled:
            continue
        creator = session.get(Principal, rule.creator_principal_id)
        if (creator is None or not creator.active or creator.organization_id != session.get(Project, task.project_id).organization_id
            or creator.role not in {"admin", "manager"}
            or session.scalar(select(ProjectMembership.id).where(
                ProjectMembership.project_id == task.project_id, ProjectMembership.principal_id == creator.id
            )) is None):
            continue
        if not _rule_matches(rule, task):
            continue
        params = _loads(rule.parameters_json, {})
        before = (task.labels_json, task.assignee_id, task.assignee_principal_id, task.status)
        if rule.action == "label":
            labels = _loads(task.labels_json, [])
            if params["label"] not in labels:
                task.labels_json = _json([*labels, params["label"]])
        elif rule.action == "assign":
            if task.status not in {"in_progress", "in_review", "done", "cancelled"} and _rule_assignee_valid(session, task.project_id, params["assignee_principal_id"]):
                task.assignee_id = None
                task.assignee_principal_id = params["assignee_principal_id"]
        elif rule.action == "ready" and task.status == "backlog":
            from . import service

            if service._dependencies_done(session, task.id):
                task.status = "ready"
                task.stage_id = None
        after = (task.labels_json, task.assignee_id, task.assignee_principal_id, task.status)
        if before != after:
            _audit(session, creator, "task.rule_applied", "task", task.id, task.project_id,
                   {"rule_id": rule.id, "source_event_id": event_id, "action": rule.action})


def create_form(session: Session, actor: Principal, project_id: str, value: dict) -> dict:
    _require_manager(session, actor, project_id)
    fields = value.get("fields", [])
    if len(fields) != len(set(fields)):
        raise bad_request("duplicate_form_field", "表單 fields 不可重複")
    field_items = list(session.scalars(select(ProjectField).where(ProjectField.project_id == project_id, ProjectField.active.is_(True))))
    definitions = {item.key for item in field_items}
    if set(fields) - definitions:
        raise bad_request("invalid_form_fields", "表單 fields 必須是啟用中的自訂欄位 key")
    if {item.key for item in field_items if item.required} - set(fields):
        raise bad_request("required_form_field_missing", "表單必須包含所有必要自訂欄位")
    now = now_utc()
    item = ProjectIntakeForm(id=new_id(), project_id=project_id, name=value["name"], description=value.get("description", ""),
        work_type=value.get("work_type", "task"), fields_json=_json(fields), active=value.get("active", True), created_at=now, updated_at=now)
    session.add(item)
    _audit(session, actor, "planning.form_created", "intake_form", item.id, project_id)
    session.flush()
    return form_json(item)


def patch_form(session: Session, actor: Principal, form_id: str, patch: dict) -> dict:
    item = session.get(ProjectIntakeForm, form_id)
    if item is None:
        raise not_found()
    _require_manager(session, actor, item.project_id)
    values = {key: value for key, value in patch.items()
        if key in {"name", "description", "work_type", "fields", "active"} and value is not None}
    if "fields" in values:
        if len(values["fields"]) != len(set(values["fields"])):
            raise bad_request("duplicate_form_field", "表單 fields 不可重複")
        field_items = list(session.scalars(select(ProjectField).where(
            ProjectField.project_id == item.project_id, ProjectField.active.is_(True)
        )))
        definitions = {field.key for field in field_items}
        if set(values["fields"]) - definitions:
            raise bad_request("invalid_form_fields", "表單 fields 必須是啟用中的自訂欄位 key")
        if {field.key for field in field_items if field.required} - set(values["fields"]):
            raise bad_request("required_form_field_missing", "表單必須包含所有必要自訂欄位")
    for key, value in values.items():
        setattr(item, "fields_json" if key == "fields" else key, _json(value) if key == "fields" else value)
    item.updated_at = now_utc()
    _audit(session, actor, "planning.form_updated", "intake_form", item.id, item.project_id, {"fields": sorted(values)})
    session.flush()
    return form_json(item)


def get_form(session: Session, actor: Principal, form_id: str) -> dict:
    item = session.get(ProjectIntakeForm, form_id)
    if item is None or not item.active:
        raise not_found()
    from . import service

    service.require_project(session, actor, item.project_id)
    return form_json(item)


def submit_form(session: Session, actor: Principal, form_id: str, value: dict) -> dict:
    item = session.get(ProjectIntakeForm, form_id)
    if item is None or not item.active:
        raise not_found()
    from . import service

    service.require_project(session, actor, item.project_id)
    allowed_fields = set(_loads(item.fields_json, []))
    custom_fields = value.get("custom_fields", {})
    if set(custom_fields) - allowed_fields:
        raise bad_request("form_field_not_allowed", "提交內容含表單未開放的自訂欄位")
    task = service.create_task(session, actor, {
        "project_id": item.project_id, "title": value["title"], "description": value.get("description", ""),
        "work_type": item.work_type, "status": "backlog", "custom_fields": custom_fields,
        "intake_submission": True,
    })
    return task


def reorder_tasks(session: Session, actor: Principal, project_id: str, task_ids: list[str]) -> list[dict]:
    _require_manager(session, actor, project_id)
    if len(task_ids) != len(set(task_ids)):
        raise bad_request("duplicate_task_order", "task_ids 不可重複")
    tasks = list(session.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.rank, Task.created_at, Task.id).with_for_update()))
    if set(task_ids) - {task.id for task in tasks}:
        raise bad_request("invalid_task_order", "所有 task_ids 都必須屬於相同專案")
    by_id = {item.id: item for item in tasks}
    requested = iter(task_ids)
    selected = set(task_ids)
    # Reorder filtered cards in their existing slots; hidden cards keep their relative position.
    ordered_ids = [next(requested) if task.id in selected else task.id for task in tasks]
    for index, task_id in enumerate(ordered_ids):
        by_id[task_id].rank = float(index)
        by_id[task_id].updated_at = now_utc()
    _audit(session, actor, "planning.tasks_reordered", "project", project_id, project_id, {"task_count": len(task_ids)})
    session.flush()
    from . import service

    return [service.task_json(session, by_id[task_id]) for task_id in task_ids]


def add_worklog(session: Session, actor: Principal, task_id: str, value: dict) -> dict:
    from . import service

    task = authorize_worklog_actor(session, actor, task_id)
    started_at = _utc(value["started_at"])
    if started_at > now_utc():
        raise bad_request("future_worklog", "started_at 不可晚於目前時間")
    item = TaskWorklog(id=new_id(), task_id=task.id, principal_id=actor.id, minutes=value["minutes"], started_at=started_at,
        description=value.get("description", ""), created_at=now_utc())
    session.add(item)
    _audit(session, actor, "task.worklog_added", "worklog", item.id, task.project_id, {"task_id": task.id, "minutes": item.minutes})
    session.flush()
    return worklog_json(item)


def authorize_worklog_actor(session: Session, actor: Principal, task_id: str) -> Task:
    from . import service

    task = service.task_for_actor(session, actor, task_id)
    agent = service.actor_agent(session, actor)
    owns_task = task.assignee_principal_id == actor.id or bool(agent and task.assignee_id == agent.id)
    if actor.role not in service.ACTIVE_ROLES and not owns_task:
        raise forbidden("只能記錄自己負責任務的工時")
    return task


def worklog_json(item: TaskWorklog) -> dict:
    return {"id": item.id, "task_id": item.task_id, "principal_id": item.principal_id, "minutes": item.minutes,
        "started_at": _iso(item.started_at), "description": item.description, "created_at": _iso(item.created_at)}


def list_worklogs(session: Session, actor: Principal, task_id: str) -> list[dict]:
    from . import service

    task = service.task_for_actor(session, actor, task_id)
    return [worklog_json(item) for item in session.scalars(select(TaskWorklog).where(TaskWorklog.task_id == task.id).order_by(TaskWorklog.started_at, TaskWorklog.created_at))]


def project_reports(session: Session, actor: Principal, project_id: str) -> dict:
    from . import service

    service.require_project(session, actor, project_id)
    tasks = list(session.scalars(select(Task).where(Task.project_id == project_id)))
    counts = {state: sum(1 for task in tasks if task.status == state) for state in sorted(TASK_STATES)}
    durations = []
    starts = dict(session.execute(select(Execution.task_id, func.min(Execution.started_at)).join(Task, Task.id == Execution.task_id).where(
        Task.project_id == project_id).group_by(Execution.task_id)).all())
    accepted = {item.id: item for item in session.scalars(select(Execution).join(Task, Task.id == Execution.task_id).where(
        Task.project_id == project_id, Execution.status == "accepted"))}
    for event in session.scalars(select(AuditEvent).where(AuditEvent.project_id == project_id, AuditEvent.action == 'task.review.accept')):
        execution = accepted.get(_loads(event.data_json, {}).get('execution_id'))
        if execution is None or execution.task_id not in starts:
            continue
        # finished_at is submission time. The review audit records actual independent acceptance.
        seconds = (_utc(event.created_at) - _utc(starts[execution.task_id])).total_seconds()
        if seconds >= 0:
            durations.append(seconds)
    worklogs = list(session.scalars(select(TaskWorklog).join(Task, Task.id == TaskWorklog.task_id).where(Task.project_id == project_id)))
    capacity: dict[str, int] = {}
    for item in worklogs:
        capacity[item.principal_id] = capacity.get(item.principal_id, 0) + item.minutes
    week_start = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start -= timedelta(days=week_start.weekday())
    limits = {item.principal_id: item.weekly_minutes for item in session.scalars(select(ProjectCapacity).where(ProjectCapacity.project_id == project_id))}
    participants = session.scalars(select(Principal).join(ProjectMembership, ProjectMembership.principal_id == Principal.id).where(
        ProjectMembership.project_id == project_id, Principal.active.is_(True), Principal.kind.in_(["human", "agent"])).order_by(Principal.name)).all()
    rows = []
    for person in participants:
        week_minutes = sum(item.minutes for item in worklogs if item.principal_id == person.id and week_start <= _utc(item.started_at) < week_start + timedelta(days=7))
        agent = session.scalar(select(Agent).where(Agent.principal_id == person.id)) if person.kind == "agent" else None
        assigned = [task for task in tasks if task.status not in {"done", "cancelled"} and (task.assignee_principal_id == person.id or bool(agent and task.assignee_id == agent.id))]
        weekly = limits.get(person.id)
        rows.append({"principal_id": person.id, "name": person.name, "kind": person.kind, "observed_minutes": capacity.get(person.id, 0),
            "weekly_minutes": weekly, "observed_week_minutes": week_minutes, "assigned_open_tasks": len(assigned),
            "assigned_estimate_points": sum(task.estimate_points or 0 for task in assigned),
            "utilization_percent": round(week_minutes * 100 / weekly, 1) if weekly else None})
    return {
        "totals": {"tasks": len(tasks), "by_status": counts, "estimate_points": sum(task.estimate_points or 0 for task in tasks)},
        "cycle_time": {"basis": "task first execution start to accepted review", "samples": len(durations),
            "average_seconds": statistics.mean(durations) if durations else None,
            "median_seconds": statistics.median(durations) if durations else None},
        "capacity": rows,
        "week_start": _iso(week_start),
        "worklogs": {"entries": len(worklogs), "observed_minutes": sum(item.minutes for item in worklogs)},
    }


def set_capacity(session: Session, actor: Principal, project_id: str, value: dict) -> dict:
    project = _require_manager(session, actor, project_id)
    session.refresh(project, with_for_update=True)
    person = session.get(Principal, value["principal_id"])
    if not person or not person.active or person.organization_id != actor.organization_id or person.kind not in {"human", "agent"} or not session.scalar(select(ProjectMembership.id).where(
        ProjectMembership.project_id == project_id, ProjectMembership.principal_id == person.id)):
        raise not_found()
    row = session.scalar(select(ProjectCapacity).where(ProjectCapacity.project_id == project_id, ProjectCapacity.principal_id == person.id))
    if not row:
        row = ProjectCapacity(id=new_id(), project_id=project_id, principal_id=person.id, weekly_minutes=value["weekly_minutes"])
        session.add(row)
    else:
        row.weekly_minutes = value["weekly_minutes"]
    _audit(session, actor, "planning.capacity_updated", "principal", person.id, project_id, {"weekly_minutes": value["weekly_minutes"]})
    session.flush()
    return {"principal_id": person.id, "weekly_minutes": row.weekly_minutes}


CSV_COLUMNS = ["title", "description", "work_type", "priority", "status", "due_at", "start_at", "estimate_points", "epic_id", "sprint_id", "milestone_id", "labels", "custom_fields"]


def _safe_csv_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.lstrip(" \t\r\n\f\v").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def export_tasks_csv(session: Session, actor: Principal, project_id: str) -> str:
    from . import service

    service.require_project(session, actor, project_id)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    for task in session.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.rank, Task.created_at)):
        row = {
            "title": task.title, "description": task.description, "work_type": task.work_type, "priority": task.priority,
            "status": task.status, "due_at": _iso(task.due_at), "start_at": _iso(task.start_at), "estimate_points": task.estimate_points,
            "epic_id": task.epic_id, "sprint_id": task.sprint_id, "milestone_id": task.milestone_id,
            "labels": _json(_loads(task.labels_json, [])), "custom_fields": _json(_loads(task.custom_fields_json, {})),
        }
        writer.writerow({key: _safe_csv_cell(value) for key, value in row.items()})
    return output.getvalue()


def import_tasks_csv(session: Session, actor: Principal, project_id: str, csv_text: str) -> dict:
    from . import service

    _require_manager(session, actor, project_id)
    if len(csv_text.encode("utf-8")) > 2_000_000:
        raise bad_request("csv_too_large", "CSV 不可超過 2 MB")
    reader = csv.DictReader(io.StringIO(csv_text, newline=""), strict=True)
    try:
        fieldnames = reader.fieldnames
    except csv.Error as error:
        raise bad_request("invalid_csv", "CSV 格式不合法。") from error
    if not fieldnames or "title" not in fieldnames or len(set(fieldnames)) != len(fieldnames) or set(fieldnames) - set(CSV_COLUMNS):
        raise bad_request("invalid_csv_header", "CSV 必須包含 title，且只能使用支援的欄位")
    parsed = []
    try:
        for row in reader:
            if len(parsed) >= MAX_IMPORT_ROWS:
                raise bad_request("csv_row_limit", f"CSV 最多可匯入 {MAX_IMPORT_ROWS} 列")
            parsed.append(row)
    except csv.Error as error:
        raise bad_request("invalid_csv", "CSV 格式不合法。") from error
    rows = []
    errors = []
    for line, row in enumerate(parsed, start=2):
        if line > MAX_IMPORT_ROWS + 1:
            raise bad_request("csv_row_limit", f"CSV 最多可匯入 {MAX_IMPORT_ROWS} 列")
        if None in row:
            errors.append({"row": line, "message": "欄位數量與標題列不一致"})
            continue
        try:
            title = (row.get("title") or "").strip()
            if not title or len(title) > 300:
                raise ValueError("title 必須為 1 至 300 個字元")
            value: dict[str, Any] = {"project_id": project_id, "title": title,
                "description": row.get("description") or "", "work_type": row.get("work_type") or "task",
                "priority": row.get("priority") or "medium", "status": row.get("status") or "backlog"}
            if value["work_type"] not in WORK_TYPES or value["priority"] not in {"urgent", "high", "medium", "low"} or value["status"] not in {"backlog", "ready"}:
                raise ValueError("work_type、priority 或 status 不合法")
            for field in ("due_at", "start_at"):
                if row.get(field):
                    value[field] = datetime.fromisoformat(row[field].replace("Z", "+00:00"))
            if row.get("estimate_points"):
                value["estimate_points"] = float(row["estimate_points"])
                if not math.isfinite(value["estimate_points"]) or value["estimate_points"] < 0:
                    raise ValueError("estimate_points 必須為非負有限數字")
            for field in ("epic_id", "sprint_id", "milestone_id"):
                if row.get(field):
                    value[field] = row[field]
            if row.get("labels"):
                value["labels"] = json.loads(row["labels"])
                if not isinstance(value["labels"], list) or any(not isinstance(label, str) for label in value["labels"]):
                    raise ValueError("labels 必須是字串陣列 JSON")
            if row.get("custom_fields"):
                value["custom_fields"] = json.loads(row["custom_fields"])
                if not isinstance(value["custom_fields"], dict):
                    raise ValueError("custom_fields 必須是 JSON 物件")
            planning = {key: value[key] for key in PLANNING_FIELDS.intersection(value)}
            planning.setdefault("custom_fields", {})
            validate_task_metadata(session, actor, project_id, planning, current_status=value["status"])
            rows.append(value)
        except (ValueError, TypeError, json.JSONDecodeError, csv.Error) as exc:
            errors.append({"row": line, "message": str(exc)[:300]})
        except Exception as exc:
            from .errors import DomainError

            if isinstance(exc, DomainError):
                errors.append({"row": line, "message": exc.message})
            else:
                raise
    if errors:
        return {"created": [], "errors": errors}
    created = [service.create_task(session, actor, value) for value in rows]
    return {"created": created, "errors": []}


def list_saved_queries(session: Session, actor: Principal) -> list[dict]:
    from . import service

    project_ids = service.principal_projects(session, actor.id)
    return [saved_query_json(item) for item in session.scalars(select(SavedQuery).where(
        SavedQuery.principal_id == actor.id, SavedQuery.project_id.in_(project_ids)
    ).order_by(SavedQuery.created_at.desc()))]


def create_saved_query(session: Session, actor: Principal, value: dict) -> dict:
    from . import service

    service.require_project(session, actor, value["project_id"])
    filters = value.get("filters", {}) or {}
    allowed = {"status", "q", "work_type", "sprint_id", "milestone_id", "assignee_principal_id", "overdue"}
    if set(filters) - allowed:
        raise bad_request("invalid_saved_query_filters", "saved query filters 包含未知欄位")
    if "status" in filters and filters["status"] not in TASK_STATES:
        raise bad_request("invalid_saved_query_filters", "status filter 不合法")
    if "work_type" in filters and filters["work_type"] not in WORK_TYPES:
        raise bad_request("invalid_saved_query_filters", "work_type filter 不合法")
    item = SavedQuery(id=new_id(), principal_id=actor.id, project_id=value["project_id"], name=value["name"],
        filters_json=_json(filters), created_at=now_utc())
    session.add(item)
    _audit(session, actor, "planning.saved_query_created", "saved_query", item.id, item.project_id)
    session.flush()
    return saved_query_json(item)


def delete_saved_query(session: Session, actor: Principal, query_id: str) -> dict:
    item = session.get(SavedQuery, query_id)
    if item is None:
        raise not_found()
    from . import service

    service.require_project(session, actor, item.project_id)
    if item.principal_id != actor.id:
        raise forbidden("只能刪除自己建立的 saved query")
    _audit(session, actor, "planning.saved_query_deleted", "saved_query", item.id, item.project_id)
    session.delete(item)
    return {"deleted": True, "id": item.id, "project_id": item.project_id, "principal_id": item.principal_id}
