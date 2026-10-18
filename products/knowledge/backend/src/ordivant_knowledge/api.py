from __future__ import annotations

import hashlib
import ipaddress
import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .errors import conflict, forbidden, not_found
from .config import authorized_dev_proxy
from .identity import bearer_principal, cookie_principal, identity_configured, require_identity_admin_for_scope_creation
from .models import (
    AuditEvent,
    Decision,
    Document,
    DocumentComment,
    DocumentVersion,
    KnowledgeSpace,
    Principal,
    SpaceMembership,
)
from .schemas import (
    DocumentCommentCreate,
    DocumentCommentPatch,
    DecisionCreate,
    DocumentCreate,
    DocumentOrganizationPatch,
    DocumentRestore,
    DraftPublish,
    DraftUpdate,
    LocalSessionCreate,
    Reference,
    SpaceCreate,
    SpaceTemplateCreate,
    VersionPublish,
)
from .security import (
    require_current_scope,
    PrincipalContext,
    authenticate,
    expires_after,
    issue_token,
    new_id,
    now_iso,
    principal_for_token,
    principal_json,
    require_manager,
    require_scope,
    require_writer,
)
from .service import (
    add_audit,
    document_context,
    document_uri,
    document_view,
    decision_view,
    mutate,
    reference_list,
    space_view,
    version_view,
)
from .drafts import apply_document_draft_update, get_document_draft, publish_document_draft, synchronize_legacy_publish
from .authoring import (
    create_comment,
    create_template,
    diff_versions,
    list_comments,
    list_templates,
    organize_document,
    resolve_comment,
    restore_version,
)


router = APIRouter(prefix="/api")


def get_session(request: Request):
    with request.app.state.session_factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


