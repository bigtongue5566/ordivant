from __future__ import annotations

import asyncio
import json
import uuid

import httpx
import pytest

from ordivant_knowledge import mcp_server


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


def test_mcp_registers_user_and_space_tools_without_caller_identity():
    tools = {tool.name: tool for tool in mcp_server.mcp._tool_manager.list_tools()}
    assert {"get_me", "list_spaces", "create_space"} <= tools.keys()
    for name in ("get_me", "list_spaces", "create_space"):
        assert "caller_user_id" not in tools[name].parameters["properties"]


def test_user_space_requests_use_rest_paths_body_and_idempotency(monkeypatch):
    requests = capture_requests(monkeypatch)
    monkeypatch.setattr(mcp_server, "API_URL", "http://mcp.test")

    async def run():
        await mcp_server.get_me()
        await mcp_server.list_spaces()
        await mcp_server.create_space(
            "KNOWLEDGE_MCP",
            "Knowledge MCP space",
            description="Created through Knowledge MCP",
            request_id="stable-space-create",
        )
        await mcp_server.create_space("KNOWLEDGE_AUTO", "Automatic request id")

    asyncio.run(run())
    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", "/api/me"),
        ("GET", "/api/spaces"),
        ("POST", "/api/spaces"),
        ("POST", "/api/spaces"),
    ]
    assert json.loads(requests[2].content) == {
        "key": "KNOWLEDGE_MCP",
        "name": "Knowledge MCP space",
        "description": "Created through Knowledge MCP",
    }
    assert requests[2].headers["Idempotency-Key"] == "stable-space-create"
    assert str(uuid.UUID(requests[3].headers["Idempotency-Key"])) == requests[3].headers["Idempotency-Key"]


@pytest.mark.parametrize(
    ("base_url", "expected_path"),
    [
        ("http://mcp.test", "/api/me"),
        ("http://mcp.test/api", "/api/me"),
        ("http://mcp.test/knowledge-api", "/knowledge-api/api/me"),
        ("http://mcp.test/knowledge-api/api", "/knowledge-api/api/me"),
        ("http://mcp.test/proxy", "/proxy/api/me"),
    ],
)
def test_api_base_url_prefix_is_normalized_once(monkeypatch, base_url, expected_path):
    requests = capture_requests(monkeypatch)
    monkeypatch.setattr(mcp_server, "API_URL", base_url)

    asyncio.run(mcp_server.get_me())

    assert requests[0].url.path == expected_path
