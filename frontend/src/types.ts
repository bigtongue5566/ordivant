export type Principal = {
  id: string;
  name: string;
  kind: 'human' | 'agent' | 'runtime';
  role: 'admin' | 'manager' | 'worker' | 'reviewer';
  organization_id: string;
  project_ids: string[];
};

export type Project = {
  id: string;
  key: string;
  name: string;
  description: string;
  organization_id: string;
  team_id: string | null;
  budget_usd: number;
  created_at: string;
};

export type Agent = {
  id: string;
  principal_id: string;
  name: string;
  role: 'worker' | 'reviewer';
  team_id: string | null;
  capabilities: string[];
  project_ids: string[];
  status: 'available' | 'busy' | 'offline' | 'disabled';
  runtime: 'external' | 'pi';
  model: string | null;
  model_config?: ModelSelection | null;
  effective_model_config?: ModelSelection | null;
  execution_config: ExecutionConfig;
  template_id: string | null;
  created_at: string;
};

export type ProjectParticipant = {
  id: string;
  principal_id: string;
  name: string;
  kind: 'human' | 'agent';
  role: 'admin' | 'manager' | 'worker' | 'reviewer';
};

export type TaskAssignment = {
  id: string;
  principal_id: string;
  name: string;
  kind: 'human' | 'agent';
};

export type ReasoningEffort = 'low' | 'medium' | 'high' | 'xhigh' | 'max';

export type ModelDefinition = {
  id: string;
  name: string;
  context_window: number;
  max_output_tokens: number;
  reasoning_efforts: ReasoningEffort[];
};

export type ModelProvider = {
  id: string;
  name: string;
  base_url: string;
  enabled: boolean;
  key_configured: boolean;
  models: ModelDefinition[];
};

export type ModelSelection = {
  provider_id: string;
  model_id: string;
  reasoning_effort: ReasoningEffort;
  max_output_tokens: number;
};

export type ModelCatalog = {
  providers: ModelProvider[];
  default: ModelSelection | null;
};

export type ModelSettings = ModelCatalog & {
  revision?: number;
};

export type ModelProviderInput = Pick<ModelProvider, 'id' | 'name' | 'base_url' | 'enabled' | 'models'> & {
  api_key?: string;
};

export type DiscoveredModel = Pick<ModelDefinition, 'id' | 'name'> & Partial<Omit<ModelDefinition, 'id' | 'name'>>;

export type ModelDiscoveryResult = {
  models: DiscoveredModel[];
  source: 'provider_api';
};

export type ModelSettingsUpdate = {
  revision: number;
  providers: ModelProviderInput[];
  default: ModelSelection | null;
};

export type TaskStatus = 'backlog' | 'ready' | 'in_progress' | 'blocked' | 'in_review' | 'done' | 'cancelled' | string;
export type Priority = 'urgent' | 'high' | 'medium' | 'low';

export type Task = {
  id: string;
  key: string;
  project_id: string;
  title: string;
  description: string;
  goal: string;
  inputs: string;
  scope: string;
  constraints: string;
  acceptance_criteria: string[];
  priority: Priority;
  status: TaskStatus;
  assignee_id: string | null;
  assignee_principal_id?: string | null;
  assignee?: TaskAssignment | null;
  reviewer_id: string | null;
  reviewer_principal_id?: string | null;
  reviewer?: TaskAssignment | null;
  parent_task_id: string | null;
  dependency_ids: string[];
  labels: string[];
  blocked_reason: string | null;
  progress: number;
  handoff: string | null;
  budget_usd: number;
  work_type?: 'task' | 'story' | 'bug' | 'epic';
  epic_id?: string | null;
  due_at?: string | null;
  start_at?: string | null;
  sprint_id?: string | null;
  milestone_id?: string | null;
  estimate_points?: number | null;
  rank?: number;
  stage_id?: string | null;
  custom_fields?: Record<string, string | number | boolean | null>;
  created_at: string;
  updated_at: string;
};

export type PlanningSprint = {
  id: string;
  project_id: string;
  name: string;
  goal: string;
  start_at: string | null;
  end_at: string | null;
  status: 'planned' | 'active' | 'closed';
};

export type PlanningMilestone = {
  id: string;
  project_id: string;
  name: string;
  due_at: string | null;
  description: string;
  status: 'open' | 'closed';
};

