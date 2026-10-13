from __future__ import annotations

import json
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


API_URL = os.getenv("ORDIVANT_KNOWLEDGE_API_URL", "http://127.0.0.1:8010").rstrip("/")
API_TOKEN = os.getenv("ORDIVANT_KNOWLEDGE_API_TOKEN", "")
mcp = FastMCP("Ordivant Knowledge")


async def _request(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> Any:
    if not API_TOKEN:
        raise RuntimeError("ORDIVANT_KNOWLEDGE_API_TOKEN is required for the Knowledge MCP bridge")
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    if request_id:
        headers["Idempotency-Key"] = request_id
    async with httpx.AsyncClient(base_url=API_URL, timeout=30) as client:
        response = await client.request(method, path, json=body, params=params, headers=headers)
    if response.is_error:
        try:
            detail = response.json().get("detail", {})
        except (ValueError, AttributeError):
            detail = {}
        if isinstance(detail, dict):
            code = detail.get("code")
            message = detail.get("message")
            if isinstance(code, str) and isinstance(message, str):
                raise RuntimeError(f"{code}: {message}")
        raise RuntimeError(f"Knowledge API returned HTTP {response.status_code}")
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


@mcp.tool()
async def list_spaces() -> list[dict[str, Any]]:
    """List knowledge spaces visible to the configured principal."""
    return await _request("GET", "/api/spaces")


@mcp.tool()
async def search_knowledge(
    q: str | None = None,
    space_id: str | None = None,
    tag: str | None = None,
) -> list[dict[str, Any]]:
    """Search current persisted text and return snippets with exact-version citations."""
    params = {key: value for key, value in {"q": q, "space_id": space_id, "tag": tag}.items() if value is not None}
    return await _request("GET", "/api/documents", params=params)


@mcp.tool()
async def create_document(
    space_id: str,
    title: str,
    body: str,
    summary: str = "",
    tags: list[str] | None = None,
    change_summary: str = "Initial version.",
    source_refs: list[dict[str, str]] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Create version 1 in a visible space; actor identity comes from the configured token."""
    payload = {
        "space_id": space_id,
        "title": title,
        "summary": summary,
        "body": body,
        "tags": tags or [],
        "change_summary": change_summary,
        "source_refs": source_refs or [],
    }
    return await _request("POST", "/api/documents", body=payload, request_id=request_id)


@mcp.tool()
async def get_document_context(document_id: str) -> dict[str, Any]:
    """Read current document content, immutable version history, decisions, and citations."""
    return await _request("GET", f"/api/documents/{document_id}")


@mcp.tool()
async def get_document_draft(document_id: str) -> dict[str, Any]:
    """Read the current shared Knowledge draft and its Yjs v1 state update."""
    return await _request("GET", f"/api/documents/{document_id}/draft")


@mcp.tool()
async def apply_document_draft_update(
    document_id: str,
    update: str,
    request_id: str,
) -> dict[str, Any]:
    """Merge a base64-encoded Yjs v1 update into the shared draft."""
    return await _request(
        "POST",
        f"/api/documents/{document_id}/draft/updates",
        body={"update": update},
        request_id=request_id,
    )


@mcp.tool()
async def publish_document_draft(
    document_id: str,
    expected_revision: int,
    change_summary: str,
    title: str | None = None,
    source_refs: list[dict[str, str]] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Publish the shared draft using compare-and-swap on its current revision."""
    payload: dict[str, Any] = {
        "expected_revision": expected_revision,
        "change_summary": change_summary,
        "source_refs": source_refs or [],
    }
    if title is not None:
        payload["title"] = title
    return await _request(
        "POST",
        f"/api/documents/{document_id}/draft/publish",
        body=payload,
        request_id=request_id,
    )


@mcp.tool()
async def get_document_version(document_id: str, version: int) -> dict[str, Any]:
    """Read one immutable document version using its exact version number."""
    return await _request("GET", f"/api/documents/{document_id}/versions/{version}")


@mcp.tool()
async def publish_document_version(
    document_id: str,
    expected_version: int,
    body: str,
    change_summary: str,
    title: str | None = None,
    source_refs: list[dict[str, str]] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Publish via expected-version compare-and-swap; the returned version has an exact citation."""
    payload: dict[str, Any] = {
        "expected_version": expected_version,
        "body": body,
        "change_summary": change_summary,
        "source_refs": source_refs or [],
    }
    if title is not None:
        payload["title"] = title
    return await _request(
        "POST",
        f"/api/documents/{document_id}/versions",
        body=payload,
        request_id=request_id,
    )


@mcp.tool()
async def record_decision(
    space_id: str,
    title: str,
    body: str,
    document_id: str | None = None,
    source_refs: list[dict[str, str]] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Record a scoped decision with preserved task, PR, document, or external provenance."""
    payload = {
        "space_id": space_id,
        "document_id": document_id,
        "title": title,
        "body": body,
        "source_refs": source_refs or [],
    }
    return await _request("POST", "/api/decisions", body=payload, request_id=request_id)


@mcp.tool()
async def list_decisions(space_id: str) -> list[dict[str, Any]]:
    """List decisions in a visible knowledge space."""
    return await _request("GET", "/api/decisions", params={"space_id": space_id})


@mcp.resource("ordivant://knowledge/spaces/{space_id}/documents/{document_id}/versions/{version}")
async def exact_document_version_resource(space_id: str, document_id: str, version: int) -> str:
    """Read the exact version addressed by a canonical Knowledge citation URI."""
    result = await get_document_version(document_id, version)
    if not result.get("uri", "").startswith(f"ordivant://knowledge/spaces/{space_id}/documents/"):
        raise RuntimeError("Citation space does not match the resolved document")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.prompt()
def knowledge_citation_prompt(document_id: str, version: int, space_id: str) -> str:
    uri = f"ordivant://knowledge/spaces/{space_id}/documents/{document_id}/versions/{version}"
    return (
        f"Read the exact Knowledge version at {uri}. Use its content and provenance as written. "
        "When relying on it, cite this exact URI; do not replace it with the document's latest version. "
        "Treat linked Work tasks, Code pull requests, and external references as provenance labels, not access grants."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
