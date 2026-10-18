from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

import httpx
from fastapi import Request
from sqlalchemy import Boolean, ForeignKey, String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .db import Base
from .errors import DomainError
from .models import Organization, Principal, Project, Scope, ScopeMembership
from .security import new_id, now_utc


_IDENTITY_ENV = (
    "ORDIVANT_AUTH_COOKIE_NAME",
    "ORDIVANT_AUTH_ORIGINS",
    "ORDIVANT_IDENTITY_URL",
    "ORDIVANT_IDENTITY_SERVICE_TOKEN_FILE",
)


class IdentityBinding(Base):
    __tablename__ = "identity_bindings"

    subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id", ondelete="CASCADE"), nullable=False, unique=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    identity_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


_EMPTY_DATABASE_ORGANIZATION_ID = str(uuid5(NAMESPACE_URL, "ordivant://identity/local-organization"))


def identity_configured() -> bool:
    return any(os.getenv(name, "").strip() for name in _IDENTITY_ENV)


def _unavailable() -> DomainError:
    return DomainError(503, "identity_unavailable", "Identity authentication is unavailable")


def _configuration() -> tuple[str, str, str]:
    cookie_name = os.getenv("ORDIVANT_AUTH_COOKIE_NAME", "").strip()
    service_token_file = os.getenv("ORDIVANT_IDENTITY_SERVICE_TOKEN_FILE", "").strip()
    identity_url = os.getenv("ORDIVANT_IDENTITY_URL", "http://identity-api:8030").strip()
    if not cookie_name or not service_token_file or not identity_url:
        raise _unavailable()
    parsed_url = urlsplit(identity_url)
    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.netloc
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise _unavailable()
    try:
        service_token = Path(service_token_file).expanduser().read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise _unavailable() from exc
    if not service_token:
        raise _unavailable()
    return cookie_name, identity_url.rstrip("/"), service_token


async def _introspect(identity_url: str, service_token: str, session_token: str) -> tuple[dict[str, Any], str]:
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(3.0, connect=1.0),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.post(
                f"{identity_url}/api/auth/introspect",
                headers={"Authorization": f"Bearer {service_token}"},
                json={"session_token": session_token},
            )
    except httpx.HTTPError as exc:
        raise _unavailable() from exc
    if response.status_code == 401:
        raise DomainError(401, "unauthenticated", "Identity session is invalid or expired")
    if response.status_code != 200:
        raise _unavailable()
    try:
        payload = response.json()
    except ValueError as exc:
        raise _unavailable() from exc
    user = payload.get("user") if isinstance(payload, dict) else None
    csrf_token = payload.get("csrf_token") if isinstance(payload, dict) else None
    if (
        not isinstance(user, dict)
        or not isinstance(user.get("id"), str)
        or not user["id"]
        or len(user["id"]) > 255
    ):
        raise _unavailable()
    if not isinstance(csrf_token, str) or not csrf_token:
        raise _unavailable()
    if (
        not isinstance(user.get("name"), str)
        or not user["name"]
        or len(user["name"]) > 160
        or not isinstance(user.get("active"), bool)
    ):
        raise _unavailable()
    return user, csrf_token


async def _introspect_access_token(identity_url: str, service_token: str, access_token: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(3.0, connect=1.0), follow_redirects=False, trust_env=False,
        ) as client:
            response = await client.post(
                f"{identity_url}/api/auth/access-tokens/introspect",
                headers={"Authorization": f"Bearer {service_token}"},
                json={"access_token": access_token, "product": "code"},
            )
    except httpx.HTTPError as exc:
        raise _unavailable() from exc
    if response.status_code == 401:
        raise DomainError(401, "unauthenticated", "Personal access token is invalid or expired")
    if response.status_code == 403:
        raise DomainError(403, "token_product_forbidden", "Personal access token does not allow this product")
    if response.status_code != 200:
        raise _unavailable()
    try:
        payload = response.json()
    except ValueError as exc:
        raise _unavailable() from exc
    user = payload.get("user") if isinstance(payload, dict) else None
    if (
        not isinstance(user, dict)
        or not isinstance(user.get("id"), str) or not user["id"] or len(user["id"]) > 255
        or not isinstance(user.get("name"), str) or not user["name"] or len(user["name"]) > 160
        or not isinstance(user.get("active"), bool)
    ):
        raise _unavailable()
    return user


