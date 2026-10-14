"""Identity mail delivery and bounded enterprise governance."""
from __future__ import annotations

import asyncio
import json
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage
from urllib.parse import urlencode
from uuid import uuid4
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.orm import Session
from .api import SessionContext, _audit, _aware, _check_csrf, _client_host, _now, _record_throttle_failure, _require_admin, _sso_only, _throttle_is_locked, _throttle_key, current_session, get_db
from .config import Settings
from .enterprise_models import EnterprisePolicy, MailOutbox
from .errors import DomainError
from .models import IdentityAuditEvent, RecoveryCode, User
from .schemas import permissions_data
from .security import keyed_hash, new_secret

router = APIRouter()


def policy(db: Session) -> dict:
    row = db.get(EnterprisePolicy, 1)
    return {"audit_retention_days": 365, "scim_group_mappings": {}, **(row.values if row else {})}


def mail_enabled(settings: Settings) -> bool:
    return bool(settings.smtp_host and settings.smtp_sender)


def queue_mail(db: Session, settings: Settings, *, kind: str, recipient: str, code: str, expires_at) -> bool:
    if not mail_enabled(settings):
        return False
    from .sso import _encrypt
    payload = json.dumps({"code": code})
    db.add(MailOutbox(id=str(uuid4()), kind=kind, recipient=recipient,
        payload_ciphertext=_encrypt(settings, payload, b"mail"), status="pending", attempts=0,
        next_attempt_at=_now(), created_at=_now(), expires_at=expires_at))
    return True


def deliver_mail(factory, settings: Settings) -> None:
    if not mail_enabled(settings):
        return
    # Production mail must authenticate the transport, including when no SMTP login is required.
    if settings.mode == "production" and not settings.smtp_starttls:
        return
    with factory() as db:
        now = _now()
        row = db.scalar(select(MailOutbox).where(MailOutbox.status.in_(["pending", "sending"]),
                MailOutbox.next_attempt_at <= now).order_by(MailOutbox.created_at).limit(1).with_for_update(skip_locked=True))
        if not row:
            return
        if _aware(row.expires_at) <= now:
            row.status, row.payload_ciphertext = "expired", ""
            db.commit()
            return
        ident = row.id
        row.status, row.attempts = "sending", row.attempts + 1
        row.next_attempt_at = now + timedelta(seconds=120)
        db.commit()
    try:
        from .sso import _decrypt
        payload = json.loads(_decrypt(settings, row.payload_ciphertext, b"mail"))
        origin = settings.mail_public_origin or settings.auth_origins[0]
        fragment = urlencode({"auth": "invite" if row.kind == "invitation" else "recover",
                              "code": payload["code"], "email": row.recipient})
        email = EmailMessage()
        email["From"], email["To"] = settings.smtp_sender, row.recipient
        email["Subject"] = "Ordivant invitation" if row.kind == "invitation" else "Ordivant account recovery"
        email["Message-ID"] = f"<{ident}@ordivant.local>"
        email.set_content(f"{email['Subject']}\n\n{origin}/work#{fragment}\n\nThis link expires at {_aware(row.expires_at).isoformat()}.\nIf you did not request this, ignore this email.")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(email)
    except Exception:
        with factory() as db:
            current = db.get(MailOutbox, ident)
            current.status = "failed" if current.attempts >= 5 else "pending"
            current.last_error = "smtp_delivery_failed"
            current.next_attempt_at = _now() + timedelta(seconds=min(3600, 30 * 2 ** current.attempts))
            db.commit()
        return
    with factory() as db:
        current = db.get(MailOutbox, ident)
        current.status, current.sent_at, current.last_error = "sent", _now(), None
        current.payload_ciphertext = ""
        _audit(db, "mail.sent", details={"mail_id": ident, "kind": current.kind})
        db.commit()


async def mail_worker(factory, settings: Settings) -> None:
    while True:
        try:
            await asyncio.to_thread(deliver_mail, factory, settings)
        except Exception:
            # A DB outage leaves the durable queue available for the next attempt.
            pass
        await asyncio.sleep(10)


class RecoveryMailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


@router.post("/request-recovery")
def request_recovery(body: RecoveryMailRequest, request: Request, db: Session = Depends(get_db)):
    settings = request.app.state.settings
    email = str(body.email).casefold()
    throttle = _throttle_key(settings, "recovery_mail", email, _client_host(request))
    if _throttle_is_locked(db, throttle):
        raise DomainError(429, "auth_throttled", "Try again later")
    _record_throttle_failure(db, throttle, settings)
    user = db.scalar(select(User).where(User.normalized_email == email, User.active.is_(True)))
    if mail_enabled(settings) and user and user.credential_type == "local" and (user.role == "admin" or not _sso_only(db)):
        code = new_secret()
        now = _now()
        # A mail link is a short-lived, one-time recovery credential; existing offline codes remain valid.
        from .enterprise_models import RecoveryMailCredential
        db.add(RecoveryMailCredential(code_hash=keyed_hash(settings.service_secret, "recovery", code),
                                      user_id=user.id, expires_at=now + timedelta(minutes=30)))
        db.add(RecoveryCode(id=str(uuid4()), user_id=user.id, code_hash=keyed_hash(settings.service_secret, "recovery", code), created_at=now))
        queue_mail(db, settings, kind="recovery", recipient=user.email, code=code, expires_at=now + timedelta(minutes=30))
        _audit(db, "recovery.mail_requested", user_id=user.id)
    db.commit()
    # Identical for nonexistent, disabled, external-only and local accounts.
    return {"accepted": True}


class PolicyWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audit_retention_days: int = Field(default=365, ge=30, le=3650)
    scim_group_mappings: dict = Field(default_factory=dict)


def admin(request: Request, ctx: SessionContext, csrf: str | None) -> None:
    _require_admin(ctx)
    if request.method != "GET":
        _check_csrf(ctx, request.app.state.settings, csrf)


@router.get("/enterprise")
def get_enterprise(request: Request, ctx: SessionContext = Depends(current_session), db: Session = Depends(get_db)):
    _require_admin(ctx)
    return {**policy(db), "scim_enabled": bool(request.app.state.settings.scim_token),
            "scim_endpoint": "/api/scim/v2", "mail_enabled": mail_enabled(request.app.state.settings),
            "mail_transport_ready": mail_enabled(request.app.state.settings) and (request.app.state.settings.mode != "production" or request.app.state.settings.smtp_starttls)}


@router.put("/enterprise")
def put_enterprise(body: PolicyWrite, request: Request, ctx: SessionContext = Depends(current_session), db: Session = Depends(get_db),
                   x_csrf_token: str | None = Header(default=None)):
    admin(request, ctx, x_csrf_token)
    from .scim import lock_provisioning
    lock_provisioning(db)
    if len(body.scim_group_mappings) > 500:
        raise DomainError(422, "invalid_mapping", "Too many group mappings")
    mappings = {}
    for name, grants in body.scim_group_mappings.items():
        if not isinstance(name, str) or not name.strip() or len(name) > 160:
            raise DomainError(422, "invalid_mapping", "Invalid group name")
        try:
            mappings[name] = permissions_data(grants)
        except ValueError:
            raise DomainError(422, "invalid_mapping", "Invalid product grants")
        if any(scope in {"*", "**"} for grant in mappings[name].values() for scope in grant["scope_ids"]):
            raise DomainError(422, "invalid_mapping", "Provisioning requires exact resource IDs")
    values = {"audit_retention_days": body.audit_retention_days, "scim_group_mappings": mappings}
    row = db.get(EnterprisePolicy, 1)
    if row:
        row.values = values
    else:
        db.add(EnterprisePolicy(id=1, values=values))
    db.flush()
    from .scim import recompute
    recompute(db)
    _audit(db, "enterprise.policy_updated", actor_id=ctx.user.id)
    db.commit()
    return get_enterprise(request, ctx, db)


