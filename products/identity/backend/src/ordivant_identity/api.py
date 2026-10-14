from __future__ import annotations

import ipaddress
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import case, delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings
from .db import session_dependency
from .errors import DomainError
from .models import (
    AuthSession,
    AuthThrottle,
    IdentityAuditEvent,
    IdentityLink,
    Invitation,
    RecoveryCode,
    SetupMarker,
    SSOConfiguration,
    User,
)
from .schemas import (
    AcceptInvitationRequest,
    ChangePasswordRequest,
    IntrospectRequest,
    InvitationRequest,
    LoginRequest,
    RecoverRequest,
    SessionOut,
    SetupRequest,
    UserOut,
    UserPatch,
    permissions_data,
)
from .security import (
    DUMMY_PASSWORD_HASH,
    constant_time_equal,
    csrf_token,
    hash_password,
    keyed_hash,
    new_secret,
    session_hash,
    verify_password,
)


router = APIRouter()
_SESSION_ERROR = "Authentication is required"
_CREDENTIAL_ERROR = "Unable to authenticate with those credentials"


@dataclass
class SessionContext:
    user: User
    auth_session: AuthSession
    raw_handle: str


def get_db(request: Request):
    yield from session_dependency(request.app.state.session_factory)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _aware(value).isoformat().replace("+00:00", "Z")


def _expires_at(auth_session: AuthSession) -> datetime:
    return min(_aware(auth_session.idle_expires_at), _aware(auth_session.absolute_expires_at))


def _user_json(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        active=user.active,
        permissions=permissions_data(user.permissions),
        credential_type=user.credential_type,
        permissions_source=user.permissions_source,
    )


def _session_json(
    user: User,
    auth_session: AuthSession,
    raw_handle: str,
    settings: Settings,
    recovery_codes: list[str] | None = None,
) -> SessionOut:
    return SessionOut(
        user=_user_json(user),
        csrf_token=csrf_token(settings.service_secret, raw_handle),
        expires_at=_iso(_expires_at(auth_session)),
        authentication={"method": auth_session.authentication_method, "provider_name": auth_session.provider_name},
        recovery_codes=recovery_codes,
    )


def _new_user(
    *, email: str, name: str, role: str, password: str, permissions: dict | None = None
) -> User:
    now = _now()
    return User(
        id=str(uuid4()),
        email=email,
        normalized_email=email.casefold(),
        name=name,
        role=role,
        active=True,
        permissions=permissions or {},
        password_hash=hash_password(password),
        created_at=now,
        updated_at=now,
    )


def _new_session(
    db: Session,
    user: User,
    settings: Settings,
    *,
    authentication_method: str = "password",
    provider_name: str | None = None,
    oidc_issuer: str | None = None,
    oidc_subject: str | None = None,
    oidc_sid: str | None = None,
) -> tuple[AuthSession, str]:
    now = _now()
    handle = new_secret()
    auth_session = AuthSession(
        id=str(uuid4()),
        token_hash=session_hash(handle),
        user_id=user.id,
        created_at=now,
        last_seen_at=now,
        idle_expires_at=now + timedelta(minutes=settings.session_idle_minutes),
        absolute_expires_at=now + timedelta(hours=settings.session_absolute_hours),
        authentication_method=authentication_method,
        provider_name=provider_name,
        oidc_issuer=oidc_issuer,
        oidc_subject=oidc_subject,
        oidc_sid=oidc_sid,
        revoked_at=None,
    )
    db.add(auth_session)
    return auth_session, handle


def _audit(
    db: Session,
    action: str,
    *,
    actor_id: str | None = None,
    user_id: str | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        IdentityAuditEvent(
            id=str(uuid4()),
            created_at=_now(),
            actor_id=actor_id,
            user_id=user_id,
            action=action,
            details=details or {},
        )
    )


def _sso_only(db: Session) -> bool:
    row = db.get(SSOConfiguration, 1)
    return bool(row and (row.settings_json or {}).get("login_policy") == "sso_only")


def _new_recovery_codes(db: Session, user: User, settings: Settings) -> list[str]:
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    now = _now()
    codes = [new_secret() for _ in range(10)]
    db.add_all(
        RecoveryCode(
            id=str(uuid4()),
            user_id=user.id,
            code_hash=keyed_hash(settings.service_secret, "recovery", code),
            created_at=now,
            used_at=None,
        )
        for code in codes
    )
    return codes