export type PlanningField = {
  id: string;
  project_id: string;
  key: string;
  name: string;
  kind: 'text' | 'number' | 'boolean' | 'select';
  required: boolean;
  options: string[];
  active: boolean;
};

export type PlanningStage = {
  id: string;
  project_id: string;
  name: string;
  category: TaskStatus;
  rank: number;
  active: boolean;
};

export type PlanningRule = {
  id: string;
  project_id: string;
  name: string;
  event: 'task.created' | 'task.updated';
  conditions: { work_type?: string; priority?: Priority; status?: TaskStatus; label?: string };
  action: 'label' | 'assign' | 'ready';
  parameters: { label?: string; assignee_principal_id?: string };
  enabled: boolean;
};

export type IntakeFormDefinition = {
  id: string;
  project_id: string;
  name: string;
  description: string;
  work_type: Task['work_type'];
  fields: string[];
  active: boolean;
};

export type PlanningMetadata = {
  sprints: PlanningSprint[];
  milestones: PlanningMilestone[];
  fields: PlanningField[];
  stages: PlanningStage[];
  rules: PlanningRule[];
  forms: IntakeFormDefinition[];
};

export type SavedTaskQuery = {
  id: string;
  name: string;
  project_id: string;
  filters: Record<string, string | boolean>;
};

export type TaskWorklog = {
  id: string;
  task_id: string;
  principal_id: string;
  minutes: number;
  started_at: string;
  description: string;
  created_at: string;
};

export type PlanningCapacityRow = {
  principal_id: string;
  name: string;
  kind: 'human' | 'agent';
  observed_minutes: number;
  weekly_minutes: number | null;
  observed_week_minutes: number;
  assigned_open_tasks: number;
  assigned_estimate_points: number;
  utilization_percent: number | null;
};

export type PlanningReports = {
  totals: {
    tasks: number;
    by_status: Record<string, number>;
    estimate_points: number;
  };
  cycle_time: {
    basis: string;
    samples: number;
    average_seconds: number | null;
    median_seconds: number | null;
  };
  capacity: PlanningCapacityRow[];
  week_start: string;
  worklogs: {
    entries: number;
    observed_minutes: number;
  };
};

export type Execution = {
  id: string;
  task_id: string;
  agent_id: string | null;
  executor_id?: string | null;
  executor_kind?: 'human' | 'agent' | 'runtime' | null;
  executor_name?: string | null;
  claimed_by_principal_id?: string | null;
  submitted_by_principal_id?: string | null;
  status: 'running' | 'submitted' | 'accepted' | 'rejected' | 'expired' | 'released';
  lease_expires_at: string | null;
  started_at: string;
  finished_at: string | null;
  progress: number;
  summary: string | null;
  cost_usd: number;
  cost_source: 'self_reported' | 'measured';
};

export type Artifact = {
  id: string;
  task_id: string;
  execution_id: string;
  kind: 'document' | 'url' | 'test_report' | 'file' | 'summary';
  title: string;
  uri: string | null;
  content: string | null;
  created_at: string;
};

export type Message = {
  id: string;
  project_id: string;
  task_id: string | null;
  sender_id: string;
  recipient_id: string | null;
  kind: 'question' | 'reply' | 'help_request' | 'decision' | 'handoff';
  body: string;
  reply_to_id: string | null;
  status: 'delivered' | 'accepted' | 'completed';
  created_at: string;
};

export type AuditEvent = {
  id: string;
  project_id: string | null;
  actor_id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  data: Record<string, unknown>;
  created_at: string;
};

export type TaskContext = {
  task: Task;
  executions: Execution[];
  artifacts: Artifact[];
  messages: Message[];
  events: AuditEvent[];
  dependencies: Task[];
};

export type ProjectContext = {
  project: Project;
  tasks: Task[];
  agents: Agent[];
  decisions: unknown[];
};

export type Overview = {
  counts: {
    total: number;
    ready: number;
    in_progress: number;
    blocked: number;
    in_review: number;
    done: number;
  };
  agents: { total: number; available: number; busy: number };
  cost_usd: number;
  budget_usd: number;
  activity: AuditEvent[];
};

export type ClaimedExecution = {
  task: Task;
  execution: Execution;
  lease_token: string | null;
};

export type ExecutionConfig = {
  instructions: string;
  tool_connection_ids: string[];
  sandbox_profile_id: string | null;
  limits: { max_turns: number; timeout_seconds: number };
};

