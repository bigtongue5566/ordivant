import type { LocalizedMessage } from './i18n';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Avatar,
  Button,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Progress,
  Select,
  Skeleton,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  AppstoreOutlined,
  AuditOutlined,
  BranchesOutlined,
  CheckOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseOutlined,
  CopyOutlined,
  CodeOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  FileSearchOutlined,
  InboxOutlined,
  LinkOutlined,
  LockOutlined,
  PlusOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SendOutlined,
  SettingOutlined,
  TeamOutlined,
  ToolOutlined,
  UnorderedListOutlined,
  UserAddOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { api, createIdempotencyKey, isDefinitiveClientError } from './api';
import { RunConsole } from './RunConsole';
import { Automation } from './Automation';
import { ToolSettings } from './ToolSettings';
import { PlanningWorkspace } from './components/planning/PlanningWorkspace';
import { ProjectCompanionsModal } from './components/ProjectCompanionsModal';
import { agentTemplateFormValues, localizeAgentTemplate } from './agents/templatePresets';
import { MarkdownContent } from './shared/MarkdownContent';
import './AgentExecution.css';
import { ProductSwitcher } from './products/shared/ProductSwitcher';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { AuthScreen } from './auth/AuthScreen';
import { AuthAccessDenied } from './auth/AuthAccessDenied';
import { AccountControl } from './auth/AccountSettings';
import { AgentModelConfigFields, ModelSettings } from './models/ModelSettings';
import { CollaborationPanel } from './products/shared/CollaborationPanel';
import { formatDate, formatNumber, t as translate, useI18n, useLocalizedForm, localized } from './i18n';
import type {
  Agent,
  AgentTemplate,
  Artifact,
  AuditEvent,
  ClaimedExecution,
  Execution,
  ExecutionConfig,
  Message as ProjectMessage,
  ModelCatalog,
  ModelSelection,
  Overview,
  Principal,
  Project,
  ProjectContext,
  ProjectParticipant,
  Task,
  TaskAssignment,
  TaskContext,
  TaskStatus,
} from './types';

const { Text, Title, Paragraph } = Typography;
const { TextArea } = Input;

type Section = 'tasks' | 'planning' | 'runs' | 'automation' | 'tools' | 'overview' | 'agents' | 'inbox' | 'audit' | 'model-settings';
type Lease = Pick<ClaimedExecution, 'execution' | 'lease_token'>;
type TaskOperation = 'progress' | 'submit' | 'block' | 'release';
type ExistingPullRequest = {
  provider: 'github' | 'gitlab' | 'gitea';
  repository: string;
  number: number;
  title: string;
  state: string;
  web_url: string;
  head_sha: string;
  head: string;
  base: string;
  checks: Array<{ context: string; state: string; description: string | null; target_url: string | null }>;
  checks_available: boolean;
  source: 'provider_api';
};

const sectionNames: Record<Section, string> = {
  tasks: '任務工作區',
  planning: '規劃工作區',
  runs: 'Run 執行',
  automation: '自動化',
  tools: '工具與沙箱',
  overview: '專案總覽',
  agents: 'Agent 名錄',
  inbox: '協作收件匣',
  audit: '操作稽核',
  'model-settings': '模型連線',
};

const statusLabel: Record<string, string> = {
  backlog: '待整理',
  ready: '待執行',
  in_progress: '進行中',
  blocked: '受阻',
  in_review: '待審核',
  done: '已完成',
  cancelled: '已取消',
};

const statusColor: Record<string, string> = {
  backlog: 'default',
  ready: 'blue',
  in_progress: 'purple',
  blocked: 'red',
  in_review: 'gold',
  done: 'green',
  cancelled: 'default',
};

const priorityLabel: Record<string, string> = {
  urgent: '緊急',
  high: '高',
  medium: '一般',
  low: '低',
};

const priorityColor: Record<string, string> = {
  urgent: 'red',
  high: 'volcano',
  medium: 'blue',
  low: 'default',
};

const principalRoleLabel: Record<string, string> = {
  admin: '系統管理員',
  manager: '管理者',
  reviewer: '審核者',
  worker: '執行者',
};

function errorText(error: unknown): string {
  if (error instanceof Error) {
    if ('sourceMessage' in error) return String((error as Error & { sourceMessage: unknown }).sourceMessage ?? error.message);
    return error.message;
  }
  return '發生未預期的錯誤。';
}

