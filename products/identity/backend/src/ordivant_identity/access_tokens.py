from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .api import (
    SessionContext,
    _aware,
    _audit,
    _check_csrf,
    _iso,
    _now,
    _settings,
    _unauthorized,
    _user_json,
    current_session,
    get_db,
)
from .errors import DomainError
from .models import PersonalAccessToken, User
from .schemas import AccessTokenCreateRequest, AccessTokenIntrospectRequest
from .security import constant_time_equal


router = APIRouter()
_ACTIVE_TOKEN_LIMIT = 50


def _metadata(token: PersonalAccessToken) -> dict:
    return {
        "id": token.id,
        "name": token.name,
        "prefix": token.prefix,
        "products": list(token.products),
        "created_at": _iso(token.created_at),
        "expires_at": _iso(token.expires_at),
        "last_used_at": _iso(token.last_used_at) if token.last_used_at else None,
        "revoked_at": _iso(token.revoked_at) if token.revoked_at else None,
    }


def _user_has_product(user: User, product: str) -> bool:
    permissions = user.permissions or {}
    permission = permissions.get(product)
    return user.role == "admin" or isinstance(permission, dict) and bool(permission.get("role"))


@router.get("/access-tokens")
def list_access_tokens(
    ctx: SessionContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.scalars(
        select(PersonalAccessToken)
        .where(PersonalAccessToken.user_id == ctx.user.id)
        .order_by(PersonalAccessToken.created_at.desc(), PersonalAccessToken.id)
    ).all()
    result = {"tokens": [_metadata(item) for item in rows]}
    db.commit()
    return result


@router.post("/access-tokens", status_code=201)
def create_access_token(
    body: AccessTokenCreateRequest,
    request: Request,
    ctx: SessionContext = Depends(current_session),
    db: Session = Depends(get_db),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    settings = _settings(request)
    _check_csrf(ctx, settings, x_csrf_token)

    user = db.scalar(
        select(User)
        .where(User.id == ctx.user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None or not user.active:
        raise _unauthorized()
    if user.role != "admin" and any(not _user_has_product(user, product) for product in body.products):
        raise DomainError(403, "token_product_forbidden", "Access token is not authorized for this product")

    now = _now()
    active_count = db.scalar(
        select(func.count())
        .select_from(PersonalAccessToken)
        .where(
            PersonalAccessToken.user_id == user.id,
            PersonalAccessToken.revoked_at.is_(None),
            PersonalAccessToken.expires_at > now,
        )
    ) or 0
    if active_count >= _ACTIVE_TOKEN_LIMIT:
        raise DomainError(409, "token_limit", "No more than 50 active access tokens are allowed")

    raw_token = f"ord_pat_{secrets.token_urlsafe(32)}"
    token = PersonalAccessToken(
        id=str(uuid4()),
        user_id=user.id,
        name=body.name,
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        prefix=raw_token[:16],
        products=body.products,
        created_at=now,
        expires_at=now + timedelta(days=body.expires_in_days),
        last_used_at=None,
        revoked_at=None,
    )
    db.add(token)
    _audit(
        db,
        "access_token.created",
        actor_id=user.id,
        user_id=user.id,
        details={"token_id": token.id, "name": token.name, "products": list(token.products)},
    )
    db.commit()
    return {"token": raw_token, "access_token": _metadata(token)}


@router.delete("/access-tokens/{token_id}", status_code=204)
def revoke_access_token(
    token_id: str,
    request: Request,
    ctx: SessionContext = Depends(current_session),
    db: Session = Depends(get_db),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> Response:
    _check_csrf(ctx, _settings(request), x_csrf_token)
    token = db.scalar(
        select(PersonalAccessToken).where(
            PersonalAccessToken.id == token_id,
            PersonalAccessToken.user_id == ctx.user.id,
        )
    )
    if token is None:
        raise DomainError(404, "access_token_not_found", "Access token not found")
    if token.revoked_at is None:
        token.revoked_at = _now()
        _audit(
            db,
            "access_token.revoked",
            actor_id=ctx.user.id,
            user_id=ctx.user.id,
            details={"token_id": token.id},
        )
    db.commit()
    return Response(status_code=204)


@router.post("/access-tokens/introspect")
def introspect_access_token(
    body: AccessTokenIntrospectRequest,
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    settings = _settings(request)
    if not constant_time_equal(f"Bearer {settings.service_secret}", authorization):
        raise _unauthorized("service_unauthorized", "Identity service authorization is required")

    raw_token = body.access_token.get_secret_value()
    digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    token = db.scalar(select(PersonalAccessToken).where(PersonalAccessToken.token_hash == digest))
    now = _now()
    if token is None or token.revoked_at is not None or _aware(token.expires_at) <= now:
        raise _unauthorized("access_token_invalid", "Access token is invalid or expired")
    if body.product not in token.products:
        raise DomainError(403, "token_product_forbidden", "Access token is not authorized for this product")

    user = db.scalar(select(User).where(User.id == token.user_id).execution_options(populate_existing=True))
    if user is None or not user.active:
        raise _unauthorized("access_token_invalid", "Access token is invalid or expired")

    token.last_used_at = now
    result = {"user": _user_json(user), "token_id": token.id, "expires_at": _iso(token.expires_at)}
    db.commit()
    return result
