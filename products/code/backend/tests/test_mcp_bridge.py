from __future__ import annotations

import asyncio
import os
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from conftest import REPO_ROOT
from ordivant_code.main import app


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_official_mcp_stdio_bridge_uses_scoped_rest_api(api, credentials, repository, monkeypatch):
    from ordivant_code import service

    class PullStub:
        def pull(self, owner, repo, number):
            return {
                "number": number, "title": "MCP collaboration", "body": "", "state": "open",
                "head": {"ref": "topic", "sha": "e" * 40},
                "base": {"ref": "main", "sha": "f" * 40},
                "html_url": f"http://127.0.0.1:3001/demo/pulls/{number}",
                "created_at": "2026-10-10T00:00:00Z", "updated_at": "2026-10-10T00:00:00Z",
            }

    monkeypatch.setattr(service, "_gitea", lambda: PullStub())
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 8
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "uvicorn did not start for MCP bridge test"

    backend = REPO_ROOT / "products" / "code" / "backend"
    env = os.environ.copy()
    env["ORDIVANT_CODE_API_URL"] = f"http://127.0.0.1:{port}"
    env["ORDIVANT_CODE_API_TOKEN"] = credentials["manager_token"]
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ordivant_code.mcp_server"],
        env=env,
        cwd=backend,
    )

    async def round_trip():
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tool_list = await session.list_tools()
                names = {tool.name for tool in tool_list.tools}
                assert names == {
                    "list_code_projects", "list_repositories", "create_repository", "create_branch",
                    "commit_file", "create_pull_request", "get_pull_request",
                    "get_pull_request_collaboration", "comment_on_pull_request", "review_pull_request",
                    "report_check", "get_code_events",
                }
                result = await session.call_tool("list_code_projects", {})
                assert not result.isError
                text = "\n".join(item.text for item in result.content if hasattr(item, "text"))
                assert "code-demo" in text and "DEMO Code Repository Pilot" in text
                collaboration = await session.call_tool("get_pull_request_collaboration", {
                    "repository_id": repository["id"], "number": 321,
                })
                assert not collaboration.isError
                comment = await session.call_tool("comment_on_pull_request", {
                    "repository_id": repository["id"], "number": 321, "body": "MCP local comment",
                    "request_id": "mcp-comment-321",
                })
                assert not comment.isError
                review = await session.call_tool("review_pull_request", {
                    "repository_id": repository["id"], "number": 321,
                    "decision": "approve", "expected_head_sha": "e" * 40,
                    "comment": "MCP local review", "request_id": "mcp-review-321",
                })
                assert not review.isError
                latest = await session.call_tool("get_pull_request_collaboration", {
                    "repository_id": repository["id"], "number": 321,
                })
                assert not latest.isError
                latest_text = "\n".join(item.text for item in latest.content if hasattr(item, "text"))
                assert "MCP local comment" in latest_text and "MCP local review" in latest_text
                templates = await session.list_resource_templates()
                template_uris = {item.uriTemplate for item in templates.resourceTemplates}
                assert "code://projects/{project_id}/repositories" in template_uris
                assert "code://repositories/{repository_id}/pulls/{number}" in template_uris

    try:
        asyncio.run(round_trip())
    finally:
        server.should_exit = True
        thread.join(timeout=8)
    assert not thread.is_alive()