function displayDate(value?: string | null): string {
  return formatDate(value, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
}

function money(value?: number | null): string {
  return formatNumber(value ?? 0, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
}

function nameFor(
  id: string | null | undefined,
  people: Array<{ id: string; principal_id?: string; name: string }>,
  principal?: Pick<Principal, 'id' | 'name'> | null,
): string {
  if (!id) return translate('未指派');
  if (principal?.id === id) return principal.name;
  return people.find((person) => person.id === id || person.principal_id === id)?.name ?? id.slice(0, 8);
}

function taskAssignment(task: Task, field: 'assignee' | 'reviewer', participants: ProjectParticipant[]): TaskAssignment | null {
  const details = task[field];
  const principalId = field === 'assignee' ? task.assignee_principal_id : task.reviewer_principal_id;
  const agentId = field === 'assignee' ? task.assignee_id : task.reviewer_id;
  const id = details?.id ?? principalId ?? agentId;
  if (!id) return null;
  const participant = participants.find((item) => item.id === id || item.principal_id === id || item.principal_id === details?.principal_id);
  const kind = details?.kind ?? (principalId ? 'human' : 'agent');
  return {
    id: details?.id ?? participant?.id ?? id,
    principal_id: details?.principal_id ?? principalId ?? participant?.principal_id ?? id,
    name: details?.name ?? participant?.name ?? nameFor(id, participants),
    kind,
  };
}

function participantOption(participant: ProjectParticipant, t = translate) {
  return {
    value: participant.principal_id,
    label: <Space size={6}><span>{participant.name}</span><Tag color={participant.kind === 'human' ? 'cyan' : 'purple'}>{t(participant.kind === 'human' ? '真人' : 'Agent')}</Tag></Space>,
  };
}

function IdentityLabel({ id, participants, principal }: { id: string | null | undefined; participants: ProjectParticipant[]; principal?: Pick<Principal, 'id' | 'name'> | null }) {
  const { t } = useI18n();
  const participant = participants.find((person) => person.id === id || person.principal_id === id);
  const kind = participant?.kind ?? (principal?.id === id ? 'human' : null);
  return <Space size={6}>{kind && <Tag color={kind === 'human' ? 'cyan' : 'purple'}>{t(kind === 'human' ? '真人' : 'Agent')}</Tag>}<span>{nameFor(id, participants, principal)}</span></Space>;
}

function TaskAssignmentLabel({ assignment }: { assignment: TaskAssignment | null }) {
  const { t } = useI18n();
  if (!assignment) return <Text type="secondary">{t('未指派')}</Text>;
  return <Space size={6}><Tag color={assignment.kind === 'human' ? 'cyan' : 'purple'}>{t(assignment.kind === 'human' ? '真人' : 'Agent')}</Tag><span>{assignment.name}</span></Space>;
}

function splitLines(value?: string): string[] {
  return (value ?? '').split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

function safeWebUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return (url.protocol === 'https:' || url.protocol === 'http:') && !url.username && !url.password ? url.toString() : null;
  } catch {
    return null;
  }
}

function taskStatusTag(status: TaskStatus, t = translate) {
  return <Tag color={statusColor[status] ?? 'default'}>{statusLabel[status] ? t(statusLabel[status]) : status}</Tag>;
}

function NavItem({
  active,
  icon,
  label,
  onClick,
  count,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  count?: number;
}) {
  const { t } = useI18n();
  return (
    <button className={`nav-item${active ? ' nav-item-active' : ''}`} onClick={onClick} type="button">
      <span className="nav-item-icon">{icon}</span>
      <span>{t(label)}</span>
      {typeof count === 'number' && count > 0 && <span className="nav-count">{count > 99 ? '99+' : count}</span>}
    </button>
  );
}

export default function App() {
  return <AuthProvider><WorkWorkspace /></AuthProvider>;
}

function WorkWorkspace() {
  const { t, locale } = useI18n();
  const auth = useAuth();
  const canCreateProject = auth.session?.user.role === 'admin';
  const [messageApi, messageContext] = message.useMessage();
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const [authBusy, setAuthBusy] = useState(false);
  const [principalError, setPrincipalError] = useState('');
  const [principalErrorStatus, setPrincipalErrorStatus] = useState(0);
  const [principalSessionKey, setPrincipalSessionKey] = useState('');
  const [health, setHealth] = useState<'checking' | 'ok' | 'error'>('checking');
  const [apiMode, setApiMode] = useState<'development' | 'production' | ''>('');
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState('');
  const [projectContext, setProjectContext] = useState<ProjectContext | null>(null);
  const [projectParticipants, setProjectParticipants] = useState<ProjectParticipant[]>([]);
  const [participantsBusy, setParticipantsBusy] = useState(false);
  const [participantsError, setParticipantsError] = useState('');
  const [projectBusy, setProjectBusy] = useState(false);
  const [projectError, setProjectError] = useState<string | LocalizedMessage>('');
  const [overview, setOverview] = useState<Overview | null>(null);
  const [section, setSection] = useState<Section>('tasks');
  const [tasks, setTasks] = useState<Task[]>([]);
  const [tasksBusy, setTasksBusy] = useState(false);
  const [tasksError, setTasksError] = useState('');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [selectedTaskId, setSelectedTaskId] = useState('');
  const [taskContext, setTaskContext] = useState<TaskContext | null>(null);
  const [taskContextBusy, setTaskContextBusy] = useState(false);
  const [taskContextError, setTaskContextError] = useState('');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [leases, setLeases] = useState<Record<string, Lease>>({});
  const [claimAgentId, setClaimAgentId] = useState<string>();
  const [dispatchBusy, setDispatchBusy] = useState(false);
  const [taskModalOpen, setTaskModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [taskSaving, setTaskSaving] = useState(false);
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [projectSaving, setProjectSaving] = useState(false);
  const [companionProject, setCompanionProject] = useState<Project | null>(null);
  const [agentList, setAgentList] = useState<Agent[]>([]);
  const [agentsBusy, setAgentsBusy] = useState(false);
  const [agentModalOpen, setAgentModalOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [agentSaving, setAgentSaving] = useState(false);
  const [agentTemplates, setAgentTemplates] = useState<AgentTemplate[]>([]);
  const [agentToolConnections, setAgentToolConnections] = useState<import('./types').ToolConnection[]>([]);
  const [agentSandboxProfiles, setAgentSandboxProfiles] = useState<import('./types').SandboxProfile[]>([]);
  const [agentExecutionOptionsLoading, setAgentExecutionOptionsLoading] = useState(false);
  const [agentExecutionOptionsError, setAgentExecutionOptionsError] = useState<Array<{ source: string; error: string }>>([]);
  const [newAgentToken, setNewAgentToken] = useState('');
  const [modelCatalog, setModelCatalog] = useState<ModelCatalog | null>(null);
  const [modelCatalogLoading, setModelCatalogLoading] = useState(false);
  const [modelCatalogError, setModelCatalogError] = useState('');
  const [inbox, setInbox] = useState<ProjectMessage[]>([]);
  const [inboxBusy, setInboxBusy] = useState(false);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [eventsBusy, setEventsBusy] = useState(false);
  const [messageModal, setMessageModal] = useState<{ open: boolean; replyTo?: ProjectMessage; taskId?: string; kind?: ProjectMessage['kind'] }>({ open: false });
  const [messageSaving, setMessageSaving] = useState(false);
  const [delegateOpen, setDelegateOpen] = useState(false);
  const [delegateSaving, setDelegateSaving] = useState(false);
  const [operationModal, setOperationModal] = useState<TaskOperation | null>(null);
  const [operationSaving, setOperationSaving] = useState(false);
  const [reviewDecision, setReviewDecision] = useState<'accept' | 'reject' | null>(null);
  const [reviewSaving, setReviewSaving] = useState(false);
  const [taskForm] = Form.useForm();
  useLocalizedForm(taskForm);
  const [projectForm] = Form.useForm();
  useLocalizedForm(projectForm);
  const [agentForm] = Form.useForm();
  useLocalizedForm(agentForm);
  const [messageForm] = Form.useForm();
  useLocalizedForm(messageForm);
  const [delegateForm] = Form.useForm();
  useLocalizedForm(delegateForm);
  const [operationForm] = Form.useForm();
  useLocalizedForm(operationForm);
  const [reviewForm] = Form.useForm();
  useLocalizedForm(reviewForm);
  const agentRuntime = (Form.useWatch('runtime', agentForm) as Agent['runtime'] | undefined) ?? 'pi';
  const agentModelMode = Form.useWatch('modelMode', agentForm) as 'inherit' | 'override' | undefined;
  const selectedAgentTemplateId = Form.useWatch('template_id', agentForm) as string | undefined;
  const selectedAgentTemplate = agentTemplates.find(template => template.id === selectedAgentTemplateId);
  const agentTemplateName = useRef('');
  const taskRequestSequence = useRef(0);
  const agentExecutionOptionsSequence = useRef(0);
  const pendingDispatchKey = useRef<{ taskId: string; agentId: string; key: string } | null>(null);
  const requestedResourceId = useRef(new URLSearchParams(window.location.search).get('resource')?.trim() ?? '');
  const resourceAttemptKey = useRef('');
  const prefetchedTaskContext = useRef<{ id: string; context: TaskContext } | null>(null);

  useEffect(() => {
    agentExecutionOptionsSequence.current += 1;
    setClaimAgentId(undefined);
    setAgentTemplates([]);
    setAgentToolConnections([]);
    setAgentSandboxProfiles([]);
    setAgentExecutionOptionsLoading(false);
    setAgentExecutionOptionsError([]);
    setAgentModalOpen(false);
    setEditingAgent(null);
    setNewAgentToken('');
    agentForm.resetFields();
  }, [projectId]);

  useEffect(() => {
    setClaimAgentId(undefined);
  }, [selectedTaskId]);

  const currentProject = projects.find((project) => project.id === projectId) ?? projectContext?.project ?? null;
  const people = projectContext?.agents ?? agentList.filter((agent) => !projectId || agent.project_ids.includes(projectId));
  const collaborators = projectParticipants;
  const selectedTask = taskContext?.task ?? tasks.find((task) => task.id === selectedTaskId) ?? null;
  const activeHumanExecution = taskContext?.executions.find((execution) => execution.status === 'running'
    && (execution.executor_kind === 'human' || Boolean(execution.claimed_by_principal_id))
    && execution.claimed_by_principal_id === principal?.id);
  const lease = selectedTaskId
    ? leases[selectedTaskId] ?? (activeHumanExecution ? { execution: activeHumanExecution, lease_token: null } : undefined)
    : undefined;
  const canManageAgents = Boolean(principal && ['admin', 'manager'].includes(principal.role));
  const dispatchAgents = people.filter((agent) => agent.status === 'available' && agent.role === 'worker' && agent.runtime === 'pi' && agent.id === selectedTask?.assignee_id);
  const activeReviewer = taskContext?.executions.find((execution) => execution.status === 'submitted') ?? null;
  const submittedByCurrentPrincipal = Boolean(activeReviewer && principal && (
    activeReviewer.submitted_by_principal_id === principal.id
      || activeReviewer.claimed_by_principal_id === principal.id
      || activeReviewer.executor_id === principal.id
      || activeReviewer.agent_id === principal.id
      || people.some((agent) => agent.id === activeReviewer.agent_id && agent.principal_id === principal.id)
  ));
  const designatedReviewerPrincipal = selectedTask?.reviewer_principal_id
    ?? (selectedTask?.reviewer_id ? people.find((agent) => agent.id === selectedTask.reviewer_id)?.principal_id : undefined);
  const humanMayClaim = Boolean(principal?.kind === 'human'
    && ['admin', 'manager', 'worker'].includes(principal.role)
    && !selectedTask?.assignee_id
    && (!selectedTask?.assignee_principal_id || selectedTask.assignee_principal_id === principal.id));
  const currentAgentId = principal?.kind === 'agent' ? people.find((agent) => agent.principal_id === principal.id)?.id : undefined;
  const agentMayClaim = Boolean(principal?.kind === 'agent'
    && !selectedTask?.assignee_principal_id
    && (!selectedTask?.assignee_id || selectedTask.assignee_id === currentAgentId));
  const mayClaimDirectly = humanMayClaim || agentMayClaim;
  const canReview = Boolean(
    selectedTask?.status === 'in_review'
      && principal
      && ['admin', 'manager', 'reviewer'].includes(principal.role)
      && !submittedByCurrentPrincipal
      && (!selectedTask.reviewer_id && !selectedTask.reviewer_principal_id || selectedTask.reviewer_id === principal.id || selectedTask.reviewer_principal_id === principal.id || designatedReviewerPrincipal === principal.id),
  );

  useEffect(() => {
    api.get<{ status: string; mode?: 'development' | 'production' }>('/api/health')
      .then((result) => { setHealth('ok'); setApiMode(result.mode ?? ''); })
      .catch(() => setHealth('error'));
  }, []);

  useEffect(() => {
    if (!auth.session) {
      setPrincipal(null);
      setPrincipalSessionKey('');
      setPrincipalError('');
      setPrincipalErrorStatus(0);
      resourceAttemptKey.current = '';
      prefetchedTaskContext.current = null;
      setProjects([]);
      setProjectId('');
      setProjectContext(null);
      setProjectParticipants([]);
      setParticipantsError('');
      setOverview(null);
      setTasks([]);
      setTaskContext(null);
      setAgentList([]);
      setModelCatalog(null);
      setModelCatalogError('');
      setInbox([]);
      setEvents([]);
      setLeases({});
      setDrawerOpen(false);
      return;
    }
    let current = true;
    setPrincipal(null);
    setPrincipalSessionKey(auth.session.csrf_token);
    setAuthBusy(true);
    setPrincipalError('');
    setPrincipalErrorStatus(0);
    api.me()
      .then((result) => {
        if (!current) return;
        setPrincipal(result);
        setPrincipalSessionKey(auth.session?.csrf_token ?? '');
      })
      .catch((error) => { if (current) { setPrincipalError(errorText(error)); setPrincipalErrorStatus(error instanceof Error && 'status' in error ? Number((error as { status: unknown }).status) : 0); } })
      .finally(() => { if (current) setAuthBusy(false); });
    return () => { current = false; };
  }, [auth.session]);

  useEffect(() => {
    if (!principal) return;
    let current = true;
    api.projects()
      .then((result) => {
        if (!current) return;
        setProjects(result);
        setProjectId((existing) => result.some((project) => project.id === existing) ? existing : result[0]?.id ?? '');
      })
      .catch((error) => {
        if (current) setProjectError(errorText(error));
      });
    return () => { current = false; };
  }, [principal]);

  useEffect(() => {
    const resourceId = requestedResourceId.current;
    if (!principal || !resourceId) return;
    const attemptKey = `${principal.id}:${resourceId}`;
    if (resourceAttemptKey.current === attemptKey) return;
    resourceAttemptKey.current = attemptKey;
    let current = true;
    setTaskContextBusy(true);
    setTaskContextError('');
    api.taskContext(resourceId)
      .then((context) => {
        if (!current) return;
        prefetchedTaskContext.current = { id: context.task.id, context };
        setSection('tasks');
        setProjectId(context.task.project_id);
        setSelectedTaskId(context.task.id);
        setDrawerOpen(true);
      })
      .catch((error) => {
        if (!current) return;
        setSection('tasks');
        setSelectedTaskId(resourceId);
        setDrawerOpen(true);
        setTaskContextError(errorText(error));
      })
      .finally(() => { if (current) setTaskContextBusy(false); });
    return () => { current = false; };
  }, [principal]);

  useEffect(() => {
    if (!principal || !projectId) {
      setProjectContext(null);
      setOverview(null);
      return;
    }
    let current = true;
    setProjectBusy(true);
    setProjectError('');
    Promise.allSettled([
      api.projectContext(projectId),
      api.overview(projectId),
    ])
      .then(([contextResult, overviewResult]) => {
        if (!current) return;
        if (contextResult.status === 'fulfilled') setProjectContext(contextResult.value);
        else setProjectError(errorText(contextResult.reason));
        if (overviewResult.status === 'fulfilled') setOverview(overviewResult.value);
        else if (contextResult.status === 'fulfilled') setProjectError(localized('專案摘要無法載入：{{error}}', { error: localized(errorText(overviewResult.reason)) }));
      })
      .finally(() => { if (current) setProjectBusy(false); });
    return () => { current = false; };
  }, [principal, projectId]);

  useEffect(() => {
    if (!principal || !projectId) {
      setProjectParticipants([]);
      setParticipantsError('');
      setParticipantsBusy(false);
      return;
    }
    let current = true;
    setProjectParticipants([]);
    setParticipantsError('');
    setParticipantsBusy(true);
    api.participants(projectId)
      .then((result) => { if (current) setProjectParticipants(result); })
      .catch((error) => { if (current) setParticipantsError(errorText(error)); })
      .finally(() => { if (current) setParticipantsBusy(false); });
    return () => { current = false; };
  }, [principal, projectId]);

  const loadTasks = useCallback(async () => {
    if (!projectId) return;
    const sequence = ++taskRequestSequence.current;
    setTasksBusy(true);
    setTasksError('');
    try {
      const result = await api.tasks(projectId, statusFilter, search);
      if (sequence === taskRequestSequence.current) setTasks(result);
    } catch (error) {
      if (sequence === taskRequestSequence.current) setTasksError(errorText(error));
    } finally {
      if (sequence === taskRequestSequence.current) setTasksBusy(false);
    }
  }, [projectId, search, statusFilter]);

  useEffect(() => {
    if (!projectId) return;
    const timer = window.setTimeout(() => { void loadTasks(); }, search ? 220 : 0);
    return () => window.clearTimeout(timer);
  }, [loadTasks, projectId, search]);

  useEffect(() => {
    if (!selectedTaskId || !drawerOpen) {
      setTaskContext(null);
      return;
    }
    const prefetched = prefetchedTaskContext.current;
    if (prefetched?.id === selectedTaskId) {
      prefetchedTaskContext.current = null;
      setTaskContext(prefetched.context);
      setTaskContextBusy(false);
      setTaskContextError('');
      return;
    }
    let current = true;
    setTaskContext(null);
    setTaskContextBusy(true);
    setTaskContextError('');
    api.taskContext(selectedTaskId)
      .then((context) => { if (current) setTaskContext(context); })
      .catch((error) => { if (current) setTaskContextError(errorText(error)); })
      .finally(() => { if (current) setTaskContextBusy(false); });
    return () => { current = false; };
  }, [selectedTaskId, drawerOpen]);

  useEffect(() => {
    if (!projectId || !principal || section !== 'agents') return;
    let current = true;
    setAgentsBusy(true);
    api.agents()
      .then((result) => { if (current) setAgentList(result.filter((agent) => agent.project_ids.includes(projectId))); })
      .catch((error) => { if (current) messageApi.error(t(errorText(error))); })
      .finally(() => { if (current) setAgentsBusy(false); });
    return () => { current = false; };
  }, [messageApi, principal, projectId, section]);

  useEffect(() => {
    if (!projectId || !principal || section !== 'inbox') return;
    let current = true;
    setInboxBusy(true);
    api.messages(projectId, true)
      .then((result) => { if (current) setInbox(result); })
      .catch((error) => { if (current) messageApi.error(t(errorText(error))); })
      .finally(() => { if (current) setInboxBusy(false); });
    return () => { current = false; };
  }, [messageApi, principal, projectId, section]);

  useEffect(() => {
    if (!projectId || !principal || section !== 'audit') return;
    let current = true;
    setEventsBusy(true);
    api.events(projectId)
      .then((result) => { if (current) setEvents(result); })
      .catch((error) => { if (current) messageApi.error(t(errorText(error))); })
      .finally(() => { if (current) setEventsBusy(false); });
    return () => { current = false; };
  }, [messageApi, principal, projectId, section]);

  const reloadTaskContext = useCallback(async (id = selectedTaskId) => {
    if (!id) return;
    const [context] = await Promise.all([
      api.taskContext(id).then((result) => { setTaskContext(result); return result; }),
      loadTasks(),
      projectId ? api.overview(projectId).then(setOverview).catch(() => undefined) : Promise.resolve(),
    ]);
    return context;
  }, [loadTasks, projectId, selectedTaskId]);

  const refreshProjectList = useCallback(async (selectId?: string) => {
    const result = await api.projects();
    setProjects(result);
    if (selectId) setProjectId(selectId);
    else if (!projectId && result[0]) setProjectId(result[0].id);
    return result;
  }, [projectId]);

  function openNewTask() {
    setEditingTask(null);
    taskForm.resetFields();
    taskForm.setFieldsValue({ priority: 'medium', acceptance_criteria: '', labels: [], dependency_ids: [], budget_usd: 0, assignee: undefined, reviewer: undefined });
    setTaskModalOpen(true);
  }

  function openEditTask(task: Task) {
    setEditingTask(task);
    taskForm.setFieldsValue({
      ...task,
      assignee: taskAssignment(task, 'assignee', collaborators)?.principal_id,
      reviewer: taskAssignment(task, 'reviewer', collaborators)?.principal_id,
      acceptance_criteria: task.acceptance_criteria.join('\n'),
      labels: task.labels,
      dependency_ids: task.dependency_ids,
    });
    setTaskModalOpen(true);
  }

  function updateResourceQuery(taskId?: string) {
    const url = new URL(window.location.href);
    if (taskId) url.searchParams.set('resource', taskId);
    else url.searchParams.delete('resource');
    window.history.replaceState(window.history.state, '', url);
  }

  function openTask(task: Task) {
    updateResourceQuery(task.id);
    setSelectedTaskId(task.id);
    setDrawerOpen(true);
  }

  function useExistingPullRequest(result: ExistingPullRequest) {
    operationForm.resetFields();
    operationForm.setFieldsValue({
      summary: t('{{provider}} {{repository}}#{{number}}「{{title}}」目前狀態：{{state}}。查詢來源為既有版控 provider API。', {
        provider: result.provider,
        repository: result.repository,
        number: result.number,
        title: result.title,
        state: result.state,
      }),
      kind: 'url',
      artifact_title: t('{{provider}} {{repository}}#{{number}} · {{title}}', {
        provider: result.provider,
        repository: result.repository,
        number: result.number,
        title: result.title,
      }),
      uri: result.web_url,
      content: [
        t('狀態：{{state}}', { state: result.state }),
        t('來源：{{source}}', { source: result.source }),
        t('Base：{{value}}', { value: result.base }),
        t('Head：{{value}}', { value: result.head }),
        t('Head SHA：{{value}}', { value: result.head_sha }),
        result.checks_available
          ? t('Provider checks：{{checks}}', { checks: result.checks.length ? result.checks.map((check) => `${check.context}: ${check.state}${check.description ? ` (${check.description})` : ''}`).join('\n') : t('provider 未回傳 check 項目。') })
          : t('Provider 未提供 checks API。'),
      ].join('\n'),
    });
    setOperationModal('submit');
  }

  async function saveTask(values: Record<string, unknown>) {
    if (!projectId) return;
    setTaskSaving(true);
    const currentAssignee = editingTask ? taskAssignment(editingTask, 'assignee', collaborators) : null;
    const currentReviewer = editingTask ? taskAssignment(editingTask, 'reviewer', collaborators) : null;
    const assignee = collaborators.find((participant) => participant.principal_id === values.assignee)
      ?? (currentAssignee?.principal_id === values.assignee ? currentAssignee : null);
    const reviewer = collaborators.find((participant) => participant.principal_id === values.reviewer)
      ?? (currentReviewer?.principal_id === values.reviewer ? currentReviewer : null);
    const body = {
      title: values.title,
      description: values.description ?? '',
      goal: values.goal ?? '',
      inputs: values.inputs ?? '',
      scope: values.scope ?? '',
      constraints: values.constraints ?? '',
      acceptance_criteria: splitLines(String(values.acceptance_criteria ?? '')),
      priority: values.priority,
      assignee_id: assignee?.kind === 'agent' ? assignee.id : null,
      assignee_principal_id: assignee?.kind === 'human' ? assignee.principal_id : null,
      reviewer_id: reviewer?.kind === 'agent' ? reviewer.id : null,
      reviewer_principal_id: reviewer?.kind === 'human' ? reviewer.principal_id : null,
      dependency_ids: values.dependency_ids ?? [],
      labels: values.labels ?? [],
      budget_usd: values.budget_usd ?? 0,
    };
    try {
      const saved = editingTask
        ? await api.patch<Task>(`/api/tasks/${encodeURIComponent(editingTask.id)}`, body)
        : await api.post<Task>('/api/tasks', { project_id: projectId, ...body });
      setTaskModalOpen(false);
      await Promise.all([loadTasks(), refreshProjectList()]);
      openTask(saved);
      await reloadTaskContext(saved.id);
      messageApi.success(editingTask ? t('任務規格已更新。') : t('任務已建立。'));
    } catch (error) {
      messageApi.error(t(errorText(error)));
    } finally {
      setTaskSaving(false);
    }
  }

  async function refreshParticipants() {
    if (!projectId) return;
    setParticipantsBusy(true);
    setParticipantsError('');
    try {
      setProjectParticipants(await api.participants(projectId));
    } catch (error) {
      setParticipantsError(errorText(error));
    } finally {
      setParticipantsBusy(false);
    }
  }

  async function retryParticipants() {
    await refreshParticipants();
  }

  async function saveProject(values: Record<string, unknown>) {
    if (auth.session?.user.role !== 'admin') {
      setProjectModalOpen(false);
      messageApi.error(t('只有管理員可以建立專案。'));
      return;
    }
    setProjectSaving(true);
    try {
      const created = await api.post<Project>('/api/projects', {
        key: values.key,
        name: values.name,
        description: values.description ?? '',
        team_id: values.team_id || undefined,
        budget_usd: values.budget_usd ?? 0,
      });
      setProjectModalOpen(false);
      projectForm.resetFields();
      setProjects(current => [created, ...current.filter(project => project.id !== created.id)]);
      setProjectId(created.id);
      setCompanionProject(created);
      messageApi.success(t('專案已建立。'));
      // Creation has succeeded even if the follow-up list refresh is unavailable.
      void refreshProjectList(created.id).catch(error => messageApi.error(t(errorText(error))));
    } catch (error) {
      messageApi.error(t(errorText(error)));
    } finally {
      setProjectSaving(false);
    }
  }

  async function claimTask(agentId?: string) {
    if (!selectedTask || !principal) return;
    if (principal.kind === 'runtime') {
      messageApi.error(t('執行服務身分不可代替 Agent 認領任務。'));
      return;
    }
    if (agentId && (principal.kind !== 'human' || !canManageAgents || selectedTask.assignee_principal_id || (selectedTask.assignee_id && selectedTask.assignee_id !== agentId))) {
      messageApi.error(t('目前身分不可代替 Agent 認領此任務。'));
      return;
    }
    if (agentId && !people.some((agent) => agent.id === agentId && agent.role === 'worker' && agent.status === 'available')) {
      messageApi.error(t('所選 Agent 目前無法認領任務。'));
      return;
    }
    if (!agentId && !mayClaimDirectly) {
      messageApi.error(t('此任務指派給其他執行者，無法直接認領。'));
      return;
    }
    try {
      const result = await api.claim(selectedTask.id, agentId ? { agent_id: agentId } : {});
      setLeases((current) => ({ ...current, [selectedTask.id]: { execution: result.execution, lease_token: result.lease_token ?? null } }));
      await reloadTaskContext(selectedTask.id);
      messageApi.success(t(agentId ? '已代表 Agent 開始執行 {{key}}。' : '已認領 {{key}}。', { key: selectedTask.key }));
    } catch (error) {
      messageApi.error(t(errorText(error)));
    }
  }

  async function dispatchSelectedTask() {
    if (!selectedTask || !principal || dispatchBusy) return;
    if (principal.kind !== 'human' || !canManageAgents || selectedTask.status !== 'ready' || selectedTask.assignee_principal_id) return;
    const agent = dispatchAgents.find((candidate) => candidate.id === selectedTask.assignee_id);
    if (!agent) return;

    setDispatchBusy(true);
    const pending = pendingDispatchKey.current;
    const idempotencyKey = pending?.taskId === selectedTask.id && pending.agentId === agent.id
      ? pending.key
      : createIdempotencyKey();
    pendingDispatchKey.current = { taskId: selectedTask.id, agentId: agent.id, key: idempotencyKey };
    try {
      await api.dispatchTask(selectedTask.id, { agent_id: agent.id }, idempotencyKey);
      pendingDispatchKey.current = null;
      try {
        await reloadTaskContext(selectedTask.id);
      } catch (error) {
        setTaskContextError(errorText(error));
      }
      messageApi.success(t('已派發給 {{agent}}。請前往 Run 執行查看狀態。', { agent: agent.name }));
    } catch (error) {
      if (isDefinitiveClientError(error)) pendingDispatchKey.current = null;
      messageApi.error(t(errorText(error)));
    } finally {
      setDispatchBusy(false);
    }
  }

  async function runTaskOperation(values: Record<string, unknown>) {
    if (!selectedTask || !lease || !operationModal) return;
    setOperationSaving(true);
    const prefix = `/api/tasks/${encodeURIComponent(selectedTask.id)}`;
    const leaseBody = { execution_id: lease.execution.id, ...(lease.lease_token ? { lease_token: lease.lease_token } : {}) };
    try {
      if (operationModal === 'progress') {
        await api.post<Task>(`${prefix}/progress`, {
          ...leaseBody,
          progress: values.progress,
          summary: values.summary || undefined,
          cost_usd: values.cost_usd === undefined ? undefined : Number(values.cost_usd),
        });
      } else if (operationModal === 'submit') {
        const artifact: Partial<Artifact> = {
          kind: values.kind as Artifact['kind'],
          title: String(values.artifact_title),
          uri: values.uri ? String(values.uri) : null,
          content: values.content ? String(values.content) : null,
        };
        await api.post<TaskContext>(`${prefix}/submit`, {
          ...leaseBody,
          summary: values.summary,
          artifacts: [artifact],
          cost_usd: values.cost_usd === undefined ? 0 : Number(values.cost_usd),
        });
        setLeases((current) => { const next = { ...current }; delete next[selectedTask.id]; return next; });
      } else if (operationModal === 'block') {
        await api.post<Task>(`${prefix}/block`, {
          ...leaseBody,
          reason: values.reason,
          handoff: values.handoff || undefined,
        });
        setLeases((current) => { const next = { ...current }; delete next[selectedTask.id]; return next; });
      } else {
        await api.post<Task>(`${prefix}/release`, { ...leaseBody, handoff: values.handoff });
        setLeases((current) => { const next = { ...current }; delete next[selectedTask.id]; return next; });
      }
      setOperationModal(null);
      operationForm.resetFields();
      await reloadTaskContext(selectedTask.id);
      messageApi.success(t('執行狀態已更新。'));
    } catch (error) {
      messageApi.error(t(errorText(error)));
    } finally {
      setOperationSaving(false);
    }
  }

  async function renewLease() {
    if (!selectedTask || !lease?.lease_token) return;
    try {
      const result = await api.post<ClaimedExecution>(`/api/tasks/${encodeURIComponent(selectedTask.id)}/renew`, {
        execution_id: lease.execution.id,
        lease_token: lease.lease_token,
        lease_seconds: 300,
      });
      setLeases((current) => ({ ...current, [selectedTask.id]: { execution: result.execution, lease_token: result.lease_token } }));
      messageApi.success(t('執行租約已延長。'));
    } catch (error) {
      setLeases((current) => { const next = { ...current }; delete next[selectedTask.id]; return next; });
      messageApi.error(t(errorText(error)));
    }
  }

  async function unblockTask() {
    if (!selectedTask) return;
    try {
      await api.post<Task>(`/api/tasks/${encodeURIComponent(selectedTask.id)}/unblock`, {});
      await reloadTaskContext(selectedTask.id);
      messageApi.success(t('任務已解除阻塞。'));
    } catch (error) {
      messageApi.error(t(errorText(error)));
    }
  }

  async function reviewTask(values: Record<string, unknown>) {
    if (!selectedTask || !reviewDecision) return;
    setReviewSaving(true);
    try {
      const context = await api.post<TaskContext>(`/api/tasks/${encodeURIComponent(selectedTask.id)}/review`, {
        decision: reviewDecision,
        comment: values.comment,
      });
      setTaskContext(context);
      setReviewDecision(null);
      reviewForm.resetFields();
      await loadTasks();
      messageApi.success(reviewDecision === 'accept' ? t('審核通過，任務已完成。') : t('已退回執行，歷史證據仍保留。'));
    } catch (error) {
      messageApi.error(t(errorText(error)));
    } finally {
      setReviewSaving(false);
    }
  }

  async function loadModelCatalog() {
    setModelCatalogLoading(true);
    setModelCatalogError('');
    try {
      setModelCatalog(await api.modelCatalog());
    } catch (error) {
      setModelCatalog(null);
      setModelCatalogError(errorText(error));
    } finally {
      setModelCatalogLoading(false);
    }
  }

  async function loadAgentExecutionOptions() {
    const sequence = ++agentExecutionOptionsSequence.current;
    const requestedProjectId = projectId;
    setAgentExecutionOptionsLoading(true);
    setAgentExecutionOptionsError([]);
    setAgentTemplates([]);
    setAgentToolConnections([]);
    setAgentSandboxProfiles([]);
    const results = await Promise.allSettled([api.agentTemplates(), api.toolConnections(projectId), api.sandboxProfiles(projectId)]);
    if (sequence !== agentExecutionOptionsSequence.current || requestedProjectId !== projectId) return;
    const failures: Array<{ source: string; error: string }> = [];
    if (results[0].status === 'fulfilled') setAgentTemplates(results[0].value);
    else failures.push({ source: 'Agent 範本：{{error}}', error: errorText(results[0].reason) });
    if (results[1].status === 'fulfilled') setAgentToolConnections(results[1].value);
    else failures.push({ source: '工具連線：{{error}}', error: errorText(results[1].reason) });
    if (results[2].status === 'fulfilled') setAgentSandboxProfiles(results[2].value);
    else failures.push({ source: 'Sandbox profiles：{{error}}', error: errorText(results[2].reason) });
    setAgentExecutionOptionsError(failures);
    setAgentExecutionOptionsLoading(false);
  }

  function applyTemplateToAgentForm(template: AgentTemplate) {
    const localized = localizeAgentTemplate(template);
    const name = String(agentForm.getFieldValue('name') ?? '');
    if (!editingAgent && (!name.trim() || name === agentTemplateName.current)) {
      agentForm.setFieldValue('name', localized.name);
      agentTemplateName.current = localized.name;
    }
    const values = agentTemplateFormValues(template);
    agentForm.setFieldsValue(editingAgent ? { ...values, runtime: editingAgent.runtime } : values);
  }

  function openNewAgent(template?: AgentTemplate) {
    setEditingAgent(null);
    agentTemplateName.current = '';
    setNewAgentToken('');
    agentForm.resetFields();
    agentForm.setFieldsValue({
      role: 'worker', capabilities: [], runtime: 'pi', modelMode: 'inherit', model: undefined, model_config: undefined, template_id: undefined,
      execution_config: { instructions: '', tool_connection_ids: [], sandbox_profile_id: null, limits: { max_turns: 20, timeout_seconds: 600 } },
    });
    if (template) applyTemplateToAgentForm(template);
    setAgentModalOpen(true);
    void loadModelCatalog();
    void loadAgentExecutionOptions();
  }

  function openEditAgent(agent: Agent) {
    setEditingAgent(agent);
    agentTemplateName.current = '';
    agentForm.resetFields();
    agentForm.setFieldsValue({
      name: agent.name,
      role: agent.role,
      runtime: agent.runtime,
      model: agent.model,
      modelMode: agent.model_config ? 'override' : 'inherit',
      model_config: agent.model_config ?? undefined,
      capabilities: agent.capabilities,
      team_id: agent.team_id,
      template_id: agent.template_id,
      execution_config: agent.execution_config ?? { instructions: '', tool_connection_ids: [], sandbox_profile_id: null, limits: { max_turns: 20, timeout_seconds: 600 } },
    });
    setAgentModalOpen(true);
    void loadModelCatalog();
    void loadAgentExecutionOptions();
  }

  async function saveAgent(values: Record<string, unknown>) {
    setAgentSaving(true);
    try {
      const executionConfig = values.execution_config as ExecutionConfig;
      const templateId = values.template_id ? String(values.template_id) : null;
      if (editingAgent) {
        const modelConfig = values.runtime === 'pi' && values.modelMode === 'override'
          ? values.model_config as ModelSelection | undefined ?? null
          : null;
        const updated = await api.patch<Agent>(`/api/agents/${encodeURIComponent(editingAgent.id)}`, {
          capabilities: values.capabilities ?? [],
          model: values.model || null,
          model_config: modelConfig,
          template_id: templateId,
          execution_config: executionConfig,
        });
        setAgentList((current) => current.map((agent) => agent.id === updated.id ? updated : agent));
        setProjectContext((current) => current ? { ...current, agents: current.agents.map((agent) => agent.id === updated.id ? updated : agent) } : current);
      } else {
        const modelConfig = values.runtime === 'pi' && values.modelMode === 'override'
          ? values.model_config as ModelSelection | undefined ?? null
          : null;
        const result = await api.post<Agent & { token?: string }>('/api/agents', {
          name: values.name,
          role: values.role,
          team_id: values.team_id || undefined,
          capabilities: values.capabilities ?? [],
          project_ids: [projectId],
          runtime: values.runtime,
          model: values.model || null,
          model_config: modelConfig,
          template_id: templateId,
          execution_config: executionConfig,
        });
        setNewAgentToken(result.token ?? '');
        if (projectId) {
          const fresh = await api.agents();
          const scopedAgents = fresh.filter((agent) => agent.project_ids.includes(projectId));
          setAgentList(scopedAgents);
          setProjectContext((current) => current ? { ...current, agents: scopedAgents } : current);
        }
      }
      await refreshParticipants();
      setAgentModalOpen(false);
      setEditingAgent(null);
      agentForm.resetFields();
      messageApi.success(editingAgent ? t('Agent 能力與模型設定已更新。') : t('Agent 已建立。'));
    } catch (error) {
      messageApi.error(t(errorText(error)));
    } finally {
      setAgentSaving(false);
    }
  }

  async function disableAgent(agent: Agent) {
    try {
      await api.patch<Agent>(`/api/agents/${encodeURIComponent(agent.id)}`, { status: 'disabled' });
      setAgentList((current) => current.map((entry) => entry.id === agent.id ? { ...entry, status: 'disabled' } : entry));
      setProjectContext((current) => current ? { ...current, agents: current.agents.map((entry) => entry.id === agent.id ? { ...entry, status: 'disabled' } : entry) } : current);
      await refreshParticipants();
      messageApi.success(t('{{name}} 已停用。', { name: agent.name }));
    } catch (error) {
      messageApi.error(t(errorText(error)));
    }
  }

  async function copyNewAgentToken() {
    if (!newAgentToken) return;
    try {
      await navigator.clipboard.writeText(newAgentToken);
      messageApi.success(t('Agent token 已複製。'));
    } catch {
      messageApi.error(t('瀏覽器無法存取剪貼簿，請在關閉提示前手動複製。'));
    }
  }

  async function sendProjectMessage(values: Record<string, unknown>) {
    if (!projectId) return;
    setMessageSaving(true);
    const replyTo = messageModal.replyTo;
    try {
      await api.post<ProjectMessage>('/api/messages', {
        project_id: projectId,
        task_id: messageModal.taskId ?? replyTo?.task_id ?? undefined,
        recipient_id: replyTo ? replyTo.sender_id : values.recipient_id || undefined,
        kind: replyTo ? 'reply' : (values.kind ?? messageModal.kind ?? 'question'),
        body: values.body,
        reply_to_id: replyTo?.id,
      });
      setMessageModal({ open: false });
      messageForm.resetFields();
      messageApi.success(replyTo ? t('回覆已送出。') : t('訊息已送出。'));
      if (section === 'inbox') setInbox(await api.messages(projectId, true));
      if (selectedTaskId && drawerOpen) await reloadTaskContext(selectedTaskId);
    } catch (error) {
      messageApi.error(t(errorText(error)));
    } finally {
      setMessageSaving(false);
    }
  }

  async function acknowledgeMessage(item: ProjectMessage, status: 'accepted' | 'completed') {
    try {
      await api.post<ProjectMessage>(`/api/messages/${encodeURIComponent(item.id)}/ack`, { status });
      setInbox((current) => current.map((entry) => entry.id === item.id ? { ...entry, status } : entry));
      messageApi.success(status === 'accepted' ? t('已接收訊息。') : t('訊息已標記完成。'));
    } catch (error) {
      messageApi.error(t(errorText(error)));
    }
  }

  async function delegateTask(values: Record<string, unknown>) {
    if (!selectedTask) return;
    setDelegateSaving(true);
    try {
      const delegate = collaborators.find((participant) => participant.principal_id === values.delegatee);
      if (!delegate) throw new Error(t('請選擇有效的同事或 Agent。'));
      await api.post<Task>(`/api/tasks/${encodeURIComponent(selectedTask.id)}/delegate`, {
        ...(delegate.kind === 'human' ? { assignee_principal_id: delegate.principal_id } : { agent_id: delegate.id }),
        title: values.title,
        goal: values.goal,
        description: values.description ?? '',
        inputs: values.inputs ?? '',
        scope: values.scope ?? '',
        constraints: values.constraints ?? '',
        acceptance_criteria: splitLines(String(values.acceptance_criteria ?? '')),
        priority: values.priority ?? 'medium',
        budget_usd: values.budget_usd ?? 0,
      });
      setDelegateOpen(false);
      delegateForm.resetFields();
      await reloadTaskContext(selectedTask.id);
      messageApi.success(t('子任務已委派。'));
    } catch (error) {
      messageApi.error(t(errorText(error)));
    } finally {
      setDelegateSaving(false);
    }
  }

  const taskColumns: ColumnsType<Task> = useMemo(() => [
    {
      title: t('任務'),
      dataIndex: 'title',
      key: 'title',
      render: (_: unknown, task) => (
        <div className="task-title-cell">
          <span className="task-key">{task.key}</span>
          <span className="task-title">{task.title}</span>
          {task.labels?.length > 0 && <span className="task-label-preview">{task.labels.slice(0, 2).join(' · ')}</span>}
        </div>
      ),
    },
    {
      title: t('狀態'),
      dataIndex: 'status',
      key: 'status',
      width: 112,
      render: (value: TaskStatus) => taskStatusTag(value),
    },
    {
      title: t('優先級'),
      dataIndex: 'priority',
      key: 'priority',
      width: 88,
      render: (value: string) => <Tag color={priorityColor[value] ?? 'default'}>{priorityLabel[value] ? t(priorityLabel[value]) : value}</Tag>,
    },
    {
      title: t('負責者'),
      dataIndex: 'assignee_id',
      key: 'assignee',
      width: 190,
      render: (_: string | null, task) => <TaskAssignmentLabel assignment={taskAssignment(task, 'assignee', collaborators)} />,
    },
    {
      title: t('進度'),
      dataIndex: 'progress',
      key: 'progress',
      width: 118,
      render: (value: number) => (
        <div className="progress-cell"><Progress percent={Math.max(0, Math.min(100, value ?? 0))} size="small" showInfo={false} /><span>{formatNumber(value ?? 0)}%</span></div>
      ),
    },
    {
      title: t('更新'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 110,
      render: (value: string) => <span className="muted-cell">{displayDate(value)}</span>,
    },
  ], [collaborators, locale]);

  const agentColumns: ColumnsType<Agent> = [
    {
      title: 'Agent',
      dataIndex: 'name',
      key: 'name',
      render: (_: unknown, agent) => (
        <div className="agent-identity"><Avatar size={30} className="agent-avatar">{agent.name.slice(0, 1).toUpperCase()}</Avatar><div><strong>{agent.name}</strong><div className="subline">{t(agent.role === 'reviewer' ? '審核者' : '執行者')} · {t(agent.runtime === 'pi' ? '平台執行' : '外部程式執行')}</div></div></div>
      ),
    },
    { title: t('能力'), dataIndex: 'capabilities', key: 'capabilities', render: (items: string[]) => <span>{items?.length ? items.join(' · ') : t('未設定')}</span> },
    {
      title: t('模型'),
      dataIndex: 'effective_model_config',
      key: 'model',
      render: (_: Agent['effective_model_config'], agent) => {
        if (agent.runtime !== 'pi') return agent.model || t('未指定');
        const selection = agent.effective_model_config ?? agent.model_config;
        if (selection) {
          return <span>{selection.model_id}<div className="subline">{selection.provider_id} · {selection.reasoning_effort} · {formatNumber(selection.max_output_tokens)} tokens</div></span>;
        }
        return agent.runtime === 'pi' ? t('繼承全域預設（尚未設定）') : agent.model || t('未指定');
      },
    },
    { title: t('狀態'), dataIndex: 'status', key: 'status', width: 110, render: (value: Agent['status']) => <Tag color={value === 'available' ? 'green' : value === 'busy' ? 'blue' : value === 'disabled' ? 'default' : 'gold'}>{t(({ available: '可用', busy: '執行中', offline: '離線', disabled: '已停用' })[value])}</Tag> },
    {
      title: '',
      key: 'actions',
        width: 160,
        render: (_: unknown, agent) => (
          <Space><Button size="small" icon={<EditOutlined />} disabled={!canManageAgents} onClick={() => openEditAgent(agent)} aria-label={t('編輯 {{name}}', { name: agent.name })}>{t('編輯')}</Button><Button size="small" icon={<LockOutlined />} disabled={!canManageAgents || agent.status === 'disabled'} onClick={() => void disableAgent(agent)} aria-label={t('停用 {{name}}', { name: agent.name })}>{t('停用')}</Button></Space>
        ),
    },
  ];

  const inboxColumns: ColumnsType<ProjectMessage> = [
    { title: t('訊息'), dataIndex: 'body', key: 'body', render: (body: string, item) => <div className="message-cell"><Tag>{t(({ question: '問題', reply: '回覆', help_request: '求助', decision: '決議', handoff: '交接' })[item.kind])}</Tag><MarkdownContent content={body} />{item.task_id && <span className="subline">{t('任務 {{key}}', { key: tasks.find((task) => task.id === item.task_id)?.key ?? item.task_id.slice(0, 8) })}</span>}</div> },
    { title: t('寄件者'), dataIndex: 'sender_id', key: 'sender_id', width: 190, render: (id: string) => <IdentityLabel id={id} participants={collaborators} principal={principal} /> },
    { title: t('狀態'), dataIndex: 'status', key: 'status', width: 100, render: (value: ProjectMessage['status']) => <Tag color={value === 'completed' ? 'green' : value === 'accepted' ? 'blue' : 'default'}>{t(({ delivered: '待處理', accepted: '已接收', completed: '已完成' })[value])}</Tag> },
    { title: t('時間'), dataIndex: 'created_at', key: 'created_at', width: 118, render: (value: string) => displayDate(value) },
    { title: '', key: 'actions', width: 230, render: (_: unknown, item) => <Space wrap><Button size="small" icon={<SendOutlined />} onClick={() => { messageForm.resetFields(); setMessageModal({ open: true, replyTo: item }); }}>{t('回覆')}</Button>{item.status !== 'accepted' && item.status !== 'completed' && <Button size="small" onClick={() => void acknowledgeMessage(item, 'accepted')}>{t('接收')}</Button>}{item.status !== 'completed' && <Button size="small" onClick={() => void acknowledgeMessage(item, 'completed')}>{t('完成')}</Button>}</Space> },
  ];

  if (!auth.session) return <>{messageContext}<AuthScreen product="work" productName="Ordivant Work" /></>;
  if (authBusy || principalSessionKey !== auth.session.csrf_token) return <>{messageContext}<div className="auth-loading"><Spin size="large" /><Text>{t('正在確認 Work 存取權')}</Text></div></>;
  if (!principal) return <>{messageContext}<AuthAccessDenied product="work" productName="Work" error={principalError} forbidden={principalErrorStatus === 403} onRetry={() => window.location.reload()} /></>;

  const navSections: Array<{ id: Section; icon: React.ReactNode; label: string; count?: number }> = [
    { id: 'tasks', icon: <UnorderedListOutlined />, label: '任務' },
    { id: 'planning', icon: <AppstoreOutlined />, label: '規劃工作區' },
    { id: 'runs', icon: <PlayCircleOutlined />, label: 'Run 執行' },
    { id: 'automation', icon: <BranchesOutlined />, label: '自動化' },
    { id: 'tools', icon: <ToolOutlined />, label: '工具與沙箱' },
    { id: 'overview', icon: <AppstoreOutlined />, label: '專案總覽' },
    { id: 'agents', icon: <TeamOutlined />, label: 'Agent 名錄' },
    { id: 'inbox', icon: <InboxOutlined />, label: '協作收件匣', count: inbox.filter((item) => item.status === 'delivered').length },
    { id: 'audit', icon: <AuditOutlined />, label: '操作稽核' },
  ];
  if (auth.session.user.role === 'admin') navSections.push({ id: 'model-settings', icon: <SettingOutlined />, label: '模型連線' });

  return (
    <div className="app-shell">
      {messageContext}
      <aside className="side-rail">
        <div className="side-brand"><span className="brand-mark">O</span><div><strong>Ordivant</strong><span>{t('Agent 作業管理')}</span></div></div>
        <ProductSwitcher active="work" />
        <div className="rail-label">{t('工作區')}</div>
        <div className="rail-nav" role="navigation" aria-label={t('主要導覽')}>
          {navSections.map((item) => <NavItem key={item.id} active={section === item.id} icon={item.icon} label={item.label} count={item.id === 'inbox' ? undefined : item.count} onClick={() => setSection(item.id)} />)}
        </div>
        <div className="rail-bottom">
        <div className="workspace-identity"><Avatar size={28}>{principal.name.slice(0, 1).toUpperCase()}</Avatar><div className="workspace-user"><strong>{principal.name}</strong><span>{principalRoleLabel[principal.role] ? t(principalRoleLabel[principal.role]) : principal.role}</span></div><AccountControl product="work" productLabel="Ordivant Work" displayName={principal.name} businessRole={principal.role} /></div>
          <div className="rail-service"><span className={`health-dot ${health === 'ok' ? 'health-good' : health === 'error' ? 'health-bad' : ''}`} />{t(health === 'ok' ? 'API 已連線' : health === 'error' ? 'API 連線中斷' : '檢查服務中')}</div>
        </div>
      </aside>

      <main className="main-pane">
        <header className="topbar">
          <div className="topbar-project">
            <span className="project-caption">{t('專案')}</span>
            <Select
              aria-label={t('選擇專案')}
              value={projectId || undefined}
              placeholder={t('選擇專案')}
              options={projects.map((project) => ({ value: project.id, label: <span><b>{project.key}</b><span className="project-option-name">{project.name}</span></span> }))}
              onChange={(value) => {
                if (value !== projectId) agentExecutionOptionsSequence.current += 1;
                updateResourceQuery();
                setProjectId(value);
                setSelectedTaskId('');
                setDrawerOpen(false);
              }}
              className="project-select"
              popupMatchSelectWidth={false}
              notFoundContent={t('尚無可存取的專案')}
            />
            {canCreateProject && <Button icon={<PlusOutlined />} onClick={() => setProjectModalOpen(true)} aria-label={t('建立專案')} title={t('建立專案')} />}
          </div>
          <div className="topbar-right">
            <Tag bordered={false} color={apiMode === 'production' ? 'green' : 'purple'}>{apiMode === 'production' ? 'PROD' : apiMode === 'development' ? 'DEV' : 'API'}</Tag>
            <Tooltip title={t('重新整理工作資料')}><Button type="text" icon={<ReloadOutlined />} onClick={() => { void loadTasks(); if (projectId) api.overview(projectId).then(setOverview).catch((error) => messageApi.error(t(errorText(error)))); }} aria-label={t('重新整理')} /></Tooltip>
            <span className="topbar-date">{formatDate(new Date(), { year: 'numeric', month: '2-digit', day: '2-digit' })}</span>
          </div>
        </header>

        <div className="workspace-content">
          {projectError && <Alert className="page-alert" type="error" showIcon message={t('專案資料無法載入')} description={t(projectError)} action={<Button size="small" onClick={() => { if (projectId) { setProjectId(''); window.setTimeout(() => setProjectId(projectId), 0); } }}>{t('重試')}</Button>} />}
          {!projectId && section !== 'model-settings' ? (
          <div className="empty-project"><div className="empty-icon"><AppstoreOutlined /></div><Title level={3}>{t(canCreateProject ? '建立第一個專案' : '目前沒有可存取的專案')}</Title><Paragraph>{t(canCreateProject ? '目前帳號沒有可用專案。建立專案後即可新增任務、邀請 Agent 並追蹤執行證據。' : '請聯絡管理員授予專案存取權，或由管理員建立新專案。')}</Paragraph>{canCreateProject && <Button type="primary" icon={<PlusOutlined />} onClick={() => setProjectModalOpen(true)}>{t('建立專案')}</Button>}</div>
          ) : (
            <>
              <div className="page-heading">
                <div><Text className="eyebrow">{section === 'model-settings' ? t('組織設定') : `${currentProject?.key ?? 'PROJECT'} · ${currentProject?.name ?? t('專案')}`}</Text><Title level={2}>{t(sectionNames[section])}</Title></div>
                {section === 'tasks' && <Button type="primary" icon={<PlusOutlined />} onClick={openNewTask}>{t('新增任務')}</Button>}
                {section === 'agents' && canManageAgents && <Button type="primary" icon={<UserAddOutlined />} onClick={() => openNewAgent()}>{t('新增 Agent')}</Button>}
                {section === 'inbox' && <Button type="primary" icon={<SendOutlined />} onClick={() => { messageForm.resetFields(); setMessageModal({ open: true }); }}>{t('傳送訊息')}</Button>}
              </div>

              {section === 'tasks' && (
                <>
                  <section className="metric-strip" aria-label={t('專案任務摘要')}>
                    <Metric label="全部任務" value={overview?.counts.total} loading={projectBusy} />
                    <Metric label="待執行" value={overview?.counts.ready} loading={projectBusy} />
                    <Metric label="進行中" value={overview?.counts.in_progress} loading={projectBusy} />
                    <Metric label="待審核" value={overview?.counts.in_review} loading={projectBusy} />
                    <Metric label="已完成" value={overview?.counts.done} loading={projectBusy} />
                    <div className="metric-cost"><span>{t('執行成本彙總')}</span><strong>{overview ? money(overview.cost_usd) : '—'}</strong><small>{t('成本來源依執行紀錄標示')}</small></div>
                  </section>
                  <div className="task-toolbar">
                    <Input allowClear prefix={<FileSearchOutlined />} placeholder={t('搜尋任務名稱或內容')} value={search} onChange={(event) => setSearch(event.target.value)} aria-label={t('搜尋任務')} />
                    <Select aria-label={t('依狀態篩選')} value={statusFilter} onChange={setStatusFilter} options={[{ value: '', label: t('全部狀態') }, ...Object.entries(statusLabel).map(([value, label]) => ({ value, label: t(label) }))]} />
                    <span className="result-count">{tasksBusy ? t('載入中') : t('{{count}} 個任務', { count: formatNumber(tasks.length) })}</span>
                  </div>
                  {tasksError && <Alert type="error" showIcon message={t('任務清單無法載入')} description={t(tasksError)} action={<Button size="small" onClick={() => void loadTasks()}>{t('重試')}</Button>} />}
                  <div className="task-list-shell">
                    <Table<Task>
                      rowKey="id"
                      size="middle"
                      columns={taskColumns}
                      dataSource={tasks}
                      loading={tasksBusy}
                      pagination={{ pageSize: 12, showSizeChanger: false, showTotal: (total) => t('共 {{count}} 個任務', { count: formatNumber(total) }) }}
                      locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={search || statusFilter ? t('沒有符合條件的任務') : t('尚無任務')}>{!search && !statusFilter && <Button type="primary" size="small" icon={<PlusOutlined />} onClick={openNewTask}>{t('建立任務')}</Button>}</Empty> }}
                      onRow={(task) => ({ onClick: () => openTask(task), tabIndex: 0, onKeyDown: (event) => { if (event.key === 'Enter') openTask(task); }, 'aria-label': t('檢視 {{key}} {{title}}', { key: task.key, title: task.title }) })}
                      rowClassName={(task) => task.id === selectedTaskId ? 'task-row-selected' : 'task-row'}
                      scroll={{ x: 780 }}
                    />
                  </div>
                </>
              )}

              {section === 'planning' && <PlanningWorkspace key={projectId} projectId={projectId} canManage={canManageAgents} canLogWork={principal.kind === 'human' && ['admin', 'manager', 'worker'].includes(principal.role)} canSubmitIntake={principal.kind === 'human'} participants={collaborators} onOpenTask={openTask} onCreateTask={openNewTask} />}

              {section === 'overview' && <OverviewView overview={overview} loading={projectBusy} project={currentProject} events={overview?.activity ?? []} agents={projectContext?.agents ?? []} onSelectTask={() => setSection('tasks')} />}

              {section === 'runs' && <RunConsole key={projectId} projectId={projectId} canControl={canManageAgents} />}

              {section === 'automation' && <Automation key={projectId} projectId={projectId} canManage={canManageAgents} agents={people} onApplyTemplate={(template) => { setSection('agents'); openNewAgent(template); }} />}

              {section === 'tools' && <ToolSettings key={projectId} projectId={projectId} canAdmin={auth.session.user.role === 'admin'} />}

              {section === 'model-settings' && auth.session.user.role === 'admin' && <ModelSettings />}

              {section === 'agents' && (
                <section className="table-section">
                  <div className="section-tools"><span>{agentsBusy ? t('正在載入') : t('{{count}} 位 Agent', { count: formatNumber(agentList.length) })}</span><span>{t('能力與模型設定來自 Ordivant API')}</span></div>
                  {newAgentToken && <Alert className="token-alert" type="warning" showIcon closable onClose={() => setNewAgentToken('')} message={t('Agent 憑證只會顯示一次')} description={<div className="token-value"><code>{newAgentToken}</code><Space wrap><Button size="small" icon={<CopyOutlined />} onClick={() => void copyNewAgentToken()}>{t('複製 token')}</Button><Text>{t('外部程式可使用此憑證以此 Agent 身分連線。請妥善保管，不要提交至版本控制或寫入日誌；關閉提示後無法再次查看。')}</Text></Space></div>} />}
                  <Table<Agent> rowKey="id" columns={agentColumns} dataSource={agentList} loading={agentsBusy} pagination={{ pageSize: 15, showSizeChanger: false }} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('此專案尚無 Agent')} /> }} scroll={{ x: 720 }} />
                </section>
              )}

              {section === 'inbox' && (
                <section className="table-section">
                  <div className="section-tools"><span>{inboxBusy ? t('正在載入') : t('{{count}} 則收件訊息', { count: formatNumber(inbox.length) })}</span><span>{t('僅顯示寄送至目前身分的訊息')}</span></div>
                  <Table<ProjectMessage> rowKey="id" columns={inboxColumns} dataSource={inbox} loading={inboxBusy} pagination={{ pageSize: 12, showSizeChanger: false }} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('收件匣目前沒有訊息')} /> }} scroll={{ x: 920 }} />
                </section>
              )}

              {section === 'audit' && (
                <section className="audit-list">
                  <div className="section-tools"><span>{eventsBusy ? t('正在載入') : t('最近 {{count}} 筆操作', { count: formatNumber(events.length) })}</span><span>{t('稽核資料由服務端記錄')}</span></div>
                  {eventsBusy && <Skeleton active />}
                  {!eventsBusy && events.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('目前沒有稽核事件')} />}
                  {events.map((event) => <AuditRow key={event.id} event={event} actor={nameFor(event.actor_id, collaborators, principal)} />)}
                </section>
              )}
            </>
          )}
        </div>
      </main>

      <Drawer
        title={<div className="drawer-title"><div><span className="task-key">{selectedTask?.key ?? 'TASK'}</span><Title level={4}>{selectedTask?.title ?? t('任務詳情')}</Title></div>{selectedTask && taskStatusTag(selectedTask.status, t)}</div>}
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false);
          updateResourceQuery();
        }}
        width={620}
        className="task-drawer"
        destroyOnClose={false}
      >
        {taskContextError && <Alert type="error" showIcon message={t('任務脈絡無法載入')} description={t(taskContextError)} action={<Button size="small" onClick={() => void reloadTaskContext()}>{t('重試')}</Button>} />}
        {taskContextBusy && !taskContext && <Skeleton active paragraph={{ rows: 8 }} />}
        {selectedTask && (
          <>
            <div className="drawer-actions">
              <Button icon={<EditOutlined />} onClick={() => openEditTask(selectedTask)}>{t('編輯規格')}</Button>
              <Button icon={<SendOutlined />} onClick={() => { messageForm.resetFields(); setMessageModal({ open: true, taskId: selectedTask.id, kind: 'help_request' }); }}>{t('請求協作')}</Button>
              <Button icon={<CodeOutlined />} onClick={() => { delegateForm.resetFields(); delegateForm.setFieldsValue({ priority: 'medium', acceptance_criteria: '', budget_usd: 0 }); setDelegateOpen(true); }}>{t('委派子任務')}</Button>
            </div>
            <div className="claim-bar">
              {!lease && selectedTask.status === 'ready' && mayClaimDirectly && <Button type="primary" icon={<CheckOutlined />} onClick={() => void claimTask()}>{t('認領任務')}</Button>}
              {!lease && principal.kind === 'human' && canManageAgents && !selectedTask.assignee_principal_id && selectedTask.status === 'ready' && <>
                <Select aria-label={t('選擇代執行 Agent')} placeholder={t('選擇執行 Agent')} value={claimAgentId} onChange={setClaimAgentId} options={people.filter((agent) => agent.status === 'available' && agent.role === 'worker' && (!selectedTask.assignee_id || selectedTask.assignee_id === agent.id)).map((agent) => ({ value: agent.id, label: <Space size={6}><span>{agent.name}</span><Tag color="purple">{t('Agent')}</Tag></Space> }))} className="claim-agent-select" />
                <Button icon={<UserAddOutlined />} onClick={() => void claimTask(claimAgentId)} disabled={!claimAgentId || !people.some((agent) => agent.id === claimAgentId && agent.role === 'worker' && agent.status === 'available' && (!selectedTask.assignee_id || agent.id === selectedTask.assignee_id))}>{t('代 Agent 認領')}</Button>
              </>}
              {!lease && principal.kind === 'human' && canManageAgents && selectedTask.assignee_id && !selectedTask.assignee_principal_id && selectedTask.status === 'ready' && dispatchAgents.length > 0 && <>
                <Tag color="purple">{t('平台 Agent：{{name}}', { name: dispatchAgents[0].name })}</Tag>
                <Button icon={<SendOutlined />} onClick={() => void dispatchSelectedTask()} disabled={dispatchBusy} loading={dispatchBusy}>{t('派發給 Agent')}</Button>
              </>}
              {lease && <Tag color="green" icon={<CheckCircleOutlined />}>{t(lease.lease_token ? '目前工作階段持有執行租約' : '目前由你執行')}</Tag>}
              {selectedTask.status === 'blocked' && ['admin', 'manager'].includes(principal.role) && <Button type="primary" onClick={() => void unblockTask()}>{t('解除阻塞')}</Button>}
            </div>
            {lease && (
              <div className="lease-panel">
                <div className="lease-heading"><span><ClockCircleOutlined /> {t('執行控制')}</span><span>{lease.lease_token ? t('租約到期 {{date}}', { date: displayDate(lease.execution.lease_expires_at) }) : t('真人工作由執行者持續保留')}</span></div>
                <Progress percent={selectedTask.progress ?? lease.execution.progress ?? 0} size="small" />
                <Space wrap>
                  {lease.lease_token && <Button size="small" icon={<ReloadOutlined />} onClick={() => void renewLease()}>{t('延長租約')}</Button>}
                  <Button size="small" onClick={() => { operationForm.resetFields(); operationForm.setFieldsValue({ progress: selectedTask.progress, summary: lease.execution.summary ?? '' }); setOperationModal('progress'); }}>{t('回報進度')}</Button>
                  <Button size="small" onClick={() => { operationForm.resetFields(); operationForm.setFieldsValue({ kind: 'summary', artifact_title: t('{{key}} 執行摘要', { key: selectedTask.key }) }); setOperationModal('submit'); }}>{t('提交成果')}</Button>
                  <Button size="small" onClick={() => { operationForm.resetFields(); setOperationModal('release'); }}>{t('交接並釋出')}</Button>
                  <Button size="small" danger onClick={() => { operationForm.resetFields(); setOperationModal('block'); }}>{t('標記受阻')}</Button>
                </Space>
                <Text className="lease-footnote">{t(lease.lease_token ? 'Agent 執行租約與 fencing token 僅保留在此分頁記憶體。' : '真人執行記錄會從任務脈絡恢復，不需要 LLM 或租約。')}</Text>
              </div>
            )}
            <Tabs
              className="detail-tabs"
              items={[
                {
                  key: 'spec', label: t('規格'), children: taskContextBusy && !taskContext ? <Spin /> : <TaskSpecification task={selectedTask} context={taskContext} participants={collaborators} />,
                },
                {
                  key: 'execution', label: t('執行與審核'), children: <ExecutionReview context={taskContext} agents={people} participants={collaborators} canReview={canReview} projectId={selectedTask.project_id} hasLease={Boolean(lease)} onUsePullRequest={useExistingPullRequest} onReview={(decision) => { reviewForm.resetFields(); setReviewDecision(decision); }} />,
                },
                {
                  key: 'collaboration', label: taskContext?.messages.length ? t('協作（{{count}}）', { count: formatNumber(taskContext.messages.length) }) : t('協作'), children: <TaskCollaboration context={taskContext} people={collaborators} principal={principal} onReply={(item) => { messageForm.resetFields(); setMessageModal({ open: true, replyTo: item }); }} />,
                },
                {
                  key: 'history', label: t('事件'), children: <div className="compact-event-list">{taskContext?.events.map((event) => <AuditRow key={event.id} event={event} actor={nameFor(event.actor_id, collaborators, principal)} />) ?? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('尚無事件')} />}</div>,
                },
              ]}
            />
            <CollaborationPanel
              product="work"
              kind="task"
              resourceId={selectedTask.id}
              canWrite={Boolean(principal && ['admin', 'manager', 'worker', 'reviewer'].includes(principal.role))}
            />
          </>
        )}
      </Drawer>

      <Modal title={t(editingTask ? '編輯任務規格' : '建立任務')} open={taskModalOpen} onCancel={() => setTaskModalOpen(false)} onOk={() => taskForm.submit()} confirmLoading={taskSaving} okText={t(editingTask ? '儲存變更' : '建立任務')} cancelText={t('取消')} width={760} destroyOnClose>
        <Form form={taskForm} layout="vertical" onFinish={(values) => void saveTask(values)} className="form-grid">
          {participantsError && <Alert className="form-span" type="error" showIcon message={t('專案成員無法載入')} description={t(participantsError)} action={<Button size="small" loading={participantsBusy} onClick={() => void retryParticipants()}>{t('重試')}</Button>} />}
          <Form.Item name="title" label={t('任務名稱')} rules={[{ required: true, message: t('請輸入任務名稱') }]}><Input maxLength={180} /></Form.Item>
          <Form.Item name="priority" label={t('優先級')} rules={[{ required: true }]}><Select options={[{ value: 'urgent', label: t('緊急') }, { value: 'high', label: t('高') }, { value: 'medium', label: t('一般') }, { value: 'low', label: t('低') }]} /></Form.Item>
          <Form.Item name="description" label={t('描述')} className="form-span"><TextArea rows={2} /></Form.Item>
          <Form.Item name="goal" label={t('目標')}><TextArea rows={2} /></Form.Item>
          <Form.Item name="inputs" label={t('輸入資料')}><TextArea rows={2} /></Form.Item>
          <Form.Item name="scope" label={t('範圍')}><TextArea rows={2} /></Form.Item>
          <Form.Item name="constraints" label={t('限制條件')}><TextArea rows={2} /></Form.Item>
          <Form.Item name="acceptance_criteria" label={t('驗收條件')} className="form-span" extra={t('每行一項')}><TextArea rows={3} /></Form.Item>
          <Form.Item name="assignee" label={t('負責者')}><Select allowClear loading={participantsBusy} placeholder={t('未指派')} options={collaborators.filter((participant) => participant.role === 'worker' || (participant.kind === 'human' && ['manager', 'admin'].includes(participant.role))).map((participant) => participantOption(participant, t))} /></Form.Item>
          <Form.Item name="reviewer" label={t('指定審核者')}><Select allowClear loading={participantsBusy} placeholder={t('未指定')} options={collaborators.filter((participant) => participant.role === 'reviewer' || (participant.kind === 'human' && ['manager', 'admin'].includes(participant.role))).map((participant) => participantOption(participant, t))} /></Form.Item>
          <Form.Item name="dependency_ids" label={t('相依任務')} className="form-span"><Select mode="multiple" placeholder={t('選擇必須先完成的任務')} options={tasks.filter((task) => task.id !== editingTask?.id).map((task) => ({ value: task.id, label: `${task.key} · ${task.title}` }))} /></Form.Item>
          <Form.Item name="labels" label={t('標籤')}><Select mode="tags" tokenSeparators={[',']} placeholder={t('輸入後按 Enter')} /></Form.Item>
          <Form.Item name="budget_usd" label={t('預算上限 (USD)')}><InputNumber min={0} precision={2} className="full-width" /></Form.Item>
          {!editingTask && <div className="form-note form-span">{t('新任務會依服務端預設進入待執行狀態。狀態轉換由受保護的工作流程操作管理。')}</div>}
        </Form>
      </Modal>

      {companionProject && <ProjectCompanionsModal key={companionProject.id} project={companionProject} onClose={() => setCompanionProject(null)} />}

      {canCreateProject && <Modal title={t('建立專案')} open={projectModalOpen} onCancel={() => setProjectModalOpen(false)} onOk={() => projectForm.submit()} confirmLoading={projectSaving} okText={t('建立專案')} cancelText={t('取消')} destroyOnClose>
        <Form form={projectForm} layout="vertical" onFinish={(values) => void saveProject(values)}>
          <Form.Item name="key" label={t('專案代碼')} rules={[{ required: true, message: t('請輸入專案代碼') }]}><Input maxLength={12} placeholder={t('例如 ORD')} /></Form.Item>
          <Form.Item name="name" label={t('專案名稱')} rules={[{ required: true, message: t('請輸入專案名稱') }]}><Input maxLength={120} /></Form.Item>
          <Form.Item name="description" label={t('描述')}><TextArea rows={3} /></Form.Item>
          <Form.Item name="team_id" label={t('團隊 ID')}><Input /></Form.Item>
          <Form.Item name="budget_usd" label={t('預算上限 (USD)')}><InputNumber min={0} precision={2} className="full-width" /></Form.Item>
        </Form>
      </Modal>}

      <Modal className="agent-execution-modal" title={editingAgent ? t('編輯 Agent · {{name}}', { name: editingAgent.name }) : t('新增 Agent')} open={agentModalOpen} onCancel={() => { setAgentModalOpen(false); setEditingAgent(null); }} onOk={() => agentForm.submit()} confirmLoading={agentSaving} okButtonProps={{ disabled: agentRuntime === 'pi' && agentModelMode === 'override' && (modelCatalogLoading || Boolean(modelCatalogError)) }} okText={editingAgent ? t('儲存變更') : t('建立 Agent')} cancelText={t('取消')} width={760} destroyOnClose>
        <Form form={agentForm} layout="vertical" onFinish={(values) => void saveAgent(values)}>
          <Form.Item name="template_id" label={t('Agent 範本版本')} extra={<>{t('選擇後會套用此不可變版本；可再調整執行設定。')}{selectedAgentTemplate && <div>{localizeAgentTemplate(selectedAgentTemplate).description}</div>}</>}>
            <Select
              allowClear
              loading={agentExecutionOptionsLoading}
              placeholder={t('不套用範本')}
              options={agentTemplates.filter((template) => !editingAgent || template.definition.role === editingAgent.role).map((template) => ({ value: template.id, label: `${template.builtin_key ? `${t('內建')} · ` : ''}${localizeAgentTemplate(template).name} · v${formatNumber(template.version)}` }))}
              onChange={(templateId: string | undefined) => {
                if (!templateId) {
                  agentForm.setFieldValue('template_id', undefined);
                  return;
                }
                const template = agentTemplates.find((item) => item.id === templateId);
                if (template) applyTemplateToAgentForm(template);
              }}
            />
          </Form.Item>
          <Form.Item name="name" label={t('名稱')} rules={[{ required: true }]}><Input maxLength={100} disabled={Boolean(editingAgent)} /></Form.Item>
          <Form.Item name="role" label={t('角色')} rules={[{ required: true }]}><Select disabled={Boolean(editingAgent)} options={[{ value: 'worker', label: t('執行者') }, { value: 'reviewer', label: t('審核者') }]} /></Form.Item>
          <Form.Item name="runtime" label={t('執行方式')} rules={[{ required: true }]} extra={<>{agentRuntime === 'pi' ? t('使用已設定的模型，由平台啟動與追蹤 Agent；需管理員啟用執行服務。') : t('由你自行串接的程式透過 API 或 MCP 認領任務、回報進度與成果；平台不會啟動它。')}{editingAgent && <div>{t('建立後無法變更執行方式。')}</div>}</>}>
            <Select disabled={Boolean(editingAgent)} options={[{ value: 'pi', label: t('由平台執行（建議）') }, { value: 'external', label: t('由外部程式執行') }]} />
          </Form.Item>
          {agentExecutionOptionsError.length > 0 && <Alert className="agent-execution-alert" type="error" showIcon message={t('範本或執行資源無法完整載入')} description={<div>{agentExecutionOptionsError.map(({ source, error }, index) => <div key={`${source}-${index}`}>{t(source, { error: t(error) })}</div>)}</div>} action={<Button size="small" loading={agentExecutionOptionsLoading} onClick={() => void loadAgentExecutionOptions()}>{t('重試')}</Button>} />}
          <AgentModelConfigFields
            form={agentForm}
            catalog={modelCatalog}
            catalogLoading={modelCatalogLoading}
            catalogError={modelCatalogError ? t(modelCatalogError) : ''}
            agent={editingAgent}
            onRetry={() => void loadModelCatalog()}
          />
          <Form.Item name="capabilities" label={t('能力標籤')}><Select mode="tags" tokenSeparators={[',']} placeholder="frontend, testing" /></Form.Item>
          <div className="agent-execution-fields">
            <div className="agent-execution-heading"><strong>{t('Agent 工作設定')}</strong><Text type="secondary">{t('套用於新 Run；已建立的 Run 保留當時快照。')}</Text></div>
            <Form.Item name={['execution_config', 'instructions']} label={t('Agent 指令')}><TextArea rows={4} maxLength={16000} showCount /></Form.Item>
            <div className="agent-execution-grid">
              <Form.Item name={['execution_config', 'tool_connection_ids']} label={t('可用工具連線')} rules={[{ validator: async (_, value: string[]) => { if ((value?.length ?? 0) > 30) throw new Error(t('工具連線最多 {{count}} 個', { count: formatNumber(30) })); } }]}><Select mode="multiple" maxCount={30} allowClear placeholder={t('不綁定外部連線')} options={agentToolConnections.map((connection) => ({ value: connection.id, label: `${connection.name}${connection.enabled ? '' : ` · ${t('已停用')}`}`, disabled: !connection.enabled }))} /></Form.Item>
              <Form.Item name={['execution_config', 'sandbox_profile_id']} label={t('Sandbox 設定檔')}><Select allowClear placeholder={t('不使用 Sandbox')} options={agentSandboxProfiles.map((profile) => ({ value: profile.id, label: `${profile.name}${profile.enabled ? '' : ` · ${t('已停用')}`}`, disabled: !profile.enabled }))} /></Form.Item>
              <Form.Item name={['execution_config', 'limits', 'max_turns']} label={t('最多模型回合')} rules={[{ required: true, type: 'number', min: 1, max: 100 }]}><InputNumber className="full-width" min={1} max={100} precision={0} /></Form.Item>
              <Form.Item name={['execution_config', 'limits', 'timeout_seconds']} label={t('執行逾時（秒）')} rules={[{ required: true, type: 'number', min: 30, max: 3600 }]}><InputNumber className="full-width" min={30} max={3600} precision={0} /></Form.Item>
            </div>
          </div>
          <Form.Item name="team_id" label={t('團隊 ID')}><Input disabled={Boolean(editingAgent)} /></Form.Item>
        </Form>
      </Modal>

      <Modal title={t(messageModal.replyTo ? '回覆訊息' : messageModal.kind === 'help_request' ? '請求協作' : '傳送訊息')} open={messageModal.open} onCancel={() => setMessageModal({ open: false })} onOk={() => messageForm.submit()} confirmLoading={messageSaving} okText={t('送出')} cancelText={t('取消')} destroyOnClose>
        <Form form={messageForm} layout="vertical" onFinish={(values) => void sendProjectMessage(values)}>
          {participantsError && !messageModal.replyTo && <Alert className="form-span" type="error" showIcon message={t('專案成員無法載入')} description={t(participantsError)} action={<Button size="small" loading={participantsBusy} onClick={() => void retryParticipants()}>{t('重試')}</Button>} />}
          <Form.Item label={t('專案')}>{currentProject ? `${currentProject.key} · ${currentProject.name}` : '—'}</Form.Item>
          {messageModal.replyTo && <Form.Item label={t('回覆對象')}><IdentityLabel id={messageModal.replyTo.sender_id} participants={collaborators} principal={principal} /></Form.Item>}
          {!messageModal.replyTo && <>
            <Form.Item name="recipient_id" label={t('收件者')} rules={messageModal.kind === 'help_request' ? [{ required: true, message: t('請選擇要求協作的同事或 Agent') }] : []}><Select allowClear loading={participantsBusy} placeholder={t('專案訊息（不指定收件者）')} options={collaborators.map((participant) => participantOption(participant, t))} /></Form.Item>
            <Form.Item name="kind" label={t('訊息類型')} initialValue={messageModal.kind ?? 'question'}><Select options={[{ value: 'question', label: t('問題') }, { value: 'help_request', label: t('求助') }, { value: 'decision', label: t('決議') }, { value: 'handoff', label: t('交接') }]} /></Form.Item>
          </>}
          <Form.Item name="body" label={t('訊息內容')} rules={[{ required: true, whitespace: true, message: t('請輸入訊息內容') }]}><TextArea rows={5} maxLength={5000} showCount /></Form.Item>
        </Form>
      </Modal>

      <Modal title={t('委派子任務')} open={delegateOpen} onCancel={() => setDelegateOpen(false)} onOk={() => delegateForm.submit()} confirmLoading={delegateSaving} okText={t('委派任務')} cancelText={t('取消')} destroyOnClose>
        <Form form={delegateForm} layout="vertical" onFinish={(values) => void delegateTask(values)}>
          {participantsError && <Alert type="error" showIcon message={t('專案成員無法載入')} description={t(participantsError)} action={<Button size="small" loading={participantsBusy} onClick={() => void retryParticipants()}>{t('重試')}</Button>} />}
          <Form.Item name="delegatee" label={t('委派對象')} rules={[{ required: true }]}><Select loading={participantsBusy} options={collaborators.filter((participant) => participant.role === 'worker' || (participant.kind === 'human' && ['manager', 'admin'].includes(participant.role))).map((participant) => participantOption(participant, t))} /></Form.Item>
          <Form.Item name="title" label={t('子任務名稱')} rules={[{ required: true }]}><Input maxLength={180} /></Form.Item>
          <Form.Item name="goal" label={t('交付目標')} rules={[{ required: true }]}><TextArea rows={2} /></Form.Item>
          <Form.Item name="description" label={t('描述')}><TextArea rows={2} /></Form.Item>
          <Form.Item name="scope" label={t('範圍')}><TextArea rows={2} /></Form.Item>
          <Form.Item name="inputs" label={t('輸入資料')}><TextArea rows={2} /></Form.Item>
          <Form.Item name="constraints" label={t('限制條件')}><TextArea rows={2} /></Form.Item>
          <Form.Item name="acceptance_criteria" label={t('驗收條件')} extra={t('每行一項')}><TextArea rows={3} /></Form.Item>
          <Form.Item name="priority" label={t('優先級')}><Select options={[{ value: 'urgent', label: t('緊急') }, { value: 'high', label: t('高') }, { value: 'medium', label: t('一般') }, { value: 'low', label: t('低') }]} /></Form.Item>
          <Form.Item name="budget_usd" label={t('預算上限 (USD)')}><InputNumber min={0} precision={2} className="full-width" /></Form.Item>
        </Form>
      </Modal>

      <Modal title={operationTitle(operationModal, t)} open={operationModal !== null} onCancel={() => setOperationModal(null)} onOk={() => operationForm.submit()} confirmLoading={operationSaving} okText={t('送出')} cancelText={t('取消')} destroyOnClose>
        <Form form={operationForm} layout="vertical" onFinish={(values) => void runTaskOperation(values)}>
          {operationModal === 'progress' && <>
            <Form.Item name="progress" label={t('完成進度')} rules={[{ required: true }]}><InputNumber min={0} max={99} addonAfter="%" className="full-width" /></Form.Item>
            <Form.Item name="summary" label={t('執行摘要')}><TextArea rows={3} /></Form.Item>
            <Form.Item name="cost_usd" label={t('自陳成本 (USD)')}><InputNumber min={0} precision={4} className="full-width" /></Form.Item>
          </>}
          {operationModal === 'submit' && <>
            <Form.Item name="summary" label={t('完成摘要')} rules={[{ required: true, whitespace: true }]}><TextArea rows={4} /></Form.Item>
            <Divider orientation="left" plain>{t('驗收證據')}</Divider>
            <Form.Item name="kind" label={t('證據類型')} rules={[{ required: true }]}><Select options={[{ value: 'summary', label: t('摘要') }, { value: 'document', label: t('文件') }, { value: 'url', label: t('網址') }, { value: 'test_report', label: t('測試報告') }, { value: 'file', label: t('檔案') }]} /></Form.Item>
            <Form.Item name="artifact_title" label={t('證據標題')} rules={[{ required: true }]}><Input /></Form.Item>
            <Form.Item name="uri" label="URI"><Input prefix={<LinkOutlined />} placeholder={t('可選')} /></Form.Item>
            <Form.Item name="content" label={t('證據內容')}><TextArea rows={3} /></Form.Item>
            <Form.Item name="cost_usd" label={t('自陳成本 (USD)')}><InputNumber min={0} precision={4} className="full-width" /></Form.Item>
            <div className="form-note">{t('成本為執行者回報，不代表已驗證的付費模型用量。')}</div>
          </>}
          {operationModal === 'block' && <>
            <Form.Item name="reason" label={t('阻塞原因')} rules={[{ required: true, whitespace: true }]}><TextArea rows={3} /></Form.Item>
            <Form.Item name="handoff" label={t('交接資訊')}><TextArea rows={3} /></Form.Item>
          </>}
          {operationModal === 'release' && <Form.Item name="handoff" label={t('交接資訊')} rules={[{ required: true, whitespace: true }]}><TextArea rows={4} /></Form.Item>}
        </Form>
      </Modal>

      <Modal title={t(reviewDecision === 'accept' ? '通過審核' : '退回任務')} open={reviewDecision !== null} onCancel={() => setReviewDecision(null)} onOk={() => reviewForm.submit()} confirmLoading={reviewSaving} okText={t(reviewDecision === 'accept' ? '確認通過' : '確認退回')} cancelText={t('取消')} destroyOnClose>
        <Form form={reviewForm} layout="vertical" onFinish={(values) => void reviewTask(values)}>
          <Alert className="review-separation-note" type="info" showIcon message={t('獨立審核')} description={t('審核決定由服務端檢查角色、指定審核者與執行者分離。')} />
          <Form.Item name="comment" label={t('審核意見')} rules={[{ required: true, whitespace: true, message: t('請填寫審核意見') }]}><TextArea rows={4} /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

