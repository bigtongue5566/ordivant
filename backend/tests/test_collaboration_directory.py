from __future__ import annotations

from collections.abc import Callable
from urllib.parse import parse_qs

import httpx
import pytest
from sqlalchemy import select

from ordivant import identity
from ordivant.identity import IdentityBinding
from ordivant.models import Organization, Principal, Project, ProjectMembership, Team
from ordivant.security import new_id, now_utc

from conftest import headers


SYNTHETIC_SERVICE_TOKEN = "synthetic-work-directory-service-token-value-0001"


def install_directory_mock(monkeypatch, tmp_path, users: list[dict] | Callable[[str], list[dict]], *, outage: bool = False):
    token_file = tmp_path / "identity-directory-token"
    token_file.write_text(SYNTHETIC_SERVICE_TOKEN, encoding="utf-8")
    monkeypatch.setenv("ORDIVANT_AUTH_COOKIE_NAME", "suite_session")
    monkeypatch.setenv("ORDIVANT_AUTH_ORIGINS", "https://suite.example")
    monkeypatch.setenv("ORDIVANT_IDENTITY_URL", "http://identity.test")
    monkeypatch.setenv("ORDIVANT_IDENTITY_SERVICE_TOKEN_FILE", str(token_file))
    calls = []
    real_async_client = httpx.AsyncClient

    async def handle(request: httpx.Request) -> httpx.Response:
        query = parse_qs(request.url.query.decode() if isinstance(request.url.query, bytes) else request.url.query)
        product = query.get("product", [""])[0]
        scope_id = query.get("scope_id", [""])[0]
        calls.append((request.url.path, product, scope_id, request.headers.get("authorization")))
        if outage:
            raise httpx.ConnectError("synthetic identity outage", request=request)
        candidates = users(scope_id) if callable(users) else users
        scoped = []
        for user in candidates:
            permission = user.get("permissions", {}).get(product, {})
            if user.get("active") and (
                user.get("role") == "admin" or scope_id in permission.get("scope_ids", [])
            ):
                scoped.append(user)
        return httpx.Response(200, json={"users": scoped})

    transport = httpx.MockTransport(handle)

    def mocked_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(identity.httpx, "AsyncClient", mocked_async_client)
    return calls


def directory_user(subject: str, name: str, project_ids: list[str], *, role: str = "worker", active: bool = True) -> dict:
    return {
        "id": subject,
        "name": name,
        "role": "member",
        "active": active,
        "permissions": {"work": {"role": role, "scope_ids": project_ids}},
    }


def test_prelogin_directory_member_can_be_assigned_and_cross_project_assignment_is_denied(
    api_client, system, monkeypatch, tmp_path
):
    project_id = system["ids"]["project"]
    coworker = directory_user("identity-prelogin-coworker", "Prelogin Coworker", [project_id])
    calls = install_directory_mock(monkeypatch, tmp_path, [coworker])

    response = api_client.get(f"/api/projects/{project_id}/participants", headers=headers(system, "manager"))
    assert response.status_code == 200, response.text
    person = next(item for item in response.json() if item["name"] == "Prelogin Coworker")
    assert person["kind"] == "human"
    assert person["role"] == "worker"
    assert calls == [
        ("/api/auth/directory", "work", project_id, f"Bearer {SYNTHETIC_SERVICE_TOKEN}")
    ]

    # The identity subject has not logged in to Work. Directory sync creates
    # the local principal and membership so a manager can assign the task.
    assigned = api_client.post(
        "/api/tasks",
        json={"project_id": project_id, "title": "Assign before first login", "assignee_principal_id": person["id"]},
        headers=headers(system, "manager"),
    )
    assert assigned.status_code == 201, assigned.text
    assert assigned.json()["assignee"] == {
        "id": person["id"],
        "principal_id": person["id"],
        "name": "Prelogin Coworker",
        "kind": "human",
    }

    isolated_project_id = system["ids"]["isolated_project"]
    other_project_participants = api_client.get(
        f"/api/projects/{isolated_project_id}/participants", headers=headers(system, "manager")
    )
    assert other_project_participants.status_code == 200, other_project_participants.text
    cross_project_assignment = api_client.post(
        "/api/tasks",
        json={
            "project_id": isolated_project_id,
            "title": "Cross project assignment",
            "assignee_principal_id": person["id"],
        },
        headers=headers(system, "manager"),
    )
    assert cross_project_assignment.status_code == 403


