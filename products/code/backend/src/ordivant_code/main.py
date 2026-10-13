from __future__ import annotations

import ipaddress
import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import app_mode, load_gitea_config
from .db import Base, SessionLocal, engine, get_db
from .errors import DomainError
from . import models  # noqa: F401
from .identity import cookie_principal, identity_configured, require_identity_admin_for_scope_creation
from .schemas import (
    BranchCreate,
    CheckCreate,
    FileCommit,
    LocalSessionInput,
    ProjectCreate,
    PullRequestCommentCreate,
    PullRequestCreate,
    PullRequestReviewCreate,
    RepositoryCreate,
    WebhookResult,
)
from .security import authenticate, issue_token, new_id, now_utc, principal_json
from .service import (
    create_branch,
    create_project,
    create_pull,
    create_repository,
    commit_file,
    comment_on_pull_request,
    get_project,
    get_pull,
    get_pull_collaboration,
    list_events,
    list_projects,
    list_pulls,
    list_repositories,
    process_webhook,
    report_check,
    review_pull_request,
)
from .models import Organization, Principal, ScopeMembership


def _get_database(request: Request):
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


async def _current_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    session: Session = Depends(_get_database),
) -> Principal:
    if authorization is not None:
        return authenticate(session, authorization)
    principal = await cookie_principal(request, session)
    if principal is not None:
        return principal
    return authenticate(session, None)


def _dev_proxy_secret() -> str | None:
    secret_path = os.getenv("ORDIVANT_DEV_PROXY_TOKEN_FILE")
    if secret_path:
        try:
            secret = Path(secret_path).read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return secret or None
    return os.getenv("ORDIVANT_DEV_PROXY_TOKEN") or None


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Ordivant Code API", version="0.2.0", lifespan=lifespan)


@app.exception_handler(DomainError)
def domain_error_handler(_: Request, exc: DomainError):
    return JSONResponse(status_code=exc.status_code, content={"detail": {"code": exc.code, "message": exc.message}})


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "product": "code",
        "database": "postgresql" if engine.dialect.name == "postgresql" else "sqlite",
        "mode": app_mode(),
        "gitea_configured": load_gitea_config() is not None,
    }


@app.post("/api/auth/local-session")
def local_session(
    body: LocalSessionInput,
    request: Request,
    proxy_token: str | None = Header(default=None, alias="X-Ordivant-Dev-Proxy"),
    session: Session = Depends(_get_database),
):
    if identity_configured():
        raise DomainError(403, "identity_configured", "Identity login is configured; local sessions are disabled")
    if app_mode() != "development":
        raise DomainError(403, "local_session_disabled", "Local sessions are disabled outside development mode")
    host = request.client.host if request.client else ""
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    expected_proxy_token = _dev_proxy_secret()
    proxy_authorized = bool(
        expected_proxy_token and proxy_token
        and hmac.compare_digest(expected_proxy_token.encode("utf-8"), proxy_token.encode("utf-8"))
    )
    if not loopback and not proxy_authorized:
        raise DomainError(403, "loopback_required", "Local session is available only over loopback or an authorized development proxy")
    organization = session.query(Organization).order_by(Organization.created_at).first()
    if organization is None:
        organization = Organization(id=new_id(), name="Local development", created_at=now_utc())
        session.add(organization)
        session.flush()
    principal = Principal(
        id=new_id(), organization_id=organization.id, name=body.name, kind="human", role="manager",
        active=True, created_at=now_utc(),
    )
    session.add(principal)
    session.flush()
    scope_ids = session.scalars(
        select(ScopeMembership.scope_id).join(models.Scope, models.Scope.id == ScopeMembership.scope_id)
        .where(models.Scope.organization_id == organization.id).distinct()
    ).all()
    for scope_id in scope_ids:
        session.add(ScopeMembership(id=new_id(), principal_id=principal.id, scope_id=scope_id, role="manager"))
    token = issue_token(session, principal.id)
    session.commit()
    return {"token": token, "principal": principal_json(session, principal)}


@app.get("/api/me")
def me(principal: Principal = Depends(_current_principal), session: Session = Depends(_get_database)):
    return principal_json(session, principal)


@app.get("/api/projects")
def projects(principal: Principal = Depends(_current_principal), session: Session = Depends(_get_database)):
    return list_projects(session, principal)


