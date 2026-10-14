from sqlalchemy import select
from .api import _document
from .models import Principal, SpaceMembership
from .security import require_writer, require_current_scope
from .collaboration_features import create_router
from .errors import DomainError


def resolve(session, actor, kind, ident, write):
    if kind != "document":
        raise DomainError(404, "not_found", "Resource not found")
    document = _document(session, actor, ident, lock=write)
    if write:
        current = require_current_scope(session, actor, document.space_id, lock=True)
        require_writer(current)
    return document.title


def eligible(session, actor, kind, ident):
    document = _document(session, actor, ident)
    rows = session.scalars(select(Principal).join(SpaceMembership, SpaceMembership.principal_id == Principal.id).where(
        SpaceMembership.space_id == document.space_id, Principal.active.is_(True), Principal.organization_id == actor.organization_id,
        Principal.kind.in_(["human", "agent"])).order_by(Principal.name)).all()
    return [{"id": row.id, "name": row.name, "kind": row.kind} for row in rows]


def install(app, get_session, get_principal):
    app.include_router(create_router(get_session, get_principal, resolve, eligible))
