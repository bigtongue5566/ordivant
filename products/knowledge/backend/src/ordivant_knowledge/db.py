from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    parsed = make_url(url)
    if parsed.get_backend_name() == "postgresql" and parsed.drivername != "postgresql+psycopg":
        parsed = parsed.set(drivername="postgresql+psycopg")
    url = parsed.render_as_string(hide_password=False)
    connect_args = {}
    if parsed.get_backend_name() == "sqlite":
        db_path = parsed.database
        if db_path and db_path != ":memory:":
            Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False, "timeout": 30}

    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            if parsed.database != ":memory:":
                cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        @event.listens_for(engine, "begin")
        def serialize_sqlite_writes(connection):
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    return session_factory(engine)


def migrate_schema(engine: Engine) -> None:
    """Create new tables and add Knowledge columns without replacing existing rows."""
    from . import models as _models  # noqa: F401

    with engine.begin() as connection:
        table_names = set(inspect(connection).get_table_names())
        if "documents" in table_names:
            columns = {column["name"] for column in inspect(connection).get_columns("documents")}
            if "parent_id" not in columns:
                connection.execute(text(
                    "ALTER TABLE documents ADD COLUMN parent_id VARCHAR(36) "
                    "REFERENCES documents(id) ON DELETE SET NULL"
                ))
            if "archived" not in columns:
                connection.execute(text(
                    "ALTER TABLE documents ADD COLUMN archived BOOLEAN NOT NULL DEFAULT FALSE"
                ))
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_documents_parent ON documents(parent_id)"))


def session_dependency(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    with factory() as session:
        yield session
