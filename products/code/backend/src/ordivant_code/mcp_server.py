from __future__ import annotations

import os
import uuid
import json
from typing import Literal
from urllib.parse import quote, urlencode

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Ordivant Code")


async def _request(method: str, path: str, *, body: dict | None = None, request_id: str | None = None):
    base = os.getenv("ORDIVANT_CODE_API_URL", "http://127.0.0.1:8020").rstrip("/")
    token = os.getenv("ORDIVANT_CODE_API_TOKEN", "")
    if not token:
        raise RuntimeError("ORDIVANT_CODE_API_TOKEN is required")
    headers = {"Authorization": f"Bearer {token}"}
    if method in {"POST", "PATCH", "PUT", "DELETE"}:
        headers["Idempotency-Key"] = request_id or str(uuid.uuid4())
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.request(method, f"{base}/api{path}", headers=headers, json=body)
    if response.is_error:
        try:
            detail = response.json().get("detail", {})
            message = detail.get("message", "Code API request failed")
        except (ValueError, AttributeError):
            message = "Code API request failed"
        raise RuntimeError(f"HTTP {response.status_code}: {message}")
    return response.json()


@mcp.tool()
async def list_code_projects() -> list[dict]:
    """List Code projects available to the configured credential."""
    return await _request("GET", "/projects")


@mcp.tool()
async def list_repositories(project_id: str) -> list[dict]:
    """List repositories bound to a Code project."""
    return await _request("GET", f"/repositories?{urlencode({'project_id': project_id})}")


@mcp.tool()
async def create_repository(project_id: str, name: str, description: str = "", request_id: str | None = None) -> dict:
    """Create a private Gitea repository bound to a scoped Code project."""
    return await _request("POST", "/repositories", body={
        "project_id": project_id, "name": name, "description": description, "private": True,
    }, request_id=request_id)


@mcp.tool()
async def create_branch(repository_id: str, name: str, from_branch: str = "main", request_id: str | None = None) -> dict:
    """Create a branch in a scoped repository."""
    return await _request("POST", f"/repositories/{quote(repository_id, safe='')}/branches", body={
        "name": name, "from_branch": from_branch,
    }, request_id=request_id)


@mcp.tool()
async def commit_file(
    repository_id: str,
    branch: str,
    path: str,
    content: str,
    commit_message: str,
    expected_sha: str | None = None,
    request_id: str | None = None,
) -> dict:
    """Commit UTF-8 file content through Gitea's Contents API."""
    return await _request("POST", f"/repositories/{quote(repository_id, safe='')}/files", body={
        "branch": branch, "path": path, "content": content,
        "commit_message": commit_message, "expected_sha": expected_sha,
    }, request_id=request_id)


@mcp.tool()
async def create_pull_request(
    repository_id: str,
    head: str,
    title: str,
    body: str = "",
    base: str = "main",
    source_refs: list[dict] | None = None,
    request_id: str | None = None,
) -> dict:
    """Create a Gitea pull request with optional cross-product references."""
    return await _request("POST", f"/repositories/{quote(repository_id, safe='')}/pulls", body={
        "head": head, "base": base, "title": title, "body": body,
        "source_refs": source_refs or [],
    }, request_id=request_id)


@mcp.tool()
async def get_pull_request(repository_id: str, number: int) -> dict:
    """Get a pull request and its persisted status receipts."""
    return await _request("GET", f"/repositories/{quote(repository_id, safe='')}/pulls/{number}")


@mcp.tool()
async def get_pull_request_collaboration(repository_id: str, number: int) -> dict:
    """Get Ordivant-local pull request comments and review receipts."""
    return await _request(
        "GET", f"/repositories/{quote(repository_id, safe='')}/pulls/{number}/collaboration",
    )


@mcp.tool()
async def comment_on_pull_request(
    repository_id: str, number: int, body: str, request_id: str | None = None,
) -> dict:
    """Add an Ordivant-local comment without creating a Gitea review."""
    return await _request(
        "POST", f"/repositories/{quote(repository_id, safe='')}/pulls/{number}/comments",
        body={"body": body}, request_id=request_id,
    )


@mcp.tool()
async def review_pull_request(
    repository_id: str,
    number: int,
    decision: Literal["approve", "request_changes", "comment"],
    expected_head_sha: str,
    comment: str = "",
    request_id: str | None = None,
) -> dict:
    """Record an Ordivant-local review receipt against the expected current head."""
    return await _request(
        "POST", f"/repositories/{quote(repository_id, safe='')}/pulls/{number}/reviews",
        body={"decision": decision, "comment": comment, "expected_head_sha": expected_head_sha},
        request_id=request_id,
    )


@mcp.tool()
async def report_check(
    repository_id: str,
    commit_sha: str,
    context: str,
    state: str,
    description: str = "",
    target_url: str | None = None,
    request_id: str | None = None,
) -> dict:
    """Report an explicitly agent-reported status receipt to Gitea."""
    return await _request("POST", f"/repositories/{quote(repository_id, safe='')}/checks", body={
        "commit_sha": commit_sha, "context": context, "state": state,
        "description": description, "target_url": target_url,
    }, request_id=request_id)


@mcp.tool()
async def get_code_events(project_id: str | None = None) -> list[dict]:
    """List project-scoped Code audit events."""
    path = f"/events?{urlencode({'project_id': project_id})}" if project_id else "/events"
    return await _request("GET", path)


@mcp.resource("code://projects/{project_id}/repositories")
async def repository_resource(project_id: str) -> str:
    """Repository metadata visible in a Code project."""
    value = await _request("GET", f"/repositories?{urlencode({'project_id': project_id})}")
    return json.dumps(value, ensure_ascii=False)


@mcp.resource("code://repositories/{repository_id}/pulls/{number}")
async def pull_request_resource(repository_id: str, number: int) -> str:
    """Pull request context and status receipts."""
    value = await _request("GET", f"/repositories/{quote(repository_id, safe='')}/pulls/{number}")
    return json.dumps(value, ensure_ascii=False)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