async def bearer_principal(request: Request, session: Session) -> Principal | None:
    """Personal tokens resolve to the same human principal as browser sessions."""
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer ord_pat_"):
        return None
    access_token = authorization[7:].strip()
    if not 20 <= len(access_token) <= 512:
        raise DomainError(401, "unauthenticated", "Personal access token is invalid or expired")
    if not identity_configured():
        raise DomainError(401, "unauthenticated", "Personal access tokens require Identity")
    _, identity_url, service_token = _configuration()
    user = await _introspect_access_token(identity_url, service_token, access_token)
    return _sync_principal(session, user)


def _require_browser_mutation(request: Request, csrf_token: str) -> None:
    if request.method.upper() in {"GET", "HEAD"}:
        return
    allowed = {origin.strip() for origin in os.getenv("ORDIVANT_AUTH_ORIGINS", "").split(",") if origin.strip()}
    origin = request.headers.get("Origin")
    if origin is None or origin not in allowed:
        raise DomainError(403, "origin_not_allowed", "Browser Origin is not allowed")
    supplied = request.headers.get("X-CSRF-Token")
    if supplied is None or not hmac.compare_digest(supplied.encode("utf-8"), csrf_token.encode("utf-8")):
        raise DomainError(403, "csrf_failed", "CSRF token is missing or invalid")


async def _cookie_identity(request: Request) -> dict[str, Any] | None:
    if not identity_configured():
        return None
    cookie_name, identity_url, service_token = _configuration()
    session_token = request.cookies.get(cookie_name)
    if not session_token:
        return None
    user, csrf_token = await _introspect(identity_url, service_token, session_token)
    _require_browser_mutation(request, csrf_token)
    return user


def _write_lock(session: Session) -> None:
    if session.bind and session.bind.dialect.name == "sqlite":
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")


def _scope_ids(session: Session, organization_id: str, requested: list[str], *, admin: bool) -> set[str]:
    statement = select(Scope.id).where(Scope.organization_id == organization_id)
    if not admin:
        if not requested:
            return set()
        statement = (
            select(Scope.id)
            .join(Project, Project.scope_id == Scope.id)
            .where(Project.organization_id == organization_id, Project.id.in_(requested))
        )
    return set(session.scalars(statement))


def _local_organization(session: Session, binding: IdentityBinding | None) -> str:
    organizations = set(session.scalars(select(Organization.id)))
    configured = os.getenv("ORDIVANT_IDENTITY_ORG_ID", "").strip()
    if binding is not None:
        if binding.organization_id not in organizations:
            raise DomainError(403, "identity_organization_missing", "The bound local organization no longer exists")
        if configured and configured != binding.organization_id:
            raise DomainError(403, "identity_organization_conflict", "ORDIVANT_IDENTITY_ORG_ID does not match the existing identity binding")
        return binding.organization_id
    if configured:
        if configured not in organizations:
            raise DomainError(403, "identity_organization_missing", "ORDIVANT_IDENTITY_ORG_ID does not name a local organization")
        return configured
    if len(organizations) == 1:
        return next(iter(organizations))
    if not organizations:
        organization = Organization(
            id=_EMPTY_DATABASE_ORGANIZATION_ID,
            name="Identity Organization",
            created_at=now_utc(),
        )
        session.add(organization)
        session.flush()
        return organization.id
    raise DomainError(403, "identity_organization_required", "Identity must map to one local organization")


def _validate_scope_organizations(session: Session, organization_id: str, requested: list[str]) -> None:
    other_org_scopes = set(
        session.scalars(
            select(Project.id).where(
                Project.id.in_(requested), Project.organization_id != organization_id
            )
        )
    ) if requested else set()
    if other_org_scopes:
        raise DomainError(403, "identity_cross_organization_scope", "Identity scopes include a different local organization")