function Metric({ label, value, loading }: { label: string; value?: number; loading: boolean }) {
  const { t } = useI18n();
  return <div className="metric-item"><span>{t(label)}</span>{loading ? <Skeleton.Input active size="small" /> : <strong>{value === undefined ? '—' : formatNumber(value)}</strong>}</div>;
}

function operationTitle(operation: TaskOperation | null, t = translate): string {
  return t(({ progress: '回報執行進度', submit: '提交成果與證據', block: '標記任務受阻', release: '交接並釋出任務' } as Record<string, string>)[operation ?? ''] ?? '執行操作');
}

function OverviewView({
  overview,
  loading,
  project,
  events,
  agents,
  onSelectTask,
}: {
  overview: Overview | null;
  loading: boolean;
  project: Project | null;
  events: AuditEvent[];
  agents: Agent[];
  onSelectTask: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="overview-page">
      <section className="overview-intro">
        <div><Text className="eyebrow">{project?.key ?? 'PROJECT'}</Text><Title level={3}>{project?.name ?? t('專案')}</Title><Paragraph>{project?.description || t('專案工作狀態與資源概況')}</Paragraph></div>
        <div className="overview-budget"><span>{t('預算額度')}</span><strong>{money(project?.budget_usd)}</strong></div>
      </section>
      <section className="overview-metrics">
        {[
          ['待整理', overview?.counts.total === undefined ? undefined : Math.max(0, overview.counts.total - overview.counts.ready - overview.counts.in_progress - overview.counts.blocked - overview.counts.in_review - overview.counts.done)],
          ['待執行', overview?.counts.ready],
          ['進行中', overview?.counts.in_progress],
          ['受阻', overview?.counts.blocked],
          ['待審核', overview?.counts.in_review],
          ['已完成', overview?.counts.done],
        ].map(([label, value]) => <div className="overview-metric" key={String(label)}><span>{t(String(label))}</span><strong>{loading || value === undefined ? '—' : formatNumber(Number(value))}</strong></div>)}
      </section>
      <div className="overview-columns">
        <section className="overview-section">
          <div className="section-heading"><div><Text className="eyebrow">{t('執行資源')}</Text><Title level={4}>{t('Agent 與成本')}</Title></div><Button type="link" onClick={onSelectTask}>{t('開啟任務清單')}</Button></div>
          <div className="overview-row"><span>{t('Agent 總數')}</span><strong>{loading ? '—' : formatNumber(overview?.agents.total ?? agents.length)}</strong></div>
          <div className="overview-row"><span>{t('可用')}</span><strong>{loading ? '—' : formatNumber(overview?.agents.available ?? agents.filter((agent) => agent.status === 'available').length)}</strong></div>
          <div className="overview-row"><span>{t('執行中')}</span><strong>{loading ? '—' : formatNumber(overview?.agents.busy ?? agents.filter((agent) => agent.status === 'busy').length)}</strong></div>
          <div className="overview-row"><span>{t('執行成本彙總')}</span><strong>{loading ? '—' : money(overview?.cost_usd)}</strong></div>
          <div className="overview-cost-note"><WarningOutlined /> {t('成本彙總不是付費模型用量驗證。請在執行明細確認來源是自陳或量測。')}</div>
        </section>
        <section className="overview-section">
          <div className="section-heading"><div><Text className="eyebrow">{t('最近紀錄')}</Text><Title level={4}>{t('專案動態')}</Title></div></div>
          {loading && <Skeleton active paragraph={{ rows: 4 }} />}
          {!loading && events.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('目前沒有操作紀錄')} />}
          {!loading && events.slice(0, 8).map((event) => <div className="overview-activity" key={event.id}><span className="activity-dot" /><div><strong>{event.action.replaceAll('_', ' ')}</strong><span>{event.entity_type} · {event.entity_id.slice(0, 8)}</span></div><time>{displayDate(event.created_at)}</time></div>)}
        </section>
      </div>
    </div>
  );
}

