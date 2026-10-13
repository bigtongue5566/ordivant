from __future__ import annotations

import hashlib
import ipaddress
import json
import os
from contextlib import asynccontextmanager
from typing import Any, Callable

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from . import automation, execution_settings, runs, sandbox_profiles, service, tool_connections, vcs
from .config import app_mode, authorized_dev_proxy
from .db import Base, SessionLocal, engine, get_db
from .migrations import migrate_collaboration
from .errors import DomainError, conflict
from .identity import cookie_principal, identity_configured, require_identity_admin_for_scope_creation, sync_project_directory
from .models import Agent, IdempotencyRecord, Message, OutboxEvent, Principal, Task
from .model_settings import (
    get_model_catalog,
    get_model_settings,
    renew_runtime_delivery,
    replace_model_settings,
    runtime_configuration,
)
from .schemas import (
    AgentTemplateCreate,
    AgentTemplateVersionCreate,
    AgentCreate,
    AgentPatch,
    BlockRequest,
    ClaimRequest,
    DelegateRequest,
    DispatchRequest,
    EmptyRequest,
    LeaseRequest,
    MessageAck,
    MessageCreate,
    ModelSettingsPut,
    OutboxAckRequest,
    OutboxClaimRequest,
    ProgressRequest,
    ProjectCreate,
    ReleaseRequest,
    ReviewRequest,
    RuntimeDeliveryRequest,
    RunControlRequest,
    RunSyncRequest,
    SandboxProfileCreate,
    SandboxProfilePatch,
    SubmitRequest,
    ToolConnectionCreate,
    ToolConnectionPatch,
    TaskCreate,
    TaskPatch,
    WorkflowCreate,
    WorkflowScheduleUpdate,
    WorkflowStart,
    WorkflowVersionCreate,
)
from .security import authenticate_header, hash_secret, issue_token, new_secret, principal_json


@asynccontextmanager
async def lifespan(_app: FastAPI):
    app_mode()
    Base.metadata.create_all(bind=engine)
    migrate_collaboration(engine)
    yield


app = FastAPI(title="Ordivant API", version="0.1.0", lifespan=lifespan)


@app.exception_handler(DomainError)
async def domain_error_handler(_request: Request, error: DomainError):
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": {"code": error.code, "message": error.message}},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, error: RequestValidationError):
    if (
        request.url.path == "/api/model-settings"
        or request.url.path.startswith("/api/tool-connections")
        or request.url.path.startswith("/api/agent-templates")
    ):
        errors = [
            {key: item[key] for key in ("type", "loc", "msg") if key in item}
            for item in error.errors()
        ]
    else:
        errors = error.errors()
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


async def get_actor(request: Request, session: Session = Depends(get_db)) -> Principal:
    authorization = request.headers.get("Authorization")
    if authorization is not None:
        actor = authenticate_header(session, authorization)
    else:
        actor = await cookie_principal(request, session)
        if actor is None:
            actor = authenticate_header(session, None)
    if actor.kind == "runtime":
        path = request.url.path
        allowed = path == "/api/me" or path == "/api/runtime/outbox/claim" or (
            path.startswith("/api/runtime/outbox/") and path.rsplit("/", 1)[-1] in {"ack", "configuration", "renew"}
        ) or path == "/api/runtime/runs/controls" or (
            path.startswith("/api/runtime/runs/") and path.rsplit("/", 1)[-1] == "sync"
        ) or path == "/api/runtime/workflows/tick"
        if not allowed:
            raise DomainError(403, "runtime_scope", "runtime credential 僅能操作授權的 runtime delivery controls")
    return actor