def _set_cookie(response: Response, handle: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.cookie_name,
        value=handle,
        max_age=settings.session_absolute_hours * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _unauthorized(code: str = "unauthorized", message: str = _SESSION_ERROR) -> DomainError:
    return DomainError(401, code, message)


def _current_session(request: Request, db: Session) -> SessionContext:
    settings = _settings(request)
    raw_handle = request.cookies.get(settings.cookie_name)
    if not raw_handle:
        raise _unauthorized()

    auth_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == session_hash(raw_handle)))
    if auth_session is None or auth_session.revoked_at is not None:
        raise _unauthorized()

    now = _now()
    if now >= _expires_at(auth_session):
        auth_session.revoked_at = now
        db.commit()
        raise _unauthorized("session_expired", "The session has expired")

    user = db.get(User, auth_session.user_id)
    if user is None or not user.active:
        auth_session.revoked_at = now
        db.commit()
        raise _unauthorized()

    auth_session.last_seen_at = now
    auth_session.idle_expires_at = min(
        now + timedelta(minutes=settings.session_idle_minutes), _aware(auth_session.absolute_expires_at)
    )
    return SessionContext(user=user, auth_session=auth_session, raw_handle=raw_handle)


def current_session(request: Request, db: Session = Depends(get_db)) -> SessionContext:
    return _current_session(request, db)


def _check_csrf(ctx: SessionContext, settings: Settings, supplied: str | None) -> None:
    expected = csrf_token(settings.service_secret, ctx.raw_handle)
    if not constant_time_equal(expected, supplied):
        raise DomainError(403, "csrf_invalid", "A valid X-CSRF-Token is required")


def _require_admin(ctx: SessionContext) -> None:
    if ctx.user.role != "admin":
        raise DomainError(403, "admin_required", "Administrator access is required")


def _throttle_key(settings: Settings, action: str, identifier: str, client_host: str) -> str:
    return keyed_hash(settings.service_secret, f"throttle-{action}", f"{identifier.casefold()}|{client_host}")


def _throttle_is_locked(db: Session, scope_hash: str) -> bool:
    row = db.get(AuthThrottle, scope_hash)
    return bool(row and row.locked_until is not None and row.locked_until > time.time())


def _record_throttle_failure(db: Session, scope_hash: str, settings: Settings) -> bool:
    now = time.time()
    expired_window = AuthThrottle.window_started_at <= now - settings.throttle_window_seconds
    new_failures = case((expired_window, 1), else_=AuthThrottle.failures + 1)
    new_lock = case(
        (expired_window, None),
        (AuthThrottle.failures + 1 >= settings.throttle_limit, now + settings.throttle_lock_seconds),
        else_=AuthThrottle.locked_until,
    )
    values = {
        "scope_hash": scope_hash,
        "failures": 1,
        "window_started_at": now,
        "locked_until": None,
    }
    if db.bind is None:
        raise RuntimeError("Database is unavailable")
    if db.bind.dialect.name == "sqlite":
        statement = sqlite_insert(AuthThrottle).values(**values)
    elif db.bind.dialect.name == "postgresql":
        statement = pg_insert(AuthThrottle).values(**values)
    else:
        raise RuntimeError("Identity database must be SQLite or PostgreSQL")
    statement = statement.on_conflict_do_update(
        index_elements=[AuthThrottle.scope_hash],
        set_={
            "failures": new_failures,
            "window_started_at": case((expired_window, now), else_=AuthThrottle.window_started_at),
            "locked_until": new_lock,
        },
    )
    db.execute(statement)
    db.flush()
    row = db.get(AuthThrottle, scope_hash)
    if row is not None:
        db.refresh(row)
    return bool(row and row.locked_until is not None and row.locked_until > now)


def _clear_throttle(db: Session, scope_hash: str) -> None:
    db.execute(delete(AuthThrottle).where(AuthThrottle.scope_hash == scope_hash))