function TaskSpecification({ task, context, participants }: { task: Task; context: TaskContext | null; participants: ProjectParticipant[] }) {
  const { t } = useI18n();
  const dependencyTasks = context?.dependencies ?? [];
  return (
    <div className="spec-view">
      <Descriptions column={1} size="small" colon={false}>
        <Descriptions.Item label={t('負責者')}><TaskAssignmentLabel assignment={taskAssignment(task, 'assignee', participants)} /></Descriptions.Item>
        <Descriptions.Item label={t('審核者')}><TaskAssignmentLabel assignment={taskAssignment(task, 'reviewer', participants)} /></Descriptions.Item>
        <Descriptions.Item label={t('預算上限')}>{money(task.budget_usd)}</Descriptions.Item>
        <Descriptions.Item label={t('建立時間')}>{displayDate(task.created_at)}</Descriptions.Item>
      </Descriptions>
      <SpecBlock title={t('描述')} value={task.description} />
      <SpecBlock title={t('目標')} value={task.goal} />
      <SpecBlock title={t('輸入資料')} value={task.inputs} />
      <SpecBlock title={t('範圍')} value={task.scope} />
      <SpecBlock title={t('限制條件')} value={task.constraints} />
      <div className="spec-block"><h4>{t('驗收條件')}</h4>{task.acceptance_criteria.length ? <ul>{task.acceptance_criteria.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul> : <span className="empty-value">{t('尚未設定')}</span>}</div>
      <div className="spec-block"><h4>{t('相依任務')}</h4>{dependencyTasks.length ? <div className="dependency-list">{dependencyTasks.map((dependency) => <Tag key={dependency.id} color={dependency.status === 'done' ? 'green' : 'default'}>{dependency.key} · {dependency.title}</Tag>)}</div> : task.dependency_ids.length ? <span>{task.dependency_ids.join(', ')}</span> : <span className="empty-value">{t('無')}</span>}</div>
      {task.blocked_reason && <Alert type="error" showIcon icon={<ExclamationCircleOutlined />} message={t('阻塞原因')} description={task.blocked_reason} />}
      {task.handoff && <SpecBlock title={t('交接資訊')} value={task.handoff} />}
      {task.labels.length > 0 && <div className="spec-block"><h4>{t('標籤')}</h4><Space wrap>{task.labels.map((label) => <Tag key={label}>{label}</Tag>)}</Space></div>}
    </div>
  );
}

function SpecBlock({ title, value }: { title: string; value?: string | null }) {
  const { t } = useI18n();
  return <div className="spec-block"><h4>{t(title)}</h4>{value ? <MarkdownContent content={value} /> : <span className="empty-value">{t('尚未設定')}</span>}</div>;
}

function ExecutionReview({ context, agents, participants, canReview, projectId, hasLease, onUsePullRequest, onReview }: { context: TaskContext | null; agents: Agent[]; participants: ProjectParticipant[]; canReview: boolean; projectId: string; hasLease: boolean; onUsePullRequest: (result: ExistingPullRequest) => void; onReview: (decision: 'accept' | 'reject') => void }) {
  const { t } = useI18n();
  return (
    <div className="execution-view">
      {!context && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('載入執行記錄中')} />}
      {context && <>
      {context.task.status === 'in_review' && (
        <div className="review-panel">
          <div className="review-heading"><div><span className="eyebrow">{t('獨立審核')}</span><h3>{t('審核決定')}</h3></div><Tag color="gold">{t('待審核')}</Tag></div>
          {canReview ? <Space><Button type="primary" icon={<CheckOutlined />} onClick={() => onReview('accept')}>{t('通過')}</Button><Button danger icon={<CloseOutlined />} onClick={() => onReview('reject')}>{t('退回')}</Button></Space> : <Text type="secondary">{t('目前身分未符合指定審核權限，或執行者不可審核自己的成果。')}</Text>}
        </div>
      )}
      <div className="detail-section-heading"><h3>{t('執行歷程')}</h3><span>{t('{{count}} 筆', { count: formatNumber(context.executions.length) })}</span></div>
      {!context.executions.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('尚無執行記錄')} />}
      {context.executions.map((execution) => {
        const actorId = execution.executor_id ?? execution.claimed_by_principal_id ?? execution.agent_id;
        const participant = participants.find((person) => person.id === actorId || person.principal_id === actorId || person.principal_id === execution.claimed_by_principal_id);
        const agent = agents.find((item) => item.id === execution.agent_id || item.id === execution.executor_id);
        const executorKind = execution.executor_kind ?? participant?.kind ?? (execution.agent_id ? 'agent' : execution.claimed_by_principal_id ? 'human' : null);
        const executorName = execution.executor_name ?? participant?.name ?? agent?.name ?? (actorId ? nameFor(actorId, [...participants, ...agents]) : t('未知執行者'));
        return <ExecutionRow key={execution.id} execution={execution} executorName={executorName} executorKind={executorKind} />;
      })}
      <div className="detail-section-heading evidence-heading"><h3>{t('成果與證據')}</h3><span>{t('{{count}} 項', { count: formatNumber(context.artifacts.length) })}</span></div>
      {!context.artifacts.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('尚無提交證據')} />}
      {context.artifacts.map((artifact) => <ArtifactRow key={artifact.id} artifact={artifact} />)}
      </>}
      <ExistingPullRequestLookup projectId={projectId} hasLease={hasLease} onUseResult={onUsePullRequest} />
    </div>
  );
}

