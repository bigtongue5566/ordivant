"""Scoped collaboration primitives. Each product owns its own tables and resolver."""
import base64
import binascii
import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, Header
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from .errors import DomainError
from .collaboration_models import CollaborationAttachment as Attachment, CollaborationSubscription as Subscription, CollaborationNotification as Notification, CollaborationMutation as Mutation

MAX_FILE = 10 * 1024 * 1024


def now():
    return datetime.now(timezone.utc)


def iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.isoformat()


def emit(session, kind, ident, event_id, actor_id, event, *, mentions=(), body=""):
    recipients = set(session.scalars(select(Subscription.principal_id).where(Subscription.resource_kind == kind, Subscription.resource_id == ident))) | set(mentions)
    for principal_id in recipients - {actor_id}:
        if not session.scalar(select(Notification.id).where(Notification.event_id == event_id, Notification.principal_id == principal_id)):
            session.add(Notification(id=str(uuid4()), event_id=event_id, resource_kind=kind, resource_id=ident,
                principal_id=principal_id, actor_id=actor_id, event=event, body=body, created_at=now(), read_at=None))


class Upload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=160)
    content_base64: str = Field(max_length=14 * 1024 * 1024)


class Discussion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=8000)
    mention_ids: list[str] = Field(default_factory=list, max_length=100)


class Follow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subscribed: bool


