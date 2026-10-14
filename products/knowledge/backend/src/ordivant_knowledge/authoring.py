from __future__ import annotations

import difflib

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import bad_request, conflict, not_found
from .models import Document, DocumentComment, DocumentVersion, KnowledgeSpace, Principal, SpaceTemplate
from .security import PrincipalContext, new_id, now_iso, require_current_scope, require_scope, require_writer
from .service import add_audit, document_uri


BUILTIN_TEMPLATES = (
    {
        "id": "builtin:prd",
        "name": "產品需求文件 (PRD)",
        "description": "規劃問題、目標、範圍與驗收條件。",
        "body": "# Product requirements\n\n## Problem\n\n## Goals and non-goals\n\n## Users and scenarios\n\n## Requirements\n\n## Acceptance criteria\n",
    },
    {
        "id": "builtin:meeting",
        "name": "會議記錄",
        "description": "整理議程、討論、決議與待辦。",
        "body": "# Meeting notes\n\n## Date and participants\n\n## Agenda\n\n## Discussion\n\n## Decisions\n\n## Action items\n",
    },
    {
        "id": "builtin:adr",
        "name": "架構決策紀錄 (ADR)",
        "description": "保留背景、選項、決定及其後果。",
        "body": "# Architecture decision\n\n## Status\n\n## Context\n\n## Options considered\n\n## Decision\n\n## Consequences\n",
    },
    {
        "id": "builtin:sop",
        "name": "標準作業程序 (SOP)",
        "description": "說明適用範圍、前置條件與可核對步驟。",
        "body": "# Standard operating procedure\n\n## Purpose and scope\n\n## Roles\n\n## Preconditions\n\n## Procedure\n\n## Verification and recovery\n",
    },
)


def lock_tree(session: Session, space_id: str) -> None:
    # One Space lock prevents reciprocal moves and create/archive races across different authors.
    if session.get_bind().dialect.name == 'postgresql':
        session.execute(select(KnowledgeSpace.id).where(KnowledgeSpace.id == space_id).with_for_update()).one()


def _validate_parent(session: Session, principal: PrincipalContext, document: Document, parent_id: str | None) -> None:
    if parent_id is None:
        return
    parent = session.get(Document, parent_id, populate_existing=True)
    if parent is None:
        raise not_found()
    require_scope(session, principal, parent.space_id)
    if parent.space_id != document.space_id:
        raise bad_request("parent_space_mismatch", "文件只能放在相同 Space 的父文件下")
    if parent.archived:
        raise conflict("parent_archived", "請先取消封存父文件，再移動子文件")
    seen = {document.id}
    current: Document | None = parent
    while current is not None:
        if current.id in seen:
            raise conflict("document_tree_cycle", "文件階層不可形成循環")
        seen.add(current.id)
        current = session.get(Document, current.parent_id, populate_existing=True) if current.parent_id else None


def organize_document(
    session: Session,
    principal: PrincipalContext,
    document_id: str,
    *,
    parent_supplied: bool,
    parent_id: str | None,
    archived: bool | None,
) -> dict[str, object]:
    initial = session.get(Document, document_id)
    if initial is None:
        raise not_found()
    require_scope(session, principal, initial.space_id)
    lock_tree(session, initial.space_id)
    document = session.scalar(
        select(Document).where(Document.id == document_id)
        .with_for_update()
        .execution_options(populate_existing=True)
        if session.get_bind().dialect.name == "postgresql"
        else select(Document).where(Document.id == document_id).execution_options(populate_existing=True)
    )
    if document is None:
        raise not_found()
    principal = require_current_scope(session, principal, document.space_id, lock=True)
    require_writer(principal)
    next_parent = parent_id if parent_supplied else document.parent_id
    if parent_supplied:
        _validate_parent(session, principal, document, next_parent)
    if archived is True and not document.archived:
        child_id = session.scalar(select(Document.id).where(Document.parent_id == document.id).limit(1))
        if child_id is not None:
            raise conflict("document_has_children", "請先將子文件移至其他父文件，再封存此文件")
    if archived is not None and archived is not document.archived:
        document.archived = archived
    if parent_supplied:
        document.parent_id = next_parent
    document.updated_at = now_iso()
    add_audit(
        session,
        principal,
        space_id=document.space_id,
        action="knowledge.document.organized",
        entity_type="document",
        entity_id=document.id,
        data={"parent_id": document.parent_id, "archived": document.archived},
    )
    session.flush()
    from .service import document_view

    return document_view(document)


