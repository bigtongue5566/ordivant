import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert, Button, Card, Checkbox, Col, Divider, Empty, Form, Input,
  InputNumber, Modal, Row, Select, Space, Spin, Statistic, Switch, Table, Tabs, Tag, Tooltip, Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { FormInstance } from 'antd/es/form';
import {
  ArrowDownOutlined, ArrowUpOutlined, BarChartOutlined, CalendarOutlined,
  ClockCircleOutlined, DeleteOutlined, DownloadOutlined, EditOutlined, FilterOutlined, FormOutlined,
  ImportOutlined, PlusOutlined, ReloadOutlined, SaveOutlined, SettingOutlined, UnorderedListOutlined,
} from '@ant-design/icons';
import { api } from '../../api';
import { useNavigationState } from '../../shared/useNavigationState';
import { formatDate, formatNumber, t } from '../../i18n';
import type {
  IntakeFormDefinition, PlanningCapacityRow, PlanningField, PlanningMetadata, PlanningMilestone, PlanningReports,
  PlanningRule, PlanningSprint, PlanningStage, Priority, ProjectParticipant, SavedTaskQuery, Task,
  TaskStatus, TaskWorklog,
} from '../../types';
import './planning.css';

const { Text, Title } = Typography;
const BUILT_IN_COLUMNS: Array<{ status: TaskStatus; label: string }> = [
  { status: 'backlog', label: '待整理' }, { status: 'ready', label: '待執行' },
  { status: 'in_progress', label: '進行中' }, { status: 'blocked', label: '受阻' },
  { status: 'in_review', label: '待審核' }, { status: 'done', label: '已完成' },
  { status: 'cancelled', label: '已取消' },
];
const PRIORITIES: Priority[] = ['urgent', 'high', 'medium', 'low'];
const WORK_TYPES: NonNullable<Task['work_type']>[] = ['task', 'story', 'bug', 'epic'];
const STAGE_CATEGORIES = BUILT_IN_COLUMNS.map(({ status }) => status);
const RESOURCE_FORM_ID = 'planning-resource-form';
const dateInput = (value: string | null | undefined) => value ? new Date(new Date(value).getTime() - new Date(value).getTimezoneOffset() * 60000).toISOString().slice(0, 16) : '';
const dateValue = (value?: string | null) => value ? new Date(value).toISOString() : null;
const orderedTasks = (values: Task[]) => [...values].sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0) || a.created_at.localeCompare(b.created_at));
const errorText = (error: unknown) => error instanceof Error ? error.message : t('發生未預期的錯誤。');

type FilterState = { text: string; status: string; work_type: string; sprint_id: string; milestone_id: string; assignee_principal_id: string; overdue: boolean };
const EMPTY_FILTER: FilterState = { text: '', status: '', work_type: '', sprint_id: '', milestone_id: '', assignee_principal_id: '', overdue: false };
type ResourceKind = 'sprint' | 'milestone' | 'field' | 'stage' | 'rule' | 'form';
type Resource = PlanningSprint | PlanningMilestone | PlanningField | PlanningStage | PlanningRule | IntakeFormDefinition;
type BoardColumn = { id: string; status: TaskStatus; name: string; stage?: PlanningStage };

export type PlanningWorkspaceProps = {
  projectId: string;
  canManage: boolean;
  canLogWork: boolean;
  canSubmitIntake: boolean;
  participants: ProjectParticipant[];
  onOpenTask: (task: Task) => void;
  onCreateTask: () => void;
};