def _client_host(request: Request) -> str:
    if request.client is None:
        return "unknown"
    peer = request.client.host
    try:
        peer_ip = ipaddress.ip_address(peer.split("%", 1)[0])
    except ValueError:
        return peer
    peer_address = str(peer_ip)
    settings = _settings(request)
    trusted_addresses: set[str] = set()
    for host in settings.auth_trusted_proxy_hosts:
        try:
            trusted_addresses.add(str(ipaddress.ip_address(host)))
        except ValueError:
            try:
                resolved = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            except OSError:
                continue
            for result in resolved:
                try:
                    trusted_addresses.add(str(ipaddress.ip_address(result[4][0].split("%", 1)[0])))
                except ValueError:
                    continue
    if peer_address not in trusted_addresses:
        return peer_address
    forwarded = request.headers.getlist("x-real-ip")
    if len(forwarded) != 1 or forwarded[0] != forwarded[0].strip() or "," in forwarded[0]:
        return peer_address
    try:
        return str(ipaddress.ip_address(forwarded[0]))
    except ValueError:
        return peer_address


def _auth_session_response(
    response: Response,
    user: User,
    auth_session: AuthSession,
    raw_handle: str,
    settings: Settings,
    recovery_codes: list[str] | None = None,
) -> SessionOut:
    _set_cookie(response, raw_handle, settings)
    return _session_json(user, auth_session, raw_handle, settings, recovery_codes)


@router.get("/status")
def status(request: Request, db: Session = Depends(get_db)) -> dict:
    settings = _settings(request)
    row = db.get(SSOConfiguration, 1)
    settings_json = row.settings_json if row else {}
    return {
        "setup_required": db.get(SetupMarker, 1) is None,
        "sso": {
            "enabled": bool(settings_json.get("enabled", False)),
            "display_name": settings_json.get("display_name", "企業帳號"),
            "login_policy": settings_json.get("login_policy", "password_and_sso"),
            "configured": bool(
                settings_json.get("enabled")
                and settings_json.get("issuer_url")
                and settings_json.get("client_id")
                and row is not None
                and row.client_secret_ciphertext
            ),
            "public_origin": settings.sso_public_origin or settings.auth_origins[0],
        },
    }


