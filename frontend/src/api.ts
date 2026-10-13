import { t } from './i18n';
import { describeApiError } from './i18n/errors';
import type {
  Agent,
  AgentTemplate,
  AgentTemplateCreateInput,
  AgentTemplateVersionInput,
  AuditEvent,
  ClaimedExecution,
  Message,
  ModelCatalog,
  ModelSettings,
  ModelSettingsUpdate,
  Overview,
  Principal,
  Project,
  ProjectContext,
  ProjectParticipant,
  Run,
  RunEvent,
  SandboxProfile,
  SandboxProfileMutationInput,
  Task,
  TaskContext,
  ToolConnection,
  ToolConnectionMutationInput,
  ToolConnectionTestResult,
  Workflow,
  WorkflowCreateInput,
  WorkflowInstance,
  WorkflowVersionInput,
} from './types';
import { announceAuthExpired, authRequestOptions } from './auth/client';

let accessToken: string | null = null;
const workApiPrefix = import.meta.env.VITE_WORK_API_PREFIX || '/api';

function apiPath(path: string): string {
  return path.startsWith('/api/') ? `${workApiPrefix}${path.slice(4)}` : path;
}

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(status: number, message: string, code?: string, public sourceMessage = message) {
    super(t(message));
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

function requestId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function createIdempotencyKey(): string {
  return requestId();
}

export function isDefinitiveClientError(error: unknown): boolean {
  return error instanceof ApiError && error.status >= 400 && error.status < 500;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has('Content-Type') && init.body) headers.set('Content-Type', 'application/json');
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  if (init.method && init.method !== 'GET' && path !== '/api/model-settings' && !headers.has('Idempotency-Key')) {
    headers.set('Idempotency-Key', requestId());
  }

  let response: Response;
  try {
    response = await fetch(apiPath(path), authRequestOptions({ ...init, headers }));
  } catch {
    throw new ApiError(0, '無法連線至 Ordivant API，請確認本機服務已啟動。');
  }

  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get('content-type') ?? '';
  let payload: unknown;
  try {
    payload = contentType.includes('application/json') ? await response.json() : await response.text();
  } catch {
    if (response.ok) throw new ApiError(response.status, 'Ordivant API 回應格式無法解析。');
    payload = null;
  }
  if (!response.ok) {
    const { message, code, sourceMessage } = describeApiError(payload, response.status);
    if (response.status === 401) {
      const usedBearerToken = Boolean(accessToken);
      accessToken = null;
      if (!usedBearerToken) announceAuthExpired();
    }
    throw new ApiError(response.status, message, code, sourceMessage);
  }
  return payload as T;
}

