from __future__ import annotations

import json
import os
import uuid
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from mcp.server.fastmcp import FastMCP


API_URL = os.getenv("ORDIVANT_KNOWLEDGE_API_URL", "http://127.0.0.1:8010").rstrip("/")
API_TOKEN = os.getenv("ORDIVANT_KNOWLEDGE_API_TOKEN", "")
mcp = FastMCP("Ordivant Knowledge")


def _normalize_api_base_url(value: str) -> str:
    parts = urlsplit(value)
    path = parts.path.rstrip("/")
    if path.endswith("/api"):
        path = path[:-4]
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment)).rstrip("/")


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
    async with httpx.AsyncClient(base_url=_normalize_api_base_url(API_URL), timeout=30) as client:
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
async def get_me() -> dict[str, Any]:
    """Read the principal associated with this configured credential."""
    return await _request("GET", "/api/me")


@mcp.tool()
async def list_spaces() -> list[dict[str, Any]]:
    """List knowledge spaces visible to the configured principal."""
    return await _request("GET", "/api/spaces")


@mcp.tool()
async def create_space(
    key: str,
    name: str,
    description: str = "",
    request_id: str | None = None,
) -> dict[str, Any]:
    """Create a Knowledge space using the configured credential's server-side authorization."""
    return await _request(
        "POST",
        "/api/spaces",
        body={"key": key, "name": name, "description": description},
        request_id=request_id or str(uuid.uuid4()),
    )


@mcp.tool()
async def search_knowledge(
    q: str | None = None,
    space_id: str | None = None,
    tag: str | None = None,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """Search current persisted text and return snippets with exact-version citations."""
    params = {key: value for key, value in {"q": q, "space_id": space_id, "tag": tag}.items() if value is not None}
    if include_archived:
        params["include_archived"] = True
    return await _request("GET", "/api/documents", params=params)


@mcp.tool()
async def create_document(
    space_id: str,
    title: str,
    body: str,
    request_id: str,
    summary: str = "",
    tags: list[str] | None = None,
    change_summary: str = "Initial version.",
    source_refs: list[dict[str, str]] | None = None,
    parent_id: str | None = None,
) -> dict[str, Any]:
    """Create version 1 in a visible space; actor identity comes from the configured credential."""
    payload = {
        "space_id": space_id,
        "title": title,
        "summary": summary,
        "body": body,
        "tags": tags or [],
        "change_summary": change_summary,
        "source_refs": source_refs or [],
        "parent_id": parent_id,
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
    request_id: str,
    title: str | None = None,
    source_refs: list[dict[str, str]] | None = None,
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
    request_id: str,
    title: str | None = None,
    source_refs: list[dict[str, str]] | None = None,
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
    request_id: str,
    document_id: str | None = None,
    source_refs: list[dict[str, str]] | None = None,
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


@mcp.tool()
async def list_knowledge_templates(space_id: str) -> list[dict[str, Any]]:
    """List built-in and custom document templates visible in a space."""
    return await _request("GET", f"/api/spaces/{space_id}/templates")


@mcp.tool()
async def create_knowledge_template(
    space_id: str,
    name: str,
    body: str,
    request_id: str,
    description: str = "",
) -> dict[str, Any]:
    """Create a reusable space template; the API checks the configured actor's writer role."""
    return await _request(
        "POST",
        f"/api/spaces/{space_id}/templates",
        body={"name": name, "description": description, "body": body},
        request_id=request_id,
    )


@mcp.tool()
async def organize_knowledge_document(
    document_id: str,
    parent_id: str | None,
    request_id: str,
    archived: bool | None = None,
) -> dict[str, Any]:
    """Move a document within its space, set it at the root with a null parent, or archive it."""
    payload: dict[str, Any] = {"parent_id": parent_id}
    if archived is not None:
        payload["archived"] = archived
    return await _request(
        "PATCH",
        f"/api/documents/{document_id}/organization",
        body=payload,
        request_id=request_id,
    )


@mcp.tool()
async def list_knowledge_comments(document_id: str) -> list[dict[str, Any]]:
    """Read document comments and replies allowed by the configured principal's space access."""
    return await _request("GET", f"/api/documents/{document_id}/comments")


@mcp.tool()
async def create_knowledge_comment(
    document_id: str,
    body: str,
    request_id: str,
    parent_id: str | None = None,
    quote: str | None = None,
    version: int | None = None,
    start: int | None = None,
    end: int | None = None,
) -> dict[str, Any]:
    """Add a plain-text comment or reply, optionally anchored to an exact version quote."""
    anchor = None
    if quote is not None:
        if version is None:
            raise ValueError("version is required when quote is provided")
        anchor = {"quote": quote, "version": version}
        if start is not None:
            anchor["start"] = start
        if end is not None:
            anchor["end"] = end
    payload: dict[str, Any] = {"body": body, "parent_id": parent_id}
    if anchor is not None:
        payload["anchor"] = anchor
    return await _request(
        "POST",
        f"/api/documents/{document_id}/comments",
        body=payload,
        request_id=request_id,
    )


@mcp.tool()
async def resolve_knowledge_comment(
    comment_id: str,
    request_id: str,
    resolved: bool = True,
) -> dict[str, Any]:
    """Resolve or reopen a comment thread; the API checks the configured actor's writer role."""
    return await _request(
        "PATCH",
        f"/api/document-comments/{comment_id}",
        body={"resolved": resolved},
        request_id=request_id,
    )


@mcp.tool()
async def diff_knowledge_document_versions(
    document_id: str,
    from_version: int,
    to_version: int,
) -> dict[str, Any]:
    """Compare two immutable versions that are visible to the configured principal."""
    return await _request(
        "GET",
        f"/api/documents/{document_id}/diff",
        params={"from_version": from_version, "to_version": to_version},
    )


@mcp.tool()
async def restore_knowledge_document_version(
    document_id: str,
    version: int,
    expected_current_version: int,
    request_id: str,
    change_summary: str = "",
) -> dict[str, Any]:
    """Restore a version as a new immutable version using compare-and-swap on the current version."""
    return await _request(
        "POST",
        f"/api/documents/{document_id}/restore",
        body={
            "version": version,
            "expected_current_version": expected_current_version,
            "change_summary": change_summary,
        },
        request_id=request_id,
    )


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


from .collaboration_mcp import install_tools as install_collaboration_tools

install_collaboration_tools(mcp, _request)


if __name__ == "__main__":
    mcp.run(transport="stdio")