def comment_view(session: Session, comment: DocumentComment, document: Document) -> dict[str, object]:
    author = session.get(Principal, comment.author_id)
    anchor = dict(comment.anchor) if comment.anchor else None
    return {
        "id": comment.id,
        "document_id": comment.document_id,
        "author_id": comment.author_id,
        "author_name": author.name if author else comment.author_id,
        "body": comment.body,
        "anchor": anchor,
        "anchor_stale": bool(anchor and anchor.get("version") != document.current_version),
        "parent_id": comment.parent_id,
        "resolved": comment.resolved,
        "created_at": comment.created_at,
    }


def list_comments(session: Session, principal: PrincipalContext, document_id: str) -> list[dict[str, object]]:
    document = session.get(Document, document_id)
    if document is None:
        raise not_found()
    require_scope(session, principal, document.space_id)
    comments = session.scalars(
        select(DocumentComment)
        .where(DocumentComment.document_id == document.id)
        .order_by(DocumentComment.created_at, DocumentComment.id)
    )
    return [comment_view(session, comment, document) for comment in comments]


def create_comment(
    session: Session,
    principal: PrincipalContext,
    document_id: str,
    *,
    body: str,
    anchor: dict[str, object] | None,
    parent_id: str | None,
) -> dict[str, object]:
    document = session.get(Document, document_id)
    if document is None:
        raise not_found()
    principal = require_current_scope(session, principal, document.space_id, lock=True)
    require_writer(principal)
    if parent_id:
        parent = session.get(DocumentComment, parent_id)
        if parent is None or parent.document_id != document.id:
            raise not_found()
        if parent.parent_id is not None:
            raise bad_request("comment_reply_depth", "回覆只能直接加入留言討論串")
    if anchor:
        version = session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version == anchor["version"],
            )
        )
        if version is None:
            raise not_found()
        start, end = anchor.get("start"), anchor.get("end")
        if (start is None) != (end is None):
            raise bad_request("invalid_comment_anchor", "引用定位需要同时提供 start 与 end")
        if start is not None and end is not None:
            if end <= start or version.body[start:end] != anchor["quote"]:
                raise bad_request("invalid_comment_anchor", "引用文字與所選版本的起訖位置不一致")
        elif anchor["quote"] not in version.body:
            raise bad_request("invalid_comment_anchor", "引用文字不在所選版本中")
    comment = DocumentComment(
        id=new_id(),
        document_id=document.id,
        author_id=principal.id,
        body=body,
        anchor=anchor,
        parent_id=parent_id,
        resolved=False,
        created_at=now_iso(),
    )
    session.add(comment)
    session.flush()
    add_audit(
        session,
        principal,
        space_id=document.space_id,
        action="knowledge.document.comment_created",
        entity_type="document_comment",
        entity_id=comment.id,
        data={"document_id": document.id, "parent_id": parent_id, "anchor_version": anchor.get("version") if anchor else None},
    )
    return comment_view(session, comment, document)


