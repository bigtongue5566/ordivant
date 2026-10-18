from __future__ import annotations

import asyncio
import json
import uuid

import httpx
import pytest

from ordivant import mcp_server


def capture_requests(monkeypatch):
    requests = []
    original_client = httpx.AsyncClient

    async def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    def client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handle)
        return original_client(*args, **kwargs)

    monkeypatch.setattr(mcp_server, "API_TOKEN", "test-only-credential")
    monkeypatch.setattr(mcp_server.httpx, "AsyncClient", client)
    return requests


def test_mcp_registers_user_and_project_tools_without_caller_identity():
    tools = {tool.name: tool for tool in mcp_server.mcp._tool_manager.list_tools()}
    assert {"get_me", "list_projects", "create_project"} <= tools.keys()
    for name in ("get_me", "list_projects", "create_project"):
        assert "caller_user_id" not in tools[name].parameters["properties"]


def test_user_project_requests_use_rest_paths_body_and_idempotency(monkeypatch):
    requests = capture_requests(monkeypatch)
    monkeypatch.setattr(mcp_server, "API_URL", "http://mcp.test")

    async def run():
        await mcp_server.get_me()
        await mcp_server.list_projects()
        await mcp_server.create_project(
            "MCP_WORK",
            "MCP Work project",
            description="Created through Work MCP",
            team_id="team-7",
            budget_usd=125.5,
            request_id="stable-work-create",
        )
        await mcp_server.create_project("MCP_AUTO", "Automatic request id")

    asyncio.run(run())
    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", "/api/me"),
        ("GET", "/api/projects"),
        ("POST", "/api/projects"),
        ("POST", "/api/projects"),
    ]
    assert json.loads(requests[2].content) == {
        "key": "MCP_WORK",
        "name": "MCP Work project",
        "description": "Created through Work MCP",
        "team_id": "team-7",
        "budget_usd": 125.5,
    }
    assert requests[2].headers["Idempotency-Key"] == "stable-work-create"
    assert str(uuid.UUID(requests[3].headers["Idempotency-Key"])) == requests[3].headers["Idempotency-Key"]


@pytest.mark.parametrize(
    ("base_url", "expected_path"),
    [
        ("http://mcp.test", "/api/me"),
        ("http://mcp.test/api", "/api/me"),
        ("http://mcp.test/proxy", "/proxy/api/me"),
    ],
)
def test_api_base_url_prefix_is_normalized_once(monkeypatch, base_url, expected_path):
    requests = capture_requests(monkeypatch)
    monkeypatch.setattr(mcp_server, "API_URL", base_url)

    async def run():
        await mcp_server.get_me()
        await mcp_server.export_project_tasks_csv("project-1")

    asyncio.run(run())

    assert [request.url.path for request in requests] == [
        expected_path,
        expected_path.replace("/api/me", "/api/projects/project-1/tasks/export"),
    ]
