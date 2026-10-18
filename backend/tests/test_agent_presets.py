from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from ordivant import agent_presets, api
from ordivant.db import Base, make_engine
from ordivant.models import Agent, AgentTemplate, Organization, Principal, ProjectMembership
from ordivant.security import issue_token, new_id, now_utc


def _make_database(path):
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_fresh_organization_gets_six_noncommitting_builtins_and_isolated_ids(tmp_path):
    engine, factory = _make_database(tmp_path / "presets.db")
    try:
        with factory() as session:
            first = Organization(id=new_id(), name="First", created_at=now_utc())
            second = Organization(id=new_id(), name="Second", created_at=now_utc())
            session.add_all([first, second])
            session.flush()
            agent_presets.ensure_builtin_agent_templates(session, first.id)
            agent_presets.ensure_builtin_agent_templates(session, second.id)
            first_rows = list(session.scalars(select(AgentTemplate).where(AgentTemplate.organization_id == first.id)))
            second_rows = list(session.scalars(select(AgentTemplate).where(AgentTemplate.organization_id == second.id)))
            assert len(first_rows) == len(second_rows) == 6
            assert {row.id for row in first_rows}.isdisjoint({row.id for row in second_rows})
            assert session.scalar(select(func.count()).select_from(AgentTemplate)) == 12
            session.rollback()

        with factory() as session:
            assert session.scalar(select(func.count()).select_from(Organization)) == 0
            assert session.scalar(select(func.count()).select_from(AgentTemplate)) == 0
    finally:
        engine.dispose()


def test_startup_backfills_existing_organizations_without_creating_one(tmp_path, monkeypatch):
    engine, factory = _make_database(tmp_path / "startup-presets.db")
    try:
        with factory() as session:
            organization = Organization(id=new_id(), name="Existing", created_at=now_utc())
            session.add(organization)
            session.commit()
            organization_id = organization.id

        monkeypatch.setenv("ORDIVANT_MODE", "development")
        monkeypatch.setattr(api, "engine", engine)
        monkeypatch.setattr(api, "SessionLocal", factory)
        monkeypatch.setattr(api, "migrate_collaboration", lambda _engine: None)

        async def start_app():
            async with api.lifespan(api.app):
                with factory() as session:
                    rows = list(session.scalars(select(AgentTemplate).where(AgentTemplate.organization_id == organization_id)))
                    assert len(rows) == 6

        asyncio.run(start_app())
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(Organization)) == 1
            assert session.scalar(select(func.count()).select_from(AgentTemplate)) == 6
    finally:
        engine.dispose()


def test_repeated_initialization_is_idempotent_and_does_not_overwrite(tmp_path):
    engine, factory = _make_database(tmp_path / "idempotent.db")
    try:
        with factory() as session:
            organization = Organization(id=new_id(), name="Idempotent", created_at=now_utc())
            session.add(organization)
            session.flush()
            agent_presets.ensure_builtin_agent_templates(session, organization.id)
            session.commit()
            row = session.scalar(select(AgentTemplate).where(AgentTemplate.organization_id == organization.id, AgentTemplate.key == "builtin-pm"))
            row.name = "Locally modified row"
            row.definition_json = json.dumps({"role": "worker", "instructions": "preserve"})
            session.commit()

            agent_presets.ensure_builtin_agent_templates(session, organization.id)
            session.commit()
            session.refresh(row)
            assert row.name == "Locally modified row"
            assert json.loads(row.definition_json)["instructions"] == "preserve"
            assert session.scalar(select(func.count()).select_from(AgentTemplate).where(AgentTemplate.organization_id == organization.id)) == 6
    finally:
        engine.dispose()


