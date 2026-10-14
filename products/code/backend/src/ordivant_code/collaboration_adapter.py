from sqlalchemy import select
from .models import Principal, ScopeMembership, PullRequest
from .service import require_repository
from .collaboration import create_router
from .errors import DomainError


def resolve(session, actor, kind, ident, write):
    if kind != "pull":
        raise DomainError(404, "not_found", "Resource not found")
    query = select(PullRequest).where(PullRequest.id == ident)
    if write:
        query = query.with_for_update()
    pull = session.scalar(query)
    if not pull:
        raise DomainError(404, "not_found", "Resource not found")
    require_repository(session, actor, pull.repository_id, write=write)
    return pull.title


def eligible(session, actor, kind, ident):
    pull = session.get(PullRequest, ident)
    _, project = require_repository(session, actor, pull.repository_id)
    rows = session.scalars(select(Principal).join(ScopeMembership, ScopeMembership.principal_id == Principal.id).where(
        ScopeMembership.scope_id == project.scope_id, Principal.active.is_(True), Principal.organization_id == actor.organization_id,
        Principal.kind.in_(["human", "agent"])).order_by(Principal.name)).all()
    return [{"id": row.id, "name": row.name, "kind": row.kind} for row in rows]


def install(app, get_session, get_principal):
    app.include_router(create_router(get_session, get_principal, resolve, eligible))
