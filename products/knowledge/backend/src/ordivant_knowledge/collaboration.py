from __future__ import annotations

import asyncio
import json
import os
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .drafts import apply_websocket_draft_update, get_document_draft
from .errors import DomainError, not_found
from .identity import websocket_cookie_principal
from .models import CollaborationPresence, Document, KnowledgeSpace, Principal, SpaceMembership
from .security import PrincipalContext, expires_after, new_id, now_iso, require_current_scope


router = APIRouter(prefix="/api")

MAX_CONNECTIONS = 100
MAX_DOCUMENT_CONNECTIONS = 25
MAX_MESSAGE_BYTES = 360_000
MAX_MESSAGES_PER_MINUTE = 600
MAX_UPDATES_PER_MINUTE = 300
DB_POLL_SECONDS = 0.5
HEARTBEAT_SECONDS = 15
PRESENCE_TTL_SECONDS = 45
REAUTH_SECONDS = 30
AUTH_TIMEOUT_SECONDS = 10


def _origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    allowed = {item.strip() for item in os.getenv("ORDIVANT_AUTH_ORIGINS", "").split(",") if item.strip()}
    return origin is not None and origin in allowed


def _participants(session: Session, document_id: str) -> list[dict[str, str]]:
    now = now_iso()
    rows = session.execute(
        select(CollaborationPresence, Principal)
        .join(Principal, Principal.id == CollaborationPresence.principal_id)
        .join(Document, Document.id == CollaborationPresence.document_id)
        .join(KnowledgeSpace, KnowledgeSpace.id == Document.space_id)
        .join(
            SpaceMembership,
            (SpaceMembership.principal_id == Principal.id) & (SpaceMembership.space_id == KnowledgeSpace.id),
        )
        .where(
            CollaborationPresence.document_id == document_id,
            CollaborationPresence.expires_at > now,
            Principal.active.is_(True),
            Principal.organization_id == KnowledgeSpace.organization_id,
        )
        .order_by(CollaborationPresence.name, CollaborationPresence.principal_id)
    ).all()
    by_principal: dict[str, dict[str, str]] = {}
    for presence, principal in rows:
        by_principal.setdefault(
            principal.id,
            {"id": principal.id, "name": principal.name, "kind": principal.kind},
        )
    return sorted(by_principal.values(), key=lambda value: (value["name"].casefold(), value["id"]))


def _touch_presence(
    session: Session,
    *,
    connection_id: str,
    document_id: str,
    principal: PrincipalContext,
    enforce_limit: bool = False,
) -> None:
    now = now_iso()
    statement = select(Document).where(Document.id == document_id)
    if session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    document = session.scalar(statement)
    if document is None:
        raise not_found()
    principal = require_current_scope(session, principal, document.space_id, lock=True)

    session.execute(
        delete(CollaborationPresence).where(
            CollaborationPresence.document_id == document_id,
            CollaborationPresence.expires_at <= now,
        )
    )
    current = session.get(CollaborationPresence, connection_id)
    if current is None and enforce_limit:
        count = session.scalar(
            select(func.count())
            .select_from(CollaborationPresence)
            .where(
                CollaborationPresence.document_id == document_id,
                CollaborationPresence.expires_at > now,
            )
        )
        if count is not None and count >= MAX_DOCUMENT_CONNECTIONS:
            raise DomainError(503, "collaboration_capacity", "此文件的共同編輯連線已達上限")
        current = CollaborationPresence(
            connection_id=connection_id,
            document_id=document_id,
            principal_id=principal.id,
            name=principal.name,
            kind=principal.kind,
            updated_at=now,
            expires_at=expires_after(PRESENCE_TTL_SECONDS),
        )
        session.add(current)
    elif current is not None:
        current.principal_id = principal.id
        current.name = principal.name
        current.kind = principal.kind
        current.updated_at = now
        current.expires_at = expires_after(PRESENCE_TTL_SECONDS)
    session.flush()


