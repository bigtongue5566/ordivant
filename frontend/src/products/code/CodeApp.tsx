import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MarkdownContent } from '../../shared/MarkdownContent';
import {
  Alert,
  Button,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  BranchesOutlined,
  CodeOutlined,
  FileAddOutlined,
  PlusOutlined,
  PullRequestOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
} from '@ant-design/icons';
import { createProductApi, productApiPrefix } from '../shared/productApi';
import { ProductLogin } from '../shared/ProductLogin';
import { ProductShell } from '../shared/ProductShell';
import { AuthProvider, useAuth } from '../../auth/AuthContext';
import { AuthAccessDenied } from '../../auth/AuthAccessDenied';
import { ReferenceFields, ReferenceList } from '../shared/References';
import type { CodeCheck, CodeHealth, CodeProject, ProductPrincipal, PullRequest, PullRequestContext, Repository } from '../shared/types';
import { formatDate, formatNumber, useI18n, useLocalizedForm } from '../../i18n';
import './code-collaboration.css';

const { Paragraph, Title } = Typography;
const { TextArea } = Input;
const codeApi = createProductApi(productApiPrefix('code'));
type CodeSection = 'repositories' | 'pulls';
type CollaborationActor = { id: string; name: string; kind: 'human' | 'agent' };
type PullCollaborationComment = { id: string; author: CollaborationActor; body: string; created_at: string };
type PullCollaborationReview = {
  id: string;
  author: CollaborationActor;
  decision: 'approve' | 'request_changes' | 'comment';
  comment: string;
  head_sha: string;
  is_current: boolean;
  created_at: string;
};
type PullCollaboration = {
  pull_request_id: string;
  head_sha: string;
  proposer: CollaborationActor | null;
  comments: PullCollaborationComment[];
  reviews: PullCollaborationReview[];
};

function dateText(value?: string | null): string {
  return formatDate(value);
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && 'sourceMessage' in error) return String((error as Error & { sourceMessage: string }).sourceMessage);
  return error instanceof Error ? error.message : '發生未預期的錯誤。';
}

function webUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return (url.protocol === 'https:' || url.protocol === 'http:') && !url.username && !url.password ? url.toString() : null;
  } catch {
    return null;
  }
}

export default function CodeApp() {
  return <AuthProvider><CodeWorkspace /></AuthProvider>;
}

