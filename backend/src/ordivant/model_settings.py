from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import DateTime, ForeignKey, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .config import data_dir
from .db import Base
from .errors import DomainError, bad_request, conflict, forbidden
from .identity import IdentityBinding, identity_configured
from .models import (
    Agent,
    AgentModelConfig,
    AuditEvent,
    ModelProviderSetting,
    OrganizationModelSetting,
    Principal,
)
from .security import hash_secret, new_id, new_secret, now_utc, principal_projects

_KEY_NAME = "model-settings.key"
_KEY_LOCK = threading.Lock()


class ModelSettingsOperatorAudit(Base):
    __tablename__ = "model_settings_operator_audits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("principals.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _read_or_create_key() -> bytes:
    path = data_dir() / _KEY_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _KEY_LOCK:
            try:
                key = path.read_bytes()
            except FileNotFoundError:
                key = os.urandom(32)
                temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
                descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(key)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    pass
                finally:
                    temporary.unlink(missing_ok=True)
                key = path.read_bytes()
            if len(key) != 32:
                raise ValueError("invalid key length")
            try:
                path.chmod(0o600)
            except OSError:
                pass
            return key
    except (OSError, ValueError) as exc:
        raise DomainError(503, "model_key_unavailable", "模型設定加密金鑰無法使用") from exc


def _encrypt_secret(value: str, organization_id: str, provider_id: str) -> str:
    nonce = os.urandom(12)
    aad = f"{organization_id}:{provider_id}".encode("utf-8")
    ciphertext = AESGCM(_read_or_create_key()).encrypt(nonce, value.encode("utf-8"), aad)
    return "v1:" + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def _decrypt_secret(value: str, organization_id: str, provider_id: str) -> str:
    try:
        packed = base64.urlsafe_b64decode(value.removeprefix("v1:").encode("ascii"))
        plaintext = AESGCM(_read_or_create_key()).decrypt(
            packed[:12], packed[12:], f"{organization_id}:{provider_id}".encode("utf-8")
        )
        return plaintext.decode("utf-8")
    except Exception as exc:
        raise DomainError(503, "provider_credential_unavailable", "Provider credential 無法解密") from exc


def _delivery_token(event_id: str, agent_principal_id: str) -> str:
    key = _read_or_create_key()
    payload = f"ordivant:runtime-agent:{event_id}:{agent_principal_id}".encode("utf-8")
    digest = hmac.new(key, payload, hashlib.sha256).digest()
    return "ovt_" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def require_model_admin(session: Session, actor: Principal) -> None:
    if actor.kind != "human" or not actor.active:
        raise forbidden("只有組織管理員可管理模型連線")
    if not identity_configured():
        if actor.role in {"admin", "manager"}:
            return
        raise forbidden("只有組織管理員可管理模型連線")
    binding = session.scalar(
        select(IdentityBinding).where(
            IdentityBinding.principal_id == actor.id,
            IdentityBinding.organization_id == actor.organization_id,
        )
    )
    if binding is None or not binding.identity_admin:
        raise forbidden("只有 Identity administrator 可管理模型連線")


def _provider_json(provider: ModelProviderSetting) -> dict:
    return {
        "id": provider.provider_id,
        "name": provider.name,
        "base_url": provider.base_url,
        "enabled": provider.enabled,
        "key_configured": bool(provider.api_key_ciphertext),
        "models": json.loads(provider.models_json),
    }


def _settings_json(session: Session, organization_id: str) -> dict:
    setting = session.get(OrganizationModelSetting, organization_id)
    providers = session.scalars(
        select(ModelProviderSetting)
        .where(ModelProviderSetting.organization_id == organization_id)
        .order_by(ModelProviderSetting.provider_id)
    )
    return {
        "revision": setting.revision if setting else 0,
        "providers": [_provider_json(provider) for provider in providers],
        "default": json.loads(setting.default_json) if setting and setting.default_json else None,
    }


def get_model_settings(session: Session, actor: Principal) -> dict:
    require_model_admin(session, actor)
    return _settings_json(session, actor.organization_id)


def get_model_catalog(session: Session, actor: Principal) -> dict:
    if actor.kind not in {"human", "agent"} or not actor.active:
        raise forbidden("此身分無法讀取模型目錄")
    if actor.kind == "agent" and not principal_projects(session, actor.id):
        raise forbidden("Agent 必須具有 Work 專案範圍才能讀取模型目錄")
    settings = _settings_json(session, actor.organization_id)
    settings["providers"] = [
        provider for provider in settings["providers"] if provider["enabled"] and provider["key_configured"]
    ]
    return settings


