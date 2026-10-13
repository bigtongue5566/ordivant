from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import DomainError, forbidden, not_found
from .models import AccessToken, KnowledgeSpace, Principal, SpaceMembership


@dataclass(frozen=True)
class PrincipalContext:
    id: str
    name: str
    kind: str
    role: str
    organization_id: str
    scope_ids: frozenset[str]


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def expires_after(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return "kn_" + secrets.token_urlsafe(36)


def issue_token(session: Session, principal_id: str, token: str | None = None, *, expires_at: str | None = None) -> str:
    credential = token or new_token()
    session.add(
        AccessToken(
            id=new_id(),
            principal_id=principal_id,
            token_hash=token_hash(credential),
            created_at=now_iso(),
            expires_at=expires_at,
        )
    )
    return credential


def principal_for_token(session: Session, credential: str) -> PrincipalContext | None:
    row = session.execute(
        select(AccessToken, Principal)
        .join(Principal, Principal.id == AccessToken.principal_id)
        .where(AccessToken.token_hash == token_hash(credential), AccessToken.revoked_at.is_(None), Principal.active.is_(True))
    ).first()
    if row is None:
        return None
    access_token, principal = row
    now = now_iso()
    if access_token.expires_at is not None and access_token.expires_at <= now:
        return None
    scopes = frozenset(session.scalars(select(SpaceMembership.space_id).where(SpaceMembership.principal_id == principal.id)))
    return PrincipalContext(
        id=principal.id,
        name=principal.name,
        kind=principal.kind,
        role=principal.role,
        organization_id=principal.organization_id,
        scope_ids=scopes,
    )


def authenticate(session: Session, authorization: str | None) -> PrincipalContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise DomainError(401, "unauthenticated", "需要 Bearer token")
    credential = authorization.removeprefix("Bearer ").strip()
    if not credential:
        raise DomainError(401, "unauthenticated", "需要 Bearer token")
    principal = principal_for_token(session, credential)
    if principal is None:
        raise DomainError(401, "unauthenticated", "token 無效、已撤銷或已過期")
    return principal


def _current_scope(
    session: Session,
    principal: PrincipalContext,
    space_id: str,
    *,
    lock: bool = False,
) -> tuple[KnowledgeSpace, PrincipalContext]:
    space = session.scalar(
        select(KnowledgeSpace)
        .where(KnowledgeSpace.id == space_id)
        .execution_options(populate_existing=True)
    )
    principal_statement = select(Principal).where(Principal.id == principal.id).execution_options(populate_existing=True)
    membership_statement = select(SpaceMembership).where(
        SpaceMembership.principal_id == principal.id,
        SpaceMembership.space_id == space_id,
    )
    if lock and session.get_bind().dialect.name == "postgresql":
        principal_statement = principal_statement.with_for_update()
        membership_statement = membership_statement.with_for_update()
    current = session.scalar(principal_statement)
    if (
        space is None
        or current is None
        or not current.active
        or current.kind != principal.kind
        or current.organization_id != principal.organization_id
        or space_id not in principal.scope_ids
        or space.organization_id != current.organization_id
        or session.scalar(membership_statement) is None
    ):
        raise not_found()
    return space, PrincipalContext(
        id=current.id,
        name=current.name,
        kind=current.kind,
        role=current.role,
        organization_id=current.organization_id,
        scope_ids=principal.scope_ids,
    )


def require_scope(session: Session, principal: PrincipalContext, space_id: str) -> KnowledgeSpace:
    space, _ = _current_scope(session, principal, space_id)
    return space


def require_current_scope(
    session: Session,
    principal: PrincipalContext,
    space_id: str,
    *,
    lock: bool = False,
) -> PrincipalContext:
    _, current = _current_scope(session, principal, space_id, lock=lock)
    return current


def require_writer(principal: PrincipalContext) -> None:
    if principal.role not in {"manager", "writer"}:
        raise forbidden("需要 manager 或 writer 權限")


def require_manager(principal: PrincipalContext) -> None:
    if principal.role != "manager":
        raise forbidden("需要 manager 權限")


def principal_json(principal: PrincipalContext) -> dict[str, object]:
    return {
        "id": principal.id,
        "name": principal.name,
        "kind": principal.kind,
        "role": principal.role,
        "organization_id": principal.organization_id,
        "scope_ids": sorted(principal.scope_ids),
    }