def create_router(get_session, get_actor, resolve, eligible):
    """Resolvers recheck current organization, membership and write role; no cross-DB access."""
    router = APIRouter(prefix="/api/collaboration")

    def mutate(session, actor, key, route, body, operation):
        if not key or len(key) > 160:
            raise DomainError(422, "idempotency_required", "An Idempotency-Key is required")
        if session.bind.dialect.name == "postgresql":
            lock = int.from_bytes(hashlib.sha256((actor.id + key).encode()).digest()[:8], "big", signed=True)
            session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
        digest = hashlib.sha256(json.dumps([route, body], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        receipt = session.scalar(select(Mutation).where(Mutation.principal_id == actor.id, Mutation.key == key))
        if receipt:
            if receipt.request_hash != digest:
                raise DomainError(409, "idempotency_conflict", "The key was used for another request")
            return json.loads(receipt.response_json)
        result = operation()
        session.add(Mutation(id=str(uuid4()), principal_id=actor.id, key=key, request_hash=digest, response_json=json.dumps(result)))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise DomainError(409, "concurrent_mutation", "A concurrent request committed; retry with the same key")
        return result

    def attachment_json(row):
        return {"id": row.id, "filename": row.filename, "size": row.size, "sha256": row.sha256,
                "actor_id": row.actor_id, "created_at": iso(row.created_at)}

    @router.get("/{kind}/{ident}/attachments")
    def attachments(kind: str, ident: str, session=Depends(get_session), actor=Depends(get_actor)):
        resolve(session, actor, kind, ident, False)
        return [attachment_json(row) for row in session.scalars(select(Attachment).where(Attachment.resource_kind == kind,
            Attachment.resource_id == ident).order_by(Attachment.created_at))]

    @router.post("/{kind}/{ident}/attachments", status_code=201)
    def upload(kind: str, ident: str, body: Upload, key: str | None = Header(default=None, alias="Idempotency-Key"), session=Depends(get_session), actor=Depends(get_actor)):
        resolve(session, actor, kind, ident, True)
        def operation():
            filename = body.filename.strip()
            if filename in {"", ".", ".."} or re.search(r'[\x00-\x1f\x7f/\\]', filename):
                raise DomainError(422, "invalid_filename", "Use a filename without paths or control characters")
            try:
                content = base64.b64decode(body.content_base64, validate=True)
            except (ValueError, binascii.Error):
                raise DomainError(422, "invalid_attachment", "Attachment encoding is invalid")
            if not content or len(content) > MAX_FILE:
                raise DomainError(422, "attachment_too_large", "Each attachment must contain 1 byte to 10 MiB")
            existing = session.execute(select(func.count(Attachment.id), func.coalesce(func.sum(Attachment.size), 0)).where(
                Attachment.resource_kind == kind, Attachment.resource_id == ident)).one()
            if existing[0] >= 100 or existing[1] + len(content) > 100 * MAX_FILE // 10:
                raise DomainError(409, "attachment_quota", "The resource attachment quota is exhausted")
            row = Attachment(id=str(uuid4()), resource_kind=kind, resource_id=ident, actor_id=actor.id, filename=filename,
                size=len(content), sha256=hashlib.sha256(content).hexdigest(), content=content, created_at=now())
            session.add(row)
            emit(session, kind, ident, row.id, actor.id, "attachment.created")
            return attachment_json(row)
        return mutate(session, actor, key, f"upload/{kind}/{ident}", body.model_dump(), operation)

    @router.get("/attachments/{attachment_id}/download")
    def download(attachment_id: str, session=Depends(get_session), actor=Depends(get_actor)):
        row = session.get(Attachment, attachment_id)
        if not row:
            raise DomainError(404, "not_found", "Attachment not found")
        resolve(session, actor, row.resource_kind, row.resource_id, False)
        from urllib.parse import quote
        return Response(row.content, media_type="application/octet-stream", headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(row.filename, safe=""),
            "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store", "ETag": '"' + row.sha256 + '"'})

    @router.get("/{kind}/{ident}/subscription")
    def subscription(kind: str, ident: str, session=Depends(get_session), actor=Depends(get_actor)):
        resolve(session, actor, kind, ident, False)
        return {"subscribed": bool(session.scalar(select(Subscription.id).where(Subscription.resource_kind == kind,
            Subscription.resource_id == ident, Subscription.principal_id == actor.id)))}

    @router.post("/{kind}/{ident}/subscription")
    def subscribe(kind: str, ident: str, body: Follow, key: str | None = Header(default=None, alias="Idempotency-Key"), session=Depends(get_session), actor=Depends(get_actor)):
        resolve(session, actor, kind, ident, False)
        def operation():
            existing = session.scalar(select(Subscription).where(Subscription.resource_kind == kind, Subscription.resource_id == ident, Subscription.principal_id == actor.id))
            if body.subscribed and not existing:
                session.add(Subscription(id=str(uuid4()), resource_kind=kind, resource_id=ident, principal_id=actor.id))
            elif existing and not body.subscribed:
                session.delete(existing)
            return {"subscribed": body.subscribed}
        return mutate(session, actor, key, f"subscribe/{kind}/{ident}", body.model_dump(), operation)

    @router.get("/{kind}/{ident}/participants")
    def participants(kind: str, ident: str, session=Depends(get_session), actor=Depends(get_actor)):
        resolve(session, actor, kind, ident, False)
        return eligible(session, actor, kind, ident)

    @router.post("/{kind}/{ident}/discussion", status_code=201)
    def discussion(kind: str, ident: str, body: Discussion, key: str | None = Header(default=None, alias="Idempotency-Key"), session=Depends(get_session), actor=Depends(get_actor)):
        resolve(session, actor, kind, ident, True)
        allowed = {item["id"] for item in eligible(session, actor, kind, ident)}
        if any(ident not in allowed for ident in body.mention_ids) or len(set(body.mention_ids)) != len(body.mention_ids):
            raise DomainError(422, "invalid_mention", "Mention only eligible resource participants")
        def operation():
            ident_event = str(uuid4())
            emit(session, kind, ident, ident_event, actor.id, "discussion.mention", mentions=body.mention_ids, body=body.body)
            # Persist a discussion event for author/subscribers even when there are no other recipients.
            session.add(Notification(id=str(uuid4()), event_id=ident_event, resource_kind=kind, resource_id=ident,
                principal_id=actor.id, actor_id=actor.id, event="discussion.created", body=body.body, created_at=now(), read_at=now()))
            return {"id": ident_event, "body": body.body}
        return mutate(session, actor, key, f"discussion/{kind}/{ident}", body.model_dump(), operation)

    @router.get("/{kind}/{ident}/discussion")
    def discussion_history(kind: str, ident: str, session=Depends(get_session), actor=Depends(get_actor)):
        resolve(session, actor, kind, ident, False)
        rows = session.scalars(select(Notification).where(Notification.resource_kind == kind, Notification.resource_id == ident,
            Notification.event == "discussion.created").order_by(Notification.created_at.desc()).limit(100)).all()
        return [{"id": row.event_id, "actor_id": row.actor_id, "body": row.body, "created_at": iso(row.created_at)} for row in rows]

    @router.get("/notifications")
    def notifications(session=Depends(get_session), actor=Depends(get_actor)):
        rows = session.scalars(select(Notification).where(Notification.principal_id == actor.id).order_by(Notification.created_at.desc()).limit(100)).all()
        result = []
        for row in rows:
            try:
                title = resolve(session, actor, row.resource_kind, row.resource_id, False)
            except DomainError as error:
                if error.status_code not in {403, 404}:
                    raise
                continue
            result.append({"id": row.id, "resource_kind": row.resource_kind, "resource_id": row.resource_id,
                "title": title, "actor_id": row.actor_id, "event": row.event, "body": row.body,
                "created_at": iso(row.created_at), "read": row.read_at is not None})
        return result

    @router.post("/notifications/{notification_id}/read")
    def read(notification_id: str, key: str | None = Header(default=None, alias="Idempotency-Key"), session=Depends(get_session), actor=Depends(get_actor)):
        row = session.get(Notification, notification_id)
        if not row or row.principal_id != actor.id:
            raise DomainError(404, "not_found", "Notification not found")
        resolve(session, actor, row.resource_kind, row.resource_id, False)
        def operation():
            row.read_at = now()
            return {"read": True}
        return mutate(session, actor, key, f"read/{notification_id}", {}, operation)

    return router