@app.post("/api/projects")
def new_project(
    payload: ProjectCreate,
    request: Request,
    key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(_current_principal),
    session: Session = Depends(_get_database),
):
    require_identity_admin_for_scope_creation(session, principal)
    return create_project(session, principal, request.url.path, key or "", payload)


@app.get("/api/projects/{project_id}")
def project(project_id: str, principal: Principal = Depends(_current_principal), session: Session = Depends(_get_database)):
    return get_project(session, principal, project_id)


@app.get("/api/repositories")
def repositories(
    project_id: str = Query(min_length=1),
    principal: Principal = Depends(_current_principal),
    session: Session = Depends(_get_database),
):
    return list_repositories(session, principal, project_id)


@app.post("/api/repositories")
def new_repository(
    payload: RepositoryCreate,
    request: Request,
    key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(_current_principal),
    session: Session = Depends(_get_database),
):
    return create_repository(session, principal, request.url.path, key or "", payload)


@app.post("/api/repositories/{repository_id}/branches")
def branch(
    repository_id: str,
    payload: BranchCreate,
    request: Request,
    key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(_current_principal),
    session: Session = Depends(_get_database),
):
    return create_branch(session, principal, repository_id, request.url.path, key or "", payload)


@app.post("/api/repositories/{repository_id}/files")
def file_commit(
    repository_id: str,
    payload: FileCommit,
    request: Request,
    key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(_current_principal),
    session: Session = Depends(_get_database),
):
    return commit_file(session, principal, repository_id, request.url.path, key or "", payload)


@app.get("/api/repositories/{repository_id}/pulls")
def pulls(repository_id: str, principal: Principal = Depends(_current_principal), session: Session = Depends(_get_database)):
    return list_pulls(session, principal, repository_id)


@app.post("/api/repositories/{repository_id}/pulls")
def new_pull(
    repository_id: str,
    payload: PullRequestCreate,
    request: Request,
    key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(_current_principal),
    session: Session = Depends(_get_database),
):
    return create_pull(session, principal, repository_id, request.url.path, key or "", payload)


@app.get("/api/repositories/{repository_id}/pulls/{number}")
def pull(
    repository_id: str,
    number: int,
    principal: Principal = Depends(_current_principal),
    session: Session = Depends(_get_database),
):
    return get_pull(session, principal, repository_id, number)


@app.get("/api/repositories/{repository_id}/pulls/{number}/collaboration")
def pull_collaboration(
    repository_id: str,
    number: int,
    principal: Principal = Depends(_current_principal),
    session: Session = Depends(_get_database),
):
    return get_pull_collaboration(session, principal, repository_id, number)


@app.post("/api/repositories/{repository_id}/pulls/{number}/comments")
def pull_comment(
    repository_id: str,
    number: int,
    payload: PullRequestCommentCreate,
    request: Request,
    key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(_current_principal),
    session: Session = Depends(_get_database),
):
    return comment_on_pull_request(session, principal, repository_id, number, request.url.path, key or "", payload)


@app.post("/api/repositories/{repository_id}/pulls/{number}/reviews")
def pull_review(
    repository_id: str,
    number: int,
    payload: PullRequestReviewCreate,
    request: Request,
    key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(_current_principal),
    session: Session = Depends(_get_database),
):
    return review_pull_request(session, principal, repository_id, number, request.url.path, key or "", payload)


@app.post("/api/repositories/{repository_id}/checks")
def check(
    repository_id: str,
    payload: CheckCreate,
    request: Request,
    key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(_current_principal),
    session: Session = Depends(_get_database),
):
    return report_check(session, principal, repository_id, request.url.path, key or "", payload)


@app.post("/api/webhooks/gitea", response_model=WebhookResult)
async def gitea_webhook(
    request: Request,
    signature: str | None = Header(default=None, alias="X-Gitea-Signature"),
    delivery: str | None = Header(default=None, alias="X-Gitea-Delivery"),
    event_name: str | None = Header(default=None, alias="X-Gitea-Event"),
    session: Session = Depends(_get_database),
):
    body = await request.body()
    return process_webhook(session, body, signature, delivery, event_name)


@app.get("/api/events")
def events(
    project_id: str | None = None,
    principal: Principal = Depends(_current_principal),
    session: Session = Depends(_get_database),
):
    return list_events(session, principal, project_id)