def _check_base_url(base_url: str) -> None:
    try:
        parsed = urlsplit(base_url)
        parsed.port
    except ValueError:
        raise bad_request("invalid_provider_url", "Provider base_url 必須是有效的 HTTP(S) base URL") from None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or any(ord(c) < 33 for c in base_url)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise bad_request("invalid_provider_url", "Provider base_url 必須是有效的 HTTP(S) base URL")


def _model_discovery_client() -> httpx.Client:
    return httpx.Client(timeout=15, follow_redirects=False, trust_env=False)


def discover_provider_models(session: Session, actor: Principal, body: dict) -> dict:
    require_model_admin(session, actor)
    if any(ord(c) < 32 for c in body["base_url"]):
        raise bad_request("invalid_provider_url", "Provider base_url 必須是有效的 HTTP(S) base URL")
    base_url = body["base_url"].strip().rstrip("/")
    _check_base_url(base_url)
    submitted_key = body.get("api_key")
    key = submitted_key.get_secret_value() if hasattr(submitted_key, "get_secret_value") else submitted_key
    if not key:
        prior = session.get(ModelProviderSetting, (actor.organization_id, body["id"]))
        # Never forward a saved credential to a different endpoint or organization.
        if not prior or prior.base_url.rstrip("/") != base_url or not prior.api_key_ciphertext:
            raise bad_request("provider_key_required", "請提供 API Key；變更 Base URL 時必須重新提供金鑰。")
        key = _decrypt_secret(prior.api_key_ciphertext, actor.organization_id, prior.provider_id)

    try:
        with _model_discovery_client() as client:
            with client.stream("GET", base_url + "/models", headers={"Authorization": f"Bearer {key}", "Accept": "application/json"}) as response:
                if response.status_code in {401, 403}:
                    raise DomainError(502, "provider_models_unauthorized", "Provider 拒絕模型清單請求，請檢查金鑰及權限。")
                if response.status_code in {404, 405, 501}:
                    raise DomainError(502, "provider_models_unsupported", "Provider 不支援 /models，請手動新增模型。")
                if response.status_code != 200:
                    raise DomainError(502, "provider_models_unavailable", "無法取得 Provider 模型清單，請稍後重試。")
                content = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    content.extend(chunk)
                    if len(content) > 1024 * 1024:
                        raise ValueError("catalog too large")
        payload = json.loads(content)
        items = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(items, list) or len(items) > 2000:
            raise ValueError("invalid catalog")
        models = {}
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("invalid model")
            model_id = item.get("id")
            if not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 200 or any(ord(c) < 32 for c in model_id):
                raise ValueError("invalid model id")
            name = item.get("name")
            model = {"id": model_id, "name": name if isinstance(name, str) and 0 < len(name) <= 200 else model_id}
            # Standard /models returns IDs only; never invent execution limits or capabilities.
            for field, minimum in (("context_window", 1), ("max_output_tokens", 16)):
                value = item.get(field)
                if type(value) is int and minimum <= value <= 2**53 - 1:
                    model[field] = value
            efforts = item.get("reasoning_efforts")
            if isinstance(efforts, list) and efforts and all(isinstance(effort, str) and effort in {"low", "medium", "high", "xhigh", "max"} for effort in efforts):
                model["reasoning_efforts"] = list(dict.fromkeys(efforts))
            models.setdefault(model_id, model)
        return {"models": sorted(models.values(), key=lambda model: model["id"]), "source": "provider_api"}
    except httpx.TimeoutException:
        raise DomainError(504, "provider_models_timeout", "取得 Provider 模型清單逾時，請稍後重試。") from None
    except httpx.HTTPError:
        raise DomainError(502, "provider_models_unavailable", "無法取得 Provider 模型清單，請稍後重試。") from None
    except (ValueError, TypeError, UnicodeError):
        raise DomainError(502, "provider_models_invalid", "Provider 回傳的模型清單格式無效。") from None


def _selection_data(value: dict | None) -> dict | None:
    if value is None:
        return None
    return {
        "provider_id": value["provider_id"],
        "model_id": value["model_id"],
        "reasoning_effort": value["reasoning_effort"],
        "max_output_tokens": value.get("max_output_tokens", 4096),
    }


def _validate_selection(selection: dict | None, providers: dict[str, dict]) -> dict | None:
    if selection is None:
        return None
    provider = providers.get(selection["provider_id"])
    if not provider or not provider["enabled"] or not provider["key_configured"]:
        raise bad_request("model_selection_invalid", "Model selection 必須指向已啟用且已設定 key 的 Provider")
    model = next((item for item in provider["models"] if item["id"] == selection["model_id"]), None)
    if (
        model is None
        or selection["reasoning_effort"] not in model["reasoning_efforts"]
        or selection["max_output_tokens"] > model["max_output_tokens"]
    ):
        raise bad_request("model_selection_invalid", "Model selection 不符合 Provider 的 model metadata")
    return _selection_data(selection)