function ExistingPullRequestLookup({ projectId, hasLease, onUseResult }: { projectId: string; hasLease: boolean; onUseResult: (result: ExistingPullRequest) => void }) {
  const { t } = useI18n();
  const [provider, setProvider] = useState<ExistingPullRequest['provider']>('github');
  const [repository, setRepository] = useState('');
  const [number, setNumber] = useState<number | null>(null);
  const [result, setResult] = useState<ExistingPullRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function lookup() {
    const normalizedRepository = repository.trim();
    if (!normalizedRepository || number === null || number < 1) return;
    setBusy(true);
    setError('');
    setResult(null);
    const params = new URLSearchParams({ repository: normalizedRepository });
    try {
      const response = await api.get<ExistingPullRequest>(`/api/projects/${encodeURIComponent(projectId)}/vcs/pulls/${provider}/${number}?${params.toString()}`);
      setResult(response);
    } catch (lookupError) {
      setError(errorText(lookupError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="existing-pr-lookup" aria-labelledby="existing-pr-title">
      <div className="detail-section-heading"><h3 id="existing-pr-title">{t('查詢既有 PR / MR')}</h3><span>{t('專案版控')}</span></div>
      <div className="existing-pr-fields">
        <Select aria-label={t('版控服務')} value={provider} onChange={(value: ExistingPullRequest['provider']) => setProvider(value)} options={[{ value: 'github', label: 'GitHub' }, { value: 'gitlab', label: 'GitLab' }, { value: 'gitea', label: 'Gitea' }]} />
        <Input aria-label={t('儲存庫 owner/repo')} placeholder="owner/repo" value={repository} onChange={(event) => setRepository(event.target.value)} onPressEnter={() => void lookup()} />
        <InputNumber aria-label={t('PR 或 MR 編號')} min={1} precision={0} placeholder="#" value={number} onChange={setNumber} onPressEnter={() => void lookup()} />
        <Button type="primary" onClick={() => void lookup()} loading={busy} disabled={!repository.trim() || !number || number < 1}>{t('查詢')}</Button>
      </div>
      <Text className="existing-pr-help">{t('使用此專案已設定的 provider allowlist。尚未設定時會顯示服務端錯誤。')}</Text>
      {error && <Alert className="existing-pr-result-alert" type="error" showIcon message={t('既有版控查詢失敗')} description={t(error)} />}
      {result && <div className="existing-pr-result">
        <div className="existing-pr-result-heading"><div><Tag color={result.state === 'open' ? 'green' : 'default'}>{result.state}</Tag><strong>{result.provider} · {result.repository}#{formatNumber(result.number)}</strong></div><span>{t('資料來源：provider API')}</span></div>
        <strong className="existing-pr-title-text">{result.title}</strong>
        {safeWebUrl(result.web_url) ? <a href={safeWebUrl(result.web_url)!} target="_blank" rel="noreferrer">{result.web_url}</a> : <code>{result.web_url}</code>}
        <div className="existing-pr-meta"><span>Base <code>{result.base}</code></span><span>Head <code>{result.head}</code></span><span>SHA <code>{result.head_sha.slice(0, 12)}</code></span></div>
        <div className="existing-pr-checks"><strong>{t('Provider checks')}</strong>{result.checks_available ? result.checks.length ? result.checks.map((check, index) => <div className="existing-pr-check" key={`${check.context}-${index}`}><Tag>{check.state}</Tag><span>{check.context}{check.description ? ` · ${check.description}` : ''}</span>{safeWebUrl(check.target_url) && <a href={safeWebUrl(check.target_url)!} target="_blank" rel="noreferrer">{t('查看')}</a>}</div>) : <Text type="secondary">{t('Provider API 未回傳 check 項目。')}</Text> : <Text type="secondary">{t('此 provider 未提供 checks API。平台未執行 CI。')}</Text>}</div>
        {hasLease && <Button size="small" onClick={() => onUseResult(result)}>{t('帶入成果草稿')}</Button>}
        {!hasLease && <Text type="secondary">{t('持有此分頁的執行租約後，可將 URL 與查詢摘要帶入提交成果。')}</Text>}
      </div>}
    </section>
  );
}

function ExecutionRow({ execution, executorName, executorKind }: { execution: Execution; executorName: string; executorKind: 'human' | 'agent' | 'runtime' | null }) {
  const { t } = useI18n();
  const labels: Record<string, string> = { running: '執行中', submitted: '已提交', accepted: '已通過', rejected: '已退回', expired: '租約逾期', released: '已釋出' };
  return (
    <div className="execution-row">
      <div className="execution-mark"><span /></div>
      <div className="execution-body">
        <div className="execution-top"><strong>{labels[execution.status] ? t(labels[execution.status]) : execution.status}</strong><span>{displayDate(execution.started_at)}</span></div>
        {execution.summary && <MarkdownContent content={execution.summary} />}
        {execution.status === 'running' && <Progress percent={execution.progress} size="small" />}
        <div className="execution-meta">{executorKind && <Tag color={executorKind === 'human' ? 'cyan' : 'purple'}>{t(executorKind === 'human' ? '真人' : executorKind === 'agent' ? 'Agent' : '執行服務')}</Tag>}<Tag>{executorName}</Tag><span>{money(execution.cost_usd)}</span><Tag color={execution.cost_source === 'self_reported' ? 'orange' : 'green'}>{t(execution.cost_source === 'self_reported' ? '自陳' : '量測')}</Tag>{execution.finished_at && <span>{displayDate(execution.finished_at)}</span>}</div>
      </div>
    </div>
  );
}

function ArtifactRow({ artifact }: { artifact: Artifact }) {
  const { t } = useI18n();
  const safeUri = safeWebUrl(artifact.uri);
  const kinds: Record<string, string> = { document: '文件', url: '網址', test_report: '測試報告', file: '檔案', summary: '摘要' };
  return (
    <div className="artifact-row"><div className="artifact-icon">{artifact.kind === 'url' ? <LinkOutlined /> : <FileSearchOutlined />}</div><div className="artifact-body"><strong>{artifact.title}</strong><span>{kinds[artifact.kind] ? t(kinds[artifact.kind]) : artifact.kind} · {displayDate(artifact.created_at)}</span>{safeUri && <a href={safeUri} target="_blank" rel="noreferrer">{safeUri}</a>}{artifact.uri && !safeUri && <code className="artifact-uri">{artifact.uri}</code>}{artifact.content && <MarkdownContent content={artifact.content} />}</div></div>
  );
}

function TaskCollaboration({ context, people, principal, onReply }: { context: TaskContext | null; people: ProjectParticipant[]; principal: Principal; onReply: (item: ProjectMessage) => void }) {
  const { t } = useI18n();
  if (!context) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('載入協作記錄中')} />;
  const kinds: Record<string, string> = { question: '問題', reply: '回覆', help_request: '求助', decision: '決議', handoff: '交接' };
  const statuses: Record<string, string> = { delivered: '待處理', accepted: '已接收', completed: '已完成' };
  return (
    <div className="task-collaboration">
      {!context.messages.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('此任務尚無訊息')} />}
      {context.messages.map((item) => <div className="thread-message" key={item.id}><div className="thread-message-head"><Avatar size={26}>{nameFor(item.sender_id, people, principal).slice(0, 1).toUpperCase()}</Avatar><IdentityLabel id={item.sender_id} participants={people} principal={principal} /><Tag>{kinds[item.kind] ? t(kinds[item.kind]) : item.kind}</Tag><time>{displayDate(item.created_at)}</time></div><MarkdownContent content={item.body} /><div className="thread-message-foot"><Tag color={item.status === 'completed' ? 'green' : item.status === 'accepted' ? 'blue' : 'default'}>{statuses[item.status] ? t(statuses[item.status]) : item.status}</Tag><Button size="small" type="link" onClick={() => onReply(item)}>{t('回覆')}</Button></div></div>)}
    </div>
  );
}

function AuditRow({ event, actor }: { event: AuditEvent; actor: string }) {
  const { t } = useI18n();
  return (
    <div className="audit-row"><div className="audit-symbol"><AuditOutlined /></div><div className="audit-content"><div className="audit-title"><strong>{event.action.replaceAll('_', ' ')}</strong><span>{actor}</span><time>{displayDate(event.created_at)}</time></div><div className="audit-reference">{event.entity_type} · {event.entity_id}</div>{Object.keys(event.data ?? {}).length > 0 && <details><summary>{t('查看事件資料')}</summary><pre>{JSON.stringify(event.data, null, 2)}</pre></details>}</div></div>
  );
}