async def get_principal(
    request: Request,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> PrincipalContext:
    if authorization is not None:
        return await bearer_principal(request, session) or authenticate(session, authorization)
    principal = await cookie_principal(request, session)
    if principal is not None:
        return principal
    return authenticate(session, None)


PrincipalDep = Annotated[PrincipalContext, Depends(get_principal)]


def _document(session: Session, principal: PrincipalContext, document_id: str, *, lock: bool = False) -> Document:
    statement = select(Document).where(Document.id == document_id)
    if lock and session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update().execution_options(populate_existing=True)
    document = session.scalar(statement)
    if document is None:
        raise not_found()
    require_scope(session, principal, document.space_id)
    return document


def _must_be_loopback(request: Request) -> None:
    host = request.client.host if request.client else ""
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host.lower() == "localhost"
    if not loopback and not authorized_dev_proxy(request.headers.get("X-Ordivant-Dev-Proxy")):
        raise forbidden("local-session 僅接受 loopback 或授權的 development proxy")


def _content_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _reference_models(values: list[Reference]) -> list[dict[str, str]]:
    return [value.model_dump(mode="json") for value in values]


@router.get("/health")
def health(request: Request) -> dict[str, str]:
    engine = request.app.state.engine
    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")
    return {
        "status": "ok",
        "product": "knowledge",
        "database": engine.dialect.name,
        "mode": request.app.state.settings.mode,
    }


@router.post("/auth/local-session")
def create_local_session(
    body: LocalSessionCreate,
    request: Request,
    session: SessionDep,
) -> dict[str, object]:
    if identity_configured():
        raise forbidden("Identity login is configured; local-session is disabled")
    if request.app.state.settings.mode != "development":
        raise forbidden("production 已停用 local-session")
    _must_be_loopback(request)
    statement = select(Principal).where(Principal.active.is_(True), Principal.kind == "human", Principal.role == "manager")
    selected_id = os.getenv("ORDIVANT_KNOWLEDGE_LOCAL_PRINCIPAL_ID") or body.principal_id
    if selected_id:
        statement = statement.where(Principal.id == selected_id)
    principal = session.scalar(statement.order_by(Principal.name, Principal.id))
    if principal is None:
        raise not_found()
    token = issue_token(session, principal.id, expires_at=expires_after(8 * 60 * 60))
    session.commit()
    context = principal_for_token(session, token)
    if context is None:
        raise RuntimeError("The local session token could not be read after issuance")
    return {"token": token, "principal": principal_json(context)}


@router.get("/me")
def me(principal: PrincipalDep) -> dict[str, object]:
    return principal_json(principal)


@router.get("/spaces")
def list_spaces(session: SessionDep, principal: PrincipalDep) -> list[dict[str, object]]:
    if not principal.scope_ids:
        return []
    spaces = session.scalars(
        select(KnowledgeSpace)
        .where(
            KnowledgeSpace.id.in_(principal.scope_ids),
            KnowledgeSpace.organization_id == principal.organization_id,
        )
        .order_by(KnowledgeSpace.key, KnowledgeSpace.id)
    )
    return [space_view(space) for space in spaces]


@router.post("/spaces", status_code=201)
def create_space(
    body: SpaceCreate,
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    require_manager(principal)
    require_identity_admin_for_scope_creation(session, principal)

    def action() -> dict[str, object]:
        existing = session.scalar(
            select(KnowledgeSpace).where(
                KnowledgeSpace.organization_id == principal.organization_id,
                KnowledgeSpace.key == body.key,
            )
        )
        if existing is not None:
            raise conflict("space_key_conflict", "此 organization 已有相同的 space key")
        space = KnowledgeSpace(
            id=new_id(),
            key=body.key,
            name=body.name,
            description=body.description,
            organization_id=principal.organization_id,
            created_at=now_iso(),
        )
        session.add(space)
        session.flush()
        session.add(SpaceMembership(id=new_id(), principal_id=principal.id, space_id=space.id))
        add_audit(
            session,
            principal,
            space_id=space.id,
            action="knowledge.space.created",
            entity_type="space",
            entity_id=space.id,
            data={"key": space.key},
        )
        session.flush()
        return space_view(space)

    return mutate(
        session,
        principal,
        route=request.url.path,
        idempotency_key=idempotency_key,
        body=body.model_dump(mode="json"),
        status_code=201,
        action=action,
        authorize_replay=lambda response: require_scope(session, principal, str(response.get("id", ""))),
    )


@router.get("/spaces/{space_id}")
def get_space(space_id: str, session: SessionDep, principal: PrincipalDep) -> dict[str, object]:
    return space_view(require_scope(session, principal, space_id))


@router.get("/documents")
def search_documents(
    session: SessionDep,
    principal: PrincipalDep,
    space_id: Annotated[str | None, Query(max_length=80)] = None,
    q: Annotated[str | None, Query(max_length=300)] = None,
    tag: Annotated[str | None, Query(max_length=80)] = None,
    include_archived: bool = False,
) -> list[dict[str, object]]:
    if space_id is not None:
        require_scope(session, principal, space_id)
        visible_spaces = [space_id]
    else:
        visible_spaces = sorted(principal.scope_ids)
    if not visible_spaces:
        return []

    statement = (
        select(Document, DocumentVersion)
        .join(
            DocumentVersion,
            (DocumentVersion.document_id == Document.id)
            & (DocumentVersion.version == Document.current_version),
        )
        .where(Document.space_id.in_(visible_spaces))
    )
    if not include_archived:
        statement = statement.where(Document.archived.is_(False))
    if q:
        statement = statement.where(
            or_(
                DocumentVersion.title.contains(q, autoescape=True),
                DocumentVersion.body.contains(q, autoescape=True),
            )
        )
    statement = statement.order_by(Document.updated_at.desc(), Document.id).limit(100)
    rows = session.execute(statement).all()
    result: list[dict[str, object]] = []
    for document, version in rows:
        if tag and tag not in document.tags:
            continue
        excerpt = version.body
        if q:
            offset = version.body.casefold().find(q.casefold())
            if offset >= 0:
                start = max(0, offset - 120)
                end = min(len(version.body), offset + len(q) + 180)
                excerpt = version.body[start:end]
        result.append(
            {
                **document_view(document),
                "version": version.version,
                "uri": document_uri(document.space_id, document.id, version.version),
                "snippet": excerpt,
                "content_sha256": version.content_sha256,
            }
        )
    return result


@router.post("/documents", status_code=201)
def create_document(
    body: DocumentCreate,
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    require_scope(session, principal, body.space_id)
    require_writer(principal)
    source_refs = _reference_models(body.source_refs)

    def action() -> dict[str, object]:
        from .authoring import lock_tree
        lock_tree(session, body.space_id)
        current = require_current_scope(session, principal, body.space_id, lock=True)
        require_writer(current)
        now = now_iso()
        document = Document(
            id=new_id(),
            space_id=body.space_id,
            parent_id=body.parent_id,
            archived=False,
            title=body.title,
            summary=body.summary,
            tags=body.tags,
            current_version=1,
            created_at=now,
            updated_at=now,
        )
        if body.parent_id:
            parent = session.get(Document, body.parent_id)
            if parent is None:
                raise not_found()
            require_scope(session, principal, parent.space_id)
            if parent.space_id != body.space_id:
                raise not_found()
            if parent.archived:
                raise conflict("parent_archived", "請先取消封存父文件，再建立子文件")
        session.add(document)
        session.flush()
        version = DocumentVersion(
            id=new_id(),
            document_id=document.id,
            version=1,
            title=body.title,
            body=body.body,
            change_summary=body.change_summary,
            author_id=principal.id,
            content_sha256=_content_hash(body.body),
            source_refs=source_refs,
            created_at=now,
        )
        session.add(version)
        session.flush()
        add_audit(
            session,
            principal,
            space_id=body.space_id,
            action="knowledge.document.created",
            entity_type="document",
            entity_id=document.id,
            data={"version": 1, "content_sha256": version.content_sha256, "source_refs": source_refs},
        )
        session.flush()
        return document_context(session, document)

    return mutate(
        session,
        principal,
        route=request.url.path,
        idempotency_key=idempotency_key,
        body=body.model_dump(mode="json"),
        status_code=201,
        action=action,
    )


@router.get("/documents/{document_id}")
def get_document(document_id: str, session: SessionDep, principal: PrincipalDep) -> dict[str, object]:
    return document_context(session, _document(session, principal, document_id))


@router.patch("/documents/{document_id}/organization")
def patch_document_organization(
    document_id: str,
    body: DocumentOrganizationPatch,
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    document = _document(session, principal, document_id)
    require_writer(principal)
    fields = body.model_dump(mode="json", exclude_unset=True)
    return mutate(
        session,
        principal,
        route=request.url.path,
        idempotency_key=idempotency_key,
        body=fields,
        status_code=200,
        action=lambda: organize_document(
            session,
            principal,
            document.id,
            parent_supplied="parent_id" in fields,
            parent_id=body.parent_id,
            archived=body.archived,
        ),
        authorize_replay=lambda _response: _document(session, principal, document_id),
    )


@router.get("/documents/{document_id}/comments")
def get_document_comments(document_id: str, session: SessionDep, principal: PrincipalDep) -> list[dict[str, object]]:
    return list_comments(session, principal, document_id)


@router.post("/documents/{document_id}/comments", status_code=201)
def post_document_comment(
    document_id: str,
    body: DocumentCommentCreate,
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    _document(session, principal, document_id)
    require_writer(principal)
    anchor = body.anchor.model_dump(mode="json") if body.anchor else None
    return mutate(
        session,
        principal,
        route=request.url.path,
        idempotency_key=idempotency_key,
        body=body.model_dump(mode="json"),
        status_code=201,
        action=lambda: create_comment(
            session,
            principal,
            document_id,
            body=body.body,
            anchor=anchor,
            parent_id=body.parent_id,
        ),
        authorize_replay=lambda _response: _document(session, principal, document_id),
    )


@router.patch("/document-comments/{comment_id}")
def patch_document_comment(
    comment_id: str,
    body: DocumentCommentPatch,
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    comment = session.get(DocumentComment, comment_id)
    if comment is None:
        raise not_found()
    _document(session, principal, comment.document_id)
    require_writer(principal)
    return mutate(
        session,
        principal,
        route=request.url.path,
        idempotency_key=idempotency_key,
        body=body.model_dump(mode="json"),
        status_code=200,
        action=lambda: resolve_comment(session, principal, comment_id, resolved=body.resolved),
        authorize_replay=lambda _response: _document(
            session,
            principal,
            (session.get(DocumentComment, comment_id) or comment).document_id,
        ),
    )


@router.get("/spaces/{space_id}/templates")
def get_space_templates(space_id: str, session: SessionDep, principal: PrincipalDep) -> list[dict[str, object]]:
    return list_templates(session, principal, space_id)


@router.post("/spaces/{space_id}/templates", status_code=201)
def post_space_template(
    space_id: str,
    body: SpaceTemplateCreate,
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    require_scope(session, principal, space_id)
    require_writer(principal)
    return mutate(
        session,
        principal,
        route=request.url.path,
        idempotency_key=idempotency_key,
        body=body.model_dump(mode="json"),
        status_code=201,
        action=lambda: create_template(
            session,
            principal,
            space_id,
            name=body.name,
            description=body.description,
            body=body.body,
        ),
        authorize_replay=lambda _response: require_scope(session, principal, space_id),
    )


@router.get("/documents/{document_id}/diff")
def get_document_diff(
    document_id: str,
    session: SessionDep,
    principal: PrincipalDep,
    from_version: Annotated[int, Query(ge=1)],
    to_version: Annotated[int, Query(ge=1)],
) -> dict[str, object]:
    return diff_versions(session, principal, document_id, from_version, to_version)


@router.post("/documents/{document_id}/restore", status_code=201)
def post_document_restore(
    document_id: str,
    body: DocumentRestore,
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    _document(session, principal, document_id, lock=True)
    require_writer(principal)
    return mutate(
        session,
        principal,
        route=request.url.path,
        idempotency_key=idempotency_key,
        body=body.model_dump(mode="json"),
        status_code=201,
        action=lambda: restore_version(
            session,
            principal,
            document_id,
            version_number=body.version,
            expected_current_version=body.expected_current_version,
            change_summary=body.change_summary,
        ),
        authorize_replay=lambda _response: _document(session, principal, document_id),
    )


@router.get("/documents/{document_id}/draft")
def get_shared_document_draft(
    document_id: str,
    session: SessionDep,
    principal: PrincipalDep,
) -> dict[str, object]:
    result = get_document_draft(session, principal, document_id)
    session.commit()
    return result


@router.post("/documents/{document_id}/draft/updates")
def apply_shared_document_draft_update(
    document_id: str,
    body: DraftUpdate,
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    return mutate(
        session,
        principal,
        route=request.url.path,
        idempotency_key=idempotency_key,
        body=body.model_dump(mode="json"),
        status_code=200,
        action=lambda: apply_document_draft_update(session, principal, document_id, body.update),
        authorize_replay=lambda _response: _document(session, principal, document_id),
    )


@router.post("/documents/{document_id}/draft/publish", status_code=201)
def publish_shared_document_draft(
    document_id: str,
    body: DraftPublish,
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    source_refs = _reference_models(body.source_refs)
    return mutate(
        session,
        principal,
        route=request.url.path,
        idempotency_key=idempotency_key,
        body=body.model_dump(mode="json"),
        status_code=201,
        action=lambda: publish_document_draft(
            session,
            principal,
            document_id,
            expected_revision=body.expected_revision,
            change_summary=body.change_summary,
            title=body.title,
            source_refs=source_refs,
        ),
        authorize_replay=lambda _response: _document(session, principal, document_id),
    )


@router.get("/documents/{document_id}/versions")
def list_document_versions(document_id: str, session: SessionDep, principal: PrincipalDep) -> list[dict[str, object]]:
    document = _document(session, principal, document_id)
    versions = session.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version.desc())
    )
    return [version_view(version, document.space_id) for version in versions]


@router.get("/documents/{document_id}/versions/{version_number}")
def get_document_version(
    document_id: str,
    version_number: int,
    session: SessionDep,
    principal: PrincipalDep,
) -> dict[str, object]:
    document = _document(session, principal, document_id)
    version = session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version == version_number,
        )
    )
    if version is None:
        raise not_found()
    return version_view(version, document.space_id)


@router.post("/documents/{document_id}/versions", status_code=201)
def publish_document_version(
    document_id: str,
    body: VersionPublish,
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    document = _document(session, principal, document_id, lock=True)
    require_writer(principal)
    source_refs = _reference_models(body.source_refs)

    def action() -> dict[str, object]:
        current = session.scalar(
            select(Document)
            .where(Document.id == document.id)
            .with_for_update()
            .execution_options(populate_existing=True)
            if session.get_bind().dialect.name == "postgresql"
            else select(Document).where(Document.id == document.id)
        )
        if current is None:
            raise not_found()
        if current.current_version != body.expected_version:
            raise conflict("stale_version", f"expected_version={body.expected_version} 不符合目前版本 {current.current_version}")
        next_number = current.current_version + 1
        title = body.title or current.title
        version = DocumentVersion(
            id=new_id(),
            document_id=current.id,
            version=next_number,
            title=title,
            body=body.body,
            change_summary=body.change_summary,
            author_id=principal.id,
            content_sha256=_content_hash(body.body),
            source_refs=source_refs,
            created_at=now_iso(),
        )
        session.add(version)
        session.flush()
        current.title = title
        current.current_version = next_number
        current.updated_at = version.created_at
        synchronize_legacy_publish(
            session,
            principal,
            current,
            title=title,
            body=body.body,
            base_version=next_number,
        )
        add_audit(
            session,
            principal,
            space_id=current.space_id,
            action="knowledge.document.version_published",
            entity_type="document_version",
            entity_id=version.id,
            data={"document_id": current.id, "version": next_number, "content_sha256": version.content_sha256, "source_refs": source_refs},
        )
        session.flush()
        return version_view(version, current.space_id)

    return mutate(
        session,
        principal,
        route=request.url.path,
        idempotency_key=idempotency_key,
        body=body.model_dump(mode="json"),
        status_code=201,
        action=action,
    )


@router.get("/decisions")
def list_decisions(
    session: SessionDep,
    principal: PrincipalDep,
    space_id: Annotated[str | None, Query(max_length=80)] = None,
) -> list[dict[str, object]]:
    if space_id:
        require_scope(session, principal, space_id)
        visible_spaces = [space_id]
    else:
        visible_spaces = sorted(principal.scope_ids)
    if not visible_spaces:
        return []
    decisions = session.scalars(
        select(Decision)
        .where(Decision.space_id.in_(visible_spaces))
        .order_by(Decision.created_at.desc(), Decision.id)
        .limit(200)
    )
    return [decision_view(decision) for decision in decisions]


@router.post("/decisions", status_code=201)
def create_decision(
    body: DecisionCreate,
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    require_scope(session, principal, body.space_id)
    require_writer(principal)
    if body.document_id:
        document = _document(session, principal, body.document_id)
        if document.space_id != body.space_id:
            raise not_found()
    source_refs = _reference_models(body.source_refs)

    def action() -> dict[str, object]:
        decision = Decision(
            id=new_id(),
            space_id=body.space_id,
            document_id=body.document_id,
            title=body.title,
            body=body.body,
            source_refs=source_refs,
            actor_id=principal.id,
            created_at=now_iso(),
        )
        session.add(decision)
        session.flush()
        add_audit(
            session,
            principal,
            space_id=body.space_id,
            action="knowledge.decision.recorded",
            entity_type="decision",
            entity_id=decision.id,
            data={"document_id": decision.document_id, "source_refs": source_refs},
        )
        session.flush()
        return decision_view(decision)

    return mutate(
        session,
        principal,
        route=request.url.path,
        idempotency_key=idempotency_key,
        body=body.model_dump(mode="json"),
        status_code=201,
        action=action,
    )


@router.get("/events")
def list_events(
    session: SessionDep,
    principal: PrincipalDep,
    space_id: Annotated[str | None, Query(max_length=80)] = None,
) -> list[dict[str, Any]]:
    if space_id:
        require_scope(session, principal, space_id)
        visible_spaces = [space_id]
    else:
        visible_spaces = sorted(principal.scope_ids)
    if not visible_spaces:
        return []
    events = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.space_id.in_(visible_spaces))
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id)
        .limit(200)
    )
    return [
        {
            "id": event.id,
            "space_id": event.space_id,
            "actor_id": event.actor_id,
            "action": event.action,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "data": event.data,
            "created_at": event.created_at,
        }
        for event in events
    ]