def validate_model_selection(session: Session, organization_id: str, selection: dict | None) -> dict | None:
    if selection is None:
        return None
    providers = {
        item.provider_id: _provider_json(item)
        for item in session.scalars(
            select(ModelProviderSetting).where(ModelProviderSetting.organization_id == organization_id)
        )
    }
    return _validate_selection(selection, providers)


def replace_model_settings(session: Session, actor: Principal, body: dict) -> dict:
    require_model_admin(session, actor)
    return _replace_model_settings(session, actor.organization_id, body, actor)


def import_model_settings(session: Session, organization_id: str, body: dict) -> dict:
    from .models import Organization

    if session.get(Organization, organization_id) is None:
        raise DomainError(404, "organization_not_found", "找不到指定組織")
    return _replace_model_settings(session, organization_id, body, None)


def _replace_model_settings(
    session: Session,
    organization_id: str,
    body: dict,
    actor: Principal | None,
) -> dict:
    setting = session.scalar(
        select(OrganizationModelSetting)
        .where(OrganizationModelSetting.organization_id == organization_id)
        .with_for_update()
    )
    current_revision = setting.revision if setting else 0
    supplied_revision = body.get("revision")
    if setting is None:
        if supplied_revision not in {None, 0}:
            raise conflict("model_settings_revision_conflict", "Model settings revision 已變更，請重新載入")
    elif supplied_revision is None:
        raise conflict("model_settings_revision_required", "更新 Model settings 時必須提供目前 revision")
    elif supplied_revision != current_revision:
        raise conflict("model_settings_revision_conflict", "Model settings revision 已變更，請重新載入")

    existing = {
        provider.provider_id: provider
        for provider in session.scalars(
            select(ModelProviderSetting).where(ModelProviderSetting.organization_id == organization_id)
        )
    }
    normalized: dict[str, dict] = {}
    secrets_to_store: dict[str, str | None] = {}
    for value in body.get("providers", []):
        provider_id = value["id"]
        if provider_id in normalized:
            raise bad_request("duplicate_provider", "Provider id 不可重複")
        base_url = value["base_url"].strip()
        _check_base_url(base_url)
        prior = existing.get(provider_id)
        submitted_key = value.get("api_key")
        if hasattr(submitted_key, "get_secret_value"):
            submitted_key = submitted_key.get_secret_value()
        if submitted_key is not None and not isinstance(submitted_key, str):
            raise bad_request("invalid_provider_key", "Provider api_key 必須是字串")
        has_new_key = bool(submitted_key)
        if prior and base_url != prior.base_url and not has_new_key:
            raise bad_request("provider_key_required", "變更 Provider base_url 時必須重新提供 api_key")
        key_configured = has_new_key or bool(prior and prior.api_key_ciphertext)
        if value["enabled"] and not key_configured:
            raise bad_request("provider_key_required", "啟用 Provider 前必須設定 api_key")
        models = [item.model_dump() if hasattr(item, "model_dump") else item for item in value.get("models", [])]
        model_ids = [item["id"] for item in models]
        if len(model_ids) != len(set(model_ids)):
            raise bad_request("duplicate_model", "同一 Provider 內 model id 不可重複")
        normalized[provider_id] = {
            "id": provider_id,
            "name": value["name"],
            "base_url": base_url,
            "enabled": value["enabled"],
            "key_configured": key_configured,
            "models": models,
        }
        secrets_to_store[provider_id] = submitted_key if has_new_key else None

    default = _validate_selection(_selection_data(body.get("default")), normalized)
    for provider_id, prior in existing.items():
        if provider_id not in normalized:
            session.delete(prior)
    now = now_utc()
    for provider_id, value in normalized.items():
        row = existing.get(provider_id)
        if row is None:
            row = ModelProviderSetting(organization_id=organization_id, provider_id=provider_id)
            session.add(row)
        submitted_key = secrets_to_store[provider_id]
        if submitted_key:
            row.api_key_ciphertext = _encrypt_secret(submitted_key, organization_id, provider_id)
        elif row.api_key_ciphertext and value["base_url"] != row.base_url:
            raise bad_request("provider_key_required", "變更 Provider base_url 時必須重新提供 api_key")
        row.name = value["name"]
        row.base_url = value["base_url"]
        row.enabled = value["enabled"]
        row.models_json = json.dumps(value["models"], ensure_ascii=False, separators=(",", ":"))
        row.updated_at = now
    if setting is None:
        setting = OrganizationModelSetting(organization_id=organization_id, revision=0, updated_at=now)
        session.add(setting)
    setting.default_json = json.dumps(default, ensure_ascii=False, separators=(",", ":")) if default else None
    setting.revision = current_revision + 1
    setting.updated_at = now
    audit_data = json.dumps(
        {"revision": setting.revision, "provider_ids": sorted(normalized), "default": default},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if actor is None:
        session.add(
            ModelSettingsOperatorAudit(
                id=new_id(),
                organization_id=organization_id,
                actor_id=None,
                action="model_settings.operator_imported",
                data_json=audit_data,
                created_at=now,
            )
        )
    else:
        session.add(
            AuditEvent(
                id=new_id(),
                project_id=None,
                actor_id=actor.id,
                action="model_settings.updated",
                entity_type="model_settings",
                entity_id=organization_id,
                data_json=audit_data,
                created_at=now,
            )
        )
    session.flush()
    return _settings_json(session, organization_id)


def agent_model_config(session: Session, agent: Agent) -> dict | None:
    row = session.get(AgentModelConfig, agent.id)
    return json.loads(row.config_json) if row else None


def effective_agent_model_config(session: Session, agent: Agent) -> dict | None:
    override = agent_model_config(session, agent)
    if override is not None:
        return override
    principal = session.get(Principal, agent.principal_id)
    setting = session.get(OrganizationModelSetting, principal.organization_id) if principal else None
    return json.loads(setting.default_json) if setting and setting.default_json else None


def set_agent_model_config(session: Session, actor: Principal, agent: Agent, selection: dict | None) -> None:
    canonical = validate_model_selection(session, actor.organization_id, selection)
    row = session.get(AgentModelConfig, agent.id)
    if canonical is None:
        if row:
            session.delete(row)
        return
    if row is None:
        row = AgentModelConfig(agent_id=agent.id, config_json="{}", updated_at=now_utc())
        session.add(row)
    row.config_json = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"))
    row.updated_at = now_utc()


def validate_effective_agent_model_config(session: Session, agent: Agent) -> dict | None:
    selection = effective_agent_model_config(session, agent)
    if selection is None:
        return None
    principal = session.get(Principal, agent.principal_id)
    if principal is None:
        raise conflict("agent_model_config_invalid", "Agent model selection 無法使用")
    try:
        return validate_model_selection(session, principal.organization_id, selection)
    except DomainError as exc:
        if exc.code == "model_selection_invalid":
            raise conflict("agent_model_config_invalid", "Agent model selection 無法使用，請更新 Agent 設定") from exc
        raise


def _provider_for_handoff(session: Session, organization_id: str, selection: dict | None) -> dict | None:
    if selection is None:
        return None
    row = session.get(ModelProviderSetting, (organization_id, selection["provider_id"]))
    if row is None:
        raise conflict("admitted_provider_unavailable", "Dispatch 所選 Provider 已不再可用")
    public = _provider_json(row)
    try:
        _validate_selection(selection, {row.provider_id: public})
    except DomainError as exc:
        raise conflict("admitted_provider_unavailable", "Dispatch 所選 Provider 已不再可用") from exc
    public["api_key"] = _decrypt_secret(row.api_key_ciphertext or "", organization_id, row.provider_id)
    return public


def _require_current_delivery(session: Session, actor: Principal, event_id: str, body: dict):
    from .models import OutboxEvent, Project
    from .service import _utc, now_utc

    if actor.kind != "runtime":
        raise forbidden("只有 runtime principal 可操作 delivery configuration")
    event = session.scalar(select(OutboxEvent).where(OutboxEvent.id == event_id).with_for_update())
    if event is None:
        raise DomainError(404, "not_found", "找不到 outbox event")
    project = session.get(Project, event.project_id)
    if (
        project is None
        or actor.organization_id != project.organization_id
        or event.project_id not in principal_projects(session, actor.id)
    ):
        raise DomainError(404, "not_found", "找不到 outbox event")
    if event.status != "claimed" or event.worker_id != body["worker_id"]:
        raise conflict("delivery_lease_invalid", "outbox ownership 已變更")
    if event.claim_expires_at is None or _utc(event.claim_expires_at) <= now_utc():
        raise conflict("delivery_lease_expired", "outbox claim 已過期")
    if not event.delivery_token_hash or not hmac.compare_digest(
        event.delivery_token_hash, hash_secret(body["delivery_token"])
    ):
        raise conflict("delivery_token_invalid", "delivery token 無效")
    agent = session.get(Agent, event.agent_id)
    agent_principal = session.get(Principal, agent.principal_id) if agent else None
    if agent is None or agent_principal is None or agent_principal.organization_id != project.organization_id:
        raise conflict("agent_scope_invalid", "Dispatch Agent 不屬於此組織")
    return event, project, agent, agent_principal


def runtime_configuration(session: Session, actor: Principal, event_id: str, body: dict) -> dict:
    from .models import AuthToken, Execution, RunMirror, Task
    from .service import _iso, _utc

    event, project, agent, agent_principal = _require_current_delivery(session, actor, event_id, body)
    token = _delivery_token(event.id, agent_principal.id)
    token_hash = hash_secret(token)
    row = session.scalar(select(AuthToken).where(AuthToken.token_hash == token_hash))
    if row is not None:
        if row.principal_id != agent_principal.id or row.revoked_at is not None:
            raise conflict("delivery_credential_unavailable", "Dispatch Agent credential 已撤銷")
    else:
        session.add(AuthToken(id=new_id(), principal_id=agent_principal.id, token_hash=token_hash, created_at=now_utc()))
    payload = json.loads(event.payload_json)
    selection = payload.get("model_config")
    provider = _provider_for_handoff(session, agent_principal.organization_id, selection)
    run = session.get(RunMirror, event.id)
    execution_lease = None
    if (
        run is not None
        and run.agent_id == event.agent_id
        and run.execution_id
        and run.status in {"running", "paused"}
        and run.desired_action != "stop"
    ):
        task = session.scalar(select(Task).where(Task.id == run.task_id).with_for_update())
        if task is not None and task.status == "in_progress":
            execution = session.scalar(
                select(Execution).where(Execution.id == run.execution_id).with_for_update()
            )
            now = now_utc()
            other_execution = session.scalar(
                select(Execution.id)
                .where(
                    Execution.task_id == task.id,
                    Execution.id != run.execution_id,
                    Execution.status == "running",
                    Execution.lease_expires_at > now,
                )
                .limit(1)
            )
            if (
                execution is not None
                and execution.id == run.execution_id
                and execution.task_id == run.task_id == task.id
                and execution.agent_id == run.agent_id == event.agent_id
                and execution.claimed_by_principal_id == agent_principal.id
                and execution.status == "running"
                and execution.lease_token_hash
                and _utc(execution.lease_expires_at) > now
                and other_execution is None
            ):
                lease_token = new_secret("lease")
                execution.lease_token_hash = hash_secret(lease_token)
                execution_lease = {
                    "task_id": task.id,
                    "execution_id": execution.id,
                    "agent_id": execution.agent_id,
                    "lease_token": lease_token,
                    "expires_at": _iso(execution.lease_expires_at),
                }
    execution_config = json.loads(run.execution_config_json) if run else {
        "instructions": "", "tool_connection_ids": [], "sandbox_profile_id": None,
        "limits": {"max_turns": 20, "timeout_seconds": 600},
    }
    from .tool_connections import handoff_tool_connections

    tool_connections = handoff_tool_connections(session, event.id, agent_principal.organization_id, project.id)
    sandbox_profile = json.loads(run.sandbox_profile_json) if run and run.sandbox_profile_json else None
    return {
        "agent": {"id": agent.id, "token": token},
        "model_config": selection,
        "provider": provider,
        "execution_config": execution_config,
        "tool_connections": tool_connections,
        "sandbox_profile": sandbox_profile,
        "execution_lease": execution_lease,
    }


def renew_runtime_delivery(session: Session, actor: Principal, event_id: str, body: dict) -> dict:
    from .service import _iso, now_utc
    from datetime import timedelta

    event, _project, _agent, _principal = _require_current_delivery(session, actor, event_id, body)
    event.claim_expires_at = now_utc() + timedelta(seconds=60)
    event.updated_at = now_utc()
    session.flush()
    return {"id": event.id, "status": event.status, "claim_expires_at": _iso(event.claim_expires_at)}


def revoke_runtime_credential(session: Session, event_id: str, agent_id: str) -> None:
    from .models import AuthToken

    agent = session.get(Agent, agent_id)
    if agent is None:
        return
    principal = session.get(Principal, agent.principal_id)
    if principal is None:
        return
    token_hash = hash_secret(_delivery_token(event_id, principal.id))
    row = session.scalar(select(AuthToken).where(AuthToken.token_hash == token_hash))
    if row is not None and row.revoked_at is None:
        row.revoked_at = now_utc()