def _request_hash(body: Any) -> str:
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _authorize_idempotent_replay(session: Session, actor: Principal, path: str, body: Any, response: Any) -> None:
    parts = path.strip("/").split("/")
    if parts[:2] == ["api", "tasks"] and len(parts) >= 3 and parts[2] != "tasks":
        service.task_for_actor(session, actor, parts[2])
    elif path == "/api/tasks":
        service.require_project(session, actor, body["project_id"])
        if actor.role not in service.ACTIVE_ROLES and not (actor.kind == "agent" and actor.role == "worker"):
            raise DomainError(403, "forbidden", "此身分無法建立任務")
    elif path == "/api/projects":
        service.require_role(actor, service.ACTIVE_ROLES)
        if isinstance(response, dict) and response.get("id"):
            service.require_project(session, actor, response["id"])
    elif path == "/api/agents":
        service.require_role(actor, service.ACTIVE_ROLES)
        for project_id in body.get("project_ids", []):
            service.require_project(session, actor, project_id)
    elif len(parts) == 3 and parts[:2] == ["api", "agents"]:
        service.require_role(actor, service.ACTIVE_ROLES)
        agent = session.get(Agent, parts[2])
        if agent is None:
            raise DomainError(404, "not_found", "找不到 agent")
        principal = session.get(Principal, agent.principal_id)
        for project_id in service.principal_projects(session, principal.id):
            service.require_project(session, actor, project_id)
    elif path == "/api/messages":
        service.require_project(session, actor, body["project_id"])
    elif len(parts) == 4 and parts[:2] == ["api", "messages"]:
        message = session.get(Message, parts[2])
        if message is None:
            raise DomainError(404, "not_found", "找不到訊息")
        service.require_project(session, actor, message.project_id)
        if message.recipient_id != actor.id and actor.role not in service.ACTIVE_ROLES:
            raise DomainError(403, "forbidden", "只有收件者可確認訊息")
    elif path == "/api/runtime/outbox/claim":
        if actor.kind != "runtime" and actor.role != "admin":
            raise DomainError(403, "forbidden", "只有 runtime 或 admin 可領取 outbox")
    elif len(parts) == 5 and parts[:3] == ["api", "runtime", "outbox"]:
        event = session.get(OutboxEvent, parts[3])
        if event is None:
            raise DomainError(404, "not_found", "找不到 outbox event")
        if actor.kind == "runtime":
            service.require_project(session, actor, event.project_id)
        elif actor.role != "admin":
            raise DomainError(403, "forbidden", "只有 runtime 或 admin 可確認 outbox")
    elif len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "control":
        runs._require_manager(actor)
        runs._require_run(session, actor, parts[2])
    elif path == "/api/workflows":
        service.require_role(actor, service.ACTIVE_ROLES)
        service.require_project(session, actor, body["project_id"])
    elif len(parts) == 4 and parts[:2] == ["api", "workflows"] and parts[3] in {"versions", "schedule", "start"}:
        automation._require_manager(actor)
        automation._workflow_for_actor(session, actor, parts[2])
    elif len(parts) == 4 and parts[:2] == ["api", "workflow-runs"] and parts[3] == "cancel":
        automation._require_manager(actor)
        automation.get_workflow_instance(session, actor, parts[2])
    elif path == "/api/agent-templates":
        service.require_role(actor, service.ACTIVE_ROLES)
    elif len(parts) == 4 and parts[:2] == ["api", "agent-templates"] and parts[3] == "versions":
        service.require_role(actor, service.ACTIVE_ROLES)
        execution_settings.get_agent_template(session, actor, parts[2])
    elif path == "/api/sandbox-profiles":
        service.require_role(actor, service.ACTIVE_ROLES)
        service.require_project(session, actor, body["project_id"])


def _strip_fencing_tokens(path: str, response: Any) -> Any:
    if isinstance(response, dict) and path.startswith("/api/tasks/") and path.endswith(("/claim", "/renew")):
        return {key: value for key, value in response.items() if key != "lease_token"}
    if isinstance(response, list) and path == "/api/runtime/outbox/claim":
        return [
            {key: value for key, value in item.items() if key != "delivery_token"}
            if isinstance(item, dict)
            else item
            for item in response
        ]
    return response


def _refresh_fencing_tokens(session: Session, actor: Principal, path: str, body: Any, response: Any) -> Any:
    parts = path.strip("/").split("/")
    if isinstance(response, dict) and path.startswith("/api/tasks/") and path.endswith(("/claim", "/renew")):
        task = service.task_for_actor(session, actor, parts[2])
        execution_data = response.get("execution") or {}
        execution = session.get(service.Execution, execution_data.get("id"))
        if execution and execution.agent_id is None:
            response["lease_token"] = None
        elif execution and execution.status == "running" and execution.claimed_by_principal_id == actor.id:
            token = new_secret("lease")
            execution.lease_token_hash = hash_secret(token)
            response["lease_token"] = token
    if isinstance(response, list) and path == "/api/runtime/outbox/claim":
        if actor.kind != "runtime" and actor.role != "admin":
            raise DomainError(403, "forbidden", "只有 runtime 或 admin 可領取 outbox")
        for item in response:
            event = session.get(service.OutboxEvent, item.get("id"))
            if (
                event
                and event.status == "claimed"
                and event.worker_id == body.get("worker_id")
                and (event.claim_expires_at is None or service._utc(event.claim_expires_at) > service.now_utc())
            ):
                token = new_secret("delivery")
                event.delivery_token_hash = hash_secret(token)
                item["delivery_token"] = token
    return response