@router.post("/setup", status_code=201)
def setup(body: SetupRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> SessionOut:
    settings = _settings(request)
    if db.get(SetupMarker, 1) is not None:
        raise DomainError(409, "setup_complete", "Initial administrator setup has already completed")
    user = _new_user(email=str(body.email), name=body.name, role="admin", password=body.password)
    db.add(user)
    try:
        db.flush()
        db.add(SetupMarker(id=1, admin_user_id=user.id))
        recovery_codes = _new_recovery_codes(db, user, settings)
        auth_session, raw_handle = _new_session(db, user, settings)
        _audit(db, "admin.setup", actor_id=user.id, user_id=user.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DomainError(409, "setup_complete", "Initial administrator setup has already completed") from exc
    return _auth_session_response(response, user, auth_session, raw_handle, settings, recovery_codes)


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> SessionOut:
    settings = _settings(request)
    scope = _throttle_key(settings, "login", str(body.email), _client_host(request))
    if _throttle_is_locked(db, scope):
        raise DomainError(429, "auth_throttled", _CREDENTIAL_ERROR)

    user = db.scalar(select(User).where(User.normalized_email == str(body.email)))
    verified = verify_password(user.password_hash if user else DUMMY_PASSWORD_HASH, body.password)
    password_allowed = user is not None and (
        user.role == "admin" or (not _sso_only(db) and user.credential_type == "local")
    )
    if user is None or not user.active or not verified or not password_allowed:
        locked = _record_throttle_failure(db, scope, settings)
        _audit(db, "local.login_failure", user_id=user.id if user else None)
        db.commit()
        if locked:
            raise DomainError(429, "auth_throttled", _CREDENTIAL_ERROR)
        raise DomainError(401, "invalid_credentials", _CREDENTIAL_ERROR)

    _clear_throttle(db, scope)
    auth_session, raw_handle = _new_session(db, user, settings)
    _audit(db, "local.login_success", actor_id=user.id, user_id=user.id)
    db.commit()
    return _auth_session_response(response, user, auth_session, raw_handle, settings)


@router.get("/me")
def me(request: Request, response: Response, ctx: SessionContext = Depends(current_session), db: Session = Depends(get_db)) -> SessionOut:
    db.commit()
    return _session_json(ctx.user, ctx.auth_session, ctx.raw_handle, _settings(request))


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    ctx: SessionContext = Depends(current_session),
    db: Session = Depends(get_db),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    settings = _settings(request)
    _check_csrf(ctx, settings, x_csrf_token)
    ctx.auth_session.revoked_at = _now()
    _audit(db, "session.logout", actor_id=ctx.user.id, user_id=ctx.user.id, details={"method": ctx.auth_session.authentication_method})
    db.commit()
    _clear_cookie(response, settings)
    return {"ok": True}


@router.post("/logout-all")
def logout_all(
    request: Request,
    response: Response,
    ctx: SessionContext = Depends(current_session),
    db: Session = Depends(get_db),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    settings = _settings(request)
    _check_csrf(ctx, settings, x_csrf_token)
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == ctx.user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    _audit(db, "session.logout_all", actor_id=ctx.user.id, user_id=ctx.user.id)
    db.commit()
    _clear_cookie(response, settings)
    return {"ok": True}


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    ctx: SessionContext = Depends(current_session),
    db: Session = Depends(get_db),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> SessionOut:
    settings = _settings(request)
    _check_csrf(ctx, settings, x_csrf_token)
    if ctx.user.role != "admin" and (_sso_only(db) or ctx.user.credential_type == "sso"):
        raise DomainError(403, "sso_only", "This account uses enterprise sign-in")
    if not verify_password(ctx.user.password_hash, body.current_password):
        raise DomainError(401, "invalid_current_password", "Current password is incorrect")
    now = _now()
    ctx.user.password_hash = hash_password(body.new_password)
    ctx.user.updated_at = now
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == ctx.user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    recovery_codes = _new_recovery_codes(db, ctx.user, settings)
    auth_session, raw_handle = _new_session(db, ctx.user, settings)
    _audit(db, "local.password_changed", actor_id=ctx.user.id, user_id=ctx.user.id)
    db.commit()
    return _auth_session_response(response, ctx.user, auth_session, raw_handle, settings, recovery_codes)


@router.post("/recover")
def recover(body: RecoverRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> SessionOut:
    settings = _settings(request)
    scope = _throttle_key(settings, "recover", str(body.email), _client_host(request))
    if _throttle_is_locked(db, scope):
        raise DomainError(429, "auth_throttled", "Unable to recover with those credentials")

    user = db.scalar(select(User).where(User.normalized_email == str(body.email)))
    code_hash = keyed_hash(settings.service_secret, "recovery", body.recovery_code)
    recovery = None
    from .enterprise_models import RecoveryMailCredential
    mail_credential = db.get(RecoveryMailCredential, code_hash)
    mail_expired = bool(mail_credential and _aware(mail_credential.expires_at) <= _now())
    if user is not None and user.active and user.role != "admin" and (_sso_only(db) or user.credential_type == "sso"):
        user = None
    if user is not None and user.active and not mail_expired:
        recovery = db.scalar(
            select(RecoveryCode).where(
                RecoveryCode.user_id == user.id,
                RecoveryCode.code_hash == code_hash,
                RecoveryCode.used_at.is_(None),
            )
        )
    if user is None or not user.active or recovery is None:
        locked = _record_throttle_failure(db, scope, settings)
        _audit(db, "local.recovery_failure", user_id=user.id if user else None)
        db.commit()
        if locked:
            raise DomainError(429, "auth_throttled", "Unable to recover with those credentials")
        raise DomainError(401, "invalid_recovery", "Unable to recover with those credentials")

    now = _now()
    consumed = db.execute(
        update(RecoveryCode)
        .where(RecoveryCode.id == recovery.id, RecoveryCode.used_at.is_(None))
        .values(used_at=now)
    )
    if consumed.rowcount != 1:
        db.rollback()
        raise DomainError(401, "invalid_recovery", "Unable to recover with those credentials")
    user.password_hash = hash_password(body.new_password)
    user.updated_at = now
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    recovery_codes = _new_recovery_codes(db, user, settings)
    auth_session, raw_handle = _new_session(db, user, settings)
    _clear_throttle(db, scope)
    _audit(db, "local.password_recovered", actor_id=user.id, user_id=user.id)
    db.commit()
    return _auth_session_response(response, user, auth_session, raw_handle, settings, recovery_codes)


@router.get("/sessions")
def sessions(
    request: Request,
    ctx: SessionContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> dict:
    now = _now()
    rows = db.scalars(
        select(AuthSession)
        .where(
            AuthSession.user_id == ctx.user.id,
            AuthSession.revoked_at.is_(None),
            AuthSession.idle_expires_at > now,
            AuthSession.absolute_expires_at > now,
        )
        .order_by(AuthSession.created_at.desc())
    ).all()
    result = [
        {
            "id": item.id,
            "created_at": _iso(item.created_at),
            "last_seen_at": _iso(item.last_seen_at),
            "expires_at": _iso(_expires_at(item)),
            "current": item.id == ctx.auth_session.id,
        }
        for item in rows
    ]
    db.commit()
    return {"sessions": result}


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: str,
    request: Request,
    response: Response,
    ctx: SessionContext = Depends(current_session),
    db: Session = Depends(get_db),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    settings = _settings(request)
    _check_csrf(ctx, settings, x_csrf_token)
    target = db.scalar(
        select(AuthSession).where(AuthSession.id == session_id, AuthSession.user_id == ctx.user.id)
    )
    if target is None:
        raise DomainError(404, "session_not_found", "Session not found")
    if target.revoked_at is None:
        target.revoked_at = _now()
    db.commit()
    if target.id == ctx.auth_session.id:
        _clear_cookie(response, settings)
    return {"ok": True}


@router.get("/users")
def users(
    ctx: SessionContext = Depends(current_session), db: Session = Depends(get_db)
) -> dict:
    _require_admin(ctx)
    rows = db.scalars(select(User).order_by(User.created_at, User.normalized_email)).all()
    db.commit()
    return {"users": [_user_json(user) for user in rows]}


@router.post("/invitations", status_code=201)
def create_invitation(
    body: InvitationRequest,
    request: Request,
    ctx: SessionContext = Depends(current_session),
    db: Session = Depends(get_db),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    settings = _settings(request)
    _check_csrf(ctx, settings, x_csrf_token)
    _require_admin(ctx)
    email = str(body.email)
    if db.scalar(select(User.id).where(User.normalized_email == email)) is not None:
        raise DomainError(409, "account_exists", "An account already exists for this email")

    code = new_secret()
    now = _now()
    invitation = Invitation(
        id=str(uuid4()),
        code_hash=keyed_hash(settings.service_secret, "invitation", code),
        email=email,
        normalized_email=email,
        name=body.name,
        role=body.role,
        permissions=permissions_data(body.permissions),
        created_by=ctx.user.id,
        created_at=now,
        expires_at=now + timedelta(hours=24),
        consumed_at=None,
    )
    db.add(invitation)
    from .enterprise import queue_mail
    queued = queue_mail(db, settings, kind="invitation", recipient=email, code=code, expires_at=invitation.expires_at)
    _audit(db, "invitation.created", actor_id=ctx.user.id, details={"role": body.role})
    db.commit()
    return {"invitation_code": code, "expires_at": _iso(invitation.expires_at), "mail_queued": queued}


@router.post("/accept-invitation", status_code=201)
def accept_invitation(
    body: AcceptInvitationRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> SessionOut:
    settings = _settings(request)
    digest = keyed_hash(settings.service_secret, "invitation", body.invitation_code)
    invitation = db.scalar(
        select(Invitation).where(
            Invitation.code_hash == digest,
            Invitation.consumed_at.is_(None),
        )
    )
    now = _now()
    if invitation is None or now >= _aware(invitation.expires_at):
        raise DomainError(401, "invalid_invitation", "Invitation is invalid or expired")
    if invitation.role != "admin" and _sso_only(db):
        raise DomainError(409, "sso_only", "Member accounts must use enterprise sign-in")
    if db.scalar(select(User.id).where(User.normalized_email == invitation.normalized_email)) is not None:
        raise DomainError(409, "account_exists", "An account already exists for this email")

    consumed = db.execute(
        update(Invitation)
        .where(Invitation.id == invitation.id, Invitation.consumed_at.is_(None), Invitation.expires_at > now)
        .values(consumed_at=now)
        .execution_options(synchronize_session=False)
    )
    if consumed.rowcount != 1:
        db.rollback()
        raise DomainError(401, "invalid_invitation", "Invitation is invalid or expired")

    user = _new_user(
        email=invitation.email,
        name=invitation.name,
        role=invitation.role,
        password=body.password,
        permissions=invitation.permissions,
    )
    db.add(user)
    try:
        db.flush()
        recovery_codes = _new_recovery_codes(db, user, settings)
        auth_session, raw_handle = _new_session(db, user, settings)
        _audit(db, "invitation.accepted", actor_id=user.id, user_id=user.id, details={"role": user.role})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DomainError(409, "invitation_conflict", "Invitation could not be accepted") from exc
    return _auth_session_response(response, user, auth_session, raw_handle, settings, recovery_codes)


@router.patch("/users/{user_id}")
def patch_user(
    user_id: str,
    body: UserPatch,
    request: Request,
    response: Response,
    ctx: SessionContext = Depends(current_session),
    db: Session = Depends(get_db),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> UserOut:
    settings = _settings(request)
    _check_csrf(ctx, settings, x_csrf_token)
    _require_admin(ctx)
    target = db.get(User, user_id)
    if target is None:
        raise DomainError(404, "user_not_found", "User not found")

    fields = body.model_fields_set
    if "active" in fields and body.active is False and target.active and target.role == "admin":
        admin_ids = db.scalars(
            select(User.id)
            .where(User.role == "admin", User.active.is_(True))
            .order_by(User.id)
            .with_for_update()
        ).all()
        if len(admin_ids) <= 1:
            raise DomainError(409, "last_admin", "The last active administrator cannot be disabled")
    if target.id == ctx.user.id and "active" in fields and body.active is False:
        raise DomainError(409, "self_lockout", "An administrator cannot disable their own account")

    permissions_changed = False
    if "name" in fields and body.name is not None:
        target.name = body.name
    if "active" in fields and body.active is not None:
        target.active = body.active
    if "permissions" in fields and body.permissions is not None:
        new_permissions = permissions_data(body.permissions)
        if target.permissions_source == "scim" and new_permissions != (target.permissions or {}):
            raise DomainError(409, "scim_managed_user", "Manage this account's permissions through provisioning groups")
        permissions_changed = new_permissions != (target.permissions or {})
        target.permissions = new_permissions
        if target.credential_type == "sso" and target.permissions_source != "scim":
            target.permissions_source = "manual"
            db.execute(
                update(IdentityLink)
                .where(IdentityLink.user_id == target.id, IdentityLink.managed_permissions.is_(True))
                .values(managed_permissions=False)
            )

    if permissions_changed or ("active" in fields and body.active is False):
        now = _now()
        db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == target.id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        if target.id == ctx.user.id:
            _clear_cookie(response, settings)
    target.updated_at = _now()
    changed_fields = sorted(name for name in ("active", "name", "permissions") if name in fields)
    if changed_fields:
        _audit(
            db,
            "admin.user_updated",
            actor_id=ctx.user.id,
            user_id=target.id,
            details={"fields": changed_fields, "active": target.active},
        )
    db.commit()
    return _user_json(target)


@router.post("/introspect")
def introspect(
    body: IntrospectRequest,
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    settings = _settings(request)
    expected = f"Bearer {settings.service_secret}"
    if not constant_time_equal(expected, authorization):
        raise _unauthorized("service_unauthorized", "Identity service authorization is required")

    auth_session = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == session_hash(body.session_token))
    )
    now = _now()
    if auth_session is None or auth_session.revoked_at is not None or now >= _expires_at(auth_session):
        raise _unauthorized("session_invalid", "Session is invalid or expired")
    user = db.get(User, auth_session.user_id)
    if user is None or not user.active:
        raise _unauthorized("session_invalid", "Session is invalid or expired")
    auth_session.last_seen_at = now
    auth_session.idle_expires_at = min(
        now + timedelta(minutes=settings.session_idle_minutes), _aware(auth_session.absolute_expires_at)
    )
    result = {
        "user": _user_json(user),
        "csrf_token": csrf_token(settings.service_secret, body.session_token),
        "session_id": auth_session.id,
        "expires_at": _iso(_expires_at(auth_session)),
        "authentication": {
            "method": auth_session.authentication_method,
            "provider_name": auth_session.provider_name,
        },
    }
    db.commit()
    return result


@router.get("/directory")
def product_directory(
    request: Request,
    product: str = Query(pattern="^(work|knowledge|code)$"),
    scope_id: str = Query(min_length=1, max_length=80),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    if not constant_time_equal(f"Bearer {_settings(request).service_secret}", authorization):
        raise _unauthorized("service_unauthorized", "Identity service authorization is required")
    roles = {"manager", "worker", "reviewer"} if product == "work" else {"manager", "writer", "reader"}
    result = []
    for user in db.scalars(select(User).where(User.active.is_(True)).order_by(User.name, User.id)):
        permission = (user.permissions or {}).get(product, {})
        if user.role != "admin" and (permission.get("role") not in roles or scope_id not in permission.get("scope_ids", [])):
            continue
        result.append({"id": user.id, "name": user.name, "role": user.role, "active": user.active, "permissions": user.permissions})
    return {"users": result}


__all__ = ["router"]
