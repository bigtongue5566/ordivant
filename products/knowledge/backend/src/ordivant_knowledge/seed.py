from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import make_engine, migrate_schema
from .models import AccessToken, KnowledgeSpace, Organization, Principal, SpaceMembership
from .security import issue_token, new_token, now_iso, token_hash
from . import models as _models  # noqa: F401


SEED_ORGANIZATION_ID = "knowledge-demo-organization"
PRIMARY_SCOPE_ID = "knowledge-primary"
ISOLATED_SCOPE_ID = "knowledge-isolated"
MANAGER_ID = "knowledge-manager"
WRITER_ID = "knowledge-writer"
READER_ID = "knowledge-reader"


def _read_bootstrap(path: Path) -> dict[str, str] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    expected = {
        "manager_token", "writer_token", "reader_token", "manager_id", "writer_id", "reader_id",
        "organization_id", "primary_scope_id", "isolated_scope_id",
    }
    if not isinstance(value, dict) or any(not isinstance(value.get(key), str) for key in expected):
        return None
    return {key: value[key] for key in expected}


def _write_bootstrap(path: Path, value: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix="bootstrap-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        try:
            os.chmod(temporary_name, 0o600)
        except OSError:
            pass
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def seed_knowledge(database_url: str | None = None, *, settings: Settings | None = None) -> dict[str, str]:
    active_settings = settings or get_settings()
    bootstrap_path = active_settings.data_dir / "bootstrap.json"
    bootstrap = _read_bootstrap(bootstrap_path) or {
        "manager_token": new_token(),
        "writer_token": new_token(),
        "reader_token": new_token(),
        "manager_id": MANAGER_ID,
        "writer_id": WRITER_ID,
        "reader_id": READER_ID,
        "organization_id": SEED_ORGANIZATION_ID,
        "primary_scope_id": PRIMARY_SCOPE_ID,
        "isolated_scope_id": ISOLATED_SCOPE_ID,
    }
    engine: Engine = make_engine(database_url or active_settings.database_url)
    try:
        migrate_schema(engine)
        with Session(engine, expire_on_commit=False, autoflush=False) as session:
            _seed_rows(session, bootstrap)
            session.commit()
    finally:
        engine.dispose()
    _write_bootstrap(bootstrap_path, bootstrap)
    return bootstrap


def _seed_rows(session: Session, bootstrap: dict[str, str]) -> None:
    organization = session.get(Organization, bootstrap["organization_id"])
    if organization is None:
        organization = Organization(
            id=bootstrap["organization_id"],
            name="Ordivant Knowledge Demo",
            created_at=now_iso(),
        )
        session.add(organization)
        session.flush()

    space_specs = [
        (bootstrap["primary_scope_id"], "primary", "Primary knowledge", "Shared product knowledge"),
        (bootstrap["isolated_scope_id"], "isolated", "Isolated knowledge", "Scope isolation acceptance space"),
    ]
    for space_id, key, name, description in space_specs:
        space = session.get(KnowledgeSpace, space_id)
        if space is None:
            space = KnowledgeSpace(
                id=space_id,
                key=key,
                name=name,
                description=description,
                organization_id=organization.id,
                created_at=now_iso(),
            )
            session.add(space)
        else:
            space.key = key
            space.name = name
            space.description = description
            space.organization_id = organization.id
    session.flush()

    principal_specs = [
        (bootstrap["manager_id"], "Knowledge Manager", "human", "manager"),
        (bootstrap["writer_id"], "Knowledge Writer", "agent", "writer"),
        (bootstrap["reader_id"], "Knowledge Reader", "agent", "reader"),
    ]
    for principal_id, name, kind, role in principal_specs:
        principal = session.get(Principal, principal_id)
        if principal is None:
            principal = Principal(
                id=principal_id,
                name=name,
                kind=kind,
                role=role,
                organization_id=organization.id,
                active=True,
            )
            session.add(principal)
        else:
            principal.name = name
            principal.kind = kind
            principal.role = role
            principal.organization_id = organization.id
            principal.active = True
    session.flush()

    memberships = [
        (bootstrap["manager_id"], bootstrap["primary_scope_id"]),
        (bootstrap["manager_id"], bootstrap["isolated_scope_id"]),
        (bootstrap["writer_id"], bootstrap["primary_scope_id"]),
        (bootstrap["reader_id"], bootstrap["primary_scope_id"]),
    ]
    for principal_id, space_id in memberships:
        current = session.scalar(
            select(SpaceMembership).where(
                SpaceMembership.principal_id == principal_id,
                SpaceMembership.space_id == space_id,
            )
        )
        if current is None:
            session.add(SpaceMembership(id=f"{principal_id}:{space_id}", principal_id=principal_id, space_id=space_id))
    session.flush()

    token_specs = [
        (bootstrap["manager_id"], bootstrap["manager_token"]),
        (bootstrap["writer_id"], bootstrap["writer_token"]),
        (bootstrap["reader_id"], bootstrap["reader_token"]),
    ]
    for principal_id, token in token_specs:
        existing = session.scalar(select(AccessToken).where(AccessToken.token_hash == token_hash(token)))
        if existing is None:
            issue_token(session, principal_id, token)
        elif existing.principal_id != principal_id:
            raise RuntimeError("The Knowledge bootstrap token is already assigned to another principal")


def main() -> None:
    seed_knowledge()
    print("Knowledge seed is ready. Generated tokens are stored in the product bootstrap file.")


if __name__ == "__main__":
    main()
