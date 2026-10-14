from __future__ import annotations

import json
import os
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx
from mcp.server.fastmcp import FastMCP

from .schemas import ArtifactInput


API_URL = os.getenv("ORDIVANT_API_URL", "http://127.0.0.1:8000").rstrip("/")
API_TOKEN = os.getenv("ORDIVANT_API_TOKEN", "")
mcp = FastMCP("Ordivant")


async def _request(
    method: str,
    path: str,
    *,
    body: dict | None = None,
    params: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> Any:
    if not API_TOKEN:
        raise RuntimeError("ORDIVANT_API_TOKEN is required for the Ordivant MCP bridge")
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    if request_id:
        headers["Idempotency-Key"] = request_id
    async with httpx.AsyncClient(base_url=API_URL, timeout=30) as client:
        response = await client.request(method, path, json=body, params=params, headers=headers)
    if response.is_error:
        detail = response.text[:2000]
        raise RuntimeError(f"Ordivant API returned HTTP {response.status_code}: {detail}")
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


async def _request_text(method: str, path: str, *, body: dict | None = None, request_id: str | None = None) -> str:
    if not API_TOKEN:
        raise RuntimeError("ORDIVANT_API_TOKEN is required for the Ordivant MCP bridge")
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    if request_id:
        headers["Idempotency-Key"] = request_id
    async with httpx.AsyncClient(base_url=API_URL, timeout=30) as client:
        response = await client.request(method, path, json=body, headers=headers)
    if response.is_error:
        raise RuntimeError(f"Ordivant API returned HTTP {response.status_code}: {response.text[:2000]}")
    return response.text


@mcp.tool()
async def get_project_context(project_id: str) -> dict:
    """Read a project, its tasks, scoped agents, and decisions."""
    return await _request("GET", f"/api/projects/{project_id}/context")


@mcp.tool()
async def list_project_participants(project_id: str) -> list[dict]:
    """List authorized human coworkers and agents for collaboration in this project."""
    return await _request("GET", f"/api/projects/{project_id}/participants")


@mcp.tool()
async def get_vcs_pull_request(project_id: str, provider: str, repository: str, number: int) -> dict:
    """Read authorized existing GitHub/GitLab/Gitea PR evidence directly through Work."""
    return await _request("GET", f"/api/projects/{project_id}/vcs/pulls/{provider}/{number}", params={"repository": repository})


@mcp.tool()
async def get_project_planning(project_id: str) -> dict:
    """Read scoped sprints, milestones, custom fields, stages, rules, and intake forms."""
    return await _request("GET", f"/api/projects/{project_id}/planning")


@mcp.tool()
async def create_task(
    project_id: str,
    title: str,
    goal: str,
    description: str = "",
    inputs: str = "",
    scope: str = "",
    constraints: str = "",
    acceptance_criteria: list[str] | None = None,
    priority: str = "medium",
    request_id: str | None = None,
    planning: dict[str, Any] | None = None,
) -> dict:
    """Create a scoped task; actor identity comes from the configured agent token."""
    body = {
        "project_id": project_id,
        "title": title,
        "goal": goal,
        "description": description,
        "inputs": inputs,
        "scope": scope,
        "constraints": constraints,
        "acceptance_criteria": acceptance_criteria or [],
        "priority": priority,
    }
    if planning:
        body.update(planning)
    return await _request("POST", "/api/tasks", body=body, request_id=request_id or (str(uuid.uuid4()) if planning else None))


@mcp.tool()
async def update_task(task_id: str, patch: dict[str, Any], request_id: str | None = None) -> dict:
    """Update manager-editable task specification fields."""
    uses_planning = bool(set(patch) & {"work_type", "epic_id", "due_at", "start_at", "sprint_id", "milestone_id", "estimate_points", "rank", "stage_id", "custom_fields"})
    return await _request("PATCH", f"/api/tasks/{task_id}", body=patch, request_id=request_id or (str(uuid.uuid4()) if uses_planning else None))


@mcp.tool()
async def create_sprint(project_id: str, value: dict[str, Any], request_id: str | None = None) -> dict:
    """Create a project sprint; only one sprint can be active at a time."""
    return await _request("POST", f"/api/projects/{project_id}/sprints", body=value, request_id=request_id or str(uuid.uuid4()))


@mcp.tool()
async def update_sprint(sprint_id: str, patch: dict[str, Any], request_id: str | None = None) -> dict:
    """Update a sprint without changing task execution status."""
    return await _request("PATCH", f"/api/sprints/{sprint_id}", body=patch, request_id=request_id or str(uuid.uuid4()))


@mcp.tool()
async def create_milestone(project_id: str, value: dict[str, Any], request_id: str | None = None) -> dict:
    """Create a project milestone."""
    return await _request("POST", f"/api/projects/{project_id}/milestones", body=value, request_id=request_id or str(uuid.uuid4()))


@mcp.tool()
async def update_milestone(milestone_id: str, patch: dict[str, Any], request_id: str | None = None) -> dict:
    """Update a project milestone."""
    return await _request("PATCH", f"/api/milestones/{milestone_id}", body=patch, request_id=request_id or str(uuid.uuid4()))


@mcp.tool()
async def create_project_field(project_id: str, value: dict[str, Any], request_id: str | None = None) -> dict:
    """Create a validated text, number, boolean, or select task field."""
    return await _request("POST", f"/api/projects/{project_id}/fields", body=value, request_id=request_id or str(uuid.uuid4()))


@mcp.tool()
async def update_project_field(field_id: str, patch: dict[str, Any], request_id: str | None = None) -> dict:
    """Update a project task field; used keys and kinds are immutable."""
    return await _request("PATCH", f"/api/fields/{field_id}", body=patch, request_id=request_id or str(uuid.uuid4()))


@mcp.tool()
async def create_project_stage(project_id: str, value: dict[str, Any], request_id: str | None = None) -> dict:
    """Create a planning stage mapped to an existing task lifecycle status."""
    return await _request("POST", f"/api/projects/{project_id}/stages", body=value, request_id=request_id or str(uuid.uuid4()))


@mcp.tool()
async def update_project_stage(stage_id: str, patch: dict[str, Any], request_id: str | None = None) -> dict:
    """Update a planning stage without bypassing task execution or review."""
    return await _request("PATCH", f"/api/stages/{stage_id}", body=patch, request_id=request_id or str(uuid.uuid4()))


@mcp.tool()
async def reorder_project_tasks(project_id: str, task_ids: list[str], request_id: str | None = None) -> list[dict]:
    """Set an ordered list of task ranks; every task must belong to the project."""
    return await _request("POST", f"/api/projects/{project_id}/reorder", body={"task_ids": task_ids}, request_id=request_id or str(uuid.uuid4()))


@mcp.tool()
async def create_task_rule(project_id: str, value: dict[str, Any], request_id: str | None = None) -> dict:
    """Create an authorized, synchronous task rule. Rules never invoke an LLM."""
    return await _request("POST", f"/api/projects/{project_id}/rules", body=value, request_id=request_id or str(uuid.uuid4()))


@mcp.tool()
async def update_task_rule(rule_id: str, patch: dict[str, Any], request_id: str | None = None) -> dict:
    """Update a task rule."""
    return await _request("PATCH", f"/api/rules/{rule_id}", body=patch, request_id=request_id or str(uuid.uuid4()))


@mcp.tool()
async def create_intake_form(project_id: str, value: dict[str, Any], request_id: str | None = None) -> dict:
    """Create an authenticated project intake form."""
    return await _request("POST", f"/api/projects/{project_id}/forms", body=value, request_id=request_id or str(uuid.uuid4()))


@mcp.tool()
async def update_intake_form(form_id: str, patch: dict[str, Any], request_id: str | None = None) -> dict:
    """Update an authenticated project intake form."""
    return await _request("PATCH", f"/api/forms/{form_id}", body=patch, request_id=request_id or str(uuid.uuid4()))


@mcp.tool()
async def get_intake_form(form_id: str) -> dict:
    """Read a form only when the current actor can access its project."""
    return await _request("GET", f"/api/forms/{form_id}")


@mcp.tool()
async def submit_intake_form(form_id: str, value: dict[str, Any], request_id: str | None = None) -> dict:
    """Submit a scoped intake request as a backlog task."""
    return await _request("POST", f"/api/forms/{form_id}/submit", body=value, request_id=request_id or str(uuid.uuid4()))


@mcp.tool()
async def add_task_worklog(task_id: str, minutes: int, started_at: str, description: str = "", request_id: str | None = None) -> dict:
    """Record observed time against an authorized task; attribution comes from the token."""
    return await _request("POST", f"/api/tasks/{task_id}/worklogs", body={"minutes": minutes, "started_at": started_at, "description": description}, request_id=request_id or str(uuid.uuid4()))


@mcp.tool()
async def get_task_worklogs(task_id: str) -> list[dict]:
    """Read worklogs for a task in the caller's authorized project."""
    return await _request("GET", f"/api/tasks/{task_id}/worklogs")


@mcp.tool()
async def get_project_reports(project_id: str) -> dict:
    """Read observed task totals, accepted execution elapsed time, capacity, and worklogs."""
    return await _request("GET", f"/api/projects/{project_id}/reports")


@mcp.tool()
async def export_project_tasks_csv(project_id: str) -> str:
    """Export authorized tasks as spreadsheet-safe CSV."""
    return await _request_text("GET", f"/api/projects/{project_id}/tasks/export")


@mcp.tool()
async def import_project_tasks_csv(project_id: str, csv: str, request_id: str | None = None) -> dict:
    """Atomically validate and import a bounded CSV batch of tasks."""
    return await _request("POST", f"/api/projects/{project_id}/tasks/import", body={"csv": csv}, request_id=request_id or str(uuid.uuid4()))


@mcp.tool()
async def list_saved_queries() -> list[dict]:
    """List saved queries owned by the current actor and still in accessible projects."""
    return await _request("GET", "/api/saved-queries")


@mcp.tool()
async def create_saved_query(name: str, project_id: str, filters: dict[str, Any], request_id: str | None = None) -> dict:
    """Save a scoped task query for the current actor."""
    return await _request("POST", "/api/saved-queries", body={"name": name, "project_id": project_id, "filters": filters}, request_id=request_id or str(uuid.uuid4()))


@mcp.tool()
async def delete_saved_query(query_id: str, request_id: str | None = None) -> dict:
    """Delete a saved query owned by the current actor."""
    return await _request("DELETE", f"/api/saved-queries/{query_id}", request_id=request_id or str(uuid.uuid4()))


@mcp.tool()
async def find_ready_tasks(project_id: str | None = None, q: str | None = None) -> list[dict]:
    """Find ready tasks visible to this credential."""
    params: dict[str, Any] = {"ready_only": "true"}
    if project_id:
        params["project_id"] = project_id
    if q:
        params["q"] = q
    return await _request("GET", "/api/tasks", params=params)


@mcp.tool()
async def claim_task(task_id: str, lease_seconds: int = 300, request_id: str | None = None) -> dict:
    """Atomically claim a ready task and return its fenced lease token."""
    return await _request(
        "POST", f"/api/tasks/{task_id}/claim", body={"lease_seconds": lease_seconds}, request_id=request_id
    )


@mcp.tool()
async def renew_lease(
    task_id: str,
    execution_id: str,
    lease_token: str,
    lease_seconds: int = 300,
    request_id: str | None = None,
) -> dict:
    """Renew a running execution lease; renewal rotates its fencing token."""
    body = {"execution_id": execution_id, "lease_token": lease_token, "lease_seconds": lease_seconds}
    return await _request("POST", f"/api/tasks/{task_id}/renew", body=body, request_id=request_id)


@mcp.tool()
async def report_progress(
    task_id: str,
    execution_id: str,
    lease_token: str,
    progress: int,
    summary: str | None = None,
    cost_usd: float | None = None,
    request_id: str | None = None,
) -> dict:
    """Report progress only while holding the current execution lease."""
    body = {
        "execution_id": execution_id,
        "lease_token": lease_token,
        "progress": progress,
        "summary": summary,
        "cost_usd": cost_usd,
    }
    return await _request("POST", f"/api/tasks/{task_id}/progress", body=body, request_id=request_id)


@mcp.tool()
async def get_task_context(task_id: str) -> dict:
    """Read task specification, executions, evidence, messages, audit, and dependencies."""
    return await _request("GET", f"/api/tasks/{task_id}/context")


@mcp.tool()
async def block_task(
    task_id: str,
    execution_id: str,
    lease_token: str,
    reason: str,
    handoff: str | None = None,
    request_id: str | None = None,
) -> dict:
    """Block a task and close the current execution lease."""
    body = {"execution_id": execution_id, "lease_token": lease_token, "reason": reason, "handoff": handoff}
    return await _request("POST", f"/api/tasks/{task_id}/block", body=body, request_id=request_id)


@mcp.tool()
async def release_task(
    task_id: str,
    execution_id: str,
    lease_token: str,
    handoff: str,
    request_id: str | None = None,
) -> dict:
    """Return a task to ready and record a handoff."""
    body = {"execution_id": execution_id, "lease_token": lease_token, "handoff": handoff}
    return await _request("POST", f"/api/tasks/{task_id}/release", body=body, request_id=request_id)


@mcp.tool()
async def submit_result(
    task_id: str,
    execution_id: str,
    lease_token: str,
    summary: str,
    artifacts: list[ArtifactInput],
    cost_usd: float = 0,
    request_id: str | None = None,
) -> dict:
    """Submit a result with at least one evidence artifact for independent review."""
    body = {
        "execution_id": execution_id,
        "lease_token": lease_token,
        "summary": summary,
        "artifacts": [item.model_dump() for item in artifacts],
        "cost_usd": cost_usd,
    }
    return await _request("POST", f"/api/tasks/{task_id}/submit", body=body, request_id=request_id)


@mcp.tool()
async def review_result(task_id: str, decision: str, comment: str, request_id: str | None = None) -> dict:
    """Accept or reject submitted evidence as an independent reviewer."""
    return await _request(
        "POST", f"/api/tasks/{task_id}/review", body={"decision": decision, "comment": comment}, request_id=request_id
    )


@mcp.tool()
async def find_agents(project_id: str | None = None) -> list[dict]:
    """Find agents whose project access overlaps this credential's scope."""
    params = {"project_id": project_id} if project_id else None
    return await _request("GET", "/api/agents", params=params)


@mcp.tool()
async def request_help(
    project_id: str,
    task_id: str,
    recipient_id: str,
    body: str,
    request_id: str | None = None,
) -> dict:
    """Send a scoped help request to an agent or principal."""
    message = {
        "project_id": project_id,
        "task_id": task_id,
        "recipient_id": recipient_id,
        "kind": "help_request",
        "body": body,
    }
    return await _request("POST", "/api/messages", body=message, request_id=request_id)


@mcp.tool()
async def send_message(
    project_id: str,
    body: str,
    task_id: str | None = None,
    recipient_id: str | None = None,
    kind: str = "question",
    reply_to_id: str | None = None,
    request_id: str | None = None,
) -> dict:
    """Send or reply to a project message."""
    message = {
        "project_id": project_id,
        "task_id": task_id,
        "recipient_id": recipient_id,
        "kind": kind,
        "body": body,
        "reply_to_id": reply_to_id,
    }
    return await _request("POST", "/api/messages", body=message, request_id=request_id)


@mcp.tool()
async def read_inbox(project_id: str | None = None, task_id: str | None = None) -> list[dict]:
    """Read messages addressed to the configured agent principal."""
    params: dict[str, Any] = {"inbox": "true"}
    if project_id:
        params["project_id"] = project_id
    if task_id:
        params["task_id"] = task_id
    return await _request("GET", "/api/messages", params=params)


@mcp.tool()
async def delegate_task(
    task_id: str,
    title: str,
    goal: str,
    acceptance_criteria: list[str],
    agent_id: str | None = None,
    description: str = "",
    inputs: str = "",
    scope: str = "",
    constraints: str = "",
    priority: str = "medium",
    budget_usd: float = 0,
    request_id: str | None = None,
    assignee_principal_id: str | None = None,
) -> dict:
    """Delegate a child task to exactly one scoped coworker or worker agent."""
    body = {
        "agent_id": agent_id,
        "assignee_principal_id": assignee_principal_id,
        "title": title,
        "goal": goal,
        "acceptance_criteria": acceptance_criteria,
        "description": description,
        "inputs": inputs,
        "scope": scope,
        "constraints": constraints,
        "priority": priority,
        "budget_usd": budget_usd,
    }
    return await _request("POST", f"/api/tasks/{task_id}/delegate", body=body, request_id=request_id)


@mcp.tool()
async def list_runs(project_id: str | None = None, task_id: str | None = None, status: str | None = None) -> list[dict]:
    """List scoped durable runtime runs, optionally filtered by project, task, or status."""
    params = {key: value for key, value in {"project_id": project_id, "task_id": task_id, "status": status}.items() if value}
    return await _request("GET", "/api/runs", params=params or None)


@mcp.tool()
async def get_run(run_id: str) -> dict:
    """Read one scoped runtime run and its safe receipt."""
    return await _request("GET", f"/api/runs/{run_id}")


@mcp.tool()
async def get_run_events(run_id: str, after_sequence: int = 0) -> list[dict]:
    """Read ordered, sanitized events for a scoped runtime run."""
    return await _request("GET", f"/api/runs/{run_id}/events", params={"after_sequence": after_sequence})


@mcp.tool()
async def control_run(run_id: str, action: str, request_id: str | None = None) -> dict:
    """Request a manager-authorized pause, resume, stop, or retry for a run."""
    return await _request(
        "POST", f"/api/runs/{run_id}/control", body={"action": action}, request_id=request_id or str(uuid.uuid4())
    )


@mcp.tool()
async def list_agent_templates() -> list[dict]:
    """List immutable Agent template versions visible in the current organization scope."""
    return await _request("GET", "/api/agent-templates")


@mcp.tool()
async def list_workflows(project_id: str | None = None) -> list[dict]:
    """List versioned workflows visible to this credential."""
    params = {"project_id": project_id} if project_id else None
    return await _request("GET", "/api/workflows", params=params)


@mcp.tool()
async def start_workflow(workflow_id: str, inputs: str = "", request_id: str | None = None) -> dict:
    """Start one idempotent, manager-authorized workflow instance."""
    return await _request(
        "POST", f"/api/workflows/{workflow_id}/start", body={"inputs": inputs}, request_id=request_id or str(uuid.uuid4())
    )


@mcp.tool()
async def list_workflow_runs(project_id: str | None = None) -> list[dict]:
    """List workflow instances and their stable task/run links."""
    params = {"project_id": project_id} if project_id else None
    return await _request("GET", "/api/workflow-runs", params=params)


@mcp.tool()
async def get_workflow_run(instance_id: str) -> dict:
    """Read one scoped workflow instance and step state."""
    return await _request("GET", f"/api/workflow-runs/{instance_id}")


@mcp.tool()
async def list_tool_connections(project_id: str | None = None) -> list[dict]:
    """List safe metadata for MCP tool connections visible to this project scope."""
    params = {"project_id": project_id} if project_id else None
    return await _request("GET", "/api/tool-connections", params=params)


@mcp.tool()
async def list_sandbox_profiles(project_id: str | None = None) -> list[dict]:
    """List bounded sandbox profiles visible to this project scope."""
    params = {"project_id": project_id} if project_id else None
    return await _request("GET", "/api/sandbox-profiles", params=params)


@mcp.tool()
async def set_member_capacity(project_id: str, principal_id: str, weekly_minutes: int, request_id: str | None = None) -> dict:
    """Configure an explicitly agreed weekly capacity. No LLM or inferred availability."""
    return await _request("POST", f"/api/projects/{project_id}/capacity", body={"principal_id": principal_id, "weekly_minutes": weekly_minutes}, request_id=request_id or str(uuid.uuid4()))


@mcp.resource("ordivant://projects/{project_id}/context")
async def project_context_resource(project_id: str) -> str:
    result = await get_project_context(project_id)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.resource("ordivant://tasks/{task_id}/context")
async def task_context_resource(task_id: str) -> str:
    result = await get_task_context(task_id)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.prompt()
def work_task_prompt(task_id: str) -> str:
    uri = f"ordivant://tasks/{task_id}/context"
    return (
        f"Read the Ordivant task context at {uri}. "
        "Check its scope, dependencies, acceptance criteria, and evidence requirements. "
        "Claim it before work, report progress with the current lease, and submit evidence for review."
    )


@mcp.prompt()
def review_task_prompt(task_id: str) -> str:
    uri = f"ordivant://tasks/{task_id}/context"
    return (
        f"Review task {task_id} using {uri}. "
        "Compare submitted artifacts with the acceptance criteria. The submitting actor must not approve their own work. "
        "Use review_result to accept or reject with a concise evidence-based comment."
    )


from .collaboration_mcp import install_tools as install_collaboration_tools

install_collaboration_tools(mcp, _request)


if __name__ == "__main__":
    mcp.run(transport="stdio")