def _actual_request_path(request: Request) -> str:
    return request.url.path


def _perform_mutation(
    request: Request,
    session: Session,
    actor: Principal,
    body: Any,
    callback: Callable[[], Any],
    status_code: int = 200,
) -> JSONResponse:
    if session.bind and session.bind.dialect.name == "sqlite":
        # The actor lookup has opened a deferred read transaction. Take SQLite's writer lock
        # before checking idempotency or mutating state so lease writes serialize across workers.
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    key = request.headers.get("Idempotency-Key")
    route = _actual_request_path(request)
    if (route.endswith("/start") and route.startswith("/api/workflows/")) or (
        route.endswith("/control") and route.startswith("/api/runs/") and body.get("action") == "retry"
    ):
        if key is None:
            raise DomainError(422, "idempotency_key_required", "此操作需要 Idempotency-Key")
    request_hash = _request_hash(body)
    record = None
    if key is not None:
        if not key or len(key) > 200:
            raise DomainError(422, "invalid_idempotency_key", "Idempotency-Key 長度須介於 1 到 200")
        record = session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.actor_id == actor.id,
                IdempotencyRecord.route == route,
                IdempotencyRecord.key == key,
            )
        )
        if record:
            if record.request_hash != request_hash:
                session.rollback()
                raise conflict("idempotency_conflict", "此 Idempotency-Key 已用於不同請求內容")
            payload = json.loads(record.response_json)
            _authorize_idempotent_replay(session, actor, route, body, payload)
            # Agent credentials are returned only to the authenticated creator. A retry issues a
            # fresh opaque credential for the existing agent; the stored response contains no token.
            if route == "/api/agents" and isinstance(payload, dict) and "id" in payload:
                agent = session.get(Agent, payload["id"])
                if agent is None:
                    session.rollback()
                    raise DomainError(404, "not_found", "找不到 agent")
                payload["token"] = issue_token(session, agent.principal_id)
                session.commit()
            else:
                payload = _refresh_fencing_tokens(session, actor, route, body, payload)
                session.commit()
            return JSONResponse(status_code=record.status_code, content=payload)
    try:
        result = jsonable_encoder(callback())
        session.flush()
        if key is not None:
            stored_result = _strip_fencing_tokens(route, result)
            if route == "/api/agents" and isinstance(stored_result, dict):
                stored_result = {field: value for field, value in stored_result.items() if field != "token"}
            session.add(
                IdempotencyRecord(
                    id=service.new_id(),
                    actor_id=actor.id,
                    route=route,
                    key=key,
                    request_hash=request_hash,
                    status_code=status_code,
                    response_json=json.dumps(stored_result, ensure_ascii=False, separators=(",", ":")),
                    created_at=service.now_utc(),
                )
            )
        session.commit()
        return JSONResponse(status_code=status_code, content=result)
    except DomainError:
        session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
        raise conflict("resource_conflict", "資料已存在或與其他請求衝突") from exc
    except OperationalError as exc:
        session.rollback()
        message = str(exc).lower()
        if "locked" in message or "deadlock" in message or "serialization" in message:
            raise conflict("concurrent_update", "資源剛被其他請求更新，請重新讀取後再試") from exc
        raise


def _perform_uncached_mutation(session: Session, callback: Callable[[], Any], status_code: int = 200) -> JSONResponse:
    if session.bind and session.bind.dialect.name == "sqlite":
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    try:
        result = jsonable_encoder(callback())
        session.commit()
        return JSONResponse(status_code=status_code, content=result, headers={"Cache-Control": "no-store"})
    except DomainError:
        session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
        raise conflict("resource_conflict", "資料已存在或與其他請求衝突") from exc
    except OperationalError as exc:
        session.rollback()
        message = str(exc).lower()
        if "locked" in message or "deadlock" in message or "serialization" in message:
            raise conflict("concurrent_update", "資源剛被其他請求更新，請重新讀取後再試") from exc
        raise