@router.get("/mail-outbox")
def mail_outbox(request: Request, ctx: SessionContext = Depends(current_session), db: Session = Depends(get_db)):
    admin(request, ctx, None)
    rows = db.scalars(select(MailOutbox).order_by(MailOutbox.created_at.desc()).limit(100)).all()
    return [{"id": row.id, "kind": row.kind, "recipient": row.recipient, "status": row.status, "attempts": row.attempts,
             "created_at": _aware(row.created_at).isoformat(), "last_error": row.last_error} for row in rows]


@router.post("/mail-outbox/{ident}/retry")
def retry_mail(ident: str, request: Request, ctx: SessionContext = Depends(current_session), db: Session = Depends(get_db),
               x_csrf_token: str | None = Header(default=None)):
    admin(request, ctx, x_csrf_token)
    row = db.get(MailOutbox, ident)
    if not row or row.status not in {"failed", "pending"} or _aware(row.expires_at) <= _now():
        raise DomainError(409, "mail_not_retryable", "Mail delivery cannot be retried")
    row.status, row.attempts, row.next_attempt_at = "pending", 0, _now()
    _audit(db, "mail.retry_requested", actor_id=ctx.user.id, details={"mail_id": ident})
    db.commit()
    return {"accepted": True}


@router.get("/audit/export")
def export_audit(request: Request, ctx: SessionContext = Depends(current_session), db: Session = Depends(get_db),
                 limit: int = Query(default=1000, ge=1, le=10000), before: str | None = None,
                 before_id: str | None = Query(default=None, min_length=1, max_length=36)):
    admin(request, ctx, None)
    query = select(IdentityAuditEvent).order_by(IdentityAuditEvent.created_at.desc(), IdentityAuditEvent.id)
    if before:
        from datetime import datetime
        try:
            cutoff = datetime.fromisoformat(before.replace("Z", "+00:00"))
            if cutoff.tzinfo is None:
                raise ValueError()
        except ValueError:
            raise DomainError(422, "invalid_cursor", "Use an ISO timestamp with a timezone")
        if before_id:
            query = query.where(or_(IdentityAuditEvent.created_at < cutoff,
                and_(IdentityAuditEvent.created_at == cutoff, IdentityAuditEvent.id > before_id)))
        else:
            query = query.where(IdentityAuditEvent.created_at < cutoff)
    elif before_id:
        raise DomainError(422, "invalid_cursor", "Use an ISO timestamp with a timezone")
    rows = db.scalars(query.limit(limit)).all()
    # Audit detail schemas are internal; never export arbitrary future detail values/credentials.
    safe_keys = {"role", "resource_id", "resource_type", "mail_id", "kind", "count", "method", "reason", "provider_name"}
    lines = [json.dumps({"id": row.id, "created_at": _aware(row.created_at).isoformat(), "actor_id": row.actor_id,
        "user_id": row.user_id, "action": row.action, "details": {key: value for key, value in row.details.items() if key in safe_keys}}, ensure_ascii=False) for row in rows]
    _audit(db, "audit.exported", actor_id=ctx.user.id, details={"count": len(rows)})
    db.commit()
    headers = {"Content-Disposition": 'attachment; filename="ordivant-identity-audit.jsonl"', "Cache-Control": "private, no-store"}
    if len(rows) == limit:
        headers.update({"X-Next-Before": _aware(rows[-1].created_at).isoformat(), "X-Next-Before-Id": rows[-1].id})
    return Response("\n".join(lines) + ("\n" if lines else ""), media_type="application/x-ndjson", headers=headers)


@router.post("/audit/retention")
def apply_retention(request: Request, ctx: SessionContext = Depends(current_session), db: Session = Depends(get_db),
                    x_csrf_token: str | None = Header(default=None)):
    admin(request, ctx, x_csrf_token)
    cutoff = _now() - timedelta(days=policy(db)["audit_retention_days"])
    result = db.execute(delete(IdentityAuditEvent).where(IdentityAuditEvent.created_at < cutoff))
    _audit(db, "audit.retention_applied", actor_id=ctx.user.id, details={"count": result.rowcount})
    db.commit()
    return {"deleted": result.rowcount, "cutoff": cutoff.isoformat()}
