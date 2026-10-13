from __future__ import annotations

import base64
import binascii
import hashlib
import time

from pycrdt import Doc, Text
from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import DomainError, bad_request, conflict, not_found
from .models import (
    Document,
    DocumentDraft,
    DocumentVersion,
    DraftRateWindow,
    DraftUpdateReceipt,
)
from .security import PrincipalContext, new_id, now_iso, require_current_scope, require_writer
from .service import add_audit, version_view


MAX_UPDATE_BYTES = 256 * 1024
MAX_STATE_BYTES = 8 * 1024 * 1024
MAX_DOCUMENT_BYTES = 2_000_000
MAX_DRAFT_UPDATES_PER_WINDOW = 300


def _document(
    session: Session,
    principal: PrincipalContext,
    document_id: str,
    *,
    lock: bool = False,
) -> Document:
    statement = select(Document).where(Document.id == document_id)
    if lock and session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update().execution_options(populate_existing=True)
    document = session.scalar(statement)
    if document is None:
        raise not_found()
    require_current_scope(session, principal, document.space_id, lock=lock)
    return document


def _new_doc(body: str = "") -> Doc:
    doc = Doc()
    text = doc.get("body", type=Text)
    if body:
        text += body
    return doc


def _body(doc: Doc) -> str:
    return str(doc.get("body", type=Text))


def _encode_state(doc: Doc) -> bytes:
    state = doc.get_update()
    if len(state) > MAX_STATE_BYTES:
        raise bad_request("draft_state_too_large", "共同草稿狀態超過允許大小")
    return state


def _decode_update(encoded: str) -> bytes:
    if len(encoded) > ((MAX_UPDATE_BYTES + 2) // 3) * 4:
        raise bad_request("draft_update_too_large", "共同編輯更新超過允許大小")
    try:
        update = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise bad_request("invalid_draft_update", "共同編輯更新必須是有效的 base64") from exc
    if not update or len(update) > MAX_UPDATE_BYTES:
        raise bad_request("draft_update_too_large", "共同編輯更新為空或超過允許大小")
    return update


def _load_doc(state: bytes) -> Doc:
    doc = Doc()
    try:
        doc.apply_update(state)
        doc.get("body", type=Text)
    except Exception as exc:
        raise bad_request("invalid_draft_update", "共同編輯更新不是有效的 Yjs v1 更新") from exc
    return doc


def _ensure_draft(session: Session, document: Document) -> DocumentDraft:
    statement = select(DocumentDraft).where(DocumentDraft.document_id == document.id)
    if session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    draft = session.scalar(statement)
    if draft is not None:
        return draft

    version = session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version == document.current_version,
        )
    )
    if version is None:
        raise RuntimeError("The document current version is missing")
    now = now_iso()
    draft = DocumentDraft(
        document_id=document.id,
        base_version=version.version,
        revision=0,
        published_revision=0,
        title=version.title,
        state=_encode_state(_new_doc(version.body)),
        updated_at=now,
    )
    session.add(draft)
    session.flush()
    return draft


def draft_view(draft: DocumentDraft) -> dict[str, object]:
    doc = _load_doc(draft.state)
    return {
        "document_id": draft.document_id,
        "base_version": draft.base_version,
        "revision": draft.revision,
        "published_revision": draft.published_revision,
        "title": draft.title,
        "body": _body(doc),
        "update": base64.b64encode(draft.state).decode("ascii"),
    }


def get_document_draft(session: Session, principal: PrincipalContext, document_id: str) -> dict[str, object]:
    document = _document(session, principal, document_id)
    draft = session.get(DocumentDraft, document.id)
    if draft is None:
        document = _document(session, principal, document_id, lock=True)
        draft = _ensure_draft(session, document)
    require_current_scope(session, principal, document.space_id)
    return draft_view(draft)