function CodeWorkspace() {
  const { t, locale } = useI18n();
  const auth = useAuth();
  const [messageApi, messageContext] = message.useMessage();
  const [health, setHealth] = useState<CodeHealth | null>(null);
  const [healthStatus, setHealthStatus] = useState<'checking' | 'ok' | 'error'>('checking');
  const [healthError, setHealthError] = useState('');
  const [principal, setPrincipal] = useState<import('../shared/types').ProductPrincipal | null>(null);
  const [principalSessionKey, setPrincipalSessionKey] = useState('');
  const [principalErrorStatus, setPrincipalErrorStatus] = useState(0);
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState('');
  const [projects, setProjects] = useState<CodeProject[]>([]);
  const [projectId, setProjectId] = useState('');
  const [projectsBusy, setProjectsBusy] = useState(false);
  const [projectError, setProjectError] = useState('');
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [repositoriesBusy, setRepositoriesBusy] = useState(false);
  const [repositoriesError, setRepositoriesError] = useState('');
  const [repositoryId, setRepositoryId] = useState('');
  const [section, setSection] = useState<CodeSection>('repositories');
  const [pulls, setPulls] = useState<PullRequest[]>([]);
  const [pullsBusy, setPullsBusy] = useState(false);
  const [pullsError, setPullsError] = useState('');
  const [selectedPullNumber, setSelectedPullNumber] = useState<number | null>(null);
  const [pullContext, setPullContext] = useState<PullRequestContext | null>(null);
  const [pullBusy, setPullBusy] = useState(false);
  const [pullError, setPullError] = useState('');
  const [pullDrawerOpen, setPullDrawerOpen] = useState(false);
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [repositoryModalOpen, setRepositoryModalOpen] = useState(false);
  const [branchModalOpen, setBranchModalOpen] = useState(false);
  const [fileModalOpen, setFileModalOpen] = useState(false);
  const [pullModalOpen, setPullModalOpen] = useState(false);
  const [checkModalOpen, setCheckModalOpen] = useState(false);
  const [projectSaving, setProjectSaving] = useState(false);
  const [repositorySaving, setRepositorySaving] = useState(false);
  const [branchSaving, setBranchSaving] = useState(false);
  const [fileSaving, setFileSaving] = useState(false);
  const [pullSaving, setPullSaving] = useState(false);
  const [checkSaving, setCheckSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [projectForm] = Form.useForm();
  useLocalizedForm(projectForm);
  const [repositoryForm] = Form.useForm();
  useLocalizedForm(repositoryForm);
  const [branchForm] = Form.useForm();
  useLocalizedForm(branchForm);
  const [fileForm] = Form.useForm();
  useLocalizedForm(fileForm);
  const [pullForm] = Form.useForm();
  useLocalizedForm(pullForm);
  const [checkForm] = Form.useForm();
  useLocalizedForm(checkForm);
  const healthRequestId = useRef(0);
  const selectedProject = projects.find((project) => project.id === projectId) ?? null;
  const selectedRepository = repositories.find((repository) => repository.id === repositoryId) ?? null;
  const canWrite = Boolean(principal && ['admin', 'manager', 'writer'].includes(principal.role));
  const canCreateProject = auth.session?.user.role === 'admin';
  const giteaConfigured = health?.gitea_configured === true;

  const checkHealth = useCallback(async () => {
    const requestId = ++healthRequestId.current;
    setHealthStatus('checking');
    setHealthError('');
    try {
      const result = await codeApi.health();
      if (requestId !== healthRequestId.current) return;
      setHealth(result as CodeHealth);
      setHealthError('');
      setHealthStatus('ok');
    } catch (error) {
      if (requestId !== healthRequestId.current) return;
      setHealthError(errorMessage(error));
      setHealthStatus('error');
    }
  }, []);

  useEffect(() => {
    void checkHealth();
    return () => { healthRequestId.current += 1; };
  }, [checkHealth]);

  const loadProjects = useCallback(async (selectId?: string) => {
    setProjectsBusy(true);
    setProjectError('');
    try {
      const result = await codeApi.get<CodeProject[]>('/projects');
      setProjects(result);
      if (selectId) setProjectId(selectId);
      else setProjectId((existing) => result.some((project) => project.id === existing) ? existing : result[0]?.id ?? '');
    } catch (error) {
      setProjectError(errorMessage(error));
    } finally {
      setProjectsBusy(false);
    }
  }, []);

  useEffect(() => {
    if (principal) void loadProjects();
  }, [loadProjects, principal]);

  const loadRepositories = useCallback(async () => {
    if (!projectId) {
      setRepositories([]);
      setRepositoryId('');
      return;
    }
    setRepositoriesBusy(true);
    setRepositoriesError('');
    try {
      const params = new URLSearchParams({ project_id: projectId });
      const result = await codeApi.get<Repository[]>(`/repositories?${params.toString()}`);
      setRepositories(result);
      setRepositoryId((existing) => result.some((repository) => repository.id === existing) ? existing : result[0]?.id ?? '');
    } catch (error) {
      setRepositoriesError(errorMessage(error));
    } finally {
      setRepositoriesBusy(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (principal) void loadRepositories();
  }, [loadRepositories, principal]);

  const loadPulls = useCallback(async () => {
    if (!repositoryId) {
      setPulls([]);
      return;
    }
    setPullsBusy(true);
    setPullsError('');
    try {
      const result = await codeApi.get<PullRequest[]>(`/repositories/${encodeURIComponent(repositoryId)}/pulls`);
      setPulls(result);
      if (selectedPullNumber && !result.some((pull) => pull.number === selectedPullNumber)) setSelectedPullNumber(null);
    } catch (error) {
      setPullsError(errorMessage(error));
    } finally {
      setPullsBusy(false);
    }
  }, [repositoryId, selectedPullNumber]);

  useEffect(() => {
    if (principal && repositoryId) void loadPulls();
    else setPulls([]);
  }, [loadPulls, principal, repositoryId]);

  const loadPullContext = useCallback(async (number = selectedPullNumber) => {
    if (!repositoryId || !number) return;
    setPullBusy(true);
    setPullError('');
    try {
      const context = await codeApi.get<PullRequestContext>(`/repositories/${encodeURIComponent(repositoryId)}/pulls/${number}`);
      setPullContext(context);
      return context;
    } catch (error) {
      setPullError(errorMessage(error));
      throw error;
    } finally {
      setPullBusy(false);
    }
  }, [repositoryId, selectedPullNumber]);

  useEffect(() => {
    if (!pullDrawerOpen || !selectedPullNumber) {
      setPullContext(null);
      return;
    }
    void loadPullContext().catch(() => undefined);
  }, [loadPullContext, pullDrawerOpen, selectedPullNumber]);

  useEffect(() => {
    if (!auth.session) {
      setPrincipal(null);
      setPrincipalSessionKey('');
      setAuthError('');
      setPrincipalErrorStatus(0);
      setProjects([]);
      setProjectId('');
      setRepositories([]);
      setRepositoryId('');
      setPulls([]);
      setPullContext(null);
      return;
    }
    let current = true;
    setPrincipal(null);
    setPrincipalSessionKey(auth.session.csrf_token);
    setAuthBusy(true);
    setAuthError('');
    setPrincipalErrorStatus(0);
    codeApi.me()
      .then((result) => { if (current) setPrincipal(result); })
      .catch((error) => { if (current) { setAuthError(errorMessage(error)); setPrincipalErrorStatus(error instanceof Error && 'status' in error ? Number((error as { status: unknown }).status) : 0); } })
      .finally(() => { if (current) setAuthBusy(false); });
    return () => { current = false; };
  }, [auth.session]);

  async function createProject(values: Record<string, unknown>) {
    if (auth.session?.user.role !== 'admin') {
      setProjectModalOpen(false);
      messageApi.error(t('只有管理員可以建立 Code project。'));
      return;
    }
    setProjectSaving(true);
    setFormError('');
    try {
      const created = await codeApi.post<CodeProject>('/projects', { key: values.key, name: values.name, description: values.description ?? '' });
      await loadProjects(created.id);
      setProjectModalOpen(false);
      projectForm.resetFields();
      messageApi.success(t('Code project 已建立。'));
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setProjectSaving(false);
    }
  }

  async function createRepository(values: Record<string, unknown>) {
    if (!projectId) return;
    setRepositorySaving(true);
    setFormError('');
    try {
      const repository = await codeApi.post<Repository>('/repositories', {
        project_id: projectId,
        name: values.name,
        description: values.description ?? '',
        private: true,
      });
      await loadRepositories();
      setRepositoryId(repository.id);
      setRepositoryModalOpen(false);
      repositoryForm.resetFields();
      messageApi.success(t('Private repository 已建立。'));
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setRepositorySaving(false);
    }
  }

  async function createBranch(values: Record<string, unknown>) {
    if (!repositoryId) return;
    setBranchSaving(true);
    setFormError('');
    try {
      const result = await codeApi.post<{ name: string; commit_sha: string }>(`/repositories/${encodeURIComponent(repositoryId)}/branches`, { name: values.name, from_branch: values.from_branch || undefined });
      setBranchModalOpen(false);
      branchForm.resetFields();
      messageApi.success(t('Branch {{branch}} 已建立，起始 commit {{sha}}。', { branch: result.name, sha: result.commit_sha.slice(0, 8) }));
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setBranchSaving(false);
    }
  }

  async function commitFile(values: Record<string, unknown>) {
    if (!repositoryId) return;
    setFileSaving(true);
    setFormError('');
    try {
      const result = await codeApi.post<{ path: string; branch: string; commit_sha: string; file_sha: string }>(`/repositories/${encodeURIComponent(repositoryId)}/files`, {
        branch: values.branch,
        path: values.path,
        content: values.content,
        commit_message: values.commit_message,
        expected_sha: values.expected_sha || undefined,
      });
      setFileModalOpen(false);
      fileForm.resetFields();
      messageApi.success(t('UTF-8 檔案已提交：{{sha}}。', { sha: result.commit_sha.slice(0, 8) }));
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setFileSaving(false);
    }
  }

  async function createPull(values: Record<string, unknown>) {
    if (!repositoryId) return;
    setPullSaving(true);
    setFormError('');
    try {
      const pull = await codeApi.post<PullRequest>(`/repositories/${encodeURIComponent(repositoryId)}/pulls`, {
        head: values.head,
        base: values.base || 'main',
        title: values.title,
        body: values.body ?? '',
        source_refs: values.source_refs ?? [],
      });
      await loadPulls();
      setSelectedPullNumber(pull.number);
      setPullModalOpen(false);
      setPullDrawerOpen(true);
      pullForm.resetFields();
      messageApi.success(t('已建立 Gitea PR #{{number}}。', { number: formatNumber(pull.number) }));
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setPullSaving(false);
    }
  }

  async function reportCheck(values: Record<string, unknown>) {
    if (!repositoryId) return;
    setCheckSaving(true);
    setFormError('');
    try {
      await codeApi.post<CodeCheck>(`/repositories/${encodeURIComponent(repositoryId)}/checks`, {
        commit_sha: values.commit_sha,
        context: values.context,
        state: values.state,
        description: values.description ?? '',
        target_url: values.target_url || undefined,
      });
      setCheckModalOpen(false);
      checkForm.resetFields();
      if (selectedPullNumber) await loadPullContext(selectedPullNumber);
      messageApi.success(t('狀態已送至 Gitea；紀錄會標示為 Agent 回報。'));
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setCheckSaving(false);
    }
  }

  function openCreateRepository() {
    setFormError('');
    repositoryForm.resetFields();
    setRepositoryModalOpen(true);
  }

  function openBranchModal() {
    setFormError('');
    branchForm.resetFields();
    branchForm.setFieldsValue({ from_branch: selectedRepository?.default_branch || 'main' });
    setBranchModalOpen(true);
  }

  function openFileModal() {
    setFormError('');
    fileForm.resetFields();
    fileForm.setFieldsValue({ branch: selectedRepository?.default_branch || 'main', commit_message: 'Add project file' });
    setFileModalOpen(true);
  }

  function openPullModal() {
    setFormError('');
    pullForm.resetFields();
    pullForm.setFieldsValue({ base: selectedRepository?.default_branch || 'main', source_refs: [] });
    setPullModalOpen(true);
  }

  function openCheckModal() {
    setFormError('');
    checkForm.resetFields();
    checkForm.setFieldsValue({ commit_sha: pullContext?.head_sha || '', context: 'agent/review', state: 'pending' });
    setCheckModalOpen(true);
  }

  const projectOptions = projects.map((project) => ({ value: project.id, label: `${project.key} · ${project.name}` }));
  const repositoryColumns: ColumnsType<Repository> = useMemo(() => [
    { title: t('儲存庫'), dataIndex: 'name', key: 'name', render: (_: unknown, repository) => <button type="button" className={`repository-list-row${repository.id === repositoryId ? ' repository-selected' : ''}`} onClick={() => { setRepositoryId(repository.id); setSection('repositories'); }}><CodeOutlined /><span><strong>{repository.owner}/{repository.name}</strong><small>{repository.default_branch} · {dateText(repository.created_at)}</small></span><Tag color="purple">{t('私人')}</Tag></button> },
  ], [repositoryId, locale]);

  const pullColumns: ColumnsType<PullRequest> = [
    { title: t('合併請求'), dataIndex: 'title', key: 'title', render: (title: string, pull) => <button type="button" className="pull-table-link" onClick={() => { setSelectedPullNumber(pull.number); setPullDrawerOpen(true); }}><span className={`pull-state-mark pull-state-${pull.state}`} /><span><strong>#{formatNumber(pull.number)} · {title}</strong><small>{pull.head} → {pull.base}</small></span></button> },
    { title: t('狀態'), dataIndex: 'state', key: 'state', width: 90, render: (value: PullRequest['state']) => <Tag color={value === 'open' ? 'green' : 'default'}>{t(value === 'open' ? '開啟' : '關閉')}</Tag> },
    { title: t('更新'), dataIndex: 'updated_at', key: 'updated_at', width: 130, render: dateText },
    { title: '', key: 'external', width: 80, render: (_: unknown, pull) => { const href = webUrl(pull.web_url); return href ? <Tooltip title={t('在 Gitea 檢視')}><Button type="link" href={href} target="_blank" rel="noreferrer">{t('開啟')}</Button></Tooltip> : null; } },
  ];

  if (!auth.session) {
    return <>{messageContext}<ProductLogin product="code" productName="Code" /></>;
  }
  if (authBusy || principalSessionKey !== auth.session.csrf_token) {
    return <>{messageContext}<div className="product-inline-loading"><Spin /></div></>;
  }
  if (!principal) {
    return <>{messageContext}<AuthAccessDenied product="code" productName="Code" error={authError} forbidden={principalErrorStatus === 403} onRetry={() => window.location.reload()} /></>;
  }

  return (
    <>
      {messageContext}
      <ProductShell
        product="code"
        productLabel="Ordivant Code"
        principal={principal}
        sectionLabel="Code"
        navigation={[
          { key: 'repositories', label: t('儲存庫'), icon: <CodeOutlined /> },
          { key: 'pulls', label: t('合併請求'), icon: <PullRequestOutlined /> },
        ]}
        activeSection={section}
        onSectionChange={(key) => setSection(key as CodeSection)}
        mode={health?.mode ?? 'unavailable'}
        serviceStatus={healthStatus}
        headerExtra={<Space size={7}><Select aria-label={t('選擇 Code project')} className="product-scope-select" placeholder={t('選擇 Project')} value={projectId || undefined} loading={projectsBusy} onChange={(value) => { setProjectId(value); setRepositoryId(''); setSelectedPullNumber(null); }} options={projectOptions} notFoundContent={t('沒有可存取的 Project')} />{canCreateProject && <Button aria-label={t('建立 Code project')} icon={<PlusOutlined />} onClick={() => { projectForm.resetFields(); setFormError(''); setProjectModalOpen(true); }}>{t('新增 Project')}</Button>}<Button aria-label={t('重新檢查 Code 與 Gitea 狀態')} icon={<ReloadOutlined />} loading={healthStatus === 'checking'} onClick={() => void checkHealth()}>{t('重新檢查')}</Button></Space>}
        title={t(section === 'repositories' ? '儲存庫' : '合併請求')}
        eyebrow={selectedProject ? `${selectedProject.key} · ${selectedProject.name}` : 'CODE'}
        actions={section === 'repositories' && canWrite ? <Button type="primary" icon={<PlusOutlined />} disabled={!projectId || !giteaConfigured} onClick={openCreateRepository}>{t('新增私人儲存庫')}</Button> : undefined}
      >
        {healthStatus === 'error' && <Alert className="product-page-alert" type="error" showIcon message={t('Code API 無法連線')} description={t(healthError)} action={<Button size="small" onClick={() => void checkHealth()}>{t('重試')}</Button>} />}
        {!giteaConfigured && healthStatus === 'ok' && <Alert className="product-page-alert" type="warning" showIcon message={t('Gitea 未設定')} description={t('儲存庫與合併請求中繼資料仍可檢視；新增儲存庫、分支、提交、PR 與回報狀態目前不可用。Code 服務本身仍可正常啟動。')} action={<Button size="small" onClick={() => void checkHealth()}>{t('重新檢查')}</Button>} />}
        {projectError && <Alert className="product-page-alert" type="error" showIcon message={t('Code project 載入失敗')} description={t(projectError)} action={<Button size="small" onClick={() => void loadProjects()}>{t('重試')}</Button>} />}
        {!projectId ? (
          <div className="product-empty-state"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t(projectsBusy ? '正在載入 Code project' : canCreateProject ? '目前沒有可存取的 Code project' : '目前沒有可存取的 Code project，請聯絡管理員授予 Project 存取權或建立新 Project。')} />{canCreateProject && <Button type="primary" icon={<PlusOutlined />} onClick={() => setProjectModalOpen(true)}>{t('建立 Code project')}</Button>}</div>
        ) : section === 'repositories' ? (
          <div className="code-workspace">
            <aside className="repository-list-pane">
              <div className="product-list-head"><span>{t('儲存庫')}</span><span>{repositoriesBusy ? t('載入中') : formatNumber(repositories.length)}</span></div>
              {repositoriesError && <Alert type="error" showIcon message={t(repositoriesError)} action={<Button size="small" onClick={() => void loadRepositories()}>{t('重試')}</Button>} />}
              {repositoriesBusy && !repositories.length && <div className="product-inline-loading"><Spin size="small" /></div>}
              {!repositoriesBusy && repositories.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('此 project 尚無儲存庫')}>{canWrite && giteaConfigured && <Button size="small" type="primary" onClick={openCreateRepository}>{t('建立私人儲存庫')}</Button>}</Empty>}
              {repositories.length > 0 && <Table<Repository> rowKey="id" columns={repositoryColumns} dataSource={repositories} showHeader={false} pagination={false} size="small" />}
            </aside>
            <main className="repository-detail-pane">
              {!selectedRepository && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('選取儲存庫以檢視分支與 PR')} />}
              {selectedRepository && <>
                <div className="repository-header"><div><div className="repository-path">{selectedRepository.owner}/{selectedRepository.name}</div><Title level={3}>{selectedRepository.name}</Title><Paragraph>{selectedRepository.project_id.slice(0, 8)} · {t('Gitea 私人儲存庫')}</Paragraph></div><Space wrap><Button icon={<ReloadOutlined />} onClick={() => { void loadRepositories(); void loadPulls(); }}>{t('重新整理')}</Button>{giteaConfigured && canWrite && <Button icon={<BranchesOutlined />} onClick={openBranchModal}>{t('建立分支')}</Button>}{giteaConfigured && canWrite && <Button icon={<FileAddOutlined />} onClick={openFileModal}>{t('提交檔案')}</Button>}{giteaConfigured && canWrite && <Button type="primary" icon={<PullRequestOutlined />} onClick={openPullModal}>{t('建立 PR')}</Button>}</Space></div>
                <Descriptions className="repository-metadata" size="small" column={{ xs: 1, sm: 2 }}>
                  <Descriptions.Item label={t('Provider')}>Gitea</Descriptions.Item><Descriptions.Item label={t('Default branch')}><Tag>{selectedRepository.default_branch}</Tag></Descriptions.Item>
                  <Descriptions.Item label={t('Web URL')}>{webUrl(selectedRepository.web_url) ? <a href={webUrl(selectedRepository.web_url) ?? undefined} target="_blank" rel="noreferrer">{selectedRepository.web_url}</a> : selectedRepository.web_url}</Descriptions.Item>
                  <Descriptions.Item label={t('Clone URL')}><span className="clone-url">{selectedRepository.clone_url}</span></Descriptions.Item>
                  <Descriptions.Item label={t('建立時間')}>{dateText(selectedRepository.created_at)}</Descriptions.Item>
                </Descriptions>
                {!giteaConfigured && <div className="gitea-unavailable-inline"><SafetyCertificateOutlined /><span>{t('服務尚未連接 Gitea。現有儲存庫綁定可供查閱，寫入操作需先完成服務端 Gitea 設定。')}</span></div>}
                <div className="repository-pr-heading"><div><span className="eyebrow">{t('審查流程')}</span><h3>{t('合併請求')}</h3></div><Button type="link" icon={<PullRequestOutlined />} onClick={() => setSection('pulls')}>{t('檢視清單')}</Button></div>
                {pullsError && <Alert type="error" showIcon message={t('PR 清單載入失敗')} description={t(pullsError)} action={<Button size="small" onClick={() => void loadPulls()}>{t('重試')}</Button>} />}
                {pullsBusy && !pulls.length && <Spin size="small" />}
                {!pullsBusy && pulls.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('此儲存庫尚無 PR')} />}
                {pulls.slice(0, 6).map((pull) => <button key={pull.id} type="button" className="repository-pr-row" onClick={() => { setSelectedPullNumber(pull.number); setPullDrawerOpen(true); }}><span className={`pull-state-mark pull-state-${pull.state}`} /><span><strong>#{formatNumber(pull.number)} · {pull.title}</strong><small>{pull.head} → {pull.base}</small></span><Tag color={pull.state === 'open' ? 'green' : 'default'}>{t(pull.state === 'open' ? '開啟' : '關閉')}</Tag></button>)}
              </>}
            </main>
          </div>
        ) : (
          <section className="code-pull-list">
            <div className="product-list-head"><span>{t('合併請求')} {selectedRepository ? `· ${selectedRepository.owner}/${selectedRepository.name}` : ''}</span><Space><Select aria-label={t('篩選儲存庫')} allowClear placeholder={t('所有儲存庫')} value={repositoryId || undefined} onChange={(value) => { setRepositoryId(value ?? ''); setSelectedPullNumber(null); setPullContext(null); }} options={repositories.map((repository) => ({ value: repository.id, label: `${repository.owner}/${repository.name}` }))} /><Button icon={<ReloadOutlined />} onClick={() => void loadPulls()}>{t('重新整理')}</Button></Space></div>
            {pullsError && <Alert className="product-page-alert" type="error" showIcon message={t('PR 清單載入失敗')} description={t(pullsError)} action={<Button size="small" onClick={() => void loadPulls()}>{t('重試')}</Button>} />}
            {pullsBusy && !pulls.length && <div className="product-inline-loading"><Spin /></div>}
            {!repositoryId && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('請先選擇儲存庫')} />}
            {repositoryId && !pullsBusy && pulls.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('沒有合併請求')} />}
            <Table<PullRequest> rowKey="id" columns={pullColumns} dataSource={pulls} loading={pullsBusy} pagination={{ pageSize: 12, showSizeChanger: false }} scroll={{ x: 670 }} />
          </section>
        )}
      </ProductShell>

      {canCreateProject && <Modal title={t('建立 Code project')} open={projectModalOpen} onCancel={() => setProjectModalOpen(false)} onOk={() => projectForm.submit()} confirmLoading={projectSaving} okText={t('建立 Project')} cancelText={t('取消')} destroyOnClose>
        {formError && <Alert className="product-form-alert" type="error" showIcon message={t(formError)} />}
        <Form form={projectForm} layout="vertical" onFinish={(values) => void createProject(values)}><Form.Item name="key" label={t('Project 代碼')} rules={[{ required: true }]}><Input maxLength={24} /></Form.Item><Form.Item name="name" label={t('名稱')} rules={[{ required: true }]}><Input maxLength={120} /></Form.Item><Form.Item name="description" label={t('描述')}><TextArea rows={3} /></Form.Item></Form>
      </Modal>}

      <Modal title={t('建立私人儲存庫')} open={repositoryModalOpen} onCancel={() => setRepositoryModalOpen(false)} onOk={() => repositoryForm.submit()} confirmLoading={repositorySaving} okText={t('建立儲存庫')} cancelText={t('取消')} destroyOnClose>
        {formError && <Alert className="product-form-alert" type="error" showIcon message={t(formError)} />}
        <Form form={repositoryForm} layout="vertical" onFinish={(values) => void createRepository(values)}><Form.Item label={t('Code project')}>{selectedProject?.key} · {selectedProject?.name}</Form.Item><Form.Item name="name" label={t('儲存庫名稱')} rules={[{ required: true, whitespace: true }]}><Input maxLength={100} /></Form.Item><Form.Item name="description" label={t('描述')}><TextArea rows={3} /></Form.Item><Alert type="info" showIcon message={t('預設為私人儲存庫，使用 main 分支並初始化 README')} description={t('建立要求會送至服務端綁定的 Gitea 帳號。其 upstream token 不會送回瀏覽器。')} /></Form>
      </Modal>

      <Modal title={t('建立分支') + ` · ${selectedRepository?.name ?? ''}`} open={branchModalOpen} onCancel={() => setBranchModalOpen(false)} onOk={() => branchForm.submit()} confirmLoading={branchSaving} okText={t('建立分支')} cancelText={t('取消')} destroyOnClose>
        {formError && <Alert className="product-form-alert" type="error" showIcon message={t(formError)} />}
        <Form form={branchForm} layout="vertical" onFinish={(values) => void createBranch(values)}><Form.Item name="name" label={t('分支名稱')} rules={[{ required: true, whitespace: true }]}><Input placeholder="feature/short-description" /></Form.Item><Form.Item name="from_branch" label={t('來源分支')}><Input /></Form.Item></Form>
      </Modal>

      <Modal title={t('提交 UTF-8 檔案') + ` · ${selectedRepository?.name ?? ''}`} open={fileModalOpen} onCancel={() => setFileModalOpen(false)} onOk={() => fileForm.submit()} confirmLoading={fileSaving} okText={t('建立提交')} cancelText={t('取消')} width={720} destroyOnClose>
        {formError && <Alert className="product-form-alert" type="error" showIcon message={t(formError)} />}
        <Form form={fileForm} layout="vertical" onFinish={(values) => void commitFile(values)}><Form.Item name="branch" label={t('目標分支')} rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="path" label={t('儲存庫路徑')} rules={[{ required: true, whitespace: true }]}><Input placeholder="src/README.md" /></Form.Item><Form.Item name="content" label={t('檔案內容（UTF-8）')} rules={[{ required: true, message: t('檔案內容不得空白') }]}><TextArea rows={12} spellCheck /></Form.Item><Form.Item name="commit_message" label={t('提交訊息')} rules={[{ required: true, whitespace: true }]}><Input maxLength={200} /></Form.Item><Form.Item name="expected_sha" label={t('更新既有檔案時的 expected SHA')}><Input placeholder={t('新增檔案時留空')} /></Form.Item><div className="form-note">{t('內容會以 UTF-8 編碼送交服務端，再由 Gitea Contents API 建立提交。')}</div></Form>
      </Modal>

      <Modal title={t('建立合併請求') + ` · ${selectedRepository?.name ?? ''}`} open={pullModalOpen} onCancel={() => setPullModalOpen(false)} onOk={() => pullForm.submit()} confirmLoading={pullSaving} okText={t('建立 PR')} cancelText={t('取消')} width={720} destroyOnClose>
        {formError && <Alert className="product-form-alert" type="error" showIcon message={t(formError)} />}
        <Form form={pullForm} layout="vertical" onFinish={(values) => void createPull(values)}><Form.Item name="head" label={t('來源分支（Head）')} rules={[{ required: true }]}><Input placeholder="feature/short-description" /></Form.Item><Form.Item name="base" label={t('目標分支（Base）')} rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="title" label={t('PR 標題')} rules={[{ required: true, whitespace: true }]}><Input maxLength={250} /></Form.Item><Form.Item name="body" label={t('描述')}><TextArea rows={4} /></Form.Item><Divider orientation="left" plain>{t('Work / Knowledge / 外部來源')}</Divider><ReferenceFields /></Form>
      </Modal>

      <Modal title={t('回報提交狀態')} open={checkModalOpen} onCancel={() => setCheckModalOpen(false)} onOk={() => checkForm.submit()} confirmLoading={checkSaving} okText={t('送出狀態')} cancelText={t('取消')} destroyOnClose>
        {formError && <Alert className="product-form-alert" type="error" showIcon message={t(formError)} />}
        <Alert className="product-form-alert" type="warning" showIcon message={t('此為 Agent 回報')} description={t('狀態會送至 Gitea 並保留為 agent_reported receipt；不表示 CI runner 實際執行過測試。')} />
        <Form form={checkForm} layout="vertical" onFinish={(values) => void reportCheck(values)}><Form.Item name="commit_sha" label={t('提交 SHA')} rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="context" label={t('Context')} rules={[{ required: true }]}><Input maxLength={100} /></Form.Item><Form.Item name="state" label={t('狀態')} rules={[{ required: true }]}><Select options={[{ value: 'pending', label: t('待處理') }, { value: 'success', label: t('成功') }, { value: 'failure', label: t('失敗') }, { value: 'error', label: t('錯誤') }]} /></Form.Item><Form.Item name="description" label={t('說明')}><TextArea rows={2} /></Form.Item><Form.Item name="target_url" label={t('Target URL')}><Input /></Form.Item></Form>
      </Modal>

      <Drawer title={pullContext ? `PR #${formatNumber(pullContext.number)} · ${pullContext.title}` : t('合併請求')} open={pullDrawerOpen} onClose={() => setPullDrawerOpen(false)} width={620} className="code-pr-drawer">
        {pullError && <Alert type="error" showIcon message={t('合併請求載入失敗')} description={t(pullError)} action={<Button size="small" onClick={() => void loadPullContext()}>{t('重試')}</Button>} />}
        {pullBusy && !pullContext && <div className="product-inline-loading"><Spin /></div>}
        {pullContext && <PullDetail context={pullContext} repositoryId={repositoryId} principal={principal} canWrite={canWrite} canReport={canWrite && giteaConfigured} onReport={() => openCheckModal()} onRefreshContext={() => loadPullContext()} />}
      </Drawer>
    </>
  );
}