def resolve_comment(
    session: Session,
    principal: PrincipalContext,
    comment_id: str,
    *,
    resolved: bool,
) -> dict[str, object]:
    comment = session.scalar(
        select(DocumentComment).where(DocumentComment.id == comment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
        if session.get_bind().dialect.name == "postgresql"
        else select(DocumentComment).where(DocumentComment.id == comment_id).execution_options(populate_existing=True)
    )
    if comment is None:
        raise not_found()
    document = session.get(Document, comment.document_id)
    if document is None:
        raise not_found()
    principal = require_current_scope(session, principal, document.space_id, lock=True)
    require_writer(principal)
    comment.resolved = resolved
    add_audit(
        session,
        principal,
        space_id=document.space_id,
        action="knowledge.document.comment_resolved" if resolved else "knowledge.document.comment_reopened",
        entity_type="document_comment",
        entity_id=comment.id,
        data={"document_id": document.id},
    )
    session.flush()
    return comment_view(session, comment, document)


def list_templates(session: Session, principal: PrincipalContext, space_id: str) -> list[dict[str, object]]:
    require_scope(session, principal, space_id)
    builtins = [
        {"id": item["id"], "space_id": space_id, "name": item["name"], "description": item["description"], "body": item["body"], "builtin": True}
        for item in BUILTIN_TEMPLATES
    ]
    custom = session.scalars(
        select(SpaceTemplate).where(SpaceTemplate.space_id == space_id).order_by(SpaceTemplate.name, SpaceTemplate.id)
    )
    builtins.extend(
        {"id": item.id, "space_id": item.space_id, "name": item.name, "description": item.description, "body": item.body, "builtin": False}
        for item in custom
    )
    return builtins


def create_template(
    session: Session,
    principal: PrincipalContext,
    space_id: str,
    *,
    name: str,
    description: str,
    body: str,
) -> dict[str, object]:
    require_scope(session, principal, space_id)
    principal = require_current_scope(session, principal, space_id, lock=True)
    require_writer(principal)
    if session.scalar(select(SpaceTemplate.id).where(SpaceTemplate.space_id == space_id, SpaceTemplate.name == name)):
        raise conflict("template_name_conflict", "此 Space 已有相同名稱的範本")
    template = SpaceTemplate(
        id=new_id(),
        space_id=space_id,
        name=name,
        description=description,
        body=body,
        created_by=principal.id,
        created_at=now_iso(),
    )
    session.add(template)
    session.flush()
    add_audit(
        session,
        principal,
        space_id=space_id,
        action="knowledge.space.template_created",
        entity_type="space_template",
        entity_id=template.id,
        data={"name": template.name},
    )
    return {"id": template.id, "space_id": template.space_id, "name": template.name, "description": template.description, "body": template.body, "builtin": False}


def diff_versions(
    session: Session,
    principal: PrincipalContext,
    document_id: str,
    from_version: int,
    to_version: int,
) -> dict[str, object]:
    document = session.get(Document, document_id)
    if document is None:
        raise not_found()
    require_scope(session, principal, document.space_id)
    versions = session.scalars(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version.in_([from_version, to_version]),
        )
    )
    by_number = {version.version: version for version in versions}
    if from_version not in by_number or to_version not in by_number:
        raise not_found()
    source, target = by_number[from_version], by_number[to_version]
    diff = "".join(difflib.unified_diff(
        source.body.splitlines(keepends=True),
        target.body.splitlines(keepends=True),
        fromfile=document_uri(document.space_id, document.id, from_version),
        tofile=document_uri(document.space_id, document.id, to_version),
    ))
    return {
        "document_id": document.id,
        "from_version": from_version,
        "to_version": to_version,
        "from_title": source.title,
        "to_title": target.title,
        "title_changed": source.title != target.title,
        "diff": diff,
    }


def restore_version(
    session: Session,
    principal: PrincipalContext,
    document_id: str,
    *,
    version_number: int,
    expected_current_version: int,
    change_summary: str,
) -> dict[str, object]:
    from .drafts import synchronize_legacy_publish
    from .service import version_view

    document = session.scalar(
        select(Document).where(Document.id == document_id)
        .with_for_update()
        .execution_options(populate_existing=True)
        if session.get_bind().dialect.name == "postgresql"
        else select(Document).where(Document.id == document_id).execution_options(populate_existing=True)
    )
    if document is None:
        raise not_found()
    principal = require_current_scope(session, principal, document.space_id, lock=True)
    require_writer(principal)
    if document.current_version != expected_current_version:
        raise conflict("stale_version", f"expected_current_version={expected_current_version} 不符合目前版本 {document.current_version}")
    original = session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version == version_number,
        )
    )
    if original is None:
        raise not_found()
    next_number = document.current_version + 1
    now = now_iso()
    restored = DocumentVersion(
        id=new_id(),
        document_id=document.id,
        version=next_number,
        title=original.title,
        body=original.body,
        change_summary=change_summary.strip() or f"Restored from version {version_number}.",
        author_id=principal.id,
        content_sha256=original.content_sha256,
        source_refs=list(original.source_refs),
        created_at=now,
    )
    session.add(restored)
    session.flush()
    document.title = restored.title
    document.current_version = next_number
    document.updated_at = now
    synchronize_legacy_publish(
        session,
        principal,
        document,
        title=restored.title,
        body=restored.body,
        base_version=next_number,
    )
    add_audit(
        session,
        principal,
        space_id=document.space_id,
        action="knowledge.document.version_restored",
        entity_type="document_version",
        entity_id=restored.id,
        data={"document_id": document.id, "version": next_number, "restored_from": version_number, "content_sha256": restored.content_sha256},
    )
    session.flush()
    return version_view(restored, document.space_id)