def _apply_to_draft(
    session: Session,
    principal: PrincipalContext,
    document: Document,
    encoded_update: str,
) -> DocumentDraft:
    draft = _ensure_draft(session, document)
    principal = require_current_scope(session, principal, document.space_id, lock=True)
    require_writer(principal)
    incoming = _decode_update(encoded_update)
    _enforce_update_rate_limit(session, document.id, principal.id)
    doc = _load_doc(draft.state)
    try:
        doc.apply_update(incoming)
    except Exception as exc:
        raise bad_request("invalid_draft_update", "共同編輯更新不是有效的 Yjs v1 更新") from exc
    body = _body(doc)
    if len(body.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise bad_request("draft_document_too_large", "共同草稿正文超過允許大小")

    principal = require_current_scope(session, principal, document.space_id, lock=True)
    require_writer(principal)
    draft.revision += 1
    draft.state = _encode_state(doc)
    draft.updated_at = now_iso()
    add_audit(
        session,
        principal,
        space_id=document.space_id,
        action="knowledge.document.draft_updated",
        entity_type="document_draft",
        entity_id=document.id,
        data={"revision": draft.revision, "actor_kind": principal.kind},
    )
    session.flush()
    return draft


def _enforce_update_rate_limit(session: Session, document_id: str, actor_id: str) -> None:
    window_id = int(time.time() // 60)
    statement = select(DraftRateWindow).where(
        DraftRateWindow.document_id == document_id,
        DraftRateWindow.actor_id == actor_id,
    )
    if session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    window = session.scalar(statement)
    if window is None:
        session.add(
            DraftRateWindow(
                document_id=document_id,
                actor_id=actor_id,
                window_id=window_id,
                request_count=1,
            )
        )
        return
    if window.window_id != window_id:
        window.window_id = window_id
        window.request_count = 1
        return
    if window.request_count >= MAX_DRAFT_UPDATES_PER_WINDOW:
        raise DomainError(429, "rate_limited", "此操作者對此文件的共同編輯更新頻率超過上限")
    window.request_count += 1


def apply_document_draft_update(
    session: Session,
    principal: PrincipalContext,
    document_id: str,
    encoded_update: str,
) -> dict[str, object]:
    document = _document(session, principal, document_id, lock=True)
    draft = _apply_to_draft(session, principal, document, encoded_update)
    return draft_view(draft)


def apply_websocket_draft_update(
    session: Session,
    principal: PrincipalContext,
    document_id: str,
    encoded_update: str,
    request_id: str,
) -> dict[str, object]:
    if not request_id.strip() or len(request_id) > 200:
        raise bad_request("invalid_request_id", "request_id 必須為 1 至 200 個字元")
    document = _document(session, principal, document_id, lock=True)
    principal = require_current_scope(session, principal, document.space_id, lock=True)
    require_writer(principal)
    incoming = _decode_update(encoded_update)
    digest = hashlib.sha256(incoming).hexdigest()
    receipt = session.scalar(
        select(DraftUpdateReceipt).where(
            DraftUpdateReceipt.document_id == document.id,
            DraftUpdateReceipt.actor_id == principal.id,
            DraftUpdateReceipt.request_id == request_id,
        )
    )
    if receipt is not None:
        if receipt.request_hash != digest:
            raise conflict("request_id_conflict", "此 request_id 已用於不同的共同編輯更新")
        draft = _ensure_draft(session, document)
        principal = require_current_scope(session, principal, document.space_id, lock=True)
        require_writer(principal)
        return draft_view(draft)

    draft = _apply_to_draft(session, principal, document, encoded_update)
    session.add(
        DraftUpdateReceipt(
            id=new_id(),
            document_id=document.id,
            actor_id=principal.id,
            request_id=request_id,
            request_hash=digest,
            revision=draft.revision,
            created_at=now_iso(),
        )
    )
    session.flush()
    return draft_view(draft)


def publish_document_draft(
    session: Session,
    principal: PrincipalContext,
    document_id: str,
    *,
    expected_revision: int,
    change_summary: str,
    title: str | None,
    source_refs: list[dict[str, str]],
) -> dict[str, object]:
    document = _document(session, principal, document_id, lock=True)
    draft = _ensure_draft(session, document)
    principal = require_current_scope(session, principal, document.space_id, lock=True)
    require_writer(principal)
    if draft.revision != expected_revision:
        raise conflict(
            "stale_draft_revision",
            f"expected_revision={expected_revision} 不符合目前草稿 revision {draft.revision}",
        )
    if draft.base_version != document.current_version:
        raise conflict("stale_draft_base", "共同草稿的基底版本已變更，請重新同步")

    body = _body(_load_doc(draft.state))
    if not body.strip():
        raise bad_request("empty_draft", "共同草稿正文不可為空白")
    principal = require_current_scope(session, principal, document.space_id, lock=True)
    require_writer(principal)
    next_version = document.current_version + 1
    published_title = title or draft.title
    now = now_iso()
    version = DocumentVersion(
        id=new_id(),
        document_id=document.id,
        version=next_version,
        title=published_title,
        body=body,
        change_summary=change_summary,
        author_id=principal.id,
        content_sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        source_refs=source_refs,
        created_at=now,
    )
    session.add(version)
    document.title = published_title
    document.current_version = next_version
    document.updated_at = now
    draft.title = published_title
    draft.base_version = next_version
    draft.revision += 1
    draft.published_revision = draft.revision
    draft.updated_at = now
    add_audit(
        session,
        principal,
        space_id=document.space_id,
        action="knowledge.document.draft_published",
        entity_type="document_version",
        entity_id=version.id,
        data={
            "document_id": document.id,
            "version": next_version,
            "revision": draft.revision,
            "content_sha256": version.content_sha256,
            "source_refs": source_refs,
            "actor_kind": principal.kind,
        },
    )
    session.flush()
    return version_view(version, document.space_id)


def synchronize_legacy_publish(
    session: Session,
    principal: PrincipalContext,
    document: Document,
    *,
    title: str,
    body: str,
    base_version: int,
) -> None:
    draft = _ensure_draft(session, document)
    principal = require_current_scope(session, principal, document.space_id, lock=True)
    require_writer(principal)
    if draft.revision != draft.published_revision:
        raise conflict(
            "draft_has_unpublished_changes",
            "此文件有尚未發布的共同草稿，請先同步草稿並透過共同草稿發布",
        )
    doc = _load_doc(draft.state)
    text = doc.get("body", type=Text)
    text.clear()
    if body:
        text += body
    principal = require_current_scope(session, principal, document.space_id, lock=True)
    require_writer(principal)
    draft.state = _encode_state(doc)
    draft.title = title
    draft.base_version = base_version
    draft.revision += 1
    draft.published_revision = draft.revision
    draft.updated_at = now_iso()