def _error_payload(error: DomainError, request_id: str | None = None) -> dict[str, str]:
    result = {"type": "error", "code": error.code, "message": error.message}
    if request_id is not None:
        result["request_id"] = request_id
    return result


async def _send_error(websocket: WebSocket, error: DomainError, request_id: str | None = None) -> None:
    await websocket.send_json(_error_payload(error, request_id))


async def _receive_json(websocket: WebSocket, timeout: float | None = None) -> dict[str, object] | None:
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=timeout) if timeout is not None else await websocket.receive_text()
    except TimeoutError:
        return None
    if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise DomainError(413, "collaboration_message_too_large", "共同編輯訊息超過允許大小")
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise DomainError(422, "invalid_collaboration_message", "共同編輯訊息必須是有效 JSON") from exc
    if not isinstance(value, dict):
        raise DomainError(422, "invalid_collaboration_message", "共同編輯訊息必須是 JSON 物件")
    return value


def _principal_id_for_cookie(principal: PrincipalContext, candidate: PrincipalContext) -> None:
    if principal.id != candidate.id:
        raise DomainError(401, "session_changed", "共同編輯工作階段已變更，請重新連線")


@router.websocket("/documents/{document_id}/collaborate")
async def collaborate(websocket: WebSocket, document_id: str) -> None:
    if not _origin_allowed(websocket):
        await websocket.close(code=4403, reason="origin_not_allowed")
        return

    application = websocket.app
    active = application.state.collaboration_connections
    if active >= MAX_CONNECTIONS:
        await websocket.close(code=1013, reason="collaboration_capacity")
        return
    application.state.collaboration_connections = active + 1
    connection_id = new_id()
    principal: PrincipalContext | None = None
    csrf_token = ""
    last_revision = -1
    last_participants: tuple[tuple[str, str, str], ...] = ()
    last_heartbeat = time.monotonic()
    last_reauth = last_heartbeat
    message_window = last_heartbeat
    message_count = 0
    update_count = 0

    await websocket.accept()
    try:
        try:
            auth_message = await _receive_json(websocket, timeout=AUTH_TIMEOUT_SECONDS)
            if (
                auth_message is None
                or set(auth_message) != {"type", "csrf_token"}
                or auth_message.get("type") != "authenticate"
                or not isinstance(auth_message.get("csrf_token"), str)
                or not auth_message["csrf_token"]
                or len(auth_message["csrf_token"]) > 2048
            ):
                raise DomainError(401, "authentication_required", "請先使用 Identity Cookie 與 CSRF token 驗證")
            csrf_token = auth_message["csrf_token"]
            with application.state.session_factory() as session:
                principal = await websocket_cookie_principal(websocket, session, csrf_token)
                draft = get_document_draft(session, principal, document_id)
                _touch_presence(
                    session,
                    connection_id=connection_id,
                    document_id=document_id,
                    principal=principal,
                    enforce_limit=True,
                )
                participants = _participants(session, document_id)
                session.commit()
            await websocket.send_json({"type": "sync", "draft": draft, "participants": participants})
            last_revision = int(draft["revision"])
            last_participants = tuple((item["id"], item["name"], item["kind"]) for item in participants)
            last_heartbeat = last_reauth = time.monotonic()
        except DomainError as error:
            await _send_error(websocket, error)
            await websocket.close(code=4401 if error.status_code == 401 else 4403)
            return

        while True:
            now = time.monotonic()
            try:
                message = await _receive_json(websocket, timeout=DB_POLL_SECONDS)
            except DomainError as error:
                await _send_error(websocket, error)
                await websocket.close(code=1009 if error.status_code == 413 else 4400)
                return

            now = time.monotonic()
            if now - last_reauth >= REAUTH_SECONDS:
                try:
                    with application.state.session_factory() as session:
                        current = await websocket_cookie_principal(websocket, session, csrf_token)
                        _principal_id_for_cookie(principal, current)
                        get_document_draft(session, current, document_id)
                        _touch_presence(
                            session,
                            connection_id=connection_id,
                            document_id=document_id,
                            principal=current,
                        )
                        session.commit()
                    principal = current
                    last_reauth = time.monotonic()
                    last_heartbeat = last_reauth
                except DomainError as error:
                    await _send_error(websocket, error)
                    await websocket.close(code=4401 if error.status_code == 401 else 4403)
                    return

            if message is not None:
                if now - message_window >= 60:
                    message_window = now
                    message_count = 0
                    update_count = 0
                message_count += 1
                if message_count > MAX_MESSAGES_PER_MINUTE:
                    await _send_error(websocket, DomainError(429, "rate_limited", "共同編輯訊息頻率超過上限"))
                    await websocket.close(code=4429)
                    return
                if message.get("type") != "update" or set(message) != {"type", "update", "request_id"}:
                    await _send_error(websocket, DomainError(422, "invalid_collaboration_message", "只接受格式正確的 update 訊息"))
                    continue
                request_id = message.get("request_id")
                encoded_update = message.get("update")
                if not isinstance(request_id, str) or not isinstance(encoded_update, str):
                    await _send_error(websocket, DomainError(422, "invalid_collaboration_message", "update 與 request_id 必須是字串"))
                    continue
                update_count += 1
                if update_count > MAX_UPDATES_PER_MINUTE:
                    await _send_error(
                        websocket,
                        DomainError(429, "rate_limited", "共同編輯更新頻率超過上限"),
                        request_id,
                    )
                    await websocket.close(code=4429)
                    return
                try:
                    if principal is None:
                        raise DomainError(401, "authentication_required", "共同編輯工作階段尚未驗證")
                    with application.state.session_factory() as session:
                        with session.begin_nested():
                            draft = apply_websocket_draft_update(
                                session,
                                principal,
                                document_id,
                                encoded_update,
                                request_id,
                            )
                            _touch_presence(
                                session,
                                connection_id=connection_id,
                                document_id=document_id,
                                principal=principal,
                            )
                        session.commit()
                    await websocket.send_json({"type": "ack", "request_id": request_id, "draft": draft})
                    last_revision = int(draft["revision"])
                    last_heartbeat = time.monotonic()
                except DomainError as error:
                    await _send_error(websocket, error, request_id)
                    if error.status_code in {401, 403, 404}:
                        await websocket.close(code=4403)
                        return
                except Exception:
                    await _send_error(websocket, DomainError(500, "collaboration_failed", "共同編輯更新無法儲存"), request_id)
                    await websocket.close(code=1011)
                    return

            try:
                with application.state.session_factory() as session:
                    if now - last_heartbeat >= HEARTBEAT_SECONDS:
                        _touch_presence(
                            session,
                            connection_id=connection_id,
                            document_id=document_id,
                            principal=principal,
                        )
                        last_heartbeat = now
                    draft = get_document_draft(session, principal, document_id)
                    participants = _participants(session, document_id)
                    session.commit()
                revision = int(draft["revision"])
                if revision != last_revision:
                    await websocket.send_json({"type": "sync", "draft": draft, "participants": participants})
                    last_revision = revision
                participant_state = tuple((item["id"], item["name"], item["kind"]) for item in participants)
                if participant_state != last_participants:
                    await websocket.send_json({"type": "presence", "participants": participants})
                    last_participants = participant_state
            except WebSocketDisconnect:
                raise
            except DomainError as error:
                await _send_error(websocket, error)
                await websocket.close(code=4403)
                return
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await _send_error(websocket, DomainError(500, "collaboration_failed", "共同編輯連線發生錯誤"))
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        try:
            with application.state.session_factory() as session:
                session.execute(delete(CollaborationPresence).where(CollaborationPresence.connection_id == connection_id))
                session.commit()
                if principal is not None:
                    participants = _participants(session, document_id)
                else:
                    participants = []
            if websocket.application_state.name == "CONNECTED":
                await websocket.send_json({"type": "presence", "participants": participants})
                await websocket.close(code=1000)
        except Exception:
            pass
        application.state.collaboration_connections = max(0, application.state.collaboration_connections - 1)
