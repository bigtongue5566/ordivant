from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreate(InputModel):
    key: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    team_id: str | None = None
    budget_usd: float = Field(default=0, ge=0)


class ProjectSettingsSnapshot(InputModel):
    name: str
    description: str
    budget_usd: float = Field(ge=0, allow_inf_nan=False)


class ProjectPatch(InputModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=20000)
    budget_usd: float = Field(ge=0, allow_inf_nan=False)
    expected: ProjectSettingsSnapshot

    @model_validator(mode="after")
    def clean_project_name(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("name is required")
        return self


class TaskCreate(InputModel):
    project_id: str
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    goal: str = ""
    inputs: str = ""
    scope: str = ""
    constraints: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    priority: Literal["urgent", "high", "medium", "low"] = "medium"
    status: Literal["backlog", "ready"] = "ready"
    assignee_id: str | None = None
    assignee_principal_id: str | None = None
    reviewer_id: str | None = None
    reviewer_principal_id: str | None = None
    parent_task_id: str | None = None
    dependency_ids: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    handoff: str | None = None
    budget_usd: float = Field(default=0, ge=0)
    work_type: Literal["task", "story", "bug", "epic"] = "task"
    epic_id: str | None = None
    due_at: datetime | None = None
    start_at: datetime | None = None
    sprint_id: str | None = None
    milestone_id: str | None = None
    estimate_points: float | None = Field(default=None, ge=0, le=1000000)
    rank: float = Field(default=0, ge=-1000000000000, le=1000000000000)
    stage_id: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=100)


