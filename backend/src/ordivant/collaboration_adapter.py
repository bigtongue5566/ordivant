from sqlalchemy import select
from . import service
from .models import Principal, ProjectMembership
from .collaboration import create_router
from .errors import DomainError


def resolve(session, actor, kind, ident, write):
    if kind != "task":
        raise DomainError(404, "not_found", "Resource not found")
    task = service.task_for_actor(session, actor, ident)
    if write:
        service.require_role(actor, {"admin", "manager", "worker", "reviewer"})
        task = service._lock_task(session, task)
    return task.title


def eligible(session, actor, kind, ident):
    task = service.task_for_actor(session, actor, ident)
    rows = session.scalars(select(Principal).join(ProjectMembership, ProjectMembership.principal_id == Principal.id).where(
        ProjectMembership.project_id == task.project_id, Principal.active.is_(True), Principal.organization_id == actor.organization_id,
        Principal.kind.in_(["human", "agent"])).order_by(Principal.name)).all()
    return [{"id": row.id, "name": row.name, "kind": row.kind} for row in rows]


def install(app, get_db, get_actor):
    app.include_router(create_router(get_db, get_actor, resolve, eligible))
