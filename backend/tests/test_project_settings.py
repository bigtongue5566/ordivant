from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import delete, func, select

from conftest import headers
from ordivant import mcp_server
from ordivant.models import AuditEvent, ProjectMembership


def payload(client, system):
    project = client.get(f"/api/projects/{system['ids']['project']}", headers=headers(system, "manager")).json()
    fields = {key: project[key] for key in ("name", "description", "budget_usd")}
    return {**fields, "name": "Updated project", "description": "A shared project", "budget_usd": 42.5, "expected": fields}


def test_project_update_is_audited_idempotent_and_keeps_task_keys(api_client, system):
    project_id = system["ids"]["project"]
    body = payload(api_client, system)
    route = f"/api/projects/{project_id}"
    response = api_client.patch(route, json=body, headers=headers(system, "manager", "settings-one"))
    assert response.status_code == 200, response.text
    assert response.json()["key"] == "TST"
    assert response.json()["name"] == "Updated project"
    assert api_client.patch(route, json=body, headers=headers(system, "manager", "settings-one")).json() == response.json()
    assert api_client.get(route, headers=headers(system, "manager")).json()["budget_usd"] == 42.5
    with system["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "project.updated")) == 1
        db.execute(delete(ProjectMembership).where(ProjectMembership.principal_id == system["ids"]["manager"]))
        db.commit()
    assert api_client.patch(route, json=body, headers=headers(system, "manager", "settings-one")).status_code == 404


def test_project_settings_authorization_and_stale_snapshot(api_client, system):
    body = payload(api_client, system)
    route = f"/api/projects/{system['ids']['project']}"
    for actor in ("worker_a", "reviewer", "outsider"):
        assert api_client.patch(route, json=body, headers=headers(system, actor)).status_code in {403, 404}
    with system["factory"]() as db:
        db.execute(delete(ProjectMembership).where(ProjectMembership.principal_id == system["ids"]["manager"], ProjectMembership.project_id == system["ids"]["isolated_project"]))
        db.commit()
    assert api_client.patch(f"/api/projects/{system['ids']['isolated_project']}", json=body, headers=headers(system, "manager")).status_code == 404
    assert api_client.patch(route, json=body, headers=headers(system, "manager")).status_code == 200
    conflict = api_client.patch(route, json={**body, "name": "Stale overwrite"}, headers=headers(system, "manager"))
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "project_settings_changed"
    assert api_client.get(route, headers=headers(system, "manager")).json()["name"] == "Updated project"


def test_concurrent_project_settings_have_one_winner(api_client, system):
    body = payload(api_client, system)
    route = f"/api/projects/{system['ids']['project']}"
    def write(name):
        return api_client.patch(route, json={**body, "name": name}, headers=headers(system, "manager", name)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ("First editor", "Second editor")))
    assert sorted(results) == [200, 409]


@pytest.mark.parametrize("changes", [{"name": "   "}, {"name": None}, {"budget_usd": -1}, {"key": "OTHER"}, {"organization_id": "other"}, {"expected": None}])
def test_project_settings_reject_invalid_or_immutable_fields(api_client, system, changes):
    body = {**payload(api_client, system), **changes}
    assert api_client.patch(f"/api/projects/{system['ids']['project']}", json=body, headers=headers(system, "manager")).status_code == 422


@pytest.mark.asyncio
async def test_project_settings_mcp_keeps_snapshot_and_idempotency(monkeypatch):
    recorded = []
    async def request(method, path, **kwargs):
        recorded.append((method, path, kwargs))
        return {"id": "project"}
    monkeypatch.setattr(mcp_server, "_request", request)
    expected = {"name": "Before", "description": "", "budget_usd": 1}
    await mcp_server.update_project("project", "After", "Updated", 2, expected, "same-write")
    assert recorded == [("PATCH", "/api/projects/project", {"body": {"name": "After", "description": "Updated", "budget_usd": 2, "expected": expected}, "request_id": "same-write"})]