export type AgentTemplateDefinition = {
  role: 'worker' | 'reviewer';
  capabilities: string[];
  instructions: string;
  model_config: ModelSelection | null;
  tool_connection_ids: string[];
  sandbox_profile_id: string | null;
  limits: { max_turns: number; timeout_seconds: number };
};

export type AgentTemplate = {
  id: string;
  builtin_key?: 'pm' | 'pg' | 'sa' | 'sd' | 'qa' | 'reviewer' | null;
  key: string;
  version: number;
  name: string;
  description: string;
  definition: AgentTemplateDefinition;
  created_at: string;
};

export type AgentTemplateCreateInput = {
  key: string;
  name: string;
  description?: string;
  definition: AgentTemplateDefinition;
};

export type AgentTemplateVersionInput = {
  name: string;
  description?: string;
  definition: AgentTemplateDefinition;
};

export type RunReceipt = {
  mode: 'demo' | 'live';
  requested: ModelSelection | null;
  returned: { provider_id: string; model_id: string } | null;
  usage: {
    input_tokens: number | null;
    uncached_input_tokens: number | null;
    cached_input_tokens: number | null;
    cache_write_tokens: number | null;
    output_tokens: number | null;
    total_tokens: number | null;
  } | null;
  tools: Array<{ name: string; calls: number }>;
  cost_usd: null;
};

export type Run = {
  id: string;
  project_id: string;
  task_id: string;
  agent_id: string;
  execution_id: string | null;
  status: 'queued' | 'running' | 'paused' | 'done' | 'failed' | 'aborted';
  desired_action: 'pause' | 'resume' | 'stop' | null;
  control_revision: number;
  retry_of: string | null;
  mode: 'demo' | 'live' | null;
  model_config: ModelSelection | null;
  receipt: RunReceipt | null;
  answer: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  sandbox: Record<string, unknown> | null;
};

export type RunEvent = {
  sequence: number;
  kind: string;
  created_at: string;
  data: Record<string, unknown>;
};

export type WorkflowStep = {
  key: string;
  title: string;
  goal: string;
  description: string;
  acceptance_criteria: string[];
  dependency_keys: string[];
  agent_id: string | null;
  capabilities: string[];
  reviewer_id: string | null;
  priority: Priority;
};

export type WorkflowSchedule = {
  enabled: boolean;
  interval_minutes: number;
  max_runs: number;
};

export type Workflow = {
  id: string;
  project_id: string;
  key: string;
  version: number;
  name: string;
  description: string;
  steps: WorkflowStep[];
  schedule: WorkflowSchedule;
  next_run_at: string | null;
  created_at: string;
};

export type WorkflowCreateInput = {
  project_id: string;
  key: string;
  name: string;
  description?: string;
  steps: WorkflowStep[];
  schedule?: WorkflowSchedule;
};

export type WorkflowVersionInput = {
  name: string;
  description?: string;
  steps: WorkflowStep[];
};

export type WorkflowInstance = {
  id: string;
  workflow_id: string;
  project_id: string;
  status: 'running' | 'waiting' | 'completed' | 'failed' | 'cancelled';
  trigger: 'manual' | 'schedule';
  inputs: string;
  steps: Array<{
    key: string;
    task_id: string;
    status: string;
    run_id: string | null;
    error: string | null;
  }>;
  created_at: string;
  updated_at: string;
};

export type ToolConnection = {
  id: string;
  project_id: string;
  name: string;
  endpoint: string;
  enabled: boolean;
  allowed_tools: string[];
  key_configured: boolean;
  created_at: string;
  updated_at: string;
};

export type ToolDefinition = {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
};

export type ToolConnectionTestResult = {
  ok: true;
  tools: ToolDefinition[];
} | {
  ok: false;
  [key: string]: unknown;
};

export type ToolConnectionMutationInput = {
  project_id?: string;
  name: string;
  endpoint: string;
  enabled: boolean;
  allowed_tools: string[];
  auth_token?: string;
};

export type SandboxLimits = {
  timeout_seconds: number;
  memory_mb: number;
  cpu_count: number;
  pids_limit: number;
  output_bytes: number;
  workspace_mb: number;
};

export type SandboxProfile = {
  id: string;
  project_id: string;
  name: string;
  enabled: boolean;
  limits: SandboxLimits;
  created_at: string;
  updated_at: string;
};

export type SandboxProfileMutationInput = {
  project_id?: string;
  name: string;
  enabled: boolean;
  limits: SandboxLimits;
};