@app.get("/api/health")
def health(session: Session = Depends(get_db)):
    session.execute(text("SELECT 1"))
    database = "sqlite" if engine.dialect.name == "sqlite" else "postgresql"
    return {"status": "ok", "database": database, "mode": app_mode()}


@app.post("/api/auth/local-session")
def local_session(request: Request, session: Session = Depends(get_db)):
    if identity_configured():
        raise DomainError(403, "identity_configured", "Identity login is configured; local sessions are disabled")
    if app_mode() != "development":
        raise DomainError(403, "local_session_disabled", "production 模式已停用 local session")
    host = request.client.host if request.client else None
    try:
        loopback = bool(host and ipaddress.ip_address(host).is_loopback)
    except ValueError:
        loopback = False
    if not loopback and not authorized_dev_proxy(request.headers.get("X-Ordivant-Dev-Proxy")):
        raise DomainError(403, "loopback_required", "local session 僅允許 loopback 或授權的 development proxy")
    configured_id = os.getenv("ORDIVANT_LOCAL_PRINCIPAL_ID")
    if configured_id:
        principal = session.scalar(
            select(Principal).where(
                Principal.id == configured_id,
                Principal.kind == "human",
                Principal.role.in_(["manager", "admin"]),
                Principal.active.is_(True),
            )
        )
    else:
        principal = session.scalar(
            select(Principal)
            .where(
                Principal.kind == "human",
                Principal.role.in_(["manager", "admin"]),
                Principal.active.is_(True),
            )
            .order_by(Principal.name)
        )
    if principal is None:
        raise DomainError(404, "bootstrap_missing", "尚無可建立 local session 的 human 管理者，請先執行 seed")
    token = issue_token(session, principal.id)
    session.commit()
    return {"token": token, "principal": principal_json(session, principal)}