def require_identity_admin_for_scope_creation(session: Session, principal: Principal) -> None:
    binding = session.scalar(select(IdentityBinding).where(IdentityBinding.principal_id == principal.id))
    if binding is not None and not binding.identity_admin:
        raise DomainError(403, "identity_admin_required", "Only Identity administrators can create a new project scope")


def _sync_scope_memberships(
    session: Session,
    principal: Principal,
    organization_id: str,
    allowed_ids: set[str],
    role: str,
) -> None:
    existing = list(
        session.scalars(
            select(ScopeMembership)
            .join(Scope, Scope.id == ScopeMembership.scope_id)
            .where(ScopeMembership.principal_id == principal.id, Scope.organization_id == organization_id)
        )
    )
    current_ids = {membership.scope_id for membership in existing}
    for membership in existing:
        if membership.scope_id not in allowed_ids:
            session.delete(membership)
        else:
            membership.role = role
    for scope_id in allowed_ids - current_ids:
        session.add(ScopeMembership(id=new_id(), principal_id=principal.id, scope_id=scope_id, role=role))


def _revoke_bound_access(session: Session, binding: IdentityBinding, user: dict[str, Any]) -> None:
    principal = session.get(Principal, binding.principal_id)
    if principal is None or principal.kind != "human" or principal.organization_id != binding.organization_id:
        raise DomainError(409, "identity_binding_conflict", "Identity binding does not reference its local human principal")
    principal.name = user["name"]
    principal.active = bool(user.get("active"))
    principal.role = "reader"
    binding.identity_admin = False
    _sync_scope_memberships(session, principal, binding.organization_id, set(), "reader")
    session.commit()


def _sync_principal(session: Session, user: dict[str, Any]) -> Principal:
    subject = user["id"]
    role_name = user.get("role")
    admin = role_name == "admin"
    permissions = user.get("permissions")
    permission = permissions.get("code") if isinstance(permissions, dict) else None
    role = "manager" if admin else permission.get("role") if isinstance(permission, dict) else None
    requested = [] if admin else permission.get("scope_ids") if isinstance(permission, dict) else []
    entitled = role in {"manager", "writer", "reader"} and isinstance(requested, list) and all(
        isinstance(scope_id, str) for scope_id in requested
    )

    for attempt in range(2):
        try:
            _write_lock(session)
            binding = session.get(IdentityBinding, subject)
            if not user["active"] or not entitled or role_name not in {"admin", "member"}:
                if binding is not None:
                    _revoke_bound_access(session, binding, user)
                else:
                    session.rollback()
                if not user["active"]:
                    raise DomainError(403, "identity_user_inactive", "Identity user is inactive")
                raise DomainError(403, "product_access_denied", "Identity user has no Code permission")

            organization_id = _local_organization(session, binding)
            _validate_scope_organizations(session, organization_id, requested)
            principal = session.get(Principal, binding.principal_id) if binding is not None else None
            if binding is not None and (
                principal is None or principal.kind != "human" or principal.organization_id != organization_id
            ):
                raise DomainError(409, "identity_binding_conflict", "Identity binding does not reference its local human principal")
            if principal is None:
                principal = Principal(
                    id=new_id(),
                    organization_id=organization_id,
                    name=user["name"],
                    kind="human",
                    role=role,
                    active=True,
                    created_at=now_utc(),
                )
                session.add(principal)
                session.flush()
                binding = IdentityBinding(
                    subject=subject,
                    principal_id=principal.id,
                    organization_id=organization_id,
                    identity_admin=admin,
                )
                session.add(binding)
                session.flush()
            else:
                principal.name = user["name"]
                principal.role = role
                principal.active = True
                binding.identity_admin = admin

            allowed_ids = _scope_ids(session, organization_id, requested, admin=admin)
            _sync_scope_memberships(session, principal, organization_id, allowed_ids, role)
            session.commit()
            return principal
        except IntegrityError as exc:
            session.rollback()
            if attempt:
                raise DomainError(409, "identity_binding_conflict", "Identity binding could not be initialized safely") from exc
    raise DomainError(409, "identity_binding_conflict", "Identity binding could not be initialized safely")


async def cookie_principal(request: Request, session: Session) -> Principal | None:
    user = await _cookie_identity(request)
    if user is None:
        return None
    return _sync_principal(session, user)