function PullDetail({ context, repositoryId, principal, canWrite, canReport, onReport, onRefreshContext }: { context: PullRequestContext; repositoryId: string; principal: ProductPrincipal | null; canWrite: boolean; canReport: boolean; onReport: () => void; onRefreshContext: () => Promise<PullRequestContext | undefined> }) {
  const { t } = useI18n();
  const href = webUrl(context.web_url);
  return (
    <div className="pull-detail">
      <div className="pull-detail-top"><Tag color={context.state === 'open' ? 'green' : 'default'}>{t(context.state === 'open' ? '開啟' : '關閉')}</Tag><span>{context.head} → {context.base}</span>{href && <a href={href} target="_blank" rel="noreferrer">{t('在 Gitea 開啟')}</a>}</div>
      {context.body ? <MarkdownContent content={context.body} /> : <Paragraph>{t('沒有 PR 描述。')}</Paragraph>}
      <Descriptions size="small" column={1} colon={false}><Descriptions.Item label={t('Head SHA')}><code>{context.head_sha}</code></Descriptions.Item><Descriptions.Item label={t('建立時間')}>{dateText(context.created_at)}</Descriptions.Item><Descriptions.Item label={t('更新時間')}>{dateText(context.updated_at)}</Descriptions.Item></Descriptions>
      <div className="code-detail-section-head"><div><span className="eyebrow">{t('來源引用')}</span><h3>{t('來源與 provenance')}</h3></div><span>{formatNumber(context.source_refs.length)}</span></div>
      <ReferenceList references={context.source_refs} />
      <PullCollaborationPanel repositoryId={repositoryId} context={context} principal={principal} canWrite={canWrite} onRefreshContext={onRefreshContext} />
      <div className="code-detail-section-head check-section-head"><div><span className="eyebrow">{t('提交收據')}</span><h3>{t('Checks 與狀態')}</h3></div><Button size="small" icon={<SendOutlined />} disabled={!canReport} onClick={onReport}>{t('回報狀態')}</Button></div>
      <div className="check-receipt-note">{t('source=agent_reported 代表 Agent 提交的狀態回報；source=gitea_webhook 代表已驗證 webhook。這些資訊不會被標示成實際 CI 執行結果。')}</div>
      {!context.checks.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('此 PR 尚無 check receipt')} />}
      {context.checks.map((check) => <CheckRow key={check.id} check={check} />)}
    </div>
  );
}