def test_custom_key_collision_and_custom_version_are_never_marked_builtin(tmp_path):
    engine, factory = _make_database(tmp_path / "collision.db")
    try:
        with factory() as session:
            organization = Organization(id=new_id(), name="Collision", created_at=now_utc())
            session.add(organization)
            session.flush()
            custom_v1 = AgentTemplate(
                id=new_id(), organization_id=organization.id, key="builtin-pm", version=1,
                name="Customer PM", description="Custom data", definition_json='{"role":"worker"}', created_at=now_utc(),
            )
            custom_v2 = AgentTemplate(
                id=new_id(), organization_id=organization.id, key="builtin-pg", version=2,
                name="Customer PG v2", description="Custom version", definition_json='{"role":"worker"}', created_at=now_utc(),
            )
            session.add_all([custom_v1, custom_v2])
            session.flush()
            agent_presets.ensure_builtin_agent_templates(session, organization.id)
            session.commit()

            session.refresh(custom_v1)
            session.refresh(custom_v2)
            assert custom_v1.name == "Customer PM"
            assert custom_v1.definition_json == '{"role":"worker"}'
            assert agent_presets.builtin_key_for_template(custom_v1) is None
            assert agent_presets.builtin_key_for_template(custom_v2) is None
            assert session.scalar(select(func.count()).select_from(AgentTemplate).where(AgentTemplate.organization_id == organization.id)) == 7
    finally:
        engine.dispose()


def test_sqlite_concurrent_initialization_creates_one_copy_per_preset(tmp_path):
    engine, factory = _make_database(tmp_path / "parallel.db")
    try:
        with factory() as session:
            organization = Organization(id=new_id(), name="Concurrent", created_at=now_utc())
            session.add(organization)
            session.commit()
            organization_id = organization.id

        barrier = Barrier(6)

        def initialize():
            with factory() as session:
                barrier.wait(timeout=10)
                agent_presets.ensure_builtin_agent_templates(session, organization_id)
                session.commit()

        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda _index: initialize(), range(6)))

        with factory() as session:
            rows = list(session.scalars(select(AgentTemplate).where(AgentTemplate.organization_id == organization_id)))
            assert len(rows) == 6
            assert len({row.key for row in rows}) == 6
    finally:
        engine.dispose()


def test_builtin_templates_apply_snapshot_and_keep_agent_scope_authorization(api_client: TestClient, system):
    organization_id = system["ids"]["organization"]
    with system["factory"]() as session:
        agent_presets.ensure_builtin_agent_templates(session, organization_id)
        restricted_manager = Principal(
            id=new_id(), name="single-project-manager", kind="human", role="manager",
            organization_id=organization_id, team_id=system["ids"]["team"], active=True,
        )
        session.add(restricted_manager)
        session.flush()
        session.add(ProjectMembership(
            id=new_id(), project_id=system["ids"]["project"], principal_id=restricted_manager.id,
        ))
        token = issue_token(session, restricted_manager.id)
        session.commit()

    templates_response = api_client.get("/api/agent-templates", headers=_bearer(token))
    assert templates_response.status_code == 200, templates_response.text
    templates = templates_response.json()
    assert {row["builtin_key"] for row in templates if row["builtin_key"] is not None} == {"pm", "pg", "sa", "sd", "qa", "reviewer"}
    selected = next(row for row in templates if row["builtin_key"] == "pm")

    created = api_client.post(
        "/api/agents",
        json={"name": "Preset PM", "project_ids": [system["ids"]["project"]], "template_id": selected["id"]},
        headers=_bearer(token),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["role"] == "worker"
    assert body["capabilities"] == selected["definition"]["capabilities"]
    assert body["project_ids"] == [system["ids"]["project"]]
    assert body["model_config"] is None
    assert body["execution_config"] == {
        "instructions": selected["definition"]["instructions"],
        "tool_connection_ids": [],
        "sandbox_profile_id": None,
        "limits": {"max_turns": 20, "timeout_seconds": 600},
    }

    denied = api_client.post(
        "/api/agents",
        json={"name": "Out of scope", "project_ids": [system["ids"]["isolated_project"]], "template_id": selected["id"]},
        headers=_bearer(token),
    )
    assert denied.status_code == 404
    with system["factory"]() as session:
        assert session.scalar(select(Agent.id).where(Agent.name == "Out of scope")) is None


def test_only_independent_reviewer_preset_has_reviewer_role():
    roles = {preset["builtin_key"]: preset["definition"]["role"] for preset in agent_presets.BUILTIN_PRESETS}
    assert roles == {
        "pm": "worker",
        "pg": "worker",
        "sa": "worker",
        "sd": "worker",
        "qa": "worker",
        "reviewer": "reviewer",
    }
    for preset in agent_presets.BUILTIN_PRESETS:
        definition = preset["definition"]
        assert "model_config" not in definition
        assert definition["tool_connection_ids"] == []
        assert definition["sandbox_profile_id"] is None
        assert definition["limits"] == {"max_turns": 20, "timeout_seconds": 600}