export const api = {
  setToken(token: string | null) {
    accessToken = token;
  },
  get<T>(path: string) {
    return request<T>(path, { method: 'GET' });
  },
  post<T>(path: string, body: unknown) {
    return request<T>(path, { method: 'POST', body: JSON.stringify(body) });
  },
  patch<T>(path: string, body: unknown) {
    return request<T>(path, { method: 'PATCH', body: JSON.stringify(body) });
  },
  me: () => request<Principal>('/api/me', { method: 'GET' }),
  projects: () => request<Project[]>('/api/projects', { method: 'GET' }),
  projectContext: (id: string) => request<ProjectContext>(`/api/projects/${encodeURIComponent(id)}/context`, { method: 'GET' }),
  participants: (projectId: string) => request<ProjectParticipant[]>(`/api/projects/${encodeURIComponent(projectId)}/participants`, { method: 'GET' }),
  overview: (projectId: string) => request<Overview>(`/api/overview?project_id=${encodeURIComponent(projectId)}`, { method: 'GET' }),
  tasks: (projectId: string, status: string, query: string) => {
    const params = new URLSearchParams({ project_id: projectId });
    if (status) params.set('status', status);
    if (query.trim()) params.set('q', query.trim());
    return request<Task[]>(`/api/tasks?${params.toString()}`, { method: 'GET' });
  },
  taskContext: (id: string) => request<TaskContext>(`/api/tasks/${encodeURIComponent(id)}/context`, { method: 'GET' }),
  taskExecutions: (id: string) => request<import('./types').Execution[]>(`/api/tasks/${encodeURIComponent(id)}/executions`, { method: 'GET' }),
  dispatchTask: (id: string, body: { agent_id: string }, idempotencyKey?: string) => request<Record<string, unknown>>(`/api/tasks/${encodeURIComponent(id)}/dispatch`, {
    method: 'POST',
    body: JSON.stringify(body),
    ...(idempotencyKey ? { headers: { 'Idempotency-Key': idempotencyKey } } : {}),
  }),
  agents: () => request<Agent[]>('/api/agents', { method: 'GET' }),
  agentTemplates: () => request<AgentTemplate[]>('/api/agent-templates', { method: 'GET' }),
  createAgentTemplate: (body: AgentTemplateCreateInput) => request<AgentTemplate>('/api/agent-templates', { method: 'POST', body: JSON.stringify(body) }),
  publishAgentTemplateVersion: (id: string, body: AgentTemplateVersionInput) => request<AgentTemplate>(`/api/agent-templates/${encodeURIComponent(id)}/versions`, { method: 'POST', body: JSON.stringify(body) }),
  runs: (projectId: string, filters: { task_id?: string; status?: string } = {}) => {
    const params = new URLSearchParams({ project_id: projectId });
    if (filters.task_id) params.set('task_id', filters.task_id);
    if (filters.status) params.set('status', filters.status);
    return request<Run[]>(`/api/runs?${params.toString()}`, { method: 'GET' });
  },
  run: (id: string) => request<Run>(`/api/runs/${encodeURIComponent(id)}`, { method: 'GET' }),
  runEvents: (id: string, afterSequence = 0) => request<RunEvent[]>(`/api/runs/${encodeURIComponent(id)}/events?after_sequence=${afterSequence}`, { method: 'GET' }),
  controlRun: (id: string, action: 'pause' | 'resume' | 'stop' | 'retry', idempotencyKey?: string) => request<Run>(`/api/runs/${encodeURIComponent(id)}/control`, {
    method: 'POST',
    body: JSON.stringify({ action }),
    ...(idempotencyKey ? { headers: { 'Idempotency-Key': idempotencyKey } } : {}),
  }),
  workflows: (projectId: string) => request<Workflow[]>(`/api/workflows?project_id=${encodeURIComponent(projectId)}`, { method: 'GET' }),
  createWorkflow: (body: WorkflowCreateInput) => request<Workflow>('/api/workflows', { method: 'POST', body: JSON.stringify(body) }),
  publishWorkflowVersion: (id: string, body: WorkflowVersionInput) => request<Workflow>(`/api/workflows/${encodeURIComponent(id)}/versions`, { method: 'POST', body: JSON.stringify(body) }),
  saveWorkflowSchedule: (id: string, body: { enabled: boolean; interval_minutes: number; max_runs: number }) => request<Workflow>(`/api/workflows/${encodeURIComponent(id)}/schedule`, { method: 'PATCH', body: JSON.stringify(body) }),
  startWorkflow: (id: string, body: { inputs?: string }, idempotencyKey?: string) => request<WorkflowInstance>(`/api/workflows/${encodeURIComponent(id)}/start`, {
    method: 'POST',
    body: JSON.stringify(body),
    ...(idempotencyKey ? { headers: { 'Idempotency-Key': idempotencyKey } } : {}),
  }),
  workflowRuns: (projectId: string) => request<WorkflowInstance[]>(`/api/workflow-runs?project_id=${encodeURIComponent(projectId)}`, { method: 'GET' }),
  workflowRun: (id: string) => request<WorkflowInstance>(`/api/workflow-runs/${encodeURIComponent(id)}`, { method: 'GET' }),
  cancelWorkflowRun: (id: string) => request<WorkflowInstance>(`/api/workflow-runs/${encodeURIComponent(id)}/cancel`, { method: 'POST', body: JSON.stringify({}) }),
  toolConnections: (projectId: string) => request<ToolConnection[]>(`/api/tool-connections?project_id=${encodeURIComponent(projectId)}`, { method: 'GET' }),
  createToolConnection: (body: ToolConnectionMutationInput) => request<ToolConnection>('/api/tool-connections', { method: 'POST', body: JSON.stringify(body) }),
  updateToolConnection: (id: string, body: ToolConnectionMutationInput) => request<ToolConnection>(`/api/tool-connections/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) }),
  testToolConnection: (id: string) => request<ToolConnectionTestResult>(`/api/tool-connections/${encodeURIComponent(id)}/test`, { method: 'POST', body: JSON.stringify({}) }),
  sandboxProfiles: (projectId: string) => request<SandboxProfile[]>(`/api/sandbox-profiles?project_id=${encodeURIComponent(projectId)}`, { method: 'GET' }),
  createSandboxProfile: (body: SandboxProfileMutationInput) => request<SandboxProfile>('/api/sandbox-profiles', { method: 'POST', body: JSON.stringify(body) }),
  updateSandboxProfile: (id: string, body: SandboxProfileMutationInput) => request<SandboxProfile>(`/api/sandbox-profiles/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) }),
  modelSettings: () => request<ModelSettings>('/api/model-settings', { method: 'GET' }),
  saveModelSettings: (body: ModelSettingsUpdate) => request<void>('/api/model-settings', { method: 'PUT', body: JSON.stringify(body) }),
  modelCatalog: () => request<ModelCatalog>('/api/model-catalog', { method: 'GET' }),
  messages: (projectId: string, inbox = false) => {
    const params = new URLSearchParams({ project_id: projectId });
    if (inbox) params.set('inbox', 'true');
    return request<Message[]>(`/api/messages?${params.toString()}`, { method: 'GET' });
  },
  events: (projectId: string) => request<AuditEvent[]>(`/api/events?project_id=${encodeURIComponent(projectId)}`, { method: 'GET' }),
  claim: (taskId: string, body: { agent_id?: string }) => request<ClaimedExecution>(`/api/tasks/${encodeURIComponent(taskId)}/claim`, { method: 'POST', body: JSON.stringify(body) }),
};