function PullCollaborationPanel({ repositoryId, context, principal, canWrite, onRefreshContext }: { repositoryId: string; context: PullRequestContext; principal: ProductPrincipal | null; canWrite: boolean; onRefreshContext: () => Promise<PullRequestContext | undefined> }) {
  const { t } = useI18n();
  const [collaboration, setCollaboration] = useState<PullCollaboration | null>(null);
  const [busy, setBusy] = useState(true);
  const [savingComment, setSavingComment] = useState(false);
  const [savingReview, setSavingReview] = useState(false);
  const [error, setError] = useState('');
  const [comment, setComment] = useState('');
  const [reviewComment, setReviewComment] = useState('');
  const [decision, setDecision] = useState<PullCollaborationReview['decision']>('comment');
  const pullPath = `/repositories/${encodeURIComponent(repositoryId)}/pulls/${context.number}`;
  const collaborationPath = `${pullPath}/collaboration`;

  const loadCollaboration = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const result = await codeApi.get<PullCollaboration>(collaborationPath);
      setCollaboration(result);
      return result;
    } catch (loadError) {
      setError(errorMessage(loadError));
      return null;
    } finally {
      setBusy(false);
    }
  }, [collaborationPath]);

  useEffect(() => {
    setCollaboration(null);
    void loadCollaboration();
  }, [loadCollaboration]);

  const proposerIsCurrentPrincipal = Boolean(
    collaboration?.proposer
    && principal
    && collaboration.proposer.id === principal.id
    && collaboration.proposer.kind === principal.kind,
  );
  const collaborationHeadChanged = Boolean(collaboration && collaboration.head_sha !== context.head_sha);

  async function reloadReviews() {
    await Promise.allSettled([loadCollaboration(), onRefreshContext()]);
  }

  async function submitComment() {
    const body = comment.trim();
    if (!canWrite || !body) return;
    setSavingComment(true);
    setError('');
    try {
      await codeApi.post(`${pullPath}/comments`, { body });
      setComment('');
      await loadCollaboration();
    } catch (submitError) {
      setError(errorMessage(submitError));
    } finally {
      setSavingComment(false);
    }
  }

  async function submitReview() {
    const body = reviewComment.trim();
    if (!canWrite || !body || !context.head_sha || (proposerIsCurrentPrincipal && decision !== 'comment')) return;
    setSavingReview(true);
    setError('');
    try {
      await codeApi.post(`${pullPath}/reviews`, {
        decision,
        comment: body,
        expected_head_sha: context.head_sha,
      });
      setReviewComment('');
      await loadCollaboration();
    } catch (submitError) {
      setError(errorMessage(submitError));
    } finally {
      setSavingReview(false);
    }
  }

  const decisionLabels: Record<PullCollaborationReview['decision'], string> = {
    approve: '核准',
    request_changes: '要求變更',
    comment: '一般意見',
  };

  return (
    <section className="code-pr-collaboration" aria-label={t('Ordivant PR 協作')}>
      <div className="code-detail-section-head">
        <div><span className="eyebrow">{t('Ordivant PR 協作')}</span><h3>{t('討論與審查記錄')}</h3></div>
        <Button size="small" icon={<ReloadOutlined />} onClick={() => void loadCollaboration()} loading={busy}>{t('重新載入')}</Button>
      </div>
      <Alert className="code-collaboration-note" type="info" showIcon message={t('Ordivant 協作與審查紀錄由 Ordivant 保存；合併與 Gitea 自身的核准規則仍由 Gitea 管理，這些紀錄不代表 CI 結果。')} />
      {collaborationHeadChanged && <Alert
        className="code-collaboration-stale"
        type="warning"
        showIcon
        message={t('PR head 已變更，請重新載入審查記錄。')}
        description={<Button size="small" onClick={() => void reloadReviews()} loading={busy}>{t('重新載入審查記錄')}</Button>}
      />}
      {error && <Alert className="code-collaboration-error" type="error" showIcon message={t('Ordivant PR 協作載入或更新失敗')} description={t(error)} action={<Button size="small" onClick={() => void loadCollaboration()}>{t('重試')}</Button>} />}
      {busy && !collaboration && <div className="product-inline-loading"><Spin size="small" /></div>}
      {!busy && !collaboration && !error && <Alert type="error" showIcon message={t('協作記錄不可用')} />}
      {collaboration && <>
        {collaboration.proposer && <div className="code-collaboration-entry-head"><span>{t('提案者')}</span><strong>{collaboration.proposer.name}</strong><Tag color={collaboration.proposer.kind === 'agent' ? 'purple' : 'blue'}>{t(collaboration.proposer.kind === 'agent' ? 'Agent' : '真人')}</Tag></div>}
        <div className="code-collaboration-heads">
          <span>{t('記錄版本')} <code>{collaboration.head_sha}</code></span>
          <span>{t('目前 head')} <code>{context.head_sha}</code></span>
        </div>
        <div className="code-collaboration-subhead"><strong>{t('討論')}</strong><span>{formatNumber(collaboration.comments.length)}</span></div>
        {!collaboration.comments.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('尚無討論')} />}
        {collaboration.comments.map((item) => <div className="code-collaboration-entry" key={item.id}>
          <div className="code-collaboration-entry-head"><strong>{item.author.name}</strong><Tag color={item.author.kind === 'agent' ? 'purple' : 'blue'}>{t(item.author.kind === 'agent' ? 'Agent' : '真人')}</Tag><time>{dateText(item.created_at)}</time></div>
          <MarkdownContent content={item.body} />
        </div>)}
        {canWrite
          ? <div className="code-collaboration-compose"><TextArea value={comment} onChange={(event) => setComment(event.target.value)} rows={3} maxLength={20000} placeholder={t('新增討論')} /><Button type="primary" icon={<SendOutlined />} loading={savingComment} disabled={!comment.trim()} onClick={() => void submitComment()}>{t('送出討論')}</Button></div>
          : <div className="code-collaboration-readonly">{t('目前為唯讀，可查看討論與審查記錄。')}</div>}

        <div className="code-collaboration-subhead"><strong>{t('審查歷程')}</strong><span>{formatNumber(collaboration.reviews.length)}</span></div>
        {!collaboration.reviews.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('尚無審查記錄')} />}
        {collaboration.reviews.map((review) => {
          const isCurrent = review.is_current && review.head_sha === collaboration.head_sha && review.head_sha === context.head_sha;
          return <div className="code-collaboration-entry" key={review.id}>
            <div className="code-collaboration-entry-head"><strong>{review.author.name}</strong><Tag color={review.author.kind === 'agent' ? 'purple' : 'blue'}>{t(review.author.kind === 'agent' ? 'Agent' : '真人')}</Tag><Tag color={review.decision === 'approve' ? 'green' : review.decision === 'request_changes' ? 'red' : 'default'}>{t(decisionLabels[review.decision])}</Tag><Tag color={isCurrent ? 'green' : 'default'}>{t(isCurrent ? '最新 head' : '已過期')}</Tag><time>{dateText(review.created_at)}</time></div>
            {review.comment && <MarkdownContent content={review.comment} />}
            <div className="code-collaboration-sha">{review.head_sha}</div>
          </div>;
        })}
        {canWrite ? <div className="code-collaboration-compose code-collaboration-review">
          {proposerIsCurrentPrincipal && <Alert type="warning" showIcon message={t('PR 提案者不能核准或要求變更自己的 PR。')} />}
          <Select value={decision} onChange={(value: PullCollaborationReview['decision']) => setDecision(value)} options={(['approve', 'request_changes', 'comment'] as const).map((value) => ({ value, label: t(decisionLabels[value]), disabled: proposerIsCurrentPrincipal && value !== 'comment' }))} />
          <TextArea value={reviewComment} onChange={(event) => setReviewComment(event.target.value)} rows={3} maxLength={20000} placeholder={t('請輸入審查意見')} />
          <Button type="primary" icon={<SafetyCertificateOutlined />} loading={savingReview} disabled={!reviewComment.trim() || !context.head_sha || (proposerIsCurrentPrincipal && decision !== 'comment')} onClick={() => void submitReview()}>{t('送出審查記錄')}</Button>
        </div> : <div className="code-collaboration-readonly">{t('目前為唯讀，可查看討論與審查記錄。')}</div>}
      </>}
    </section>
  );
}

function CheckRow({ check }: { check: CodeCheck }) {
  const { t } = useI18n();
  const color = ({ pending: 'gold', success: 'green', failure: 'red', error: 'volcano' })[check.state];
  const stateLabels: Record<CodeCheck['state'], string> = { pending: '待處理', success: '成功', failure: '失敗', error: '錯誤' };
  return <div className="check-row"><div className="check-row-head"><Tag color={color}>{t(stateLabels[check.state])}</Tag><strong>{check.context}</strong><Tag color={check.source === 'agent_reported' ? 'orange' : 'blue'}>{t(check.source === 'agent_reported' ? 'Agent 回報' : 'Gitea webhook')}</Tag><time>{dateText(check.created_at)}</time></div>{check.description && <Paragraph>{check.description}</Paragraph>}{check.target_url && webUrl(check.target_url) && <a href={webUrl(check.target_url) ?? undefined} target="_blank" rel="noreferrer">{t('查看 target')}</a>}<div className="check-commit">{check.commit_sha}</div></div>;
}
