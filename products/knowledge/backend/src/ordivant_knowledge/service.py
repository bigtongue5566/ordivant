from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .errors import bad_request, conflict
from .models import AuditEvent, Decision, Document, DocumentVersion, IdempotencyRecord
from .security import PrincipalContext, new_id, now_iso


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def request_hash(body: object) -> str:
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def document_uri(space_id: str, document_id: str, version: int) -> str:
    return f"ordivant://knowledge/spaces/{space_id}/documents/{document_id}/versions/{version}"


def reference_list(values: list[object]) -> list[dict[str, str]]:
    return [item.model_dump(mode="json") for item in values]  # type: ignore[attr-defined]


def space_view(space) -> dict[str, object]:
    return {
        "id": space.id,
        "key": space.key,
        "name": space.name,
        "description": space.description,
        "organization_id": space.organization_id,
        "created_at": space.created_at,
    }


def document_view(document: Document) -> dict[str, object]:
    return {
        "id": document.id,
        "space_id": document.space_id,
        "parent_id": document.parent_id,
        "archived": document.archived,
        "title": document.title,
        "summary": document.summary,
        "tags": list(document.tags),
        "current_version": document.current_version,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


def version_view(version: DocumentVersion, space_id: str) -> dict[str, object]:
    return {
        "id": version.id,
        "document_id": version.document_id,
        "version": version.version,
        "title": version.title,
        "body": version.body,
        "change_summary": version.change_summary,
        "author_id": version.author_id,
        "content_sha256": version.content_sha256,
        "source_refs": version.source_refs,
        "created_at": version.created_at,
        "uri": document_uri(space_id, version.document_id, version.version),
    }


def decision_view(decision: Decision) -> dict[str, object]:
    return {
        "id": decision.id,
        "space_id": decision.space_id,
        "document_id": decision.document_id,
        "title": decision.title,
        "body": decision.body,
        "source_refs": decision.source_refs,
        "actor_id": decision.actor_id,
        "created_at": decision.created_at,
    }


def document_context(session: Session, document: Document) -> dict[str, object]:
    versions = list(
        session.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version.desc())
        )
    )
    latest = next((item for item in versions if item.version == document.current_version), None)
    if latest is None:
        raise RuntimeError("The document current version is missing")
    decisions = list(
        session.scalars(
            select(Decision)
            .where(Decision.document_id == document.id)
            .order_by(Decision.created_at.desc(), Decision.id)
        )
    )
    return {
        "document": document_view(document),
        "version": version_view(latest, document.space_id),
        "history": [version_view(item, document.space_id) for item in versions],
        "decisions": [decision_view(item) for item in decisions],
    }


def add_audit(
    session: Session,
    principal: PrincipalContext,
    *,
    space_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    data: dict[str, object],
) -> None:
    item = AuditEvent(
        id=new_id(),
        space_id=space_id,
        actor_id=principal.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        data=data,
        created_at=now_iso(),
    )
    session.add(item)
    document_id = entity_id if entity_type == "document" else data.get("document_id")
    document = session.get(Document, document_id) if isinstance(document_id, str) else None
    if document is not None and document.space_id == space_id:
        from .collaboration_features import emit

        emit(session, "document", document.id, item.id, principal.id, action)


def mutate(
    session: Session,
    principal: PrincipalContext,
    *,
    route: str,
    idempotency_key: str | None,
    body: object,
    status_code: int,
    action: Callable[[], dict[str, object]],
    authorize_replay: Callable[[dict[str, object]], None] | None = None,
) -> JSONResponse:
    if idempotency_key is not None and (not idempotency_key.strip() or len(idempotency_key) > 200):
        raise bad_request("invalid_idempotency_key", "Idempotency-Key must contain 1 to 200 characters")
    digest = request_hash(body)
    try:
        if idempotency_key is not None:
            _serialize_idempotency(session, principal.id, route, idempotency_key)
            existing = session.scalar(
                select(IdempotencyRecord)
                .where(
                    IdempotencyRecord.actor_id == principal.id,
                    IdempotencyRecord.route == route,
                    IdempotencyRecord.key == idempotency_key,
                )
                .with_for_update()
            )
            if existing is not None:
                if existing.request_hash != digest:
                    raise conflict("idempotency_conflict", "此 Idempotency-Key 已用於不同的請求內容")
                if authorize_replay is not None:
                    authorize_replay(existing.response)
                result = JSONResponse(status_code=existing.status_code, content=existing.response)
                session.commit()
                return result

        response = action()
        if idempotency_key is not None:
            session.add(
                IdempotencyRecord(
                    id=new_id(),
                    actor_id=principal.id,
                    route=route,
                    key=idempotency_key,
                    request_hash=digest,
                    status_code=status_code,
                    response=response,
                    created_at=now_iso(),
                )
            )
        session.commit()
        return JSONResponse(status_code=status_code, content=response)
    except Exception:
        session.rollback()
        raise


def _serialize_idempotency(session: Session, actor_id: str, route: str, key: str) -> None:
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return
    lock_text = f"{actor_id}\n{route}\n{key}"
    lock_id = int.from_bytes(hashlib.sha256(lock_text.encode("utf-8")).digest()[:8], "big", signed=True)
    session.execute(select(func.pg_advisory_xact_lock(lock_id)))