@app.get("/api/me")
def get_me(session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    return principal_json(session, actor)


@app.get("/api/model-settings")
def get_model_settings_route(session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    return JSONResponse(content=get_model_settings(session, actor), headers={"Cache-Control": "no-store"})


@app.put("/api/model-settings")
def put_model_settings(
    value: ModelSettingsPut,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump(exclude_unset=True)
    for provider in data.get("providers", []):
        submitted_key = provider.get("api_key")
        if hasattr(submitted_key, "get_secret_value"):
            provider["api_key"] = submitted_key.get_secret_value()
    return _perform_uncached_mutation(session, lambda: replace_model_settings(session, actor, data))


@app.get("/api/model-catalog")
def get_model_catalog_route(session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    return JSONResponse(content=get_model_catalog(session, actor), headers={"Cache-Control": "no-store"})


@app.get("/api/projects")
def get_projects(session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    return service.list_projects(session, actor)


@app.post("/api/projects", status_code=201)
def post_project(
    request: Request,
    value: ProjectCreate,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    require_identity_admin_for_scope_creation(session, actor)
    return _perform_mutation(request, session, actor, data, lambda: service.create_project(session, actor, data), 201)


@app.get("/api/projects/{project_id}/context")
def get_project_context(project_id: str, session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    return service.get_project_context(session, actor, project_id)


@app.get("/api/projects/{project_id}/participants")
async def get_project_participants(project_id: str, session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    await sync_project_directory(session, actor, project_id)
    return JSONResponse(content=service.list_participants(session, actor, project_id), headers={"Cache-Control": "no-store"})


@app.get("/api/projects/{project_id}")
def get_project(project_id: str, session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    from .models import Project

    return service.project_json(service.require_project(session, actor, project_id))


@app.get("/api/projects/{project_id}/vcs/pulls/{provider}/{number}")
def get_vcs_pull(project_id: str, provider: str, number: int, repository: str = Query(min_length=3, max_length=300), session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    service.require_project(session, actor, project_id)
    return vcs.inspect_pull(project_id, provider, repository, number)


@app.get("/api/overview")
def get_overview(project_id: str | None = None, session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    return service.overview(session, actor, project_id)


@app.get("/api/tasks")
def get_tasks(
    project_id: str | None = None,
    status: str | None = None,
    q: str | None = None,
    ready_only: bool = False,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    return service.list_tasks(session, actor, project_id, status, q, ready_only)


@app.post("/api/tasks", status_code=201)
async def post_task(
    request: Request,
    value: TaskCreate,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    if data.get("assignee_principal_id") or data.get("reviewer_principal_id"):
        await sync_project_directory(session, actor, data["project_id"])
    return _perform_mutation(request, session, actor, data, lambda: service.create_task(session, actor, data), 201)


@app.get("/api/tasks/{task_id}/context")
def get_task_context(task_id: str, session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    return service.get_task_context(session, actor, task_id)


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str, session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    return service.task_json(session, service.task_for_actor(session, actor, task_id))


@app.get("/api/tasks/{task_id}/executions")
def get_executions(task_id: str, session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    return service.list_executions(session, actor, task_id)


@app.post("/api/tasks/{task_id}/claim")
def post_claim(
    task_id: str,
    request: Request,
    value: ClaimRequest,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_mutation(request, session, actor, data, lambda: service.claim_task(session, actor, task_id, data))


@app.post("/api/tasks/{task_id}/renew")
def post_renew(
    task_id: str,
    request: Request,
    value: LeaseRequest,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_mutation(request, session, actor, data, lambda: service.renew_lease(session, actor, task_id, data))


@app.post("/api/tasks/{task_id}/progress")
def post_progress(
    task_id: str,
    request: Request,
    value: ProgressRequest,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_mutation(request, session, actor, data, lambda: service.report_progress(session, actor, task_id, data))


@app.post("/api/tasks/{task_id}/block")
def post_block(
    task_id: str,
    request: Request,
    value: BlockRequest,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_mutation(request, session, actor, data, lambda: service.block_task(session, actor, task_id, data))


@app.post("/api/tasks/{task_id}/release")
def post_release(
    task_id: str,
    request: Request,
    value: ReleaseRequest,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_mutation(request, session, actor, data, lambda: service.release_task(session, actor, task_id, data))


@app.post("/api/tasks/{task_id}/unblock")
def post_unblock(task_id: str, request: Request, session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    return _perform_mutation(request, session, actor, {}, lambda: service.unblock_task(session, actor, task_id))


@app.post("/api/tasks/{task_id}/submit")
def post_submit(
    task_id: str,
    request: Request,
    value: SubmitRequest,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_mutation(request, session, actor, data, lambda: service.submit_result(session, actor, task_id, data))


@app.post("/api/tasks/{task_id}/review")
def post_review(
    task_id: str,
    request: Request,
    value: ReviewRequest,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_mutation(request, session, actor, data, lambda: service.review_result(session, actor, task_id, data))


@app.post("/api/tasks/{task_id}/delegate", status_code=201)
async def post_delegate(
    task_id: str,
    request: Request,
    value: DelegateRequest,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    if data.get("assignee_principal_id"):
        task = service.task_for_actor(session, actor, task_id)
        await sync_project_directory(session, actor, task.project_id)
    return _perform_mutation(request, session, actor, data, lambda: service.delegate_task(session, actor, task_id, data), 201)


@app.patch("/api/tasks/{task_id}")
async def patch_task(
    task_id: str,
    request: Request,
    value: TaskPatch,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump(exclude_unset=True)
    if data.get("assignee_principal_id") or data.get("reviewer_principal_id"):
        task = service.task_for_actor(session, actor, task_id)
        await sync_project_directory(session, actor, task.project_id)
    return _perform_mutation(request, session, actor, data, lambda: service.patch_task(session, actor, task_id, data))


@app.get("/api/agents")
def get_agents(project_id: str | None = None, session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    return service.list_agents(session, actor, project_id)


@app.post("/api/agents", status_code=201)
def post_agent(
    request: Request,
    value: AgentCreate,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump(by_alias=True)
    return _perform_mutation(request, session, actor, data, lambda: service.create_agent(session, actor, data), 201)


@app.patch("/api/agents/{agent_id}")
def patch_agent(
    agent_id: str,
    request: Request,
    value: AgentPatch,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump(exclude_unset=True, by_alias=True)
    return _perform_mutation(request, session, actor, data, lambda: service.patch_agent(session, actor, agent_id, data))


@app.get("/api/messages")
def get_messages(
    project_id: str | None = None,
    task_id: str | None = None,
    inbox: bool = False,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    return service.list_messages(session, actor, project_id, task_id, inbox)


@app.post("/api/messages", status_code=201)
async def post_message(
    request: Request,
    value: MessageCreate,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    if data.get("recipient_id"):
        await sync_project_directory(session, actor, data["project_id"])
    return _perform_mutation(request, session, actor, data, lambda: service.create_message(session, actor, data), 201)


@app.post("/api/messages/{message_id}/ack")
def post_message_ack(
    message_id: str,
    request: Request,
    value: MessageAck,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_mutation(request, session, actor, data, lambda: service.acknowledge_message(session, actor, message_id, data["status"]))


@app.get("/api/events")
def get_events(project_id: str | None = None, task_id: str | None = None, session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    return service.list_events(session, actor, project_id, task_id)


@app.post("/api/tasks/{task_id}/dispatch", status_code=201)
def post_dispatch(
    task_id: str,
    request: Request,
    value: DispatchRequest,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_mutation(request, session, actor, data, lambda: service.dispatch_task(session, actor, task_id, data["agent_id"]), 201)


@app.post("/api/runtime/outbox/claim")
def post_outbox_claim(
    request: Request,
    value: OutboxClaimRequest,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_mutation(request, session, actor, data, lambda: service.claim_outbox(session, actor, data["worker_id"], data["limit"]))


@app.post("/api/runtime/outbox/{event_id}/ack")
def post_outbox_ack(
    event_id: str,
    request: Request,
    value: OutboxAckRequest,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_mutation(request, session, actor, data, lambda: service.acknowledge_outbox(session, actor, event_id, data))


@app.post("/api/runtime/outbox/{event_id}/configuration")
def post_outbox_configuration(
    event_id: str,
    value: RuntimeDeliveryRequest,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_uncached_mutation(session, lambda: runtime_configuration(session, actor, event_id, data))


@app.post("/api/runtime/outbox/{event_id}/renew")
def post_outbox_renew(
    event_id: str,
    value: RuntimeDeliveryRequest,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_uncached_mutation(session, lambda: renew_runtime_delivery(session, actor, event_id, data))


@app.get("/api/runs")
def get_runs(
    project_id: str | None = None,
    task_id: str | None = None,
    status: str | None = None,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    return runs.list_runs(session, actor, project_id, task_id, status)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    return runs.get_run(session, actor, run_id)


@app.get("/api/runs/{run_id}/events")
def get_run_events(
    run_id: str,
    after_sequence: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    return runs.get_run_events(session, actor, run_id, after_sequence)


@app.post("/api/runs/{run_id}/control")
def post_run_control(
    run_id: str,
    request: Request,
    value: RunControlRequest,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_mutation(request, session, actor, data, lambda: runs.control_run(session, actor, run_id, data["action"]))


@app.get("/api/runtime/runs/controls")
def get_runtime_run_controls(
    worker_id: str = Query(min_length=1, max_length=200),
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    return JSONResponse(content=runs.list_runtime_controls(session, actor, worker_id), headers={"Cache-Control": "no-store"})


@app.post("/api/runtime/runs/{run_id}/sync")
def post_runtime_run_sync(
    run_id: str,
    value: RunSyncRequest,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump(exclude_unset=True)
    return _perform_uncached_mutation(session, lambda: runs.sync_run(session, actor, run_id, data))


@app.get("/api/agent-templates")
def get_agent_templates(session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    return execution_settings.list_agent_templates(session, actor)


@app.post("/api/agent-templates", status_code=201)
def post_agent_template(
    request: Request,
    value: AgentTemplateCreate,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump(by_alias=True)
    return _perform_mutation(request, session, actor, data, lambda: execution_settings.create_agent_template(session, actor, data), 201)


@app.post("/api/agent-templates/{template_id}/versions", status_code=201)
def post_agent_template_version(
    template_id: str,
    request: Request,
    value: AgentTemplateVersionCreate,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump(by_alias=True)
    return _perform_mutation(
        request, session, actor, data,
        lambda: execution_settings.create_agent_template_version(session, actor, template_id, data), 201,
    )


@app.get("/api/workflows")
def get_workflows(project_id: str | None = None, session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    return automation.list_workflows(session, actor, project_id)


@app.post("/api/workflows", status_code=201)
def post_workflow(
    request: Request,
    value: WorkflowCreate,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_mutation(request, session, actor, data, lambda: automation.create_workflow(session, actor, data), 201)


@app.post("/api/workflows/{workflow_id}/versions", status_code=201)
def post_workflow_version(
    workflow_id: str,
    request: Request,
    value: WorkflowVersionCreate,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_mutation(request, session, actor, data, lambda: automation.create_workflow_version(session, actor, workflow_id, data), 201)


@app.patch("/api/workflows/{workflow_id}/schedule")
def patch_workflow_schedule(
    workflow_id: str,
    request: Request,
    value: WorkflowScheduleUpdate,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_mutation(request, session, actor, data, lambda: automation.update_workflow_schedule(session, actor, workflow_id, data))


@app.post("/api/workflows/{workflow_id}/start", status_code=201)
def post_workflow_start(
    workflow_id: str,
    request: Request,
    value: WorkflowStart,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_mutation(request, session, actor, data, lambda: automation.start_workflow(session, actor, workflow_id, data["inputs"]), 201)


@app.get("/api/workflow-runs")
def get_workflow_runs(project_id: str | None = None, session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    return automation.list_workflow_instances(session, actor, project_id)


@app.get("/api/workflow-runs/{instance_id}")
def get_workflow_run(instance_id: str, session: Session = Depends(get_db), actor: Principal = Depends(get_actor)):
    return automation.get_workflow_instance(session, actor, instance_id)


@app.post("/api/workflow-runs/{instance_id}/cancel")
def post_workflow_run_cancel(
    instance_id: str,
    request: Request,
    value: EmptyRequest,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_mutation(request, session, actor, data, lambda: automation.cancel_workflow_instance(session, actor, instance_id))


@app.post("/api/runtime/workflows/tick")
def post_workflow_tick(
    value: EmptyRequest,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    return _perform_uncached_mutation(session, lambda: automation.tick_workflows(session, actor))


@app.get("/api/tool-connections")
def get_tool_connections(
    project_id: str | None = None,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    return JSONResponse(content=tool_connections.list_tool_connections(session, actor, project_id), headers={"Cache-Control": "no-store"})


@app.post("/api/tool-connections", status_code=201)
def post_tool_connection(
    value: ToolConnectionCreate,
    project_id: str | None = None,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump(exclude_unset=True)
    return _perform_uncached_mutation(
        session, lambda: tool_connections.create_tool_connection(session, actor, data, project_id), status_code=201
    )


@app.patch("/api/tool-connections/{connection_id}")
def patch_tool_connection(
    connection_id: str,
    value: ToolConnectionPatch,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump(exclude_unset=True)
    return _perform_uncached_mutation(session, lambda: tool_connections.patch_tool_connection(session, actor, connection_id, data))


@app.post("/api/tool-connections/{connection_id}/test")
async def post_tool_connection_test(
    connection_id: str,
    value: EmptyRequest,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    result = await tool_connections.test_tool_connection(session, actor, connection_id)
    return JSONResponse(content=result, headers={"Cache-Control": "no-store"})


@app.get("/api/sandbox-profiles")
def get_sandbox_profiles(
    project_id: str | None = None,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    return sandbox_profiles.list_sandbox_profiles(session, actor, project_id)


@app.post("/api/sandbox-profiles", status_code=201)
def post_sandbox_profile(
    request: Request,
    value: SandboxProfileCreate,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump()
    return _perform_mutation(request, session, actor, data, lambda: sandbox_profiles.create_sandbox_profile(session, actor, data), 201)


@app.patch("/api/sandbox-profiles/{profile_id}")
def patch_sandbox_profile(
    profile_id: str,
    request: Request,
    value: SandboxProfilePatch,
    session: Session = Depends(get_db),
    actor: Principal = Depends(get_actor),
):
    data = value.model_dump(exclude_unset=True)
    return _perform_mutation(request, session, actor, data, lambda: sandbox_profiles.patch_sandbox_profile(session, actor, profile_id, data))