export function PlanningWorkspace({ projectId, canManage, canLogWork, canSubmitIntake, participants, onOpenTask, onCreateTask }: PlanningWorkspaceProps) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [metadata, setMetadata] = useState<PlanningMetadata | null>(null);
  const [savedQueries, setSavedQueries] = useState<SavedTaskQuery[]>([]);
  const [savedQueryError, setSavedQueryError] = useState('');
  const [reports, setReports] = useState<PlanningReports | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingReports, setLoadingReports] = useState(false);
  const [error, setError] = useState('');
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTER);
  const [tab, setTab] = useNavigationState<string>('planning-tab', 'board', ['board', 'backlog', 'settings', 'intake', 'insights']);
  const [selectedQueryId, setSelectedQueryId] = useState('');
  const [metadataTask, setMetadataTask] = useState<Task | null>(null);
  const [metadataForm] = Form.useForm();
  const [resourceModal, setResourceModal] = useState<{ kind: ResourceKind; item?: Resource } | null>(null);
  const [resourceForm] = Form.useForm();
  const [resourceSaving, setResourceSaving] = useState(false);
  const [queryName, setQueryName] = useState('');
  const [intakeFormId, setIntakeFormId] = useState('');
  const [intakeForm, setIntakeForm] = useState<IntakeFormDefinition | null>(null);
  const [intakeFormInstance] = Form.useForm();
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [intakeSaving, setIntakeSaving] = useState(false);
  const [worklogTask, setWorklogTask] = useState<Task | null>(null);
  const [worklogs, setWorklogs] = useState<TaskWorklog[]>([]);
  const [worklogError, setWorklogError] = useState('');
  const [worklogLoading, setWorklogLoading] = useState(false);
  const [worklogSaving, setWorklogSaving] = useState(false);
  const [worklogForm] = Form.useForm();
  const csvInput = useRef<HTMLInputElement>(null);
  const [csvBusy, setCsvBusy] = useState(false);
  const [csvResult, setCsvResult] = useState<{ created: number; errors: string[] } | null>(null);
  const [messageApi, messageContext] = message.useMessage();

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [taskRows, planning] = await Promise.all([api.tasks(projectId, '', ''), api.planning(projectId)]);
      setTasks(orderedTasks(taskRows));
      setMetadata(planning);
    } catch (loadError) {
      setError(errorText(loadError));
    } finally {
      setLoading(false);
    }
    try {
      const records = await api.savedTaskQueries();
      setSavedQueries(records.filter((item) => item.project_id === projectId));
      setSavedQueryError('');
    } catch (queryError) { setSavedQueryError(errorText(queryError)); }
  }, [projectId]);

  useEffect(() => { setSelectedQueryId(''); void refresh(); }, [refresh]);

  const filteredTasks = useMemo(() => tasks.filter((task) => {
    if (filters.text && !`${task.key} ${task.title} ${task.description} ${task.labels.join(' ')}`.toLocaleLowerCase().includes(filters.text.toLocaleLowerCase())) return false;
    if (filters.status && task.status !== filters.status) return false;
    if (filters.work_type && (task.work_type ?? 'task') !== filters.work_type) return false;
    if (filters.sprint_id && task.sprint_id !== filters.sprint_id) return false;
    if (filters.milestone_id && task.milestone_id !== filters.milestone_id) return false;
    if (filters.assignee_principal_id && (task.assignee_principal_id ?? task.assignee?.principal_id) !== filters.assignee_principal_id) return false;
    if (filters.overdue && (!task.due_at || new Date(task.due_at).getTime() >= Date.now() || ['done', 'cancelled'].includes(task.status))) return false;
    return true;
  }), [filters, tasks]);
  const orderedFilteredTasks = useMemo(() => orderedTasks(filteredTasks), [filteredTasks]);

  const columns = useMemo<BoardColumn[]>(() => {
    const activeStages = [...(metadata?.stages ?? [])].filter((stage) => stage.active).sort((a, b) => a.rank - b.rank);
    if (!activeStages.length) return BUILT_IN_COLUMNS.map((column) => ({ id: column.status, status: column.status, name: column.label }));
    const result: BoardColumn[] = activeStages.map((stage) => ({ id: stage.id, status: stage.category, name: stage.name, stage }));
    for (const column of BUILT_IN_COLUMNS) {
      if (activeStages.some((stage) => stage.category === column.status)) continue;
      if (filteredTasks.some((task) => task.status === column.status && !activeStages.some((stage) => stage.id === task.stage_id))) {
        result.push({ id: `system-${column.status}`, status: column.status, name: column.label });
      }
    }
    return result;
  }, [filteredTasks, metadata?.stages]);

  const tasksInColumn = useCallback((column: BoardColumn) => {
    if (!column.stage) {
      return filteredTasks.filter((task) => task.status === column.status && !metadata?.stages.some((stage) => stage.active && stage.id === task.stage_id));
    }
    const activeStages = metadata?.stages.filter((stage) => stage.active) ?? [];
    const firstForCategory = activeStages.filter((stage) => stage.category === column.status).sort((a, b) => a.rank - b.rank)[0]?.id === column.stage.id;
    return filteredTasks.filter((task) => task.stage_id === column.stage?.id || (firstForCategory && task.status === column.status && !activeStages.some((stage) => stage.id === task.stage_id)));
  }, [filteredTasks, metadata?.stages]);

  const reloadReports = useCallback(async () => {
    setLoadingReports(true);
    try { setReports(await api.planningReports(projectId)); }
    catch (reportError) { messageApi.error(errorText(reportError)); }
    finally { setLoadingReports(false); }
  }, [messageApi, projectId]);

  useEffect(() => { if (tab === 'insights') void reloadReports(); }, [reloadReports, tab]);

  const openTaskMetadata = (task: Task) => {
    setMetadataTask(task);
    metadataForm.resetFields();
    metadataForm.setFieldsValue({
      work_type: task.work_type ?? 'task', epic_id: task.epic_id ?? undefined,
      due_at: dateInput(task.due_at), start_at: dateInput(task.start_at),
      sprint_id: task.sprint_id ?? undefined, milestone_id: task.milestone_id ?? undefined,
      estimate_points: task.estimate_points ?? undefined, stage_id: task.stage_id ?? undefined,
      custom_fields: task.custom_fields ?? {},
    });
  };

  const saveTaskMetadata = async (values: Record<string, unknown>) => {
    if (!metadataTask) return;
    try {
      const customFields = Object.fromEntries((metadata?.fields ?? []).filter((field) => field.active).map((field) => {
        const value = (values.custom_fields as Record<string, unknown> | undefined)?.[field.key];
        return [field.key, value === undefined ? null : value as string | number | boolean | null] as const;
      }));
      await api.patch<Task>(`/api/tasks/${encodeURIComponent(metadataTask.id)}`, {
        work_type: values.work_type, epic_id: values.epic_id || null,
        due_at: dateValue(values.due_at as string | undefined), start_at: dateValue(values.start_at as string | undefined),
        sprint_id: values.sprint_id || null, milestone_id: values.milestone_id || null,
        estimate_points: values.estimate_points ?? null, stage_id: values.stage_id || null,
        custom_fields: customFields,
      });
      setMetadataTask(null);
      await refresh();
      messageApi.success(t('規劃資料已儲存。'));
    } catch (saveError) { messageApi.error(errorText(saveError)); }
  };

  const changeTaskStatus = async (task: Task, status: TaskStatus) => {
    if (!['backlog', 'ready', 'cancelled'].includes(status)) return;
    try {
      const saved = await api.patch<Task>(`/api/tasks/${encodeURIComponent(task.id)}`, { status });
      setTasks((current) => orderedTasks(current.map((item) => item.id === saved.id ? saved : item)));
      messageApi.success(t('任務狀態已更新。'));
    } catch (moveError) { messageApi.error(errorText(moveError)); }
  };

  const changeTaskStage = async (task: Task, stageId: string) => {
    const stage = metadata?.stages.find((item) => item.id === stageId);
    if (!stage || stage.category !== task.status) return;
    try {
      await api.patch<Task>(`/api/tasks/${encodeURIComponent(task.id)}`, { stage_id: stage.id });
      await refresh();
    } catch (stageError) { messageApi.error(errorText(stageError)); }
  };

  const reorder = async (task: Task, offset: number) => {
    const list = [...orderedFilteredTasks];
    const index = list.findIndex((item) => item.id === task.id);
    const nextIndex = index + offset;
    if (index < 0 || nextIndex < 0 || nextIndex >= list.length) return;
    [list[index], list[nextIndex]] = [list[nextIndex], list[index]];
    try {
      await api.reorderTasks(projectId, list.map((item) => item.id));
      await refresh();
    } catch (reorderError) { messageApi.error(errorText(reorderError)); }
  };

  const openResource = (kind: ResourceKind, item?: Resource) => {
    setResourceModal({ kind, item });
    resourceForm.resetFields();
    if (kind === 'sprint') {
      const sprint = item as PlanningSprint | undefined;
      resourceForm.setFieldsValue({ name: sprint?.name, goal: sprint?.goal, start_at: dateInput(sprint?.start_at), end_at: dateInput(sprint?.end_at), status: sprint?.status ?? 'planned' });
    } else if (kind === 'milestone') {
      const milestone = item as PlanningMilestone | undefined;
      resourceForm.setFieldsValue({ name: milestone?.name, description: milestone?.description, due_at: dateInput(milestone?.due_at), status: milestone?.status ?? 'open' });
    } else if (kind === 'field') {
      const field = item as PlanningField | undefined;
      resourceForm.setFieldsValue({ key: field?.key, name: field?.name, kind: field?.kind ?? 'text', required: field?.required ?? false, options_text: field?.options.join('\n') ?? '', active: field?.active ?? true });
    } else if (kind === 'stage') {
      const stage = item as PlanningStage | undefined;
      resourceForm.setFieldsValue({ name: stage?.name, category: stage?.category ?? 'backlog', rank: stage?.rank ?? (metadata?.stages.length ?? 0), active: stage?.active ?? true });
    } else if (kind === 'rule') {
      const rule = item as PlanningRule | undefined;
      resourceForm.setFieldsValue({ name: rule?.name, event: rule?.event ?? 'task.created', condition_work_type: rule?.conditions.work_type, condition_priority: rule?.conditions.priority, condition_status: rule?.conditions.status, condition_label: rule?.conditions.label, action: rule?.action ?? 'label', parameter_label: rule?.parameters.label, assignee_principal_id: rule?.parameters.assignee_principal_id, enabled: rule?.enabled ?? true });
    } else {
      const intake = item as IntakeFormDefinition | undefined;
      resourceForm.setFieldsValue({ name: intake?.name, description: intake?.description, work_type: intake?.work_type ?? 'task', fields_text: intake?.fields.join(', ') ?? '', active: intake?.active ?? true });
    }
  };

  const saveResource = async (values: Record<string, unknown>) => {
    if (!resourceModal) return;
    const { kind, item } = resourceModal;
    const itemId = item && 'id' in item ? item.id : undefined;
    setResourceSaving(true);
    try {
      if (kind === 'sprint') {
        const body = { name: String(values.name), goal: String(values.goal ?? ''), start_at: dateValue(values.start_at as string | undefined), end_at: dateValue(values.end_at as string | undefined), status: values.status as PlanningSprint['status'] };
        if (itemId) await api.updateSprint(itemId, body); else await api.createSprint(projectId, body);
      } else if (kind === 'milestone') {
        const body = { name: String(values.name), description: String(values.description ?? ''), due_at: dateValue(values.due_at as string | undefined), status: values.status as PlanningMilestone['status'] };
        if (itemId) await api.updateMilestone(itemId, body); else await api.createMilestone(projectId, body);
      } else if (kind === 'field') {
        const body = { key: String(values.key), name: String(values.name), kind: values.kind as PlanningField['kind'], required: Boolean(values.required), options: String(values.options_text ?? '').split(/\r?\n/).map((part) => part.trim()).filter(Boolean), active: Boolean(values.active) };
        if (itemId) await api.updatePlanningField(itemId, body); else await api.createPlanningField(projectId, body);
      } else if (kind === 'stage') {
        const body = { name: String(values.name), category: values.category as TaskStatus, rank: Number(values.rank ?? 0), active: Boolean(values.active) };
        if (itemId) await api.updatePlanningStage(itemId, body); else await api.createPlanningStage(projectId, body);
      } else if (kind === 'rule') {
        const conditions = Object.fromEntries(Object.entries({ work_type: values.condition_work_type, priority: values.condition_priority, status: values.condition_status, label: values.condition_label }).filter(([, value]) => value !== undefined && value !== '')) as PlanningRule['conditions'];
        const parameters = Object.fromEntries(Object.entries({ label: values.parameter_label, assignee_principal_id: values.assignee_principal_id }).filter(([, value]) => value !== undefined && value !== '')) as PlanningRule['parameters'];
        const body = { name: String(values.name), event: values.event as PlanningRule['event'], conditions, action: values.action as PlanningRule['action'], parameters, enabled: Boolean(values.enabled) };
        if (itemId) await api.updatePlanningRule(itemId, body); else await api.createPlanningRule(projectId, body);
      } else {
        const body = { name: String(values.name), description: String(values.description ?? ''), work_type: values.work_type as IntakeFormDefinition['work_type'], fields: String(values.fields_text ?? '').split(/[\n,]/).map((part) => part.trim()).filter(Boolean), active: Boolean(values.active) };
        if (itemId) await api.updateIntakeForm(itemId, body); else await api.createIntakeForm(projectId, body);
      }
      setResourceModal(null);
      await refresh();
      messageApi.success(t('規劃設定已儲存。'));
    } catch (saveError) { messageApi.error(errorText(saveError)); }
    finally { setResourceSaving(false); }
  };

  const chooseIntake = async (id: string) => {
    setIntakeFormId(id);
    if (!id) { setIntakeForm(null); return; }
    try {
      const detail = await api.intakeForm(id);
      setIntakeForm(detail);
      intakeFormInstance.resetFields();
    } catch (formError) { messageApi.error(errorText(formError)); }
  };

  const openSelectedIntake = async () => {
    if (!intakeFormId) return;
    try {
      const detail = await api.intakeForm(intakeFormId);
      setIntakeForm(detail);
      intakeFormInstance.resetFields();
      setIntakeOpen(true);
    } catch (formError) { messageApi.error(errorText(formError)); }
  };

  const submitIntake = async (values: Record<string, unknown>) => {
    if (!intakeForm) return;
    setIntakeSaving(true);
    try {
      const customFields = Object.fromEntries(intakeForm.fields.map((key) => {
        const value = (values.custom_fields as Record<string, unknown> | undefined)?.[key];
        return [key, value === undefined ? null : value as string | number | boolean | null] as const;
      }));
      const task = await api.submitIntakeForm(intakeForm.id, { title: String(values.title), description: String(values.description ?? ''), custom_fields: customFields });
      setIntakeOpen(false);
      await refresh();
      messageApi.success(t('已建立待整理任務 {{key}}。', { key: task.key }));
    } catch (submitError) { messageApi.error(errorText(submitError)); }
    finally { setIntakeSaving(false); }
  };

  const openWorklogs = async (task: Task) => {
    setWorklogTask(task);
    setWorklogs([]);
    setWorklogError('');
    setWorklogLoading(true);
    worklogForm.resetFields();
    worklogForm.setFieldsValue({ minutes: 30, started_at: dateInput(new Date().toISOString()), description: '' });
    try { setWorklogs(await api.taskWorklogs(task.id)); }
    catch (loadError) { setWorklogError(errorText(loadError)); }
    finally { setWorklogLoading(false); }
  };

  const saveWorklog = async (values: Record<string, unknown>) => {
    if (!worklogTask) return;
    setWorklogSaving(true);
    try {
      await api.addTaskWorklog(worklogTask.id, { minutes: Number(values.minutes), started_at: dateValue(values.started_at as string) ?? new Date().toISOString(), description: String(values.description ?? '') });
      setWorklogs(await api.taskWorklogs(worklogTask.id));
      worklogForm.resetFields();
      messageApi.success(t('工時紀錄已新增。'));
    } catch (saveError) { messageApi.error(errorText(saveError)); }
    finally { setWorklogSaving(false); }
  };

  const exportCsv = async () => {
    setCsvBusy(true);
    try {
      const csv = await api.exportTasksCsv(projectId);
      const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `ordivant-${projectId}-tasks.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (exportError) { messageApi.error(errorText(exportError)); }
    finally { setCsvBusy(false); }
  };

  const importCsv = async (file?: File) => {
    if (!file) return;
    setCsvBusy(true);
    setCsvResult(null);
    try {
      const result = await api.importTasksCsv(projectId, await file.text());
      setCsvResult({ created: result.created.length, errors: result.errors });
      if (result.created.length) await refresh();
    } catch (importError) { messageApi.error(errorText(importError)); }
    finally { setCsvBusy(false); if (csvInput.current) csvInput.current.value = ''; }
  };

  const saveQuery = async () => {
    if (!queryName.trim()) { messageApi.warning(t('請輸入查詢名稱。')); return; }
    try {
      const queryFilters = Object.fromEntries(Object.entries({
        q: filters.text,
        status: filters.status,
        work_type: filters.work_type,
        sprint_id: filters.sprint_id,
        milestone_id: filters.milestone_id,
        assignee_principal_id: filters.assignee_principal_id,
        overdue: filters.overdue,
      }).filter(([, value]) => value !== '' && value !== false));
      const record = await api.saveTaskQuery({ name: queryName.trim(), project_id: projectId, filters: queryFilters });
      setSavedQueries((current) => [...current.filter((item) => item.id !== record.id), record]);
      setQueryName('');
      messageApi.success(t('查詢已儲存。'));
    } catch (saveError) { messageApi.error(errorText(saveError)); }
  };

  const selectQuery = (id: string) => {
    const query = savedQueries.find((item) => item.id === id);
    if (!query) return;
    setSelectedQueryId(query.id);
    const { q, ...savedFilters } = query.filters;
    setFilters({ ...EMPTY_FILTER, ...savedFilters, text: typeof q === 'string' ? q : '', overdue: query.filters.overdue === true || query.filters.overdue === 'true' } as FilterState);
  };

  const deleteQuery = async (id: string) => {
    try {
      await api.deleteTaskQuery(id);
      setSavedQueries((current) => current.filter((item) => item.id !== id));
      setSelectedQueryId((current) => current === id ? '' : current);
      messageApi.success(t('已刪除儲存查詢。'));
    } catch (deleteError) { messageApi.error(errorText(deleteError)); }
  };

  const taskColumns: ColumnsType<Task> = [
    { title: t('排序'), key: 'rank', width: 92, render: (_, task) => { const index = orderedFilteredTasks.findIndex((item) => item.id === task.id); return <Space size={2}><Button size="small" icon={<ArrowUpOutlined />} disabled={!canManage || index <= 0} aria-label={t('將 {{key}} 上移', { key: task.key })} onClick={() => void reorder(task, -1)} /><Button size="small" icon={<ArrowDownOutlined />} disabled={!canManage || index < 0 || index >= orderedFilteredTasks.length - 1} aria-label={t('將 {{key}} 下移', { key: task.key })} onClick={() => void reorder(task, 1)} /></Space>; } },
    { title: t('任務'), dataIndex: 'title', key: 'title', render: (title: string, task) => <button type="button" className="planning-task-title" onClick={() => onOpenTask(task)}><strong>{task.key}</strong><span>{title}</span></button> },
    { title: t('類型'), key: 'work_type', width: 100, render: (_, task) => t(workTypeLabel(task.work_type)) },
    { title: t('優先級'), dataIndex: 'priority', key: 'priority', width: 100, render: (value: Priority) => t(priorityLabel(value)) },
    { title: t('預計點數'), dataIndex: 'estimate_points', key: 'estimate_points', width: 96, render: (value?: number | null) => value ?? '—' },
    { title: t('到期日'), dataIndex: 'due_at', key: 'due_at', width: 140, render: (value?: string | null) => value ? formatDate(value, { dateStyle: 'medium' }) : '—' },
    { title: t('狀態'), dataIndex: 'status', key: 'status', width: 110, render: (status: TaskStatus) => <Tag>{t(statusLabel(status))}</Tag> },
    { title: '', key: 'actions', width: 168, render: (_, task) => <Space wrap><Button size="small" icon={<EditOutlined />} disabled={!canManage} onClick={() => openTaskMetadata(task)}>{t('規劃')}</Button><Button size="small" icon={<ClockCircleOutlined />} disabled={!canLogWork} onClick={() => void openWorklogs(task)}>{t('工時')}</Button></Space> },
  ];
  const selectedQuery = savedQueries.find((query) => query.id === selectedQueryId && query.project_id === projectId);

  return <div className="planning-workspace">
    {messageContext}
    <div className="planning-toolbar">
      <Space wrap>
        <Input allowClear prefix={<FilterOutlined />} placeholder={t('搜尋任務')} value={filters.text} onChange={(event) => setFilters((current) => ({ ...current, text: event.target.value }))} />
        <Select allowClear placeholder={t('全部狀態')} value={filters.status || undefined} onChange={(value) => setFilters((current) => ({ ...current, status: value ?? '' }))} options={BUILT_IN_COLUMNS.map((item) => ({ value: item.status, label: t(item.label) }))} />
        <Select allowClear placeholder={t('全部類型')} value={filters.work_type || undefined} onChange={(value) => setFilters((current) => ({ ...current, work_type: value ?? '' }))} options={WORK_TYPES.map((value) => ({ value, label: t(workTypeLabel(value)) }))} />
        <Select allowClear placeholder={t('全部 Sprint')} value={filters.sprint_id || undefined} onChange={(value) => setFilters((current) => ({ ...current, sprint_id: value ?? '' }))} options={(metadata?.sprints ?? []).map((item) => ({ value: item.id, label: item.name }))} />
        <Select allowClear placeholder={t('全部里程碑')} value={filters.milestone_id || undefined} onChange={(value) => setFilters((current) => ({ ...current, milestone_id: value ?? '' }))} options={(metadata?.milestones ?? []).map((item) => ({ value: item.id, label: item.name }))} />
        <Select allowClear placeholder={t('所有負責者')} value={filters.assignee_principal_id || undefined} onChange={(value) => setFilters((current) => ({ ...current, assignee_principal_id: value ?? '' }))} options={participants.map((person) => ({ value: person.principal_id, label: person.name }))} />
        <Checkbox checked={filters.overdue} onChange={(event) => setFilters((current) => ({ ...current, overdue: event.target.checked }))}>{t('只看逾期')}</Checkbox>
      </Space>
      <Space wrap>
        <Select allowClear placeholder={t('載入儲存查詢')} className="planning-saved-query" popupClassName="planning-saved-query-popup" popupMatchSelectWidth={176} value={selectedQueryId || undefined} onChange={(id) => id ? selectQuery(id) : setSelectedQueryId('')} options={savedQueries.map((item) => ({ value: item.id, label: item.name }))} />
        <Input className="planning-query-name" placeholder={t('查詢名稱')} value={queryName} onChange={(event) => setQueryName(event.target.value)} />
        <Button icon={<SaveOutlined />} onClick={() => void saveQuery()}>{t('儲存查詢')}</Button>
        {selectedQuery && <Tooltip title={t('刪除查詢 {{name}}', { name: selectedQuery.name })}><Button size="small" danger icon={<DeleteOutlined />} aria-label={t('刪除查詢 {{name}}', { name: selectedQuery.name })} onClick={() => void deleteQuery(selectedQuery.id)} /></Tooltip>}
      </Space>
    </div>
    {error && <Alert type="error" showIcon message={t('規劃資料無法載入')} description={error} action={<Button size="small" onClick={() => void refresh()}>{t('重試')}</Button>} />}
    {savedQueryError && <Alert type="warning" showIcon message={t('儲存查詢無法載入')} description={savedQueryError} />}
    <Tabs activeKey={tab} onChange={setTab} items={[
      { key: 'board', label: <span><CalendarOutlined /> {t('看板')}</span>, children: <div className="planning-board-scroll">{loading ? <Spin /> : !metadata ? <Empty description={t('尚無可用規劃資料')} /> : <div className="planning-board">{columns.map((column) => <section className="planning-column" key={column.id} aria-label={t('{{name}} 欄', { name: column.name })}><header><strong>{t(column.name)}</strong><span>{formatNumber(tasksInColumn(column).length)}</span></header><div className="planning-column-cards">{tasksInColumn(column).map((task) => <PlanningTaskCard key={task.id} task={task} column={column} columns={columns} canManage={canManage} onOpen={() => onOpenTask(task)} onEdit={() => openTaskMetadata(task)} onStatus={changeTaskStatus} onStage={changeTaskStage} />)}{tasksInColumn(column).length === 0 && <Text type="secondary">{t('沒有任務')}</Text>}</div></section>)}</div>}</div> },
      { key: 'backlog', label: <span><UnorderedListOutlined /> {t('Backlog 排序')}</span>, children: <><div className="planning-section-actions"><Text type="secondary">{t('使用上下移動按鈕調整專案排序。排序不會改變任務狀態。')}</Text><Button icon={<PlusOutlined />} type="primary" onClick={onCreateTask}>{t('新增任務')}</Button></div><Table<Task> rowKey="id" size="small" columns={taskColumns} dataSource={orderedFilteredTasks} loading={loading} pagination={{ pageSize: 20, showSizeChanger: false }} locale={{ emptyText: <Empty description={t('沒有符合條件的任務')} /> }} /></> },
      { key: 'settings', label: <span><SettingOutlined /> {t('規劃設定')}</span>, children: <PlanningSettings metadata={metadata} canManage={canManage} onAdd={openResource} onEdit={openResource} /> },
      { key: 'intake', label: <span><FormOutlined /> {t('任務提報')}</span>, children: <div className="planning-intake"><div><Title level={4}>{t('以專案成員身分提交需求')}</Title><Text type="secondary">{t('提交後會建立待整理任務，之後由有權限的成員分類、指派與排序。')}</Text></div><Select className="planning-intake-select" placeholder={t('選擇提報表單')} value={intakeFormId || undefined} onChange={(id) => void chooseIntake(id)} options={(metadata?.forms ?? []).filter((form) => form.active).map((form) => ({ value: form.id, label: form.name }))} /><Button type="primary" disabled={!canSubmitIntake || !intakeFormId} onClick={() => void openSelectedIntake()}>{t('提交需求')}</Button>{!canSubmitIntake && <Text type="secondary">{t('只有已登入的專案成員可提交提報。')}</Text>}</div> },
      { key: 'insights', label: <span><BarChartOutlined /> {t('工時與報表')}</span>, children: <PlanningInsights reports={reports} canManage={canManage} onSetCapacity={async (principalId, weeklyMinutes) => { await api.setPlanningCapacity(projectId, { principal_id: principalId, weekly_minutes: weeklyMinutes }); await reloadReports(); }} loading={loadingReports} onRefresh={() => void reloadReports()} onExport={() => void exportCsv()} onImport={() => csvInput.current?.click()} importBusy={csvBusy} importResult={csvResult} onClearImport={() => setCsvResult(null)} /> },
    ]} />
    <input ref={csvInput} className="planning-file-input" type="file" accept=".csv,text/csv" onChange={(event) => void importCsv(event.target.files?.[0])} />

    <Modal title={t('編輯規劃資料')} open={Boolean(metadataTask)} onCancel={() => setMetadataTask(null)} onOk={() => metadataForm.submit()} okText={t('儲存')} cancelText={t('取消')} width={680} destroyOnClose>
      <Form form={metadataForm} layout="vertical" onFinish={(values) => void saveTaskMetadata(values)}>
        <Row gutter={16}><Col span={12}><Form.Item name="work_type" label={t('工作類型')} rules={[{ required: true }]}><Select options={WORK_TYPES.map((value) => ({ value, label: t(workTypeLabel(value)) }))} /></Form.Item></Col><Col span={12}><Form.Item name="epic_id" label={t('上層 Epic')}><Select allowClear options={tasks.filter((item) => item.work_type === 'epic' && item.id !== metadataTask?.id).map((item) => ({ value: item.id, label: `${item.key} · ${item.title}` }))} /></Form.Item></Col>
          <Col span={12}><Form.Item name="start_at" label={t('開始日期')}><Input type="datetime-local" /></Form.Item></Col><Col span={12}><Form.Item name="due_at" label={t('到期日')}><Input type="datetime-local" /></Form.Item></Col>
          <Col span={12}><Form.Item name="sprint_id" label={t('Sprint')}><Select allowClear options={(metadata?.sprints ?? []).filter((item) => item.status !== 'closed').map((item) => ({ value: item.id, label: item.name }))} /></Form.Item></Col><Col span={12}><Form.Item name="milestone_id" label={t('里程碑')}><Select allowClear options={(metadata?.milestones ?? []).filter((item) => item.status === 'open').map((item) => ({ value: item.id, label: item.name }))} /></Form.Item></Col>
          <Col span={12}><Form.Item name="estimate_points" label={t('預計點數')}><InputNumber min={0} precision={1} className="planning-full-width" /></Form.Item></Col><Col span={12}><Form.Item name="stage_id" label={t('規劃階段')}><Select allowClear options={(metadata?.stages ?? []).filter((stage) => stage.active && stage.category === metadataTask?.status).map((stage) => ({ value: stage.id, label: stage.name }))} /></Form.Item></Col>
        </Row>
        {(metadata?.fields ?? []).filter((field) => field.active).map((field) => <Form.Item key={field.key} name={['custom_fields', field.key]} label={field.name} rules={field.required ? [{ required: true, message: t('此欄位為必填。') }] : []} valuePropName={field.kind === 'boolean' ? 'checked' : 'value'}>{field.kind === 'select' ? <Select allowClear options={field.options.map((option) => ({ value: option, label: option }))} /> : field.kind === 'number' ? <InputNumber className="planning-full-width" /> : field.kind === 'boolean' ? <Switch /> : <Input />}</Form.Item>)}
      </Form>
    </Modal>

    <ResourceModal modal={resourceModal} form={resourceForm} saving={resourceSaving} participants={participants} onCancel={() => setResourceModal(null)} onFinish={saveResource} />

    <Modal title={t('提交任務提報')} open={intakeOpen} onCancel={() => setIntakeOpen(false)} onOk={() => intakeFormInstance.submit()} confirmLoading={intakeSaving} okText={t('送出提報')} cancelText={t('取消')} destroyOnClose>
      {intakeForm && <Form form={intakeFormInstance} layout="vertical" onFinish={(values) => void submitIntake(values)}><Form.Item label={t('表單')}><Text strong>{intakeForm.name}</Text><div><Text type="secondary">{intakeForm.description}</Text></div></Form.Item><Form.Item name="title" label={t('任務名稱')} rules={[{ required: true, whitespace: true }]}><Input maxLength={180} /></Form.Item><Form.Item name="description" label={t('描述')}><Input.TextArea rows={4} maxLength={5000} /></Form.Item>{intakeForm.fields.map((key) => { const field = metadata?.fields.find((item) => item.key === key && item.active); if (!field) return null; return <Form.Item key={key} name={['custom_fields', key]} label={field.name} rules={field.required ? [{ required: true, message: t('此欄位為必填。') }] : []} valuePropName={field.kind === 'boolean' ? 'checked' : 'value'}>{field.kind === 'select' ? <Select allowClear options={field.options.map((option) => ({ value: option, label: option }))} /> : field.kind === 'number' ? <InputNumber className="planning-full-width" /> : field.kind === 'boolean' ? <Switch /> : <Input />}</Form.Item>; })}</Form>}
    </Modal>

    <Modal title={t('任務工時')} open={Boolean(worklogTask)} onCancel={() => setWorklogTask(null)} footer={null} width={720} destroyOnClose>
      {worklogError && <Alert type="error" showIcon message={t('工時無法載入')} description={worklogError} />}
      <div className="planning-worklog-list">{worklogLoading ? <Spin /> : worklogs.length ? worklogs.map((entry) => <div className="planning-worklog-row" key={entry.id}><div><strong>{formatNumber(entry.minutes)} {t('分鐘')}</strong><span>{formatDate(entry.started_at)}</span></div><div>{entry.description}</div></div>) : <Empty description={t('尚無工時紀錄')} />}</div>
      {canLogWork && <><Divider /><Form form={worklogForm} layout="vertical" onFinish={(values) => void saveWorklog(values)}><Row gutter={12}><Col span={8}><Form.Item name="minutes" label={t('分鐘')} rules={[{ required: true, type: 'number', min: 1, max: 100000 }]}><InputNumber min={1} precision={0} className="planning-full-width" /></Form.Item></Col><Col span={16}><Form.Item name="started_at" label={t('工時開始時間')} rules={[{ required: true }]}><Input type="datetime-local" /></Form.Item></Col></Row><Form.Item name="description" label={t('工作摘要')}><Input.TextArea rows={2} maxLength={1000} /></Form.Item><Button type="primary" htmlType="submit" loading={worklogSaving}>{t('記錄工時')}</Button></Form></>}
    </Modal>
  </div>;
}

function workTypeLabel(value?: Task['work_type']) { return ({ task: '任務', story: '使用者故事', bug: 'Bug', epic: 'Epic' } as const)[value ?? 'task']; }
function priorityLabel(value: Priority) { return ({ urgent: '緊急', high: '高', medium: '一般', low: '低' } as const)[value]; }
function statusLabel(value: TaskStatus) { return ({ backlog: '待整理', ready: '待執行', in_progress: '進行中', blocked: '受阻', in_review: '待審核', done: '已完成', cancelled: '已取消' } as Record<string, string>)[value] ?? value; }
function sprintStatusLabel(value: PlanningSprint['status']) { return ({ planned: '規劃中', active: '進行中', closed: '已關閉' } as const)[value]; }
function milestoneStatusLabel(value: PlanningMilestone['status']) { return value === 'open' ? '開啟' : '已關閉'; }
function fieldKindLabel(value: PlanningField['kind']) { return ({ text: '文字', number: '數字', boolean: '是或否', select: '選項' } as const)[value]; }
function ruleEventLabel(value: PlanningRule['event']) { return value === 'task.created' ? '建立任務時' : '更新任務時'; }
function ruleActionLabel(value: PlanningRule['action']) { return ({ label: '新增標籤', assign: '指派負責者', ready: '送入待執行' } as const)[value]; }

function PlanningTaskCard({ task, column, columns, canManage, onOpen, onEdit, onStatus, onStage }: { task: Task; column: BoardColumn; columns: BoardColumn[]; canManage: boolean; onOpen: () => void; onEdit: () => void; onStatus: (task: Task, status: TaskStatus) => void; onStage: (task: Task, stageId: string) => void }) {
  const movable = ['backlog', 'ready', 'cancelled'].includes(task.status);
  const stageOptions = columns.filter((item) => item.stage && item.status === task.status).map((item) => ({ value: item.id, label: item.name }));
  return <Card size="small" className="planning-task-card" aria-label={t('{{key}} {{title}}', { key: task.key, title: task.title })}>
    <button className="planning-card-title" type="button" onClick={onOpen}><span className="planning-card-key">{task.key}</span><strong>{task.title}</strong></button>
    <Space wrap size={[4, 4]}><Tag>{t(workTypeLabel(task.work_type))}</Tag><Tag color={task.priority === 'urgent' || task.priority === 'high' ? 'red' : 'blue'}>{t(priorityLabel(task.priority))}</Tag>{task.estimate_points != null && <Tag>{formatNumber(task.estimate_points)} {t('點')}</Tag>}</Space>
    <div className="planning-card-meta">{task.assignee?.name ?? t('未指派')}{task.due_at && <span>{t('到期日 {{date}}', { date: formatDate(task.due_at, { dateStyle: 'medium' }) })}</span>}</div>
    {stageOptions.length > 1 && <Select size="small" aria-label={t('規劃階段')} value={column.id} disabled={!canManage} options={stageOptions} onChange={(value) => onStage(task, value)} />}
    <div className="planning-card-actions"><Button size="small" icon={<EditOutlined />} disabled={!canManage} onClick={onEdit}>{t('規劃')}</Button>{movable ? <Select size="small" aria-label={t('變更規劃狀態')} value={task.status} onChange={(value) => onStatus(task, value)} options={['backlog', 'ready', 'cancelled'].map((status) => ({ value: status, label: t(statusLabel(status as TaskStatus)) }))} /> : <Button size="small" onClick={onOpen}>{t('工作控制')}</Button>}</div>
    {['in_progress', 'blocked', 'in_review', 'done'].includes(task.status) && <Text type="secondary" className="planning-lifecycle-note">{t('執行與審核狀態請使用任務工作控制。')}</Text>}
  </Card>;
}

function PlanningSettings({ metadata, canManage, onAdd, onEdit }: { metadata: PlanningMetadata | null; canManage: boolean; onAdd: (kind: ResourceKind, item?: Resource) => void; onEdit: (kind: ResourceKind, item?: Resource) => void }) {
  const [tab, setTab] = useNavigationState<string>('planning-settings-tab', 'sprint', ['sprint', 'milestone', 'field', 'stage', 'rule', 'form']);
  const tabConfig: Array<{ key: ResourceKind; title: string; rows: Resource[]; columns: ColumnsType<Resource>; }> = [];
  const textCell = (value: unknown) => typeof value === 'string' ? value : '—';
  const makeColumns = (kind: ResourceKind, values: Array<{ title: string; key: string; render?: (row: Resource) => React.ReactNode }>): ColumnsType<Resource> => [
    ...values.map(({ title, key, render }) => ({ title: t(title), key, dataIndex: key, render: (_: unknown, row: Resource) => render ? render(row) : textCell((row as unknown as Record<string, unknown>)[key]) })),
    { title: '', key: 'actions', width: 96, render: (_, row) => <Button size="small" icon={<EditOutlined />} disabled={!canManage} onClick={() => onEdit(kind, row)}>{t('編輯')}</Button> },
  ];
  if (metadata) {
    tabConfig.push({ key: 'sprint', title: 'Sprint', rows: metadata.sprints, columns: makeColumns('sprint', [{ title: '名稱', key: 'name' }, { title: '目標', key: 'goal' }, { title: '狀態', key: 'status', render: (row) => t(sprintStatusLabel((row as PlanningSprint).status)) }, { title: '結束日期', key: 'end_at', render: (row) => formatDate((row as PlanningSprint).end_at, { dateStyle: 'medium' }) }]) });
    tabConfig.push({ key: 'milestone', title: '里程碑', rows: metadata.milestones, columns: makeColumns('milestone', [{ title: '名稱', key: 'name' }, { title: '描述', key: 'description' }, { title: '到期日', key: 'due_at', render: (row) => formatDate((row as PlanningMilestone).due_at, { dateStyle: 'medium' }) }, { title: '狀態', key: 'status', render: (row) => t(milestoneStatusLabel((row as PlanningMilestone).status)) }]) });
    tabConfig.push({ key: 'field', title: '自訂欄位', rows: metadata.fields, columns: makeColumns('field', [{ title: '識別碼', key: 'key' }, { title: '名稱', key: 'name' }, { title: '欄位類型', key: 'kind', render: (row) => t(fieldKindLabel((row as PlanningField).kind)) }, { title: '狀態', key: 'active', render: (row) => t((row as PlanningField).active ? '啟用' : '已停用') }]) });
    tabConfig.push({ key: 'stage', title: '規劃階段設定', rows: metadata.stages, columns: makeColumns('stage', [{ title: '名稱', key: 'name' }, { title: '任務狀態', key: 'category', render: (row) => t(statusLabel((row as PlanningStage).category)) }, { title: '排序', key: 'rank' }, { title: '狀態', key: 'active', render: (row) => t((row as PlanningStage).active ? '啟用' : '已停用') }]) });
    tabConfig.push({ key: 'rule', title: '事件規則', rows: metadata.rules, columns: makeColumns('rule', [{ title: '名稱', key: 'name' }, { title: '事件', key: 'event', render: (row) => t(ruleEventLabel((row as PlanningRule).event)) }, { title: '動作', key: 'action', render: (row) => t(ruleActionLabel((row as PlanningRule).action)) }, { title: '狀態', key: 'enabled', render: (row) => t((row as PlanningRule).enabled ? '啟用' : '已停用') }]) });
    tabConfig.push({ key: 'form', title: '提報表單', rows: metadata.forms, columns: makeColumns('form', [{ title: '名稱', key: 'name' }, { title: '工作類型', key: 'work_type', render: (row) => t(workTypeLabel((row as IntakeFormDefinition).work_type)) }, { title: '欄位', key: 'fields', render: (row) => formatNumber((row as IntakeFormDefinition).fields.length) }, { title: '狀態', key: 'active', render: (row) => t((row as IntakeFormDefinition).active ? '啟用' : '已停用') }]) });
  }
  return <div className="planning-settings">{!metadata ? <Empty description={t('規劃設定無法載入')} /> : <Tabs activeKey={tab} onChange={setTab} items={tabConfig.map(({ key, title, rows, columns }) => ({ key, label: t(title), children: <><div className="planning-section-actions"><Text type="secondary">{t(settingsHint(key))}</Text><Button type="primary" icon={<PlusOutlined />} disabled={!canManage} onClick={() => onAdd(key)}>{t('新增')}</Button></div><Table<Resource> rowKey="id" size="small" columns={columns} dataSource={rows} pagination={{ pageSize: 8, showSizeChanger: false }} locale={{ emptyText: <Empty description={t('尚未設定')} /> }} /></> }))} />}</div>;
}

function settingsHint(kind: ResourceKind) { return ({ sprint: 'Sprint 管理規劃週期；關閉 Sprint 不會自動完成任務。', milestone: '里程碑用於標記重要目標日期。', field: '自訂欄位可以補充專案工作需要的資料。', stage: '階段必須對應既有任務狀態，不會取代執行與審核流程。', rule: '事件規則會同步執行，只能套用標籤、指派或將待整理任務送入待執行。', form: '提報只接受已登入的專案成員，提交後建立待整理任務。' } as Record<ResourceKind, string>)[kind]; }

function ResourceModal({ modal, form, saving, participants, onCancel, onFinish }: { modal: { kind: ResourceKind; item?: Resource } | null; form: FormInstance; saving: boolean; participants: ProjectParticipant[]; onCancel: () => void; onFinish: (values: Record<string, unknown>) => void }) {
  if (!modal) return null;
  const kind = modal.kind;
  const title = `${modal.item ? t('編輯') : t('新增')}${t(({ sprint: 'Sprint', milestone: '里程碑', field: '自訂欄位', stage: '規劃階段設定', rule: '事件規則', form: '提報表單' })[kind])}`;
  const name = <Form.Item name="name" label={t('名稱')} rules={[{ required: true, whitespace: true }]}><Input maxLength={120} /></Form.Item>;
  return <Modal title={title} open onCancel={onCancel} okButtonProps={{ form: RESOURCE_FORM_ID, htmlType: 'submit' }} confirmLoading={saving} okText={t('儲存')} cancelText={t('取消')} destroyOnClose width={650}>
    <Form id={RESOURCE_FORM_ID} form={form} layout="vertical" onFinish={onFinish}>
      {kind === 'sprint' && <>{name}<Form.Item name="goal" label={t('目標')}><Input.TextArea rows={2} /></Form.Item><Row gutter={12}><Col span={12}><Form.Item name="start_at" label={t('Sprint 開始時間')}><Input type="datetime-local" /></Form.Item></Col><Col span={12}><Form.Item name="end_at" label={t('結束時間')}><Input type="datetime-local" /></Form.Item></Col></Row><Form.Item name="status" label={t('狀態')}><Select options={[{ value: 'planned', label: t('規劃中') }, { value: 'active', label: t('進行中') }, { value: 'closed', label: t('已關閉') }]} /></Form.Item></>}
      {kind === 'milestone' && <>{name}<Form.Item name="description" label={t('描述')}><Input.TextArea rows={2} /></Form.Item><Form.Item name="due_at" label={t('到期日')}><Input type="datetime-local" /></Form.Item><Form.Item name="status" label={t('狀態')}><Select options={[{ value: 'open', label: t('開啟') }, { value: 'closed', label: t('已關閉') }]} /></Form.Item></>}
      {kind === 'field' && <><Form.Item name="key" label={t('識別碼')} rules={[{ required: true, pattern: /^[a-z][a-z0-9_]{1,39}$/, message: t('使用小寫英文字母、數字或底線，且以英文字母開頭。') }]}><Input maxLength={40} /></Form.Item>{name}<Form.Item name="kind" label={t('欄位類型')}><Select options={[{ value: 'text', label: t('文字') }, { value: 'number', label: t('數字') }, { value: 'boolean', label: t('是或否') }, { value: 'select', label: t('選項') }]} /></Form.Item><Form.Item noStyle shouldUpdate>{({ getFieldValue }) => getFieldValue('kind') === 'select' ? <Form.Item name="options_text" label={t('選項')} extra={t('每行一個選項')}><Input.TextArea rows={3} /></Form.Item> : null}</Form.Item><Form.Item name="required" valuePropName="checked"><Checkbox>{t('必填')}</Checkbox></Form.Item><Form.Item name="active" valuePropName="checked"><Checkbox>{t('啟用')}</Checkbox></Form.Item></>}
      {kind === 'stage' && <>{name}<Form.Item name="category" label={t('任務狀態')}><Select options={STAGE_CATEGORIES.map((value) => ({ value, label: t(statusLabel(value)) }))} /></Form.Item><Form.Item name="rank" label={t('排序')}><InputNumber min={0} precision={0} className="planning-full-width" /></Form.Item><Form.Item name="active" valuePropName="checked"><Checkbox>{t('啟用')}</Checkbox></Form.Item></>}
      {kind === 'rule' && <>{name}<Form.Item name="event" label={t('觸發事件')}><Select options={[{ value: 'task.created', label: t('建立任務時') }, { value: 'task.updated', label: t('更新任務時') }]} /></Form.Item><div className="planning-form-section-title">{t('符合條件')}</div><Row gutter={12}><Col span={12}><Form.Item name="condition_work_type" label={t('工作類型')}><Select allowClear options={WORK_TYPES.map((value) => ({ value, label: t(workTypeLabel(value)) }))} /></Form.Item></Col><Col span={12}><Form.Item name="condition_priority" label={t('優先級')}><Select allowClear options={PRIORITIES.map((value) => ({ value, label: t(priorityLabel(value)) }))} /></Form.Item></Col><Col span={12}><Form.Item name="condition_status" label={t('狀態')}><Select allowClear options={BUILT_IN_COLUMNS.map((item) => ({ value: item.status, label: t(item.label) }))} /></Form.Item></Col><Col span={12}><Form.Item name="condition_label" label={t('標籤')}><Input /></Form.Item></Col></Row><Form.Item name="action" label={t('執行動作')}><Select options={[{ value: 'label', label: t('新增標籤') }, { value: 'assign', label: t('指派負責者') }, { value: 'ready', label: t('送入待執行') }]} /></Form.Item><Form.Item noStyle shouldUpdate>{({ getFieldValue }) => getFieldValue('action') === 'label' ? <Form.Item name="parameter_label" label={t('新增標籤')} rules={[{ required: true }]}><Input /></Form.Item> : getFieldValue('action') === 'assign' ? <Form.Item name="assignee_principal_id" label={t('負責者')} rules={[{ required: true }]}><Select showSearch optionFilterProp="label" options={participants.map((item) => ({ value: item.principal_id, label: item.name }))} /></Form.Item> : null}</Form.Item><Form.Item name="enabled" valuePropName="checked"><Checkbox>{t('啟用')}</Checkbox></Form.Item><Alert type="info" showIcon message={t('規則不會啟動 Agent Run，也不會完成或審核任務。')} /></>}
      {kind === 'form' && <>{name}<Form.Item name="description" label={t('描述')}><Input.TextArea rows={2} /></Form.Item><Form.Item name="work_type" label={t('工作類型')}><Select options={WORK_TYPES.map((value) => ({ value, label: t(workTypeLabel(value)) }))} /></Form.Item><Form.Item name="fields_text" label={t('欄位識別碼')} extra={t('輸入自訂欄位識別碼，以逗號或換行分隔。')}><Input.TextArea rows={2} /></Form.Item><Form.Item name="active" valuePropName="checked"><Checkbox>{t('啟用')}</Checkbox></Form.Item></>}
    </Form>
  </Modal>;
}

export function PlanningInsights({ reports, canManage, onSetCapacity, loading, onRefresh, onExport, onImport, importBusy, importResult, onClearImport }: { reports: PlanningReports | null; canManage: boolean; onSetCapacity: (principalId: string, weeklyMinutes: number) => Promise<void>; loading: boolean; onRefresh: () => void; onExport: () => void; onImport: () => void; importBusy: boolean; importResult: { created: number; errors: string[] } | null; onClearImport: () => void }) {
  const [capacityDrafts, setCapacityDrafts] = useState<Record<string, number | null>>({});
  const [capacitySaving, setCapacitySaving] = useState('');
  const [capacityError, setCapacityError] = useState('');
  useEffect(() => {
    if (reports) setCapacityDrafts(Object.fromEntries(reports.capacity.map((row) => [row.principal_id, row.weekly_minutes])));
  }, [reports]);

  const saveCapacity = async (row: PlanningCapacityRow) => {
    const weeklyMinutes = capacityDrafts[row.principal_id];
    if (weeklyMinutes === null || weeklyMinutes === undefined) return;
    setCapacitySaving(row.principal_id);
    setCapacityError('');
    try { await onSetCapacity(row.principal_id, weeklyMinutes); }
    catch (error) { setCapacityError(errorText(error)); }
    finally { setCapacitySaving(''); }
  };

  const capacityColumns: ColumnsType<PlanningCapacityRow> = [
    { title: t('成員'), dataIndex: 'name', key: 'name' },
    { title: t('每週容量（分鐘）'), dataIndex: 'weekly_minutes', key: 'weekly_minutes', render: (value: number | null, row) => {
      if (!canManage) return value === null ? t('尚未設定') : `${formatNumber(value)} ${t('分鐘')}`;
      const draft = Object.hasOwn(capacityDrafts, row.principal_id) ? capacityDrafts[row.principal_id] : value;
      return <Space><InputNumber aria-label={t('設定每週容量（分鐘）')} min={0} max={10080} precision={0} placeholder={t('尚未設定')} value={draft} disabled={capacitySaving === row.principal_id} onChange={(next) => setCapacityDrafts((current) => ({ ...current, [row.principal_id]: typeof next === 'number' ? next : null }))} /><Button size="small" loading={capacitySaving === row.principal_id} disabled={draft === null || draft === undefined || draft === value} onClick={() => void saveCapacity(row)}>{t('儲存')}</Button></Space>;
    } },
    { title: t('本週已記錄（分鐘）'), dataIndex: 'observed_week_minutes', key: 'observed_week_minutes', align: 'right', render: (value: number) => formatNumber(value) },
    { title: t('累計記錄（分鐘）'), dataIndex: 'observed_minutes', key: 'observed_minutes', align: 'right', render: (value: number) => formatNumber(value) },
    { title: t('指派未完成任務'), dataIndex: 'assigned_open_tasks', key: 'assigned_open_tasks', align: 'right', render: (value: number) => formatNumber(value) },
    { title: t('指派預估點數'), dataIndex: 'assigned_estimate_points', key: 'assigned_estimate_points', align: 'right', render: (value: number) => formatNumber(value) },
    { title: t('本週使用率'), dataIndex: 'utilization_percent', key: 'utilization_percent', align: 'right', render: (value: number | null) => value === null ? '—' : `${formatNumber(value, { maximumFractionDigits: 1 })}%` },
  ];

  return <div className="planning-insights">
    <div className="planning-section-actions"><Text type="secondary">{t('報表只呈現已記錄與觀察到的資料，不預測未來產能。')}</Text><Space><Button icon={<ReloadOutlined />} loading={loading} onClick={onRefresh}>{t('重新整理')}</Button><Button icon={<DownloadOutlined />} loading={importBusy} onClick={onExport}>{t('匯出 CSV')}</Button><Button icon={<ImportOutlined />} loading={importBusy} onClick={onImport}>{t('匯入 CSV')}</Button></Space></div>
    {importResult && <Alert className="planning-import-result" closable onClose={onClearImport} type={importResult.errors.length ? 'warning' : 'success'} showIcon message={t('已建立 {{count}} 個任務', { count: formatNumber(importResult.created) })} description={importResult.errors.length ? <ul>{importResult.errors.map((error, index) => <li key={`${index}-${error}`}>{error}</li>)}</ul> : t('CSV 匯入完成。')} />}
    {capacityError && <Alert className="planning-import-result" type="error" showIcon message={t('容量設定失敗')} description={t(capacityError)} />}
    {loading && !reports ? <Spin /> : !reports ? <Empty description={t('報表資料尚未載入')} /> : <Row gutter={[12, 12]}>
      <Col xs={24} md={12}><Card size="small" title={t('任務總覽')}>
        <div className="planning-report-grid"><Statistic title={t('全部任務')} value={reports.totals.tasks} /><Statistic title={t('預計點數')} value={reports.totals.estimate_points} /></div>
        <Table<{ status: string; count: number }> size="small" rowKey="status" pagination={false} dataSource={Object.entries(reports.totals.by_status).map(([status, count]) => ({ status, count }))} columns={[
          { title: t('狀態'), dataIndex: 'status', key: 'status', render: (value: string) => t(statusLabel(value)) },
          { title: t('總數'), dataIndex: 'count', key: 'count', align: 'right', render: (value: number) => formatNumber(value) },
        ]} />
      </Card></Col>
      <Col xs={24} md={12}><Card size="small" title={t('觀察週期')}>
        <div className="planning-report-grid"><Statistic title={t('樣本數')} value={reports.cycle_time.samples} /><Statistic title={t('平均週期（小時）')} value={reports.cycle_time.average_seconds === null ? '—' : formatNumber(reports.cycle_time.average_seconds / 3600, { maximumFractionDigits: 1 })} /><Statistic title={t('中位週期（小時）')} value={reports.cycle_time.median_seconds === null ? '—' : formatNumber(reports.cycle_time.median_seconds / 3600, { maximumFractionDigits: 1 })} /></div>
        <Text type="secondary">{t('週期從首次執行開始到審核接受，包含等待與重做。')}</Text>
      </Card></Col>
      <Col xs={24}><Card size="small" title={t('各成員工時與容量')}>
        <Text type="secondary" className="planning-report-week">{t('週起始：{{date}}', { date: formatDate(reports.week_start, { dateStyle: 'medium', timeZone: 'UTC' }) })}</Text>
        <Table<PlanningCapacityRow> size="small" rowKey="principal_id" columns={capacityColumns} dataSource={reports.capacity} scroll={{ x: 1080 }} pagination={{ pageSize: 10, showSizeChanger: false }} locale={{ emptyText: <Empty description={t('目前沒有觀察資料')} /> }} />
      </Card></Col>
      <Col xs={24} md={12}><Card size="small" title={t('已記錄工時')}>
        <div className="planning-report-grid"><Statistic title={t('工時紀錄數')} value={reports.worklogs.entries} /><Statistic title={t('已記錄分鐘')} value={reports.worklogs.observed_minutes} suffix={t('分鐘')} /></div>
      </Card></Col>
    </Row>}
  </div>;
}
