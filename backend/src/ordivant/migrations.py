"""Preserve existing agent executions while adding durable human work."""
from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateTable


def migrate_collaboration(engine: Engine) -> None:
    inspector = inspect(engine)
    if "tasks" not in inspector.get_table_names():
        return
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.exec_driver_sql("SELECT pg_advisory_xact_lock(719306142)")
        elif engine.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        columns = {item["name"] for item in inspect(connection).get_columns("tasks")}
        additions = {
            "assignee_principal_id": "VARCHAR(36) REFERENCES principals(id)",
            "reviewer_principal_id": "VARCHAR(36) REFERENCES principals(id)",
            "work_type": "VARCHAR(20) NOT NULL DEFAULT 'task'",
            "epic_id": "VARCHAR(36) REFERENCES tasks(id) ON DELETE SET NULL",
            "due_at": "TIMESTAMP WITH TIME ZONE",
            "start_at": "TIMESTAMP WITH TIME ZONE",
            "sprint_id": "VARCHAR(36) REFERENCES project_sprints(id) ON DELETE SET NULL",
            "milestone_id": "VARCHAR(36) REFERENCES project_milestones(id) ON DELETE SET NULL",
            "estimate_points": "FLOAT",
            "rank": "FLOAT NOT NULL DEFAULT 0",
            "stage_id": "VARCHAR(36) REFERENCES project_stages(id) ON DELETE SET NULL",
            "custom_fields_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        for name, definition in additions.items():
            if name not in columns:
                connection.exec_driver_sql(f"ALTER TABLE tasks ADD COLUMN {name} {definition}")
        connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_tasks_assignee_principal_id ON tasks (assignee_principal_id)")
        connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_tasks_epic_id ON tasks (epic_id)")
        connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_tasks_sprint_id ON tasks (sprint_id)")
        connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_tasks_milestone_id ON tasks (milestone_id)")
        connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_tasks_stage_id ON tasks (stage_id)")
        connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_tasks_project_rank_created ON tasks (project_id, rank, created_at)")
        if engine.dialect.name == "postgresql":
            connection.exec_driver_sql("ALTER TABLE executions ALTER COLUMN agent_id DROP NOT NULL")
            connection.exec_driver_sql("ALTER TABLE executions ALTER COLUMN lease_expires_at DROP NOT NULL")
            return
    if engine.dialect.name != "sqlite":
        return
    columns = inspect(engine).get_columns("executions")
    if all(item["nullable"] for item in columns if item["name"] in {"agent_id", "lease_expires_at"}):
        return
    from .models import Execution

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            # Recheck after acquiring the write lock; another process may have migrated.
            current = inspect(connection).get_columns("executions")
            if not all(item["nullable"] for item in current if item["name"] in {"agent_id", "lease_expires_at"}):
                ddl = str(CreateTable(Execution.__table__).compile(engine))
                ddl = ddl.replace("CREATE TABLE executions", "CREATE TABLE executions_collaboration_new", 1)
                connection.exec_driver_sql(ddl)
                names = ", ".join(f'"{column.name}"' for column in Execution.__table__.columns)
                connection.exec_driver_sql(f"INSERT INTO executions_collaboration_new ({names}) SELECT {names} FROM executions")
                connection.exec_driver_sql("DROP TABLE executions")
                connection.exec_driver_sql("ALTER TABLE executions_collaboration_new RENAME TO executions")
                for index in Execution.__table__.indexes:
                    index.create(connection, checkfirst=True)
            violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError("Collaboration migration rejected an inconsistent database")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
