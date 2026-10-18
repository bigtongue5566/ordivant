"""Initialize the execution service without creating demo projects or human accounts."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .agent_presets import ensure_builtin_agent_templates
from .config import data_dir
from .db import Base, SessionLocal, engine
from .identity import _EMPTY_DATABASE_ORGANIZATION_ID
from .models import Organization, Principal
from .security import issue_token, new_id, now_utc, principal_for_token


class BootstrapError(RuntimeError):
    pass


@contextmanager
def _installation_lock(directory: Path):
    lock_path = directory / ".runtime-bootstrap.lock"
    if lock_path.is_symlink():
        raise BootstrapError("Runtime initialization lock must be a regular file")
    with lock_path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            lock.seek(0)
            if not lock.read(1):
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            os.fchmod(lock.fileno(), 0o600)
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def initialize_runtime(*, directory: Path | None = None, factory=None) -> None:
    directory = directory or data_dir()
    factory = factory or SessionLocal
    directory.mkdir(parents=True, exist_ok=True)
    bootstrap_path = directory / "bootstrap.json"
    with _installation_lock(directory):
        if bootstrap_path.is_symlink():
            raise BootstrapError("Runtime configuration must be a regular file")
        previous = {}
        if bootstrap_path.exists():
            try:
                previous = json.loads(bootstrap_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise BootstrapError("Existing runtime configuration is invalid; it was not replaced") from None
            if not isinstance(previous, dict):
                raise BootstrapError("Existing runtime configuration is invalid; it was not replaced")
        with factory() as session:
            organizations = list(session.scalars(select(Organization)))
            configured = os.getenv("ORDIVANT_IDENTITY_ORG_ID", "").strip()
            if configured:
                organization = next((item for item in organizations if item.id == configured), None)
                if organization is None:
                    raise BootstrapError("Configured Work organization does not exist")
            elif len(organizations) > 1:
                raise BootstrapError("Select the Work organization with ORDIVANT_IDENTITY_ORG_ID")
            elif organizations:
                organization = organizations[0]
            else:
                organization = Organization(id=_EMPTY_DATABASE_ORGANIZATION_ID, name="Identity Organization", created_at=now_utc())
                session.add(organization)
                session.flush()
                ensure_builtin_agent_templates(session, organization.id)
            existing_token = previous.get("runtime_token")
            if existing_token is not None:
                principal = principal_for_token(session, existing_token) if isinstance(existing_token, str) else None
                if principal is None or principal.kind != "runtime" or principal.organization_id != organization.id:
                    raise BootstrapError("Existing runtime credential is invalid for this organization; it was not replaced")
                return
            principal = session.scalar(select(Principal).where(
                Principal.kind == "runtime", Principal.organization_id == organization.id, Principal.name == "runtime",
            ))
            if principal is not None and not principal.active:
                raise BootstrapError("The execution service was disabled; refusing to reactivate it")
            if principal is None:
                principal = Principal(id=new_id(), name="runtime", kind="runtime", role="manager", organization_id=organization.id, active=True)
                session.add(principal)
                session.flush()
            previous["runtime_token"] = issue_token(session, principal.id)
            # Validate/write the private file before committing; no credential is printed.
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, prefix=".runtime-", delete=False) as output:
                    temporary = Path(output.name)
                    os.chmod(temporary, 0o600)
                    json.dump(previous, output, ensure_ascii=False, indent=2)
                    output.write("\n")
                    output.flush()
                    os.fsync(output.fileno())
                session.commit()
                os.replace(temporary, bootstrap_path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)


def main() -> None:
    try:
        Base.metadata.create_all(bind=engine)
        initialize_runtime()
    except (BootstrapError, OSError, SQLAlchemyError) as error:
        message = str(error) if isinstance(error, BootstrapError) else "Runtime configuration could not be saved"
        raise SystemExit(message) from None
    print("Ordivant execution service initialized. No demo data or human account was created.")


if __name__ == "__main__":
    main()