class TaskPatch(InputModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    goal: str | None = None
    inputs: str | None = None
    scope: str | None = None
    constraints: str | None = None
    acceptance_criteria: list[str] | None = None
    priority: Literal["urgent", "high", "medium", "low"] | None = None
    status: Literal["backlog", "ready", "cancelled"] | None = None
    assignee_id: str | None = None
    assignee_principal_id: str | None = None
    reviewer_id: str | None = None
    reviewer_principal_id: str | None = None
    dependency_ids: list[str] | None = None
    labels: list[str] | None = None
    budget_usd: float | None = Field(default=None, ge=0)
    work_type: Literal["task", "story", "bug", "epic"] | None = None
    epic_id: str | None = None
    due_at: datetime | None = None
    start_at: datetime | None = None
    sprint_id: str | None = None
    milestone_id: str | None = None
    estimate_points: float | None = Field(default=None, ge=0, le=1000000)
    rank: float | None = Field(default=None, ge=-1000000000000, le=1000000000000)
    stage_id: str | None = None
    custom_fields: dict[str, Any] | None = Field(default=None, max_length=100)


class SprintCreate(InputModel):
    name: str = Field(min_length=1, max_length=200)
    goal: str = Field(default="", max_length=4000)
    start_at: datetime | None = None
    end_at: datetime | None = None
    status: Literal["planned", "active", "closed"] = "planned"


class SprintPatch(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    goal: str | None = Field(default=None, max_length=4000)
    start_at: datetime | None = None
    end_at: datetime | None = None
    status: Literal["planned", "active", "closed"] | None = None


class MilestoneCreate(InputModel):
    name: str = Field(min_length=1, max_length=200)
    due_at: datetime | None = None
    description: str = Field(default="", max_length=4000)
    status: Literal["open", "closed"] = "open"


class MilestonePatch(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    due_at: datetime | None = None
    description: str | None = Field(default=None, max_length=4000)
    status: Literal["open", "closed"] | None = None


class ProjectFieldCreate(InputModel):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["text", "number", "boolean", "select"]
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=100)
    active: bool = True


class ProjectFieldPatch(InputModel):
    key: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    kind: Literal["text", "number", "boolean", "select"] | None = None
    required: bool | None = None
    options: list[str] | None = Field(default=None, max_length=100)
    active: bool | None = None


class ProjectStageCreate(InputModel):
    name: str = Field(min_length=1, max_length=200)
    category: Literal["backlog", "ready", "in_progress", "blocked", "in_review", "done", "cancelled"]
    rank: float = Field(default=0, ge=-1000000000000, le=1000000000000)
    active: bool = True


class ProjectStagePatch(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: Literal["backlog", "ready", "in_progress", "blocked", "in_review", "done", "cancelled"] | None = None
    rank: float | None = Field(default=None, ge=-1000000000000, le=1000000000000)
    active: bool | None = None


class ProjectRuleCreate(InputModel):
    name: str = Field(min_length=1, max_length=200)
    event: Literal["task.created", "task.updated"]
    conditions: dict[str, Any] = Field(default_factory=dict, max_length=4)
    action: Literal["label", "assign", "ready"]
    parameters: dict[str, Any] = Field(default_factory=dict, max_length=2)
    enabled: bool = True


class ProjectRulePatch(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    event: Literal["task.created", "task.updated"] | None = None
    conditions: dict[str, Any] | None = Field(default=None, max_length=4)
    action: Literal["label", "assign", "ready"] | None = None
    parameters: dict[str, Any] | None = Field(default=None, max_length=2)
    enabled: bool | None = None


class IntakeFormCreate(InputModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    work_type: Literal["task", "story", "bug", "epic"] = "task"
    fields: list[str] = Field(default_factory=list, max_length=100)
    active: bool = True


class IntakeFormPatch(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    work_type: Literal["task", "story", "bug", "epic"] | None = None
    fields: list[str] | None = Field(default=None, max_length=100)
    active: bool | None = None


class IntakeSubmit(InputModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20000)
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=100)


class ReorderTasks(InputModel):
    task_ids: list[str] = Field(min_length=1, max_length=1000)


class WorklogCreate(InputModel):
    minutes: int = Field(ge=1, le=1000000)
    started_at: datetime
    description: str = Field(default="", max_length=4000)


class TaskImport(InputModel):
    csv: str = Field(min_length=1, max_length=2_000_000)


class SavedQueryCreate(InputModel):
    name: str = Field(min_length=1, max_length=200)
    project_id: str
    filters: dict[str, Any] = Field(default_factory=dict, max_length=50)


class ClaimRequest(InputModel):
    lease_seconds: int = Field(default=300, ge=30, le=3600)
    agent_id: str | None = None


class LeaseRequest(InputModel):
    execution_id: str
    lease_token: str | None = Field(default=None, min_length=24, max_length=200)
    lease_seconds: int = Field(default=300, ge=30, le=3600)


class ProgressRequest(InputModel):
    execution_id: str
    lease_token: str | None = Field(default=None, min_length=24, max_length=200)
    progress: int = Field(ge=0, le=100)
    summary: str | None = None
    cost_usd: float | None = Field(default=None, ge=0)


class BlockRequest(InputModel):
    execution_id: str
    lease_token: str | None = Field(default=None, min_length=24, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)
    handoff: str | None = None


class ReleaseRequest(InputModel):
    execution_id: str
    lease_token: str | None = Field(default=None, min_length=24, max_length=200)
    handoff: str = Field(min_length=1, max_length=4000)


class ArtifactInput(InputModel):
    kind: Literal["document", "url", "test_report", "file", "summary"]
    title: str = Field(min_length=1, max_length=300)
    uri: str | None = None
    content: str | None = None

    @model_validator(mode="after")
    def require_evidence_location(self):
        if not self.uri and not self.content:
            raise ValueError("artifact requires uri or content")
        return self


class SubmitRequest(InputModel):
    execution_id: str
    lease_token: str | None = Field(default=None, min_length=24, max_length=200)
    summary: str = Field(min_length=1, max_length=10000)
    artifacts: list[ArtifactInput] = Field(min_length=1)
    cost_usd: float = Field(default=0, ge=0)


class ReviewRequest(InputModel):
    decision: Literal["accept", "reject"]
    comment: str = Field(min_length=1, max_length=10000)


class DelegateRequest(InputModel):
    agent_id: str | None = None
    assignee_principal_id: str | None = None
    title: str = Field(min_length=1, max_length=300)
    goal: str = Field(min_length=1)
    description: str = ""
    inputs: str = ""
    scope: str = ""
    constraints: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    priority: Literal["urgent", "high", "medium", "low"] = "medium"
    budget_usd: float = Field(default=0, ge=0)


class ModelDefinition(InputModel):
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    context_window: int = Field(ge=1)
    max_output_tokens: int = Field(ge=16)
    reasoning_efforts: list[Literal["low", "medium", "high", "xhigh", "max"]] = Field(default_factory=list)


class ModelSelection(InputModel):
    provider_id: str = Field(min_length=1, max_length=120)
    model_id: str = Field(min_length=1, max_length=200)
    reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"]
    max_output_tokens: int = Field(default=4096, ge=16)


class AgentCreate(InputModel):
    name: str = Field(min_length=1, max_length=200)
    role: Literal["worker", "reviewer"] | None = None
    team_id: str | None = None
    capabilities: list[str] | None = None
    project_ids: list[str] = Field(min_length=1)
    runtime: Literal["external", "pi"] = "external"
    model: str | None = None
    model_selection: ModelSelection | None = Field(default=None, alias="model_config")
    execution_config: ExecutionConfig | None = None
    template_id: str | None = None


class AgentPatch(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: Literal["worker", "reviewer"] | None = None
    capabilities: list[str] | None = None
    status: Literal["available", "offline", "disabled"] | None = None
    runtime: Literal["external", "pi"] | None = None
    model: str | None = None
    model_selection: ModelSelection | None = Field(default=None, alias="model_config")
    execution_config: ExecutionConfig | None = None
    template_id: str | None = None


class ModelProviderInput(InputModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    base_url: str = Field(min_length=1, max_length=2000)
    api_key: SecretStr | None = None
    enabled: bool
    models: list[ModelDefinition] = Field(default_factory=list)


class ModelDiscoveryRequest(InputModel):
    id: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=2000)
    api_key: SecretStr | None = None


class ModelSettingsPut(InputModel):
    revision: int | None = Field(default=None, ge=0)
    providers: list[ModelProviderInput]
    default: ModelSelection | None


class RuntimeDeliveryRequest(InputModel):
    worker_id: str = Field(min_length=1, max_length=200)
    delivery_token: str = Field(min_length=24, max_length=200)


class MessageCreate(InputModel):
    project_id: str
    task_id: str | None = None
    recipient_id: str | None = None
    kind: Literal["question", "reply", "help_request", "decision", "handoff"]
    body: str = Field(min_length=1, max_length=20000)
    reply_to_id: str | None = None


class MessageAck(InputModel):
    status: Literal["accepted", "completed"]


class DispatchRequest(InputModel):
    agent_id: str


class OutboxClaimRequest(InputModel):
    worker_id: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=20)


class OutboxAckRequest(InputModel):
    worker_id: str = Field(min_length=1, max_length=200)
    delivery_token: str = Field(min_length=24, max_length=200)
    status: Literal["delivered", "failed"]
    error: str | None = Field(default=None, max_length=4000)


class ExecutionLimits(InputModel):
    max_turns: int = Field(default=20, ge=1, le=100)
    timeout_seconds: int = Field(default=600, ge=30, le=3600)


class ExecutionConfig(InputModel):
    instructions: str = Field(default="", max_length=16000)
    tool_connection_ids: list[str] = Field(default_factory=list, max_length=30)
    sandbox_profile_id: str | None = None
    limits: ExecutionLimits = Field(default_factory=ExecutionLimits)

    @model_validator(mode="after")
    def unique_connections(self):
        if len(self.tool_connection_ids) != len(set(self.tool_connection_ids)):
            raise ValueError("tool_connection_ids must be unique")
        return self


class AgentTemplateDefinition(InputModel):
    role: Literal["worker", "reviewer"]
    capabilities: list[str] = Field(default_factory=list, max_length=100)
    instructions: str = Field(default="", max_length=16000)
    model_selection: ModelSelection | None = Field(default=None, alias="model_config")
    tool_connection_ids: list[str] = Field(default_factory=list, max_length=30)
    sandbox_profile_id: str | None = None
    limits: ExecutionLimits = Field(default_factory=ExecutionLimits)

    @model_validator(mode="after")
    def unique_connections(self):
        if len(self.tool_connection_ids) != len(set(self.tool_connection_ids)):
            raise ValueError("tool_connection_ids must be unique")
        return self


class AgentTemplateCreate(InputModel):
    key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    definition: AgentTemplateDefinition


class AgentTemplateVersionCreate(InputModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    definition: AgentTemplateDefinition


class WorkflowStepInput(InputModel):
    key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    title: str = Field(min_length=1, max_length=300)
    goal: str = Field(min_length=1, max_length=10000)
    description: str = Field(default="", max_length=10000)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=100)
    dependency_keys: list[str] = Field(default_factory=list, max_length=20)
    agent_id: str | None = None
    capabilities: list[str] = Field(default_factory=list, max_length=100)
    reviewer_id: str | None = None
    priority: Literal["urgent", "high", "medium", "low"] = "medium"

    @model_validator(mode="after")
    def unique_dependencies(self):
        if len(self.dependency_keys) != len(set(self.dependency_keys)):
            raise ValueError("dependency_keys must be unique")
        return self


class WorkflowScheduleInput(InputModel):
    enabled: bool = False
    interval_minutes: int = Field(default=60, ge=1, le=525600)
    max_runs: int = Field(default=1, ge=1, le=1000)


class WorkflowCreate(InputModel):
    project_id: str
    key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    steps: list[WorkflowStepInput] = Field(min_length=1, max_length=20)
    schedule: WorkflowScheduleInput = Field(default_factory=WorkflowScheduleInput)


class WorkflowVersionCreate(InputModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    steps: list[WorkflowStepInput] = Field(min_length=1, max_length=20)


class WorkflowScheduleUpdate(InputModel):
    enabled: bool
    interval_minutes: int = Field(ge=1, le=525600)
    max_runs: int = Field(ge=1, le=1000)


class WorkflowStart(InputModel):
    inputs: str = Field(default="", max_length=20000)


class EmptyRequest(InputModel):
    pass


class RunControlRequest(InputModel):
    action: Literal["pause", "resume", "stop", "retry"]


class RunSyncEvent(InputModel):
    kind: Literal["start", "model", "tool_start", "tool_end", "error", "control", "status", "sandbox"]
    data: dict = Field(default_factory=dict)


class RunSyncRequest(InputModel):
    worker_id: str = Field(min_length=1, max_length=200)
    delivery_token: str = Field(min_length=24, max_length=200)
    sequence: int = Field(ge=1)
    status: Literal["queued", "running", "paused", "done", "failed", "aborted"]
    execution_id: str | None = None
    mode: Literal["demo", "live"] | None = None
    receipt: dict | None = None
    answer: str | None = Field(default=None, max_length=100000)
    error: str | None = Field(default=None, max_length=4000)
    events: list[RunSyncEvent] = Field(default_factory=list, max_length=100)
    sandbox: dict | None = None


class ToolConnectionCreate(InputModel):
    project_id: str | None = None
    name: str = Field(min_length=1, max_length=200)
    endpoint: str = Field(min_length=1, max_length=2000)
    enabled: bool = True
    allowed_tools: list[str] = Field(default_factory=list, max_length=100)
    auth_token: SecretStr | None = None


class ToolConnectionPatch(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    endpoint: str | None = Field(default=None, min_length=1, max_length=2000)
    enabled: bool | None = None
    allowed_tools: list[str] | None = Field(default=None, max_length=100)
    auth_token: SecretStr | None = None


class SandboxLimits(InputModel):
    timeout_seconds: int = Field(default=120, ge=1, le=120)
    memory_mb: int = Field(default=512, ge=64, le=1024)
    cpu_count: float = Field(default=1.0, ge=0.25, le=2.0)
    pids_limit: int = Field(default=64, ge=16, le=128)
    output_bytes: int = Field(default=16384, ge=1024, le=65536)
    workspace_mb: int = Field(default=32, ge=1, le=128)


class SandboxProfileCreate(InputModel):
    project_id: str
    name: str = Field(min_length=1, max_length=200)
    enabled: bool = True
    limits: SandboxLimits = Field(default_factory=SandboxLimits)


class SandboxProfilePatch(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None
    limits: SandboxLimits | None = None


class CapacityWrite(InputModel):
    principal_id: str = Field(min_length=1, max_length=36)
    weekly_minutes: int = Field(ge=0, le=10080)


AgentCreate.model_rebuild()
AgentPatch.model_rebuild()