def test_directory_refresh_revokes_withdrawn_human_membership_but_preserves_agent_memberships(
    api_client, system, monkeypatch, tmp_path
):
    project_id = system["ids"]["project"]
    coworker = directory_user("identity-withdrawn-coworker", "Withdrawn Coworker", [project_id])

    def current_directory(_scope_id: str) -> list[dict]:
        return [coworker]

    install_directory_mock(monkeypatch, tmp_path, current_directory)
    first = api_client.get(f"/api/projects/{project_id}/participants", headers=headers(system, "manager"))
    assert first.status_code == 200, first.text
    person = next(item for item in first.json() if item["name"] == "Withdrawn Coworker")

    with system["factory"]() as session:
        agent_memberships_before = set(
            session.execute(
                select(ProjectMembership.project_id, ProjectMembership.principal_id)
                .join(Principal, Principal.id == ProjectMembership.principal_id)
                .where(Principal.kind == "agent")
            ).all()
        )

    coworker["permissions"]["work"]["scope_ids"] = []
    refreshed = api_client.get(f"/api/projects/{project_id}/participants", headers=headers(system, "manager"))
    assert refreshed.status_code == 200, refreshed.text
    assert all(item["id"] != person["id"] for item in refreshed.json())

    with system["factory"]() as session:
        binding = session.get(IdentityBinding, coworker["id"])
        assert binding is not None
        assert session.scalar(
            select(ProjectMembership.id).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.principal_id == binding.principal_id,
            )
        ) is None
        agent_memberships_after = set(
            session.execute(
                select(ProjectMembership.project_id, ProjectMembership.principal_id)
                .join(Principal, Principal.id == ProjectMembership.principal_id)
                .where(Principal.kind == "agent")
            ).all()
        )
    assert agent_memberships_after == agent_memberships_before


def test_directory_cross_organization_scope_is_rejected_without_creating_binding(
    api_client, system, monkeypatch, tmp_path
):
    second_org_id = new_id()
    second_team_id = new_id()
    foreign_project_id = new_id()
    with system["factory"]() as session:
        session.add(Organization(id=second_org_id, name="Synthetic Foreign Org", created_at=now_utc()))
        session.flush()
        session.add(Team(id=second_team_id, organization_id=second_org_id, name="Foreign Team", created_at=now_utc()))
        session.flush()
        session.add(
            Project(
                id=foreign_project_id,
                key="FOREIGN",
                name="Synthetic Foreign Project",
                description="",
                organization_id=second_org_id,
                team_id=second_team_id,
                budget_usd=0,
                created_at=now_utc(),
            )
        )
        session.commit()

    monkeypatch.setenv("ORDIVANT_IDENTITY_ORG_ID", system["ids"]["organization"])
    local_project_id = system["ids"]["project"]
    coworker = directory_user(
        "identity-cross-org-coworker",
        "Cross Org Coworker",
        [local_project_id, foreign_project_id],
    )
    install_directory_mock(monkeypatch, tmp_path, [coworker])

    response = api_client.get(
        f"/api/projects/{local_project_id}/participants", headers=headers(system, "manager")
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "identity_cross_organization_scope"
    with system["factory"]() as session:
        assert session.get(IdentityBinding, coworker["id"]) is None


def test_identity_directory_outage_fails_closed(api_client, system, monkeypatch, tmp_path):
    calls = install_directory_mock(monkeypatch, tmp_path, [], outage=True)

    response = api_client.get(
        f"/api/projects/{system['ids']['project']}/participants", headers=headers(system, "manager")
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "identity_unavailable"
    assert len(calls) == 1
    with system["factory"]() as session:
        assert session.scalars(select(IdentityBinding)).all() == []
