from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import GiteaConfig, load_gitea_config
from .errors import DomainError
from .gitea import GiteaClient
from .models import (
    AuditEvent,
    CheckReceipt,
    IdempotencyRecord,
    OperationIntent,
    Principal,
    Project,
    PullRequestComment,
    PullRequest,
    PullRequestReview,
    Repository,
    Scope,
    ScopeMembership,
    WebhookDelivery,
)
from .schemas import (
    BranchCreate,
    CheckCreate,
    FileCommit,
    ProjectCreate,
    PullRequestCommentCreate,
    PullRequestCreate,
    PullRequestReviewCreate,
    RepositoryCreate,
)
from .security import new_id, now_utc

INTENT_MARKER = "<!-- ordivant-intent:{intent_id} -->"


def _hash_json(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


def _parse_time(value: str | None) -> datetime:
    if not value:
        return now_utc()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (TypeError, ValueError):
        return now_utc()


def _safe_upstream_url(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username is not None or parsed.password is not None:
        return ""
    return value


def _membership(session: Session, principal: Principal, project: Project) -> ScopeMembership:
    if project.organization_id != principal.organization_id:
        raise DomainError(404, "not_found", "Project not found")
    membership = session.scalar(
        select(ScopeMembership).where(
            ScopeMembership.principal_id == principal.id,
            ScopeMembership.scope_id == project.scope_id,
        )
    )
    if membership is None:
        raise DomainError(404, "not_found", "Project not found")
    return membership


def require_project(session: Session, principal: Principal, project_id: str, *, write: bool = False, manager: bool = False) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise DomainError(404, "not_found", "Project not found")
    membership = _membership(session, principal, project)
    manager_role = principal.role in {"manager", "admin"} and membership.role == "manager"
    writer_role = principal.role in {"manager", "admin", "writer"} and membership.role in {"manager", "writer"}
    if manager and not manager_role:
        raise DomainError(403, "forbidden", "Manager access is required")
    if write and not writer_role:
        raise DomainError(403, "forbidden", "Write access is required")
    return project


def require_repository(session: Session, principal: Principal, repository_id: str, *, write: bool = False, manager: bool = False) -> tuple[Repository, Project]:
    repository = session.get(Repository, repository_id)
    if repository is None:
        raise DomainError(404, "not_found", "Repository not found")
    project = require_project(session, principal, repository.project_id, write=write, manager=manager)
    return repository, project


def project_json(project: Project) -> dict:
    return {
        "id": project.id,
        "key": project.key,
        "name": project.name,
        "description": project.description,
        "organization_id": project.organization_id,
        "created_at": _iso(project.created_at),
    }


def repository_json(repository: Repository) -> dict:
    return {
        "id": repository.id,
        "project_id": repository.project_id,
        "provider": repository.provider,
        "owner": repository.owner,
        "name": repository.name,
        "default_branch": repository.default_branch,
        "web_url": repository.web_url,
        "clone_url": repository.clone_url,
        "created_at": _iso(repository.created_at),
    }


def pull_json(pull: PullRequest) -> dict:
    return {
        "id": pull.id,
        "repository_id": pull.repository_id,
        "number": pull.number,
        "title": pull.title,
        "body": pull.body,
        "state": pull.state,
        "head": pull.head,
        "base": pull.base,
        "web_url": pull.web_url,
        "head_sha": pull.head_sha,
        "source_refs": pull.source_refs or [],
        "created_at": _iso(pull.created_at),
        "updated_at": _iso(pull.updated_at),
    }


def check_json(check: CheckReceipt) -> dict:
    return {
        "id": check.id,
        "repository_id": check.repository_id,
        "commit_sha": check.commit_sha,
        "context": check.context,
        "state": check.state,
        "description": check.description,
        "target_url": check.target_url,
        "source": check.source,
        "actor_id": check.actor_id,
        "created_at": _iso(check.created_at),
    }


def event_json(event: AuditEvent) -> dict:
    return {
        "id": event.id,
        "project_id": event.project_id,
        "actor_id": event.actor_id,
        "action": event.action,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "data": event.data,
        "created_at": _iso(event.created_at),
    }


def _event(session: Session, project_id: str | None, actor_id: str | None, action: str, entity_type: str, entity_id: str, data: dict):
    # Callers pass allow-listed metadata only; credentials and file contents never belong in audit data.
    session.add(AuditEvent(
        id=new_id(), project_id=project_id, actor_id=actor_id, action=action,
        entity_type=entity_type, entity_id=str(entity_id), data=data, created_at=now_utc(),
    ))


def _gitea(config: GiteaConfig | None = None) -> GiteaClient:
    config = config or load_gitea_config()
    if config is None:
        raise DomainError(503, "gitea_not_configured", "Gitea is not configured")
    return GiteaClient(config)


def _cached(session: Session, principal: Principal, route: str, key: str, payload: dict) -> dict | None:
    if not key or len(key) > 255:
        raise DomainError(422, "idempotency_key_required", "Idempotency-Key is required and must be at most 255 characters")
    request_hash = _hash_json(payload)
    record = session.scalar(select(IdempotencyRecord).where(
        IdempotencyRecord.actor_id == principal.id,
        IdempotencyRecord.route == route,
        IdempotencyRecord.key == key,
    ))
    if record is None:
        return None
    if record.request_hash != request_hash:
        raise DomainError(409, "idempotency_conflict", "This idempotency key was already used with a different request")
    return record.response_json


def _save_idempotency(session: Session, principal: Principal, route: str, key: str, payload: dict, response: dict):
    session.add(IdempotencyRecord(
        id=new_id(), actor_id=principal.id, route=route, key=key,
        request_hash=_hash_json(payload), response_json=response, created_at=now_utc(),
    ))


def _local_mutation(
    session: Session, principal: Principal, route: str, key: str, payload: dict,
    action: str, entity_type: str, entity_id: str, project_id: str | None, create,
) -> dict:
    cached = _cached(session, principal, route, key, payload)
    if cached is not None:
        return cached
    response = create()
    _event(session, project_id, principal.id, action, entity_type, entity_id, {"request_idempotency": True})
    _save_idempotency(session, principal, route, key, payload, response)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        cached = _cached(session, principal, route, key, payload)
        if cached is not None:
            return cached
        raise DomainError(409, "conflict", "The request conflicts with an existing resource") from exc
    return response


def _prepare_intent(
    session: Session, principal: Principal, route: str, key: str, payload: dict,
    project_id: str, repository_id: str | None, kind: str,
) -> OperationIntent:
    request_hash = _hash_json(payload)
    intent = session.scalar(select(OperationIntent).where(
        OperationIntent.actor_id == principal.id,
        OperationIntent.route == route,
        OperationIntent.key == key,
    ))
    if intent is not None:
        if intent.request_hash != request_hash:
            raise DomainError(409, "idempotency_conflict", "This idempotency key was already used with a different request")
        if intent.state == "conflict":
            raise DomainError(409, "gitea_conflict", "The previous upstream operation conflicted and was not adopted")
        if intent.state == "complete":
            response = session.scalar(select(IdempotencyRecord).where(
                IdempotencyRecord.actor_id == principal.id,
                IdempotencyRecord.route == route,
                IdempotencyRecord.key == key,
            ))
            if response:
                return intent
            raise DomainError(409, "reconciliation_required", "The operation completed but its response needs reconciliation")
        now = time.time()
        lease_until = now + 90
        changed = session.execute(update(OperationIntent).where(
            OperationIntent.id == intent.id,
            OperationIntent.state == "pending",
            OperationIntent.lock_until <= now,
        ).values(lock_until=lease_until, updated_at=now_utc()))
        if changed.rowcount != 1:
            session.rollback()
            raise DomainError(409, "operation_in_progress", "The same upstream operation is still being reconciled")
        intent = session.get(OperationIntent, intent.id, populate_existing=True)
        session.commit()
        return intent

    now = now_utc()
    intent = OperationIntent(
        id=new_id(), actor_id=principal.id, project_id=project_id, repository_id=repository_id,
        route=route, key=key, request_hash=request_hash, kind=kind, request_json=payload,
        state="pending", lock_until=time.time() + 90, created_at=now, updated_at=now,
    )
    session.add(intent)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DomainError(409, "operation_in_progress", "The same upstream operation is being started") from exc
    return intent


def _finish_intent(
    session: Session, principal: Principal, intent: OperationIntent, payload: dict,
    response: dict, action: str, entity_type: str, entity_id: str, *, external_id: str | None = None,
) -> dict:
    current_principal = session.get(Principal, principal.id, populate_existing=True)
    if current_principal is None or not current_principal.active:
        session.rollback()
        raise DomainError(401, "unauthenticated", "Principal is no longer active")
    require_project(session, current_principal, intent.project_id, write=True)
    changed = session.execute(update(OperationIntent).where(
        OperationIntent.id == intent.id,
        OperationIntent.state == "pending",
        OperationIntent.lock_until == intent.lock_until,
    ).values(
        state="complete", external_id=external_id, result_json=response,
        lock_until=0, updated_at=now_utc(),
    ))
    if changed.rowcount != 1:
        session.rollback()
        raise DomainError(409, "reconciliation_required", "Operation intent is no longer available")
    _event(session, intent.project_id, current_principal.id, action, entity_type, entity_id, {"upstream_id": external_id} if external_id else {})
    _save_idempotency(session, current_principal, intent.route, intent.key, payload, response)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        cached = _cached(session, principal, intent.route, intent.key, payload)
        if cached is not None:
            return cached
        raise DomainError(409, "reconciliation_required", "Could not finalize the upstream operation")
    return response


def _release_intent(session: Session, intent: OperationIntent):
    session.execute(update(OperationIntent).where(
        OperationIntent.id == intent.id,
        OperationIntent.state == "pending",
        OperationIntent.lock_until == intent.lock_until,
    ).values(lock_until=0, updated_at=now_utc()))
    session.commit()


def _release_after_upstream_error(session: Session, intent: OperationIntent, error: DomainError):
    if error.status_code >= 500:
        _release_intent(session, intent)


def _fail_intent(session: Session, intent: OperationIntent):
    session.execute(update(OperationIntent).where(
        OperationIntent.id == intent.id,
        OperationIntent.state == "pending",
        OperationIntent.lock_until == intent.lock_until,
    ).values(state="conflict", lock_until=0, updated_at=now_utc()))
    session.commit()


def _require_safe_ref(name: str) -> str:
    invalid = (not name or name.startswith("/") or name.endswith(("/", ".")) or "//" in name or ".." in name or "@{" in name)
    invalid = invalid or any(ch in name for ch in " ~^:?*[\\") or name == "@" or name.lower().endswith(".lock")
    invalid = invalid or any(ord(ch) < 32 or ord(ch) == 127 for ch in name)
    invalid = invalid or any(
        part in {"", ".", ".."} or part.startswith(".") or part.endswith(".") or part.lower().endswith(".lock")
        for part in name.split("/")
    )
    if invalid:
        raise DomainError(422, "invalid_branch", "Branch name is not a valid Git reference")
    return name


def list_projects(session: Session, principal: Principal) -> list[dict]:
    projects = session.scalars(
        select(Project).join(ScopeMembership, ScopeMembership.scope_id == Project.scope_id)
        .where(ScopeMembership.principal_id == principal.id, Project.organization_id == principal.organization_id)
        .order_by(Project.created_at)
    ).all()
    return [project_json(project) for project in projects]


def get_project(session: Session, principal: Principal, project_id: str) -> dict:
    return project_json(require_project(session, principal, project_id))


def create_project(session: Session, principal: Principal, route: str, key: str, payload: ProjectCreate) -> dict:
    if principal.role not in {"manager", "admin"}:
        raise DomainError(403, "forbidden", "Manager access is required")
    data = payload.model_dump(mode="json")
    cached = _cached(session, principal, route, key, data)
    if cached is not None:
        require_project(session, principal, cached.get("id", ""), manager=True)
        return cached
    project_id, scope_id = new_id(), new_id()
    created = now_utc()
    project = Project(
        id=project_id, scope_id=scope_id, key=payload.key, name=payload.name,
        description=payload.description, organization_id=principal.organization_id, created_at=created,
    )
    session.add(Scope(id=scope_id, organization_id=principal.organization_id, name=payload.name, created_at=created))
    session.flush()
    session.add(project)
    session.flush()
    session.add(ScopeMembership(id=new_id(), principal_id=principal.id, scope_id=scope_id, role="manager"))
    response = project_json(project)
    _event(session, project_id, principal.id, "code.project_created", "project", project_id, {})
    _save_idempotency(session, principal, route, key, data, response)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        cached = _cached(session, principal, route, key, data)
        if cached:
            return cached
        raise DomainError(409, "conflict", "Project key already exists") from exc
    return response


def list_repositories(session: Session, principal: Principal, project_id: str) -> list[dict]:
    require_project(session, principal, project_id)
    repositories = session.scalars(select(Repository).where(Repository.project_id == project_id).order_by(Repository.created_at)).all()
    return [repository_json(repo) for repo in repositories]


def create_repository(session: Session, principal: Principal, route: str, key: str, payload: RepositoryCreate) -> dict:
    project = require_project(session, principal, payload.project_id, write=True)
    data = payload.model_dump(mode="json")
    cached = _cached(session, principal, route, key, data)
    if cached is not None:
        return cached
    client = _gitea()
    account = client.user()
    owner = account.get("login") or account.get("username")
    if not isinstance(owner, str) or not owner:
        raise DomainError(502, "gitea_invalid_response", "Gitea did not identify its service account")
    existing_intent = session.scalar(select(OperationIntent).where(
        OperationIntent.actor_id == principal.id, OperationIntent.route == route, OperationIntent.key == key,
    ))
    if existing_intent is None:
        existing = session.scalar(select(Repository).where(Repository.owner == owner, Repository.name == payload.name))
        if existing:
            raise DomainError(409, "repository_already_bound", "Repository is already bound to another Code project")
        try:
            upstream = client.repository(owner, payload.name)
        except DomainError as exc:
            if exc.status_code != 404:
                raise
        else:
            if upstream:
                raise DomainError(409, "repository_exists", "An existing Gitea repository cannot be adopted by this request")
    intent = _prepare_intent(session, principal, route, key, data, project.id, None, "create_repository")
    if intent.state == "complete" and intent.result_json:
        return intent.result_json
    if intent.state == "complete" and intent.result_json:
        return intent.result_json
    try:
        try:
            upstream = client.repository(owner, payload.name)
        except DomainError as exc:
            if exc.status_code != 404:
                raise
            upstream = client.create_repository(name=payload.name, description=payload.description)
    except DomainError as exc:
        if exc.code == "gitea_conflict":
            _fail_intent(session, intent)
        else:
            _release_after_upstream_error(session, intent, exc)
        raise
    repo = Repository(
        id=new_id(), project_id=project.id, provider="gitea", owner=owner,
        name=upstream.get("name", payload.name), default_branch=upstream.get("default_branch") or "main",
        web_url=_safe_upstream_url(upstream.get("html_url") or upstream.get("website")),
        clone_url=_safe_upstream_url(upstream.get("clone_url")), created_at=now_utc(),
    )
    response = repository_json(repo)
    session.add(repo)
    return _finish_intent(session, principal, intent, data, response, "code.repository_created", "repository", repo.id, external_id=f"{owner}/{repo.name}")


def create_branch(session: Session, principal: Principal, repository_id: str, route: str, key: str, payload: BranchCreate) -> dict:
    repository, project = require_repository(session, principal, repository_id, write=True)
    name, from_branch = _require_safe_ref(payload.name), _require_safe_ref(payload.from_branch)
    data = payload.model_dump(mode="json")
    cached = _cached(session, principal, route, key, data)
    if cached is not None:
        return cached
    client = _gitea()
    intent = session.scalar(select(OperationIntent).where(
        OperationIntent.actor_id == principal.id, OperationIntent.route == route, OperationIntent.key == key,
    ))
    try:
        source = client.branch(repository.owner, repository.name, from_branch)
    except DomainError:
        raise
    source_sha = (source.get("commit") or {}).get("id") or (source.get("commit") or {}).get("sha")
    if not source_sha:
        raise DomainError(502, "gitea_invalid_response", "Gitea did not return a source branch commit")
    if intent is None:
        try:
            client.branch(repository.owner, repository.name, name)
        except DomainError as exc:
            if exc.status_code != 404:
                raise
        else:
            raise DomainError(409, "branch_exists", "An existing branch cannot be adopted by this request")
    intent = _prepare_intent(session, principal, route, key, data, project.id, repository.id, "create_branch")
    if intent.state == "complete" and intent.result_json:
        return intent.result_json
    saved_sha = intent.request_json.get("resolved_from_sha", source_sha)
    if "resolved_from_sha" not in intent.request_json:
        intent.request_json = {**intent.request_json, "resolved_from_sha": source_sha}
        session.commit()
    try:
        try:
            branch = client.branch(repository.owner, repository.name, name)
            commit_sha = (branch.get("commit") or {}).get("id") or (branch.get("commit") or {}).get("sha")
            if commit_sha != saved_sha:
                _fail_intent(session, intent)
                raise DomainError(409, "branch_exists", "The branch exists with an unrelated commit")
        except DomainError as exc:
            if exc.status_code != 404:
                raise
            branch = client.create_branch(repository.owner, repository.name, name, from_branch)
            commit_sha = (branch.get("commit") or {}).get("id") or (branch.get("commit") or {}).get("sha") or saved_sha
    except DomainError as exc:
        if exc.code == "gitea_conflict":
            _fail_intent(session, intent)
        else:
            _release_after_upstream_error(session, intent, exc)
        raise
    response = {"name": name, "commit_sha": commit_sha}
    return _finish_intent(session, principal, intent, data, response, "code.branch_created", "repository", repository.id, external_id=commit_sha)


def _commit_marker(intent_id: str) -> str:
    return INTENT_MARKER.format(intent_id=intent_id)


def _find_commit_marker(commits, marker: str):
    if not isinstance(commits, list):
        return None
    for item in commits:
        commit = item.get("commit") or {}
        if marker in (commit.get("message") or item.get("message") or ""):
            return item.get("sha") or commit.get("sha")
    return None


def commit_file(session: Session, principal: Principal, repository_id: str, route: str, key: str, payload: FileCommit) -> dict:
    repository, project = require_repository(session, principal, repository_id, write=True)
    branch, path = _require_safe_ref(payload.branch), payload.path
    data = payload.model_dump(mode="json")
    cached = _cached(session, principal, route, key, data)
    if cached is not None:
        return cached
    client = _gitea()
    client.branch(repository.owner, repository.name, branch)
    existing = session.scalar(select(OperationIntent).where(
        OperationIntent.actor_id == principal.id, OperationIntent.route == route, OperationIntent.key == key,
    ))
    if existing is None:
        try:
            current = client.file(repository.owner, repository.name, path, branch)
        except DomainError as exc:
            if exc.status_code != 404:
                raise
            current = None
        if (current is None and payload.expected_sha is not None) or (current is not None and current.get("sha") != payload.expected_sha):
            raise DomainError(409, "file_sha_conflict", "File state does not match expected_sha")
    intent = _prepare_intent(session, principal, route, key, data, project.id, repository.id, "commit_file")
    if intent.state == "complete" and intent.result_json:
        return intent.result_json
    marker = _commit_marker(intent.id)
    try:
        commits = client.commits_for_path(repository.owner, repository.name, path, branch)
    except DomainError as exc:
        if exc.status_code == 404 and payload.expected_sha is None:
            commits = []
        else:
            if exc.status_code == 404:
                _fail_intent(session, intent)
            else:
                _release_after_upstream_error(session, intent, exc)
            raise
    prior_commit = _find_commit_marker(commits, marker)
    if prior_commit:
        try:
            committed_file = client.file(repository.owner, repository.name, path, prior_commit)
        except DomainError as exc:
            _release_after_upstream_error(session, intent, exc)
            if exc.status_code >= 500:
                raise
            committed_file = {}
        response = {"path": path, "branch": branch, "commit_sha": prior_commit, "file_sha": committed_file.get("sha", "")}
    else:
        current_sha = payload.expected_sha
        try:
            result = client.commit_file(
                repository.owner, repository.name, path=path, branch=branch, content=payload.content,
                message=f"{payload.commit_message}\n\n{marker}", sha=current_sha,
            )
        except DomainError as exc:
            if exc.code == "gitea_conflict":
                _fail_intent(session, intent)
            else:
                _release_after_upstream_error(session, intent, exc)
            raise
        content = result.get("content") or {}
        commit = result.get("commit") or {}
        response = {
            "path": path, "branch": branch,
            "commit_sha": commit.get("sha") or result.get("commit_sha") or "",
            "file_sha": content.get("sha") or "",
        }
    return _finish_intent(session, principal, intent, data, response, "code.file_committed", "repository", repository.id, external_id=response["commit_sha"] or None)


def _repo_json_from_pr(repository: Repository, remote: dict, source_refs: list | None = None) -> PullRequest:
    head_data, base_data = remote.get("head") or {}, remote.get("base") or {}
    state = "closed" if remote.get("state") == "closed" or remote.get("merged") else "open"
    return PullRequest(
        id=new_id(), repository_id=repository.id, number=int(remote.get("number") or remote.get("id") or 0),
        title=(remote.get("title") or "")[:500], body=_strip_intent_markers(remote.get("body") or ""),
        state=state, head=head_data.get("ref") or remote.get("head_branch") or "",
        base=base_data.get("ref") or remote.get("base_branch") or "",
        web_url=_safe_upstream_url(remote.get("html_url") or remote.get("url")),
        head_sha=head_data.get("sha") or remote.get("head_sha") or "",
        source_refs=source_refs or [], created_at=_parse_time(remote.get("created_at")), updated_at=_parse_time(remote.get("updated_at")),
    )


def _strip_intent_markers(body: str) -> str:
    return re.sub(r"\n?<!-- ordivant-intent:[0-9a-f-]+ -->", "", body).rstrip()


def _sync_pull(session: Session, repository: Repository, remote: dict) -> PullRequest:
    number = int(remote.get("number") or 0)
    existing = session.scalar(select(PullRequest).where(PullRequest.repository_id == repository.id, PullRequest.number == number))
    pull = _repo_json_from_pr(repository, remote, existing.source_refs if existing else [])
    if existing:
        existing.title, existing.body, existing.state = pull.title, pull.body, pull.state
        existing.head, existing.base, existing.web_url, existing.head_sha = pull.head, pull.base, pull.web_url, pull.head_sha
        existing.updated_at = pull.updated_at
        return existing
    session.add(pull)
    session.flush()
    return pull


def list_pulls(session: Session, principal: Principal, repository_id: str) -> list[dict]:
    repository, _ = require_repository(session, principal, repository_id)
    config = load_gitea_config()
    if config is None:
        cached = session.scalars(select(PullRequest).where(PullRequest.repository_id == repository.id).order_by(PullRequest.number)).all()
        return [pull_json(item) for item in cached]
    client = GiteaClient(config)
    remote = client.pulls(repository.owner, repository.name)
    result = []
    for item in remote:
        result.append(pull_json(_sync_pull(session, repository, item)))
    session.commit()
    return result


def create_pull(session: Session, principal: Principal, repository_id: str, route: str, key: str, payload: PullRequestCreate) -> dict:
    repository, project = require_repository(session, principal, repository_id, write=True)
    head, base = _require_safe_ref(payload.head), _require_safe_ref(payload.base)
    data = payload.model_dump(mode="json")
    cached = _cached(session, principal, route, key, data)
    if cached is not None:
        return cached
    client = _gitea()
    intent = _prepare_intent(session, principal, route, key, data, project.id, repository.id, "create_pull")
    if intent.state == "complete" and intent.result_json:
        return intent.result_json
    marker = _commit_marker(intent.id)
    try:
        remote_pulls = client.pulls(repository.owner, repository.name)
    except DomainError as exc:
        _release_after_upstream_error(session, intent, exc)
        raise
    prior = None
    same_pair = None
    for item in remote_pulls:
        item_head = (item.get("head") or {}).get("ref") or ""
        item_base = (item.get("base") or {}).get("ref") or ""
        if item_head == head and item_base == base:
            same_pair = item
            if marker in (item.get("body") or ""):
                prior = item
                break
    if prior is None and same_pair is not None:
        _fail_intent(session, intent)
        raise DomainError(409, "pull_exists", "A pull request already exists for this head and base")
    if prior is None:
        body = payload.body.rstrip()
        body = f"{body}\n\n{marker}" if body else marker
        try:
            prior = client.create_pull(repository.owner, repository.name, head=head, base=base, title=payload.title, body=body)
        except DomainError as exc:
            if exc.code == "gitea_conflict":
                _fail_intent(session, intent)
            else:
                _release_after_upstream_error(session, intent, exc)
            raise
    pull = _sync_pull(session, repository, prior)
    pull.source_refs = [item.model_dump(mode="json") for item in payload.source_refs]
    response = pull_json(pull)
    return _finish_intent(session, principal, intent, data, response, "code.pull_request_created", "pull_request", pull.id, external_id=str(pull.number))


def get_pull(session: Session, principal: Principal, repository_id: str, number: int) -> dict:
    repository, _ = require_repository(session, principal, repository_id)
    if load_gitea_config() is not None:
        remote = _gitea().pull(repository.owner, repository.name, number)
        pull = _sync_pull(session, repository, remote)
        session.commit()
    else:
        pull = session.scalar(select(PullRequest).where(PullRequest.repository_id == repository.id, PullRequest.number == number))
        if pull is None:
            raise DomainError(404, "not_found", "Pull request not found")
    checks = session.scalars(select(CheckReceipt).where(
        CheckReceipt.repository_id == repository.id, CheckReceipt.commit_sha == pull.head_sha,
    ).order_by(CheckReceipt.created_at.desc())).all()
    return {**pull_json(pull), "checks": [check_json(item) for item in checks]}


def _active_collaboration_actor(session: Session, principal: Principal, *, write: bool) -> Principal:
    actor = session.get(Principal, principal.id, populate_existing=True)
    if actor is None or not actor.active:
        raise DomainError(401, "unauthenticated", "Principal is no longer active")
    if write and actor.kind not in {"human", "agent"}:
        raise DomainError(403, "forbidden", "Only human and agent principals can collaborate on pull requests")
    return actor


def _live_pull(
    session: Session, repository: Repository, number: int,
) -> PullRequest:
    remote = _gitea().pull(repository.owner, repository.name, number)
    if not isinstance(remote, dict):
        raise DomainError(502, "gitea_invalid_pull_request", "Gitea returned an invalid pull request")
    if any(remote.get(name) is not None and not isinstance(remote.get(name), dict) for name in ("head", "base")):
        raise DomainError(502, "gitea_invalid_pull_request", "Gitea returned an invalid pull request")
    remote_number = remote.get("number") or remote.get("id")
    if str(remote_number) != str(number):
        raise DomainError(502, "gitea_invalid_pull_request", "Gitea returned an invalid pull request")
    head_sha = ((remote.get("head") or {}).get("sha") or remote.get("head_sha") or "")
    if not isinstance(head_sha, str) or not re.fullmatch(r"[a-fA-F0-9]{40,64}", head_sha):
        raise DomainError(502, "gitea_invalid_pull_request", "Gitea returned an invalid pull request head")
    try:
        pull = _sync_pull(session, repository, remote)
        session.commit()
        return pull
    except IntegrityError:
        session.rollback()
        pull = session.scalar(select(PullRequest).where(
            PullRequest.repository_id == repository.id, PullRequest.number == number,
        ))
        if pull is None:
            raise
        fresh = _repo_json_from_pr(repository, remote, pull.source_refs)
        pull.title, pull.body, pull.state = fresh.title, fresh.body, fresh.state
        pull.head, pull.base, pull.web_url, pull.head_sha = fresh.head, fresh.base, fresh.web_url, fresh.head_sha
        pull.updated_at = fresh.updated_at
        session.commit()
        return pull


def _collaboration_author(principal: Principal) -> dict:
    return {"id": principal.id, "name": principal.name, "kind": principal.kind}


def _pull_proposer(session: Session, pull: PullRequest) -> Principal | None:
    actor_id = session.scalar(select(AuditEvent.actor_id).where(
        AuditEvent.action == "code.pull_request_created",
        AuditEvent.entity_type == "pull_request",
        AuditEvent.entity_id == pull.id,
        AuditEvent.actor_id.is_not(None),
    ).order_by(AuditEvent.created_at.asc()))
    if actor_id is None:
        actor_id = session.scalar(select(OperationIntent.actor_id).where(
            OperationIntent.repository_id == pull.repository_id,
            OperationIntent.kind == "create_pull",
            OperationIntent.state == "complete",
            OperationIntent.external_id == str(pull.number),
        ).order_by(OperationIntent.created_at.asc()))
    return session.get(Principal, actor_id) if actor_id else None


def _pull_comment_json(session: Session, comment: PullRequestComment) -> dict:
    author = session.get(Principal, comment.author_id)
    return {
        "id": comment.id,
        "author": _collaboration_author(author),
        "body": comment.body,
        "created_at": _iso(comment.created_at),
    }


def _pull_review_json(session: Session, review: PullRequestReview, current_head_sha: str | None = None) -> dict:
    author = session.get(Principal, review.author_id)
    result = {
        "id": review.id,
        "author": _collaboration_author(author),
        "decision": review.decision,
        "comment": review.comment,
        "head_sha": review.head_sha,
        "created_at": _iso(review.created_at),
    }
    if current_head_sha is not None:
        result["is_current"] = review.head_sha.casefold() == current_head_sha.casefold()
    return result


def get_pull_collaboration(session: Session, principal: Principal, repository_id: str, number: int) -> dict:
    actor = _active_collaboration_actor(session, principal, write=False)
    repository, _ = require_repository(session, actor, repository_id)
    pull = _live_pull(session, repository, number)
    proposer = _pull_proposer(session, pull)
    comments = session.scalars(select(PullRequestComment).where(
        PullRequestComment.pull_request_id == pull.id,
    ).order_by(PullRequestComment.created_at.asc(), PullRequestComment.id.asc())).all()
    reviews = session.scalars(select(PullRequestReview).where(
        PullRequestReview.pull_request_id == pull.id,
    ).order_by(PullRequestReview.created_at.asc(), PullRequestReview.id.asc())).all()
    return {
        "pull_request_id": pull.id,
        "head_sha": pull.head_sha,
        "proposer": _collaboration_author(proposer) if proposer else None,
        "comments": [_pull_comment_json(session, item) for item in comments],
        "reviews": [_pull_review_json(session, item, pull.head_sha) for item in reviews],
    }


def comment_on_pull_request(
    session: Session, principal: Principal, repository_id: str, number: int,
    route: str, key: str, payload: PullRequestCommentCreate,
) -> dict:
    actor = _active_collaboration_actor(session, principal, write=True)
    repository, project = require_repository(session, actor, repository_id, write=True)
    data = payload.model_dump(mode="json")
    cached = _cached(session, actor, route, key, data)
    if cached is not None:
        return cached
    pull = _live_pull(session, repository, number)
    comment_id = new_id()

    def create():
        current_actor = _active_collaboration_actor(session, actor, write=True)
        require_repository(session, current_actor, repository_id, write=True)
        comment = PullRequestComment(
            id=comment_id, pull_request_id=pull.id, author_id=actor.id,
            body=payload.body, created_at=now_utc(),
        )
        session.add(comment)
        session.flush()
        return _pull_comment_json(session, comment)

    return _local_mutation(
        session, actor, route, key, data, "code.pull_request_comment_added",
        "pull_request_comment", comment_id, project.id, create,
    )


def review_pull_request(
    session: Session, principal: Principal, repository_id: str, number: int,
    route: str, key: str, payload: PullRequestReviewCreate,
) -> dict:
    actor = _active_collaboration_actor(session, principal, write=True)
    repository, project = require_repository(session, actor, repository_id, write=True)
    data = payload.model_dump(mode="json")
    cached = _cached(session, actor, route, key, data)
    if cached is not None:
        return cached
    pull = _live_pull(session, repository, number)
    if payload.expected_head_sha.casefold() != pull.head_sha.casefold():
        raise DomainError(409, "stale_pull_request_head", "The pull request head changed; reload it before reviewing")
    if payload.decision != "comment" and pull.state != "open":
        raise DomainError(409, "pull_request_closed", "Closed pull requests only accept comment reviews")
    proposer = _pull_proposer(session, pull)
    if payload.decision in {"approve", "request_changes"} and proposer and proposer.id == actor.id:
        raise DomainError(403, "self_review_forbidden", "Pull request proposers cannot approve or request changes on their own pull request")
    review_id = new_id()

    def create():
        current_actor = _active_collaboration_actor(session, actor, write=True)
        require_repository(session, current_actor, repository_id, write=True)
        review = PullRequestReview(
            id=review_id, pull_request_id=pull.id, author_id=actor.id,
            decision=payload.decision, comment=payload.comment,
            head_sha=pull.head_sha, created_at=now_utc(),
        )
        session.add(review)
        session.flush()
        return _pull_review_json(session, review)

    return _local_mutation(
        session, actor, route, key, data, "code.pull_request_review_recorded",
        "pull_request_review", review_id, project.id, create,
    )


def report_check(session: Session, principal: Principal, repository_id: str, route: str, key: str, payload: CheckCreate) -> dict:
    repository, project = require_repository(session, principal, repository_id, write=True)
    data = payload.model_dump(mode="json")
    cached = _cached(session, principal, route, key, data)
    if cached is not None:
        return cached
    client = _gitea()
    intent = _prepare_intent(session, principal, route, key, data, project.id, repository.id, "report_check")
    if intent.state == "complete" and intent.result_json:
        return intent.result_json
    marker = _commit_marker(intent.id)
    try:
        statuses = client.statuses(repository.owner, repository.name, payload.commit_sha)
    except DomainError as exc:
        _release_after_upstream_error(session, intent, exc)
        raise
    prior = next((item for item in statuses if marker in (item.get("description") or "")), None) if isinstance(statuses, list) else None
    if prior is None:
        try:
            remote = client.create_status(
                repository.owner, repository.name, sha=payload.commit_sha, context=payload.context,
                state=payload.state, description=f"{payload.description}\n{marker}".strip(), target_url=payload.target_url,
            )
        except DomainError as exc:
            if exc.code == "gitea_conflict":
                _fail_intent(session, intent)
            else:
                _release_after_upstream_error(session, intent, exc)
            raise
    else:
        remote = prior
    receipt = CheckReceipt(
        id=new_id(), repository_id=repository.id, commit_sha=payload.commit_sha, context=payload.context,
        state=payload.state, description=payload.description, target_url=payload.target_url,
        source="agent_reported", actor_id=principal.id, created_at=now_utc(),
    )
    session.add(receipt)
    response = check_json(receipt)
    return _finish_intent(session, principal, intent, data, response, "code.check_reported", "check", receipt.id, external_id=str(remote.get("id") or ""))


def list_events(session: Session, principal: Principal, project_id: str | None) -> list[dict]:
    if project_id:
        require_project(session, principal, project_id)
        stmt = select(AuditEvent).where(AuditEvent.project_id == project_id)
    else:
        allowed = select(Project.id).join(ScopeMembership, ScopeMembership.scope_id == Project.scope_id).where(
            ScopeMembership.principal_id == principal.id,
        )
        stmt = select(AuditEvent).where(AuditEvent.project_id.in_(allowed))
    events = session.scalars(stmt.order_by(AuditEvent.created_at.desc()).limit(200)).all()
    return [event_json(event) for event in events]


def process_webhook(session: Session, raw_body: bytes, signature: str | None, delivery_id: str | None, event_name: str | None, config: GiteaConfig | None = None) -> dict:
    config = config or load_gitea_config()
    if config is None:
        raise DomainError(503, "gitea_not_configured", "Gitea webhook is not configured")
    if len(raw_body) > 5_000_000:
        raise DomainError(413, "webhook_too_large", "Webhook payload is too large")
    expected = hmac.new(config.webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature.lower()):
        raise DomainError(401, "invalid_webhook_signature", "Gitea signature is invalid")
    if not delivery_id or len(delivery_id) > 255:
        raise DomainError(422, "invalid_delivery_id", "X-Gitea-Delivery is required")
    body_hash = hashlib.sha256(raw_body).hexdigest()
    previous = session.scalar(select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery_id))
    if previous:
        if previous.body_sha256 != body_hash:
            raise DomainError(409, "webhook_replay_conflict", "Delivery id was reused with a different body")
        return {"received": True, "duplicate": True}
    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DomainError(422, "invalid_webhook_json", "Webhook payload must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise DomainError(422, "invalid_webhook_json", "Webhook payload must be a JSON object")
    remote_repo = payload.get("repository")
    if not isinstance(remote_repo, dict):
        raise DomainError(422, "invalid_webhook_repository", "Webhook repository identity is invalid")
    remote_owner = remote_repo.get("owner")
    if not isinstance(remote_owner, dict):
        raise DomainError(422, "invalid_webhook_repository", "Webhook repository identity is invalid")
    owner_login, repo_name = remote_owner.get("login"), remote_repo.get("name")
    full_name = remote_repo.get("full_name")
    if (
        not isinstance(owner_login, str) or not owner_login or "/" in owner_login
        or not isinstance(repo_name, str) or not repo_name or "/" in repo_name
        or not isinstance(full_name, str) or full_name != f"{owner_login}/{repo_name}"
    ):
        raise DomainError(422, "invalid_webhook_repository", "Webhook repository identity is invalid")
    owner, name = full_name.split("/", 1)
    repository = session.scalar(select(Repository).where(Repository.owner == owner, Repository.name == name))
    event_value = (event_name or "unknown")[:100]
    delivery = WebhookDelivery(
        id=new_id(), delivery_id=delivery_id, body_sha256=body_hash, event=event_value,
        repository_id=repository.id if repository else None, created_at=now_utc(),
    )
    session.add(delivery)
    if repository:
        details: dict = {"delivery_id": delivery_id, "event": event_value}
        if event_value == "pull_request":
            pr_data = payload.get("pull_request")
            if not isinstance(pr_data, dict):
                raise DomainError(422, "invalid_webhook_pull_request", "Pull request webhook data is invalid")
            pull = _sync_pull(session, repository, pr_data)
            details["number"] = pull.number
            details["state"] = pull.state
            details["head_sha"] = pull.head_sha
            entity_type, entity_id = "pull_request", str(pull.number)
        elif event_value == "status":
            sha = payload.get("sha")
            if isinstance(sha, str) and re.fullmatch(r"[a-fA-F0-9]{40,64}", sha):
                receipt = CheckReceipt(
                    id=new_id(), repository_id=repository.id, commit_sha=sha, context=(payload.get("context") or "")[:255],
                    state=payload.get("state") if payload.get("state") in {"pending", "success", "failure", "error"} else "error",
                    description=(payload.get("description") or "")[:500], target_url=_safe_upstream_url(payload.get("target_url")) or None,
                    source="gitea_webhook", actor_id=None, created_at=now_utc(),
                )
                session.add(receipt)
                details["commit_sha"] = sha
            entity_type, entity_id = "repository", repository.id
        elif event_value == "push":
            after = payload.get("after")
            if isinstance(after, str) and re.fullmatch(r"[a-fA-F0-9]{40,64}", after):
                details["after"] = after
            ref = payload.get("ref")
            if isinstance(ref, str) and len(ref) <= 255:
                details["ref"] = ref
            entity_type, entity_id = "repository", repository.id
        else:
            entity_type, entity_id = "repository", repository.id
        _event(session, repository.project_id, None, f"code.gitea_{event_value}", entity_type, entity_id, details)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        previous = session.scalar(select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery_id))
        if previous and previous.body_sha256 == body_hash:
            return {"received": True, "duplicate": True}
        raise DomainError(409, "webhook_replay_conflict", "Delivery id was reused")
    return {"received": True, "duplicate": False}
