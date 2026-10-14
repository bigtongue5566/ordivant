import { localizeTemplate } from './builtinTemplates';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Divider,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import {
  FileAddOutlined,
  FileTextOutlined,
  BoldOutlined,
  CommentOutlined,
  FolderOpenOutlined,
  HistoryOutlined,
  ItalicOutlined,
  LinkOutlined,
  PictureOutlined,
  PlusOutlined,
  SearchOutlined,
  SafetyCertificateOutlined,
  TableOutlined,
} from '@ant-design/icons';
import { ProductApiError, createProductApi, productApiPrefix } from '../shared/productApi';
import { CollaborationPanel } from '../shared/CollaborationPanel';
import { ProductLogin } from '../shared/ProductLogin';
import { ProductShell } from '../shared/ProductShell';
import { MarkdownContent, MarkdownPreview } from '../../shared/MarkdownContent';
import { CollaborativeMarkdownEditor, type KnowledgeCollaborationState } from '../../shared/CollaborativeMarkdownEditor';
import { AuthProvider, useAuth } from '../../auth/AuthContext';
import { AuthAccessDenied } from '../../auth/AuthAccessDenied';
import { ReferenceFields, ReferenceList } from '../shared/References';
import type { Decision, DocumentContext, DocumentHit, DocumentVersion, ProductHealth, ProductPrincipal, Space as KnowledgeSpace } from '../shared/types';
import { formatDate, formatNumber, useI18n, useLocalizedForm } from '../../i18n';
import './KnowledgeAuthoring.css';

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;
const knowledgeApi = createProductApi(productApiPrefix('knowledge'));
const defaultTableMarkdown = '\n| 欄位 1 | 欄位 2 |\n| --- | --- |\n| 內容 | 內容 |\n';

type KnowledgeSection = 'documents' | 'decisions';
type KnowledgeDocumentHit = DocumentHit & { parent_id?: string | null; archived?: boolean };
type KnowledgeDocumentContext = Omit<DocumentContext, 'document'> & {
  document: DocumentContext['document'] & { parent_id?: string | null; archived?: boolean };
};
type SpaceTemplate = { id: string; space_id: string; name: string; description: string; body: string; builtin: boolean };
type KnowledgeComment = {
  id: string;
  document_id: string;
  author_id: string;
  author_name: string;
  body: string;
  anchor: { quote: string; start?: number; end?: number; version: number } | null;
  anchor_stale: boolean;
  parent_id: string | null;
  resolved: boolean;
  created_at: string;
};

function flattenDocumentTree(documents: KnowledgeDocumentHit[]): Array<{ document: KnowledgeDocumentHit; level: number }> {
  const byParent = new Map<string | null, KnowledgeDocumentHit[]>();
  for (const document of documents) {
    const parentId = documents.some((item) => item.id === document.parent_id) ? document.parent_id ?? null : null;
    const children = byParent.get(parentId) ?? [];
    children.push(document);
    byParent.set(parentId, children);
  }
  const output: Array<{ document: KnowledgeDocumentHit; level: number }> = [];
  const visited = new Set<string>();
  const walk = (parentId: string | null, level: number) => {
    for (const document of byParent.get(parentId) ?? []) {
      if (visited.has(document.id)) continue;
      visited.add(document.id);
      output.push({ document, level });
      walk(document.id, level + 1);
    }
  };
  walk(null, 0);
  for (const document of documents) {
    if (!visited.has(document.id)) output.push({ document, level: 0 });
  }
  return output;
}

function dateText(value?: string | null): string {
  return formatDate(value);
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && 'sourceMessage' in error) return String((error as Error & { sourceMessage: string }).sourceMessage);
  return error instanceof Error ? error.message : '發生未預期的錯誤。';
}

export default function KnowledgeApp() {
  return <AuthProvider><KnowledgeWorkspace /></AuthProvider>;
}

function KnowledgeWorkspace() {
  const { t } = useI18n();
  const requestedResourceId = useRef((typeof window === 'undefined' ? '' : new URLSearchParams(window.location.search).get('resource')?.trim()) || null);
  const resourceResolutionKey = useRef('');
  const authorizedResourceId = useRef('');
  const authorizedResourceSpaceId = useRef('');
  const auth = useAuth();
  const [messageApi, messageContext] = message.useMessage();
  const [health, setHealth] = useState<ProductHealth | null>(null);
  const [healthStatus, setHealthStatus] = useState<'checking' | 'ok' | 'error'>('checking');
  const [healthError, setHealthError] = useState('');
  const [principal, setPrincipal] = useState<ProductPrincipal | null>(null);
  const [principalSessionKey, setPrincipalSessionKey] = useState('');
  const [principalErrorStatus, setPrincipalErrorStatus] = useState(0);
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState('');
  const [spaces, setSpaces] = useState<KnowledgeSpace[]>([]);
  const [spacesError, setSpacesError] = useState('');
  const [spacesReload, setSpacesReload] = useState(0);
  const [spaceId, setSpaceId] = useState('');
  const [spaceBusy, setSpaceBusy] = useState(false);
  const [section, setSection] = useState<KnowledgeSection>('documents');
  const [documents, setDocuments] = useState<KnowledgeDocumentHit[]>([]);
  const [documentsBusy, setDocumentsBusy] = useState(false);
  const [documentsError, setDocumentsError] = useState('');
  const [query, setQuery] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const [templates, setTemplates] = useState<SpaceTemplate[]>([]);
  const [templatesBusy, setTemplatesBusy] = useState(false);
  const [documentId, setDocumentId] = useState('');
  const [resourceLoading, setResourceLoading] = useState(false);
  const [resourceError, setResourceError] = useState('');
  const [resourceAccessDenied, setResourceAccessDenied] = useState(false);
  const [documentContext, setDocumentContext] = useState<KnowledgeDocumentContext | null>(null);
  const [history, setHistory] = useState<DocumentVersion[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<DocumentVersion | null>(null);
  const [collaborationState, setCollaborationState] = useState<KnowledgeCollaborationState | null>(null);
  const [draftRefreshKey, setDraftRefreshKey] = useState(0);
  const [documentBusy, setDocumentBusy] = useState(false);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [decisionsBusy, setDecisionsBusy] = useState(false);
  const [decisionsError, setDecisionsError] = useState('');
  const [spaceModalOpen, setSpaceModalOpen] = useState(false);
  const [createDocumentOpen, setCreateDocumentOpen] = useState(false);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [decisionOpen, setDecisionOpen] = useState(false);
  const [spaceSaving, setSpaceSaving] = useState(false);
  const [documentSaving, setDocumentSaving] = useState(false);
  const [templateSaving, setTemplateSaving] = useState(false);
  const [publishSaving, setPublishSaving] = useState(false);
  const [decisionSaving, setDecisionSaving] = useState(false);
  const [publishError, setPublishError] = useState<{ message: string } | null>(null);
  const [formError, setFormError] = useState('');
  const [spaceForm] = Form.useForm();
  useLocalizedForm(spaceForm);
  const [documentForm] = Form.useForm();
  useLocalizedForm(documentForm);
  const [publishForm] = Form.useForm();
  useLocalizedForm(publishForm);
  const [decisionForm] = Form.useForm();
  useLocalizedForm(decisionForm);
  const [templateForm] = Form.useForm();
  useLocalizedForm(templateForm);
  const listRequestId = useRef(0);
  const healthRequestId = useRef(0);
  const selectedDocumentIdRef = useRef('');
  const documentContextRequestIdRef = useRef(0);
  const versionRequestIdRef = useRef(0);
  const selectDocument = useCallback((id: string) => {
    if (selectedDocumentIdRef.current !== id) {
      selectedDocumentIdRef.current = id;
      documentContextRequestIdRef.current += 1;
      versionRequestIdRef.current += 1;
      setDocumentContext(null);
      setHistory([]);
      setSelectedVersion(null);
      setCollaborationState(null);
      setDocumentBusy(Boolean(id));
    }
    setDocumentId(id);
  }, []);
  const currentSpace = spaces.find((item) => item.id === spaceId) ?? null;
  const canWrite = Boolean(principal && ['admin', 'manager', 'writer'].includes(principal.role));
  const canCreateSpace = auth.session?.user.role === 'admin';
  const flattenedDocuments = flattenDocumentTree(documents);
  const canPublishDraft = Boolean(
    canWrite
    && collaborationState?.draft.document_id === documentId
    && collaborationState.connection === 'live'
    && collaborationState.pendingUpdates === 0
    && !collaborationState.permissionLost,
  );

  const checkHealth = useCallback(async () => {
    const requestId = ++healthRequestId.current;
    setHealthStatus('checking');
    setHealthError('');
    try {
      const result = await knowledgeApi.health();
      if (requestId !== healthRequestId.current) return;
      setHealth(result);
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

  useEffect(() => {
    if (!principal) return;
    let current = true;
    setSpaceBusy(true);
    setSpacesError('');
    knowledgeApi.get<KnowledgeSpace[]>('/spaces')
      .then((result) => {
        if (!current) return;
        setSpaces(result);
        setSpaceId((existing) => result.some((space) => space.id === authorizedResourceSpaceId.current)
          ? authorizedResourceSpaceId.current
          : result.some((space) => space.id === existing) ? existing : result[0]?.id ?? '');
      })
      .catch((error) => { if (current) setSpacesError(errorMessage(error)); })
      .finally(() => { if (current) setSpaceBusy(false); });
    return () => { current = false; };
  }, [principal, spacesReload]);

  useEffect(() => {
    const resourceId = requestedResourceId.current;
    if (!principal || !resourceId) return;
    const resolutionKey = `${principal.id}:${resourceId}`;
    if (resourceResolutionKey.current === resolutionKey) return;
    resourceResolutionKey.current = resolutionKey;
    authorizedResourceId.current = '';
    authorizedResourceSpaceId.current = '';
    let current = true;
    setResourceLoading(true);
    setResourceError('');
    setResourceAccessDenied(false);
    knowledgeApi.get<KnowledgeDocumentContext>(`/documents/${encodeURIComponent(resourceId)}`)
      .then((context) => {
        if (!current || requestedResourceId.current !== resourceId) return;
        authorizedResourceId.current = resourceId;
        authorizedResourceSpaceId.current = context.document.space_id;
        setSection('documents');
        setShowArchived(Boolean(context.document.archived));
        setSpaceId(context.document.space_id);
        selectDocument(resourceId);
      })
      .catch((error) => {
        if (!current || requestedResourceId.current !== resourceId) return;
        const status = error instanceof Error && 'status' in error ? Number((error as { status: unknown }).status) : 0;
        setResourceAccessDenied(status === 403 || status === 404);
        setResourceError(errorMessage(error));
        setDocumentContext(null);
        setSelectedVersion(null);
        setHistory([]);
        selectDocument(resourceId);
      })
      .finally(() => { if (current) setResourceLoading(false); });
    return () => { current = false; };
  }, [principal, selectDocument]);

  const loadDocuments = useCallback(async () => {
    if (!spaceId) {
      setDocuments([]);
      return;
    }
    const requestId = ++listRequestId.current;
    const params = new URLSearchParams({ space_id: spaceId });
    if (query.trim()) params.set('q', query.trim());
    if (tagFilter.trim()) params.set('tag', tagFilter.trim());
    if (showArchived) params.set('include_archived', 'true');
    setDocumentsBusy(true);
    setDocumentsError('');
    try {
      const result = await knowledgeApi.get<KnowledgeDocumentHit[]>(`/documents?${params.toString()}`);
      if (requestId === listRequestId.current) {
        setDocuments(result);
        const nextDocumentId = requestedResourceId.current
          ?? (result.some((document) => document.id === selectedDocumentIdRef.current) ? selectedDocumentIdRef.current : result[0]?.id ?? '');
        selectDocument(nextDocumentId);
      }
    } catch (error) {
      if (requestId === listRequestId.current) setDocumentsError(errorMessage(error));
    } finally {
      if (requestId === listRequestId.current) setDocumentsBusy(false);
    }
  }, [query, selectDocument, showArchived, spaceId, tagFilter]);

  const loadTemplates = useCallback(async () => {
    if (!spaceId) {
      setTemplates([]);
      return;
    }
    setTemplatesBusy(true);
    try {
      setTemplates(await knowledgeApi.get<SpaceTemplate[]>(`/spaces/${encodeURIComponent(spaceId)}/templates`));
    } catch (error) {
      messageApi.error(errorMessage(error));
    } finally {
      setTemplatesBusy(false);
    }
  }, [messageApi, spaceId]);

  useEffect(() => {
    if (!principal || !spaceId || section !== 'documents') return;
    const timer = window.setTimeout(() => { void loadDocuments(); }, query ? 240 : 0);
    return () => window.clearTimeout(timer);
  }, [loadDocuments, principal, query, section, spaceId]);

  useEffect(() => {
    if (principal && spaceId) void loadTemplates();
    else setTemplates([]);
  }, [loadTemplates, principal]);

  const loadDecisions = useCallback(async () => {
    if (!spaceId) return;
    setDecisionsBusy(true);
    setDecisionsError('');
    try {
      const params = new URLSearchParams({ space_id: spaceId });
      setDecisions(await knowledgeApi.get<Decision[]>(`/decisions?${params.toString()}`));
    } catch (error) {
      setDecisionsError(errorMessage(error));
    } finally {
      setDecisionsBusy(false);
    }
  }, [spaceId]);

  useEffect(() => {
    if (principal && spaceId && section === 'decisions') void loadDecisions();
  }, [loadDecisions, principal, section, spaceId]);

  const loadDocumentContext = useCallback(async (id = documentId) => {
    if (!id || selectedDocumentIdRef.current !== id) return;
    const requestId = ++documentContextRequestIdRef.current;
    const isCurrentRequest = () => requestId === documentContextRequestIdRef.current && selectedDocumentIdRef.current === id;
    setDocumentBusy(true);
    try {
      const results = await Promise.allSettled([
        knowledgeApi.get<KnowledgeDocumentContext>(`/documents/${encodeURIComponent(id)}`),
        knowledgeApi.get<DocumentVersion[]>(`/documents/${encodeURIComponent(id)}/versions`),
      ]);
      if (!isCurrentRequest()) return;
      const contextResult = results[0];
      const historyResult = results[1];
      if (contextResult.status === 'rejected') throw contextResult.reason;
      setDocumentContext(contextResult.value);
      setSelectedVersion(contextResult.value.version);
      setHistory(historyResult.status === 'fulfilled' ? historyResult.value : contextResult.value.history);
    } finally {
      if (isCurrentRequest()) setDocumentBusy(false);
    }
  }, [documentId]);

  useEffect(() => {
    if (!documentId || section !== 'documents') {
      documentContextRequestIdRef.current += 1;
      versionRequestIdRef.current += 1;
      setDocumentContext(null);
      setHistory([]);
      setSelectedVersion(null);
      setDocumentBusy(false);
      return;
    }
    if (requestedResourceId.current === documentId && authorizedResourceId.current !== documentId && !resourceError) {
      setDocumentContext(null);
      setHistory([]);
      setSelectedVersion(null);
      setDocumentBusy(resourceLoading);
      return;
    }
    if (requestedResourceId.current === documentId && resourceError) {
      setDocumentContext(null);
      setHistory([]);
      setSelectedVersion(null);
      setDocumentBusy(false);
      return;
    }
    let current = true;
    setDocumentContext(null);
    setHistory([]);
    setSelectedVersion(null);
    setDocumentBusy(true);
    loadDocumentContext(documentId)
      .catch((error) => { if (current && selectedDocumentIdRef.current === documentId) messageApi.error(errorMessage(error)); });
    return () => {
      current = false;
      documentContextRequestIdRef.current += 1;
      versionRequestIdRef.current += 1;
    };
  }, [documentId, loadDocumentContext, messageApi, resourceError, resourceLoading, section]);

  useEffect(() => {
    if (!auth.session) {
      setPrincipal(null);
      setPrincipalSessionKey('');
      setAuthError('');
      setPrincipalErrorStatus(0);
      setSpaces([]);
      setSpaceId('');
      setDocuments([]);
      setDecisions([]);
      setDocumentContext(null);
      selectDocument('');
      return;
    }
    let current = true;
    setPrincipal(null);
    setPrincipalSessionKey(auth.session.csrf_token);
    setAuthBusy(true);
    setAuthError('');
    setPrincipalErrorStatus(0);
    knowledgeApi.me()
      .then((result) => { if (current) setPrincipal(result); })
      .catch((error) => { if (current) { setAuthError(errorMessage(error)); setPrincipalErrorStatus(error instanceof Error && 'status' in error ? Number((error as { status: unknown }).status) : 0); } })
      .finally(() => { if (current) setAuthBusy(false); });
    return () => { current = false; };
  }, [auth.session, selectDocument]);

  async function createSpace(values: Record<string, unknown>) {
    if (auth.session?.user.role !== 'admin') {
      setSpaceModalOpen(false);
      messageApi.error(t('只有管理員可以建立 Knowledge space。'));
      return;
    }
    setSpaceSaving(true);
    setFormError('');
    try {
      const created = await knowledgeApi.post<KnowledgeSpace>('/spaces', { key: values.key, name: values.name, description: values.description ?? '' });
      const refreshed = await knowledgeApi.get<KnowledgeSpace[]>('/spaces');
      setSpaces(refreshed);
      setSpaceId(created.id);
      setSpaceModalOpen(false);
      spaceForm.resetFields();
      messageApi.success(t('Knowledge space 已建立。'));
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setSpaceSaving(false);
    }
  }

  function openCreateDocument() {
    documentForm.resetFields();
    documentForm.setFieldsValue({ tags: [], source_refs: [], template_id: undefined, parent_id: undefined });
    setFormError('');
    setCreateDocumentOpen(true);
  }

  function clearResourceTarget(nextResourceId?: string) {
    requestedResourceId.current = null;
    resourceResolutionKey.current = '';
    authorizedResourceId.current = '';
    authorizedResourceSpaceId.current = '';
    setResourceLoading(false);
    setResourceError('');
    setResourceAccessDenied(false);
    const url = new URL(window.location.href);
    if (nextResourceId) url.searchParams.set('resource', nextResourceId);
    else url.searchParams.delete('resource');
    window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
  }

  async function createDocument(values: Record<string, unknown>) {
    if (!spaceId) return;
    setDocumentSaving(true);
    setFormError('');
    try {
      const created = await knowledgeApi.post<DocumentContext>('/documents', {
        space_id: spaceId,
        title: values.title,
        summary: values.summary ?? '',
        body: values.body,
        parent_id: values.parent_id || null,
        tags: values.tags ?? [],
        change_summary: values.change_summary ?? t('初版建立'),
        source_refs: values.source_refs ?? [],
      });
      setCreateDocumentOpen(false);
      documentForm.resetFields();
      setSection('documents');
      await loadDocuments();
      clearResourceTarget(created.document.id);
      selectDocument(created.document.id);
      messageApi.success(t('文件與 v1 已建立。'));
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setDocumentSaving(false);
    }
  }

  async function createTemplate(values: Record<string, unknown>) {
    if (!spaceId) return;
    setTemplateSaving(true);
    setFormError('');
    try {
      await knowledgeApi.post<SpaceTemplate>(`/spaces/${encodeURIComponent(spaceId)}/templates`, {
        name: values.name,
        description: values.description ?? '',
        body: values.body,
      });
      await loadTemplates();
      setTemplateOpen(false);
      templateForm.resetFields();
      messageApi.success(t('空間範本已建立。'));
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setTemplateSaving(false);
    }
  }

  async function organizeDocument(id: string, parentId: string | null, archived: boolean) {
    try {
      await knowledgeApi.patch(`/documents/${encodeURIComponent(id)}/organization`, { parent_id: parentId, archived });
      await loadDocuments();
      if (id === selectedDocumentIdRef.current) await loadDocumentContext(id);
      messageApi.success(t('文件結構已更新。'));
    } catch (error) {
      messageApi.error(errorMessage(error));
      throw error;
    }
  }

  async function restoreVersion(id: string, version: number, expectedCurrentVersion: number) {
    await knowledgeApi.post(`/documents/${encodeURIComponent(id)}/restore`, {
      version,
      expected_current_version: expectedCurrentVersion,
      change_summary: t('由版本 v{{version}} 還原', { version: formatNumber(version) }),
    });
    await loadDocuments();
    await loadDocumentContext(id);
    setDraftRefreshKey((value) => value + 1);
    messageApi.success(t('已建立還原內容的新版本。'));
  }

  async function selectExactVersion(versionNumber: number) {
    const id = selectedDocumentIdRef.current;
    if (!id) return;
    const requestId = ++versionRequestIdRef.current;
    const isCurrentRequest = () => requestId === versionRequestIdRef.current && selectedDocumentIdRef.current === id;
    setDocumentBusy(true);
    try {
      const version = await knowledgeApi.get<DocumentVersion>(`/documents/${encodeURIComponent(id)}/versions/${versionNumber}`);
      if (!isCurrentRequest()) return;
      setSelectedVersion(version);
    } catch (error) {
      if (isCurrentRequest()) messageApi.error(errorMessage(error));
    } finally {
      if (isCurrentRequest()) setDocumentBusy(false);
    }
  }

  function openPublish() {
    if (!documentContext || !canPublishDraft || !collaborationState) return;
    setPublishError(null);
    publishForm.resetFields();
    publishForm.setFieldsValue({
      title: collaborationState.draft.title,
      change_summary: '',
      source_refs: [],
    });
    setPublishOpen(true);
  }

  async function publishVersion(values: Record<string, unknown>) {
    if (!documentId || !collaborationState || !canPublishDraft) return;
    setPublishSaving(true);
    setPublishError(null);
    try {
      await knowledgeApi.post<DocumentVersion>(`/documents/${encodeURIComponent(documentId)}/draft/publish`, {
        expected_revision: collaborationState.draft.revision,
        ...(typeof values.title === 'string' && values.title.trim() ? { title: values.title.trim() } : {}),
        change_summary: values.change_summary,
        source_refs: values.source_refs ?? [],
      });
      setPublishOpen(false);
      publishForm.resetFields();
      await loadDocuments();
      await loadDocumentContext(documentId);
      setDraftRefreshKey((value) => value + 1);
      messageApi.success(t('新版本已發佈；舊版本保持不變。'));
    } catch (error) {
      if (error instanceof ProductApiError && error.status === 409) {
        setPublishError({ message: errorMessage(error) });
        void loadDocuments();
        void loadDocumentContext(documentId).catch(() => undefined);
        setDraftRefreshKey((value) => value + 1);
      } else {
        setPublishError({ message: errorMessage(error) });
      }
    } finally {
      setPublishSaving(false);
    }
  }

  async function createDecision(values: Record<string, unknown>) {
    if (!spaceId) return;
    setDecisionSaving(true);
    setFormError('');
    try {
      await knowledgeApi.post<Decision>('/decisions', {
        space_id: spaceId,
        document_id: values.document_id || undefined,
        title: values.title,
        body: values.body,
        source_refs: values.source_refs ?? [],
      });
      setDecisionOpen(false);
      decisionForm.resetFields();
      await loadDecisions();
      if (documentId) await loadDocumentContext(documentId).catch(() => undefined);
      messageApi.success(t('決策紀錄已建立。'));
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setDecisionSaving(false);
    }
  }

  const sectionItems = [
    { key: 'documents', label: t('文件庫'), icon: <FileTextOutlined /> },
    { key: 'decisions', label: t('決策紀錄'), icon: <SafetyCertificateOutlined /> },
  ];

  if (!auth.session) {
    return <>{messageContext}<ProductLogin product="knowledge" productName="Knowledge" /></>;
  }
  if (authBusy || principalSessionKey !== auth.session.csrf_token) {
    return <>{messageContext}<div className="product-inline-loading"><Spin /></div></>;
  }
  if (!principal) {
    return <>{messageContext}<AuthAccessDenied product="knowledge" productName="Knowledge" error={authError} forbidden={principalErrorStatus === 403} onRetry={() => window.location.reload()} /></>;
  }

  return (
    <>
      {messageContext}
      <ProductShell
        product="knowledge"
        productLabel="Ordivant Knowledge"
        principal={principal}
        sectionLabel="Knowledge"
        navigation={sectionItems}
        activeSection={section}
        onSectionChange={(key) => setSection(key as KnowledgeSection)}
        mode={health?.mode ?? 'unavailable'}
        serviceStatus={healthStatus}
        headerExtra={<Space size={7}><Select aria-label={t('選擇 Knowledge space')} className="product-scope-select" placeholder={t('選擇 Space')} value={spaceId || undefined} loading={spaceBusy} onChange={(value) => { clearResourceTarget(); setSpaceId(value); selectDocument(''); }} options={spaces.map((space) => ({ value: space.id, label: `${space.key} · ${space.name}` }))} notFoundContent={t('沒有可存取的 Space')} />{canCreateSpace && <Button aria-label={t('建立 Space')} icon={<PlusOutlined />} onClick={() => { spaceForm.resetFields(); setFormError(''); setSpaceModalOpen(true); }}>{t('新增 Space')}</Button>}</Space>}
        title={t(section === 'documents' ? '文件庫' : '決策紀錄')}
        eyebrow={currentSpace ? `${currentSpace.key} · ${currentSpace.name}` : 'KNOWLEDGE'}
        actions={canWrite && section === 'documents'
          ? <Button type="primary" icon={<FileAddOutlined />} disabled={!spaceId} onClick={openCreateDocument}>{t('新增文件')}</Button>
          : canWrite && section === 'decisions'
            ? <Button type="primary" icon={<PlusOutlined />} disabled={!spaceId} onClick={() => { decisionForm.resetFields(); decisionForm.setFieldsValue({ document_id: documentId || undefined, source_refs: [] }); setFormError(''); setDecisionOpen(true); }}>{t('新增決策')}</Button>
            : undefined}
      >
        {healthStatus === 'error' && <Alert className="product-page-alert" type="warning" showIcon message={t('Knowledge API 健康檢查失敗')} description={t(healthError)} action={<Button size="small" onClick={() => void checkHealth()}>{t('重試')}</Button>} />}
        {spacesError && <Alert className="product-page-alert" type="error" showIcon message={t('Space 清單載入失敗')} description={t(spacesError)} action={<Button size="small" onClick={() => setSpacesReload((value) => value + 1)}>{t('重試')}</Button>} />}
        {resourceLoading && <Alert className="product-page-alert" type="info" showIcon message={t('正在開啟指定文件…')} />}
        {resourceError && <Alert className="product-page-alert" type="error" showIcon message={t('無法開啟指定 Knowledge 文件')} description={resourceAccessDenied ? t('指定文件不存在，或目前帳號無權存取。') : t(resourceError)} action={<Button size="small" onClick={() => { clearResourceTarget(); selectDocument(documents[0]?.id ?? ''); }}>{t('返回文件清單')}</Button>} />}
        {!spaceId ? (
          <div className="product-empty-state"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t(spaceBusy ? '正在載入 Space' : canCreateSpace ? '目前沒有可存取的 Knowledge space' : '目前沒有可存取的 Knowledge space，請聯絡管理員授予 Space 存取權或建立新 Space。')} />{canCreateSpace && <Button type="primary" icon={<PlusOutlined />} onClick={() => { spaceForm.resetFields(); setSpaceModalOpen(true); }}>{t('建立 Space')}</Button>}</div>
        ) : section === 'documents' ? (
          <>
            {documentsError && <Alert className="product-page-alert" type="error" showIcon message={t('文件搜尋失敗')} description={t(documentsError)} action={<Button size="small" onClick={() => void loadDocuments()}>{t('重試')}</Button>} />}
            <div className="knowledge-tools">
              <Input allowClear prefix={<SearchOutlined />} aria-label={t('搜尋文件文字')} placeholder={t('搜尋標題或正文')} value={query} onChange={(event) => setQuery(event.target.value)} />
              <Input allowClear aria-label={t('依標籤篩選')} placeholder={t('標籤篩選')} value={tagFilter} onChange={(event) => setTagFilter(event.target.value)} />
              <label className="knowledge-archive-toggle"><Switch size="small" checked={showArchived} onChange={setShowArchived} /><span>{t('顯示已封存')}</span></label>
              <span>{t('文字搜尋')} · {documentsBusy ? t('搜尋中') : t('{{count}} 份文件', { count: formatNumber(documents.length) })}</span>
            </div>
            <div className="knowledge-workspace">
              <aside className="knowledge-document-list" aria-label={t('文件搜尋結果')}>
                <div className="knowledge-list-heading"><span>{t('搜尋結果')}</span><span>{formatNumber(documents.length)}</span></div>
                {documentsBusy && !documents.length && <div className="product-inline-loading"><Spin size="small" /></div>}
                {!documentsBusy && documents.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t(query || tagFilter ? '沒有符合條件的文件' : '此 Space 尚無文件')}>{canWrite && !query && !tagFilter && <Button size="small" type="primary" onClick={openCreateDocument}>{t('建立文件')}</Button>}</Empty>}
                {flattenedDocuments.map(({ document, level }) => <button type="button" key={document.id} className={`knowledge-document-item${document.id === documentId ? ' knowledge-document-active' : ''}`} style={{ paddingInlineStart: `${14 + level * 16}px` }} onClick={() => { clearResourceTarget(document.id); selectDocument(document.id); }}><span className="document-item-top"><strong>{document.title}</strong><Space size={4}>{document.archived && <Tag color="default">{t('已封存')}</Tag>}<Tag>v{document.version ?? document.current_version}</Tag></Space></span><MarkdownPreview className="document-item-summary" content={document.snippet || document.summary || t('尚無摘要')} /><span className="document-item-bottom"><span>{document.tags?.slice(0, 3).map((tag) => `#${tag}`).join(' ') || t('無標籤')}</span><time>{dateText(document.updated_at)}</time></span></button>)}
              </aside>
              <main className="knowledge-reader">
                {documentBusy && !documentContext && <div className="product-inline-loading"><Spin /></div>}
                {!documentId && !documentsBusy && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('選取一份文件以檢視版本與來源')} />}
                {documentId && (!documentContext || documentContext.document.id !== documentId) && !documentBusy && !resourceError && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('文件脈絡無法載入')} />}
                {documentContext?.document.id === documentId && selectedVersion && <DocumentReader context={documentContext} selectedVersion={selectedVersion} history={history} documents={documents} busy={documentBusy} actorId={principal.id} canWrite={canWrite} canPublish={canPublishDraft && selectedVersion.version === documentContext.document.current_version} collaborationState={collaborationState?.draft.document_id === documentContext.document.id ? collaborationState : null} refreshKey={draftRefreshKey} onCollaborationStateChange={setCollaborationState} onVersion={selectExactVersion} onPublish={openPublish} onOrganize={organizeDocument} onRestore={restoreVersion} onCreateDecision={() => { decisionForm.resetFields(); decisionForm.setFieldsValue({ document_id: documentContext.document.id, source_refs: [] }); setFormError(''); setDecisionOpen(true); }} />}
              </main>
            </div>
          </>
        ) : (
          <section className="knowledge-decisions">
            {decisionsError && <Alert className="product-page-alert" type="error" showIcon message={t('決策紀錄載入失敗')} description={t(decisionsError)} action={<Button size="small" onClick={() => void loadDecisions()}>{t('重試')}</Button>} />}
            <div className="knowledge-decisions-heading"><div><Text type="secondary">{t('依 Space 範圍載入；每筆決策保留來源引用與建立者。')}</Text></div><span>{decisionsBusy ? t('載入中') : t('{{count}} 筆決策', { count: formatNumber(decisions.length) })}</span></div>
            {decisionsBusy && !decisions.length && <div className="product-inline-loading"><Spin /></div>}
            {!decisionsBusy && decisions.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('此 Space 尚無決策紀錄')} />}
            {decisions.map((decision) => <DecisionRow key={decision.id} decision={decision} documentTitle={documents.find((item) => item.id === decision.document_id)?.title} />)}
          </section>
        )}
      </ProductShell>

      {canCreateSpace && <Modal title={t('建立 Knowledge space')} open={spaceModalOpen} onCancel={() => setSpaceModalOpen(false)} onOk={() => spaceForm.submit()} confirmLoading={spaceSaving} okText={t('建立 Space')} cancelText={t('取消')} destroyOnClose>
        {formError && <Alert className="product-form-alert" type="error" showIcon message={t(formError)} />}
        <Form form={spaceForm} layout="vertical" onFinish={(values) => void createSpace(values)}><Form.Item name="key" label={t('Space 代碼')} rules={[{ required: true, message: t('請輸入代碼') }]}><Input maxLength={20} /></Form.Item><Form.Item name="name" label={t('名稱')} rules={[{ required: true, message: t('請輸入名稱') }]}><Input maxLength={120} /></Form.Item><Form.Item name="description" label={t('描述')}><TextArea rows={3} /></Form.Item></Form>
      </Modal>}

      <Modal title={t('建立文件 v1')} open={createDocumentOpen} onCancel={() => setCreateDocumentOpen(false)} onOk={() => documentForm.submit()} confirmLoading={documentSaving} okText={t('建立文件')} cancelText={t('取消')} width={760} destroyOnClose>
        {formError && <Alert className="product-form-alert" type="error" showIcon message={t(formError)} />}
        <div className="knowledge-template-picker"><span>{t('可從範本建立，也可直接撰寫。')}</span><Button size="small" onClick={() => { templateForm.resetFields(); setFormError(''); setTemplateOpen(true); }}>{t('建立空間範本')}</Button></div>
        <Form form={documentForm} layout="vertical" onFinish={(values) => void createDocument(values)}>
          <Form.Item name="template_id" label={t('文件範本')}><Select allowClear loading={templatesBusy} placeholder={t('選擇範本')} options={templates.map((template) => ({ value: template.id, label: `${localizeTemplate(template, t).name}${template.builtin ? ` · ${t('內建')}` : ''}`, title: localizeTemplate(template, t).description }))} onChange={(templateId) => { const template = templates.find((item) => item.id === templateId); if (template) documentForm.setFieldValue('body', localizeTemplate(template, t).body); }} /></Form.Item>
          <Form.Item name="parent_id" label={t('上層文件')}><Select allowClear placeholder={t('無，上層為 Space')} options={documents.filter((document) => !document.archived).map((document) => ({ value: document.id, label: document.title }))} /></Form.Item>
          <Form.Item name="title" label={t('文件標題')} rules={[{ required: true, whitespace: true }]}><Input maxLength={200} /></Form.Item>
          <Form.Item name="summary" label={t('摘要')}><TextArea rows={2} /></Form.Item>
          <Form.Item name="body" label={t('正文（Markdown）')} rules={[{ required: true, whitespace: true, message: t('正文不得空白') }]}><TextArea rows={12} spellCheck /></Form.Item>
          <Form.Item name="tags" label={t('標籤')}><Select mode="tags" tokenSeparators={[',']} placeholder={t('輸入標籤後按 Enter')} /></Form.Item>
          <Form.Item name="change_summary" label={t('版本說明')}><Input placeholder={t('初版建立')} /></Form.Item>
          <Divider orientation="left" plain>{t('來源與 provenance')}</Divider><ReferenceFields />
        </Form>
      </Modal>

      <Modal title={t('建立空間範本')} open={templateOpen} onCancel={() => setTemplateOpen(false)} onOk={() => templateForm.submit()} confirmLoading={templateSaving} okText={t('儲存範本')} cancelText={t('取消')} width={700} destroyOnClose>
        {formError && <Alert className="product-form-alert" type="error" showIcon message={t(formError)} />}
        <Form form={templateForm} layout="vertical" onFinish={(values) => void createTemplate(values)}>
          <Form.Item name="name" label={t('範本名稱')} rules={[{ required: true, whitespace: true }]}><Input maxLength={120} /></Form.Item>
          <Form.Item name="description" label={t('用途說明')}><Input maxLength={500} /></Form.Item>
          <Form.Item name="body" label={t('Markdown 範本正文')} rules={[{ required: true, whitespace: true }]}><TextArea rows={12} /></Form.Item>
        </Form>
      </Modal>

      <Modal title={t('發佈文件新版本') + (documentContext ? ` · ${documentContext.document.title}` : '')} open={publishOpen} onCancel={() => { setPublishOpen(false); setPublishError(null); }} onOk={() => publishForm.submit()} confirmLoading={publishSaving} okText={t('發佈新版本')} cancelText={t('取消')} width={780} destroyOnClose>
        {publishError && <Alert className="product-form-alert" type="error" showIcon message={t('未發佈新版本')} description={t('版本衝突：{{message}} 目前草稿仍保留，請確認最新版本後再決定如何發佈。', { message: publishError.message })} />}
        {documentContext && collaborationState && <Alert className="product-form-alert" type="info" showIcon message={t('即將發佈共同草稿修訂 {{revision}}', { revision: formatNumber(collaborationState.draft.revision) })} description={t('發佈後會建立新的不可變版本，舊版本仍可從版本歷程閱讀。')} />}
        <Form form={publishForm} layout="vertical" onFinish={(values) => void publishVersion(values)}>
          <Form.Item name="title" label={t('版本標題（選填）')}><Input maxLength={200} /></Form.Item>
          <Form.Item name="change_summary" label={t('變更摘要')} rules={[{ required: true, whitespace: true }]}><Input maxLength={300} /></Form.Item>
          <Divider orientation="left" plain>{t('來源與 provenance')}</Divider><ReferenceFields />
        </Form>
      </Modal>

      <Modal title={t('記錄決策')} open={decisionOpen} onCancel={() => setDecisionOpen(false)} onOk={() => decisionForm.submit()} confirmLoading={decisionSaving} okText={t('建立決策')} cancelText={t('取消')} width={720} destroyOnClose>
        {formError && <Alert className="product-form-alert" type="error" showIcon message={t(formError)} />}
        <Form form={decisionForm} layout="vertical" onFinish={(values) => void createDecision(values)}>
          <Form.Item name="title" label={t('決策標題')} rules={[{ required: true, whitespace: true }]}><Input maxLength={200} /></Form.Item>
          <Form.Item name="document_id" label={t('關聯文件')}><Select allowClear placeholder={t('不關聯特定文件')} options={documents.map((document) => ({ value: document.id, label: document.title }))} /></Form.Item>
          <Form.Item name="body" label={t('決策內容')} rules={[{ required: true, whitespace: true }]}><TextArea rows={5} /></Form.Item>
          <Divider orientation="left" plain>{t('決策來源')}</Divider><ReferenceFields />
        </Form>
      </Modal>
    </>
  );
}

function KnowledgeComments({ documentId, version, publishedBody, canWrite }: { documentId: string; version: number; publishedBody: string; canWrite: boolean }) {
  const { t } = useI18n();
  const [comments, setComments] = useState<KnowledgeComment[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [body, setBody] = useState('');
  const [quote, setQuote] = useState('');
  const [quoteError, setQuoteError] = useState('');
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const loadComments = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setComments(await knowledgeApi.get<KnowledgeComment[]>(`/documents/${encodeURIComponent(documentId)}/comments`));
    } catch (loadError) {
      setError(errorMessage(loadError));
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => { void loadComments(); }, [loadComments]);

  function captureQuote() {
    const selected = window.getSelection()?.toString().trim() ?? '';
    if (!selected) {
      setQuoteError(t('先在 Markdown 預覽中選取要引用的文字。'));
      return;
    }
    const utf16Index = publishedBody.indexOf(selected);
    if (utf16Index < 0) {
      setQuoteError(t('所選文字不在目前發布版本中，請選取仍存在的文字或清除引用。'));
      return;
    }
    setQuote(selected);
    setQuoteError('');
  }

  async function submitComment() {
    if (!body.trim()) return;
    setSaving(true);
    setError('');
    try {
      let anchor: KnowledgeComment['anchor'] = null;
      if (quote.trim()) {
        if (!publishedBody.includes(quote.trim())) {
          setQuoteError(t('引用文字不在目前發布版本中。'));
          return;
        }
        anchor = { quote: quote.trim(), version };
      }
      await knowledgeApi.post(`/documents/${encodeURIComponent(documentId)}/comments`, {
        body: body.trim(),
        parent_id: replyTo,
        ...(anchor ? { anchor } : {}),
      });
      setBody('');
      setQuote('');
      setReplyTo(null);
      await loadComments();
    } catch (saveError) {
      setError(errorMessage(saveError));
    } finally {
      setSaving(false);
    }
  }

  async function setResolved(comment: KnowledgeComment, resolved: boolean) {
    try {
      await knowledgeApi.patch(`/document-comments/${encodeURIComponent(comment.id)}`, { resolved });
      await loadComments();
    } catch (saveError) {
      setError(errorMessage(saveError));
    }
  }

  const roots = comments.filter((comment) => !comment.parent_id);
  return (
    <section className="knowledge-comments" id="knowledge-comments">
      <div className="knowledge-subhead"><h3><CommentOutlined /> {t('文件留言')}</h3><span>{loading ? t('載入中') : formatNumber(comments.length)}</span></div>
      {error && <Alert type="error" showIcon message={t(error)} action={<Button size="small" onClick={() => void loadComments()}>{t('重試')}</Button>} />}
      {loading && !comments.length && <div className="product-inline-loading"><Spin size="small" /></div>}
      {!loading && !comments.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('尚無留言')} />}
      <div className="knowledge-comment-list">
        {roots.map((comment) => {
          const replies = comments.filter((item) => item.parent_id === comment.id);
          return <article className={`knowledge-comment-thread${comment.resolved ? ' knowledge-comment-resolved' : ''}`} key={comment.id}>
            <div className="knowledge-comment-head"><strong>{comment.author_name}</strong><time>{dateText(comment.created_at)}</time>{comment.resolved && <Tag>{t('已解決')}</Tag>}</div>
            {comment.anchor && <blockquote className="knowledge-comment-quote">“{comment.anchor.quote}” · v{formatNumber(comment.anchor.version)}{comment.anchor_stale && <Tag color="orange">{t('引用版本較舊')}</Tag>}</blockquote>}
            <p className="knowledge-comment-body">{comment.body}</p>
            <div className="knowledge-comment-actions">{canWrite && <Button size="small" type="link" onClick={() => { setReplyTo(comment.id); setQuote(''); }}>{t('回覆')}</Button>}{canWrite && <Button size="small" type="link" onClick={() => void setResolved(comment, !comment.resolved)}>{comment.resolved ? t('重新開啟') : t('標記已解決')}</Button>}</div>
            {replies.map((reply) => <div className="knowledge-comment-reply" key={reply.id}><div className="knowledge-comment-head"><strong>{reply.author_name}</strong><time>{dateText(reply.created_at)}</time></div><p className="knowledge-comment-body">{reply.body}</p></div>)}
          </article>;
        })}
      </div>
      {canWrite && <div className="knowledge-comment-composer">
        {replyTo && <div className="knowledge-replying"><span>{t('回覆留言')}</span><Button size="small" type="link" onClick={() => setReplyTo(null)}>{t('取消回覆')}</Button></div>}
        {!replyTo && <div className="knowledge-quote-tools"><Button size="small" icon={<CommentOutlined />} onMouseDown={(event) => event.preventDefault()} onClick={captureQuote}>{t('引用所選文字')}</Button>{quote && <Button size="small" type="link" onClick={() => { setQuote(''); setQuoteError(''); }}>{t('清除引用')}</Button>}</div>}
        {quote && <blockquote className="knowledge-comment-quote knowledge-quote-draft">“{quote}” · v{formatNumber(version)}</blockquote>}
        {quoteError && <Text type="danger">{quoteError}</Text>}
        <TextArea aria-label={t('留言內容')} rows={3} maxLength={5000} value={body} onChange={(event) => setBody(event.target.value)} placeholder={t('寫下留言或回覆')} />
        <div className="knowledge-comment-submit"><span>{t('留言以純文字顯示')}</span><Button type="primary" size="small" loading={saving} disabled={!body.trim()} onClick={() => void submitComment()}>{replyTo ? t('送出回覆') : t('新增留言')}</Button></div>
      </div>}
    </section>
  );
}

function DocumentReader({
  context,
  selectedVersion,
  history,
  documents,
  busy,
  actorId,
  canWrite,
  canPublish,
  collaborationState,
  refreshKey,
  onCollaborationStateChange,
  onVersion,
  onPublish,
  onOrganize,
  onRestore,
  onCreateDecision,
}: {
  context: KnowledgeDocumentContext;
  selectedVersion: DocumentVersion;
  history: DocumentVersion[];
  documents: KnowledgeDocumentHit[];
  busy: boolean;
  actorId: string;
  canWrite: boolean;
  canPublish: boolean;
  collaborationState: KnowledgeCollaborationState | null;
  refreshKey: number;
  onCollaborationStateChange: (state: KnowledgeCollaborationState | null) => void;
  onVersion: (version: number) => void;
  onPublish: () => void;
  onOrganize: (id: string, parentId: string | null, archived: boolean) => Promise<void>;
  onRestore: (id: string, version: number, expectedCurrentVersion: number) => Promise<void>;
  onCreateDecision: () => void;
}) {
  const { t } = useI18n();
  const [modal, modalContextHolder] = Modal.useModal();
  const [messageApi, messageContextHolder] = message.useMessage();
  const isLatest = selectedVersion.version === context.document.current_version;
  const [manageOpen, setManageOpen] = useState(false);
  const [parentId, setParentId] = useState<string | undefined>(context.document.parent_id ?? undefined);
  const [archived, setArchived] = useState(Boolean(context.document.archived));
  const [manageSaving, setManageSaving] = useState(false);
  const [diffOpen, setDiffOpen] = useState(false);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffText, setDiffText] = useState('');
  const [diffFromTitle, setDiffFromTitle] = useState('');
  const [diffToTitle, setDiffToTitle] = useState('');
  const [diffFrom, setDiffFrom] = useState(1);
  const [diffTo, setDiffTo] = useState(context.document.current_version);
  const [insertOpen, setInsertOpen] = useState(false);
  const [insertKind, setInsertKind] = useState<'link' | 'image'>('link');
  const [insertText, setInsertText] = useState('');
  const [insertUrl, setInsertUrl] = useState('');
  const [insertAlt, setInsertAlt] = useState('');
  const savedRange = useRef<Range | null>(null);
  const savedSelectionText = useRef('');
  const sortedHistory = history.slice().sort((a, b) => a.version - b.version);
  const versionOptions = sortedHistory.map((version) => ({ value: version.version, label: `v${formatNumber(version.version)}${version.version === context.document.current_version ? ` · ${t('最新')}` : ''}` }));

  useEffect(() => {
    setParentId(context.document.parent_id ?? undefined);
    setArchived(Boolean(context.document.archived));
    setDiffTo(context.document.current_version);
    setDiffFrom(Math.max(1, context.document.current_version - 1));
  }, [context.document.archived, context.document.current_version, context.document.id, context.document.parent_id]);

  function editorElement() {
    return document.querySelector<HTMLElement>('.knowledge-reader .collab-codemirror .cm-content[contenteditable="true"]');
  }

  function insertMarkdown(before: string, after: string, placeholder: string) {
    const editor = editorElement();
    if (!editor) return;
    const selected = window.getSelection()?.toString() ?? '';
    editor.focus();
    document.execCommand('insertText', false, `${before}${selected || placeholder}${after}`);
  }

  function insertBlockMarkdown(value: string) {
    const editor = editorElement();
    if (!editor) return;
    editor.focus();
    document.execCommand('insertText', false, value);
  }

  function captureEditorSelection(kind: 'link' | 'image') {
    const editor = editorElement();
    const selection = window.getSelection();
    if (editor && selection?.rangeCount && editor.contains(selection.anchorNode)) {
      savedRange.current = selection.getRangeAt(0).cloneRange();
      savedSelectionText.current = selection.toString();
    } else {
      savedRange.current = null;
      savedSelectionText.current = '';
    }
    setInsertKind(kind);
    setInsertText(savedSelectionText.current);
    setInsertUrl('');
    setInsertAlt('');
    setInsertOpen(true);
  }

  function insertLinkOrImage() {
    const editor = editorElement();
    if (!editor || !insertUrl.trim()) return;
    editor.focus();
    if (savedRange.current) {
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(savedRange.current);
    }
    const label = insertKind === 'image' ? insertAlt.trim() || insertText.trim() || t('圖片描述') : insertText.trim() || t('連結文字');
    const markdownText = insertKind === 'image' ? `![${label}](${insertUrl.trim()})` : `[${label}](${insertUrl.trim()})`;
    document.execCommand('insertText', false, markdownText);
    setInsertOpen(false);
  }

  async function loadDiff() {
    setDiffLoading(true);
    try {
      const params = new URLSearchParams({ from_version: String(diffFrom), to_version: String(diffTo) });
      const result = await knowledgeApi.get<{ diff: string; from_title: string; to_title: string }>(`/documents/${encodeURIComponent(context.document.id)}/diff?${params.toString()}`);
      setDiffText(result.diff);
      setDiffFromTitle(result.from_title);
      setDiffToTitle(result.to_title);
      setDiffOpen(true);
    } catch (error) {
      messageApi.error(errorMessage(error));
    } finally {
      setDiffLoading(false);
    }
  }

  function confirmRestore() {
    modal.confirm({
      title: t('還原為新版本'),
      content: t('將 v{{version}} 的內容建立為 v{{next}}；不會改寫既有版本。', { version: formatNumber(selectedVersion.version), next: formatNumber(context.document.current_version + 1) }),
      okText: t('建立還原版本'),
      cancelText: t('取消'),
      onOk: () => onRestore(context.document.id, selectedVersion.version, context.document.current_version),
    });
  }

  async function saveOrganization() {
    setManageSaving(true);
    try {
      await onOrganize(context.document.id, parentId ?? null, archived);
      setManageOpen(false);
    } finally {
      setManageSaving(false);
    }
  }

  return (
    <div className="document-reader-content">
      {modalContextHolder}
      {messageContextHolder}
      <div className="reader-toolbar">
        <div className="citation-uri">{selectedVersion.uri}</div>
        <Space wrap>
          <Select aria-label={t('選擇文件版本')} value={selectedVersion.version} loading={busy} onChange={(version) => onVersion(version)} options={versionOptions.slice().reverse()} />
          {canWrite && <Button aria-label={t('文件結構')} aria-haspopup="dialog" aria-expanded={manageOpen} icon={<FolderOpenOutlined />} onClick={() => setManageOpen(true)}>{t('文件結構')}</Button>}
          {canWrite && !isLatest && <Button icon={<HistoryOutlined />} onClick={confirmRestore}>{t('還原版本')}</Button>}
          {canWrite && history.length > 1 && <Button loading={diffLoading} onClick={() => void loadDiff()}>{t('比較版本')}</Button>}
          {canWrite && isLatest && <Tooltip title={!canPublish ? t('待共同草稿已同步後才能發佈') : undefined}><Button type="primary" disabled={!canPublish} onClick={onPublish}>{t('發佈新版本')}</Button></Tooltip>}
        </Space>
      </div>
      {!isLatest && <Alert className="historical-version-alert" type="warning" showIcon icon={<HistoryOutlined />} message={t('正在檢視不可變更的歷史版本 v{{version}}', { version: formatNumber(selectedVersion.version) })} />}
      <div className="reader-document-head"><div><div className="document-version-kicker">{context.document.space_id.slice(0, 8)} · {isLatest ? t('共同草稿') : t('版本')} {isLatest ? collaborationState ? formatNumber(collaborationState.draft.revision) : '…' : formatNumber(selectedVersion.version)}{context.document.archived && <Tag className="knowledge-archived-tag">{t('已封存')}</Tag>}</div><Title level={3}>{isLatest ? collaborationState?.draft.title ?? selectedVersion.title : selectedVersion.title}</Title><Paragraph>{context.document.summary}</Paragraph></div><div className="reader-head-actions">{canWrite && <Button icon={<SafetyCertificateOutlined />} onClick={onCreateDecision}>{t('記錄決策')}</Button>}</div></div>
      <Space wrap className="document-tags">{context.document.tags?.map((tag) => <Tag key={tag}>{tag}</Tag>)}</Space>
      {busy && <div className="reader-loading"><Spin size="small" /> {t('載入版本')}</div>}
      <div hidden={!isLatest}>
        {canWrite && <div className="knowledge-markdown-tools" aria-label={t('Markdown 格式工具')}>
          <Tooltip title={t('粗體')}><Button size="small" aria-label={t('粗體')} icon={<BoldOutlined />} onMouseDown={(event) => event.preventDefault()} onClick={() => insertMarkdown('**', '**', t('粗體文字'))} /></Tooltip>
          <Tooltip title={t('斜體')}><Button size="small" aria-label={t('斜體')} icon={<ItalicOutlined />} onMouseDown={(event) => event.preventDefault()} onClick={() => insertMarkdown('*', '*', t('斜體文字'))} /></Tooltip>
          <Tooltip title={t('插入連結')}><Button size="small" aria-label={t('插入連結')} icon={<LinkOutlined />} onMouseDown={(event) => { event.preventDefault(); captureEditorSelection('link'); }} /></Tooltip>
          <Tooltip title={t('插入圖片 Markdown')}><Button size="small" aria-label={t('插入圖片 Markdown')} icon={<PictureOutlined />} onMouseDown={(event) => { event.preventDefault(); captureEditorSelection('image'); }} /></Tooltip>
          <Tooltip title={t('插入表格')}><Button size="small" aria-label={t('插入表格')} icon={<TableOutlined />} onMouseDown={(event) => event.preventDefault()} onClick={() => insertBlockMarkdown(t(defaultTableMarkdown))} /></Tooltip>
          <span>{t('內容保存在共同 Markdown 草稿；切換至「預覽」分頁可即時查看內容。')}</span>
        </div>}
        <CollaborativeMarkdownEditor key={`${actorId}:${context.document.id}`} documentId={context.document.id} actorId={actorId} canEdit={canWrite && isLatest} refreshKey={refreshKey} onStateChange={onCollaborationStateChange} />
      </div>
      {!isLatest && <article className="markdown-content"><MarkdownContent content={selectedVersion.body} /></article>}
      <KnowledgeComments documentId={context.document.id} version={selectedVersion.version} publishedBody={selectedVersion.body} canWrite={canWrite} />
      <CollaborationPanel product="knowledge" kind="document" resourceId={context.document.id} canWrite={canWrite} />
      <section className="version-metadata"><div><span>{t('版本建立')}</span><strong>{dateText(selectedVersion.created_at)}</strong></div><div><span>{t('編輯者')}</span><strong>{selectedVersion.author_id}</strong></div><div><span>{t('內容 SHA-256')}</span><code>{selectedVersion.content_sha256}</code></div><div><span>{t('變更摘要')}</span><strong>{selectedVersion.change_summary || '—'}</strong></div></section>
      <section className="provenance-section"><div className="knowledge-subhead"><h3>{t('來源引用')}</h3><span>{formatNumber(selectedVersion.source_refs.length)}</span></div><ReferenceList references={selectedVersion.source_refs} /></section>
      <section className="version-history-section"><div className="knowledge-subhead"><h3>{t('不可變版本歷程')}</h3><span>{formatNumber(history.length)}</span></div>{history.slice().sort((a, b) => b.version - a.version).map((version) => <button type="button" key={version.id} className={`version-history-row${version.version === selectedVersion.version ? ' version-history-current' : ''}`} onClick={() => onVersion(version.version)}><span className="version-history-number">v{formatNumber(version.version)}</span><span className="version-history-summary">{version.change_summary || t('沒有變更摘要')}<small>{dateText(version.created_at)} · SHA-256 {version.content_sha256.slice(0, 12)}…</small></span>{version.version === context.document.current_version && <Tag color="green">{t('最新')}</Tag>}</button>)}</section>
      {context.decisions.length > 0 && <section className="version-history-section"><div className="knowledge-subhead"><h3>{t('相關決策')}</h3><span>{formatNumber(context.decisions.length)}</span></div>{context.decisions.map((decision) => <div className="inline-decision" key={decision.id}><strong>{decision.title}</strong><MarkdownContent content={decision.body} /><ReferenceList references={decision.source_refs} /></div>)}</section>}

      <Modal title={t('文件結構')} open={manageOpen} onCancel={() => setManageOpen(false)} onOk={() => void saveOrganization()} confirmLoading={manageSaving} okText={t('儲存結構')} cancelText={t('取消')} destroyOnClose>
        <Form layout="vertical"><Form.Item label={t('上層文件')}><Select allowClear value={parentId} placeholder={t('無，上層為 Space')} onChange={setParentId} options={documents.filter((document) => document.id !== context.document.id && !document.archived).map((document) => ({ value: document.id, label: document.title }))} /></Form.Item><Form.Item label={t('封存狀態')}><Switch checked={archived} onChange={setArchived} checkedChildren={t('已封存')} unCheckedChildren={t('未封存')} /></Form.Item><Text type="secondary">{t('封存文件會從預設搜尋結果隱藏；可開啟「顯示已封存」再管理。')}</Text></Form>
      </Modal>
      <Modal title={t('比較不可變版本')} open={diffOpen} onCancel={() => setDiffOpen(false)} footer={<Button onClick={() => setDiffOpen(false)}>{t('關閉比較')}</Button>} width={780} destroyOnClose>
        <div className="knowledge-diff-controls"><Select aria-label={t('比較來源版本')} value={diffFrom} onChange={setDiffFrom} options={versionOptions} /><span>→</span><Select aria-label={t('比較目標版本')} value={diffTo} onChange={setDiffTo} options={versionOptions} /><Button loading={diffLoading} onClick={() => void loadDiff()}>{t('重新比較')}</Button></div>
        <div className="knowledge-diff-titles"><strong>v{formatNumber(diffFrom)} · {diffFromTitle}</strong><span>→</span><strong>v{formatNumber(diffTo)} · {diffToTitle}</strong></div>
        <pre className="knowledge-diff">{diffText || t('所選版本沒有正文差異。')}</pre>
      </Modal>
      <Modal title={insertKind === 'image' ? t('插入圖片 Markdown') : t('插入連結')} open={insertOpen} onCancel={() => setInsertOpen(false)} onOk={insertLinkOrImage} okText={t('插入')} cancelText={t('取消')} destroyOnClose>
        <Form layout="vertical"><Form.Item label={insertKind === 'image' ? t('圖片替代文字') : t('顯示文字')}><Input value={insertKind === 'image' ? insertAlt : insertText} onChange={(event) => insertKind === 'image' ? setInsertAlt(event.target.value) : setInsertText(event.target.value)} /></Form.Item><Form.Item label={t('URL')}><Input value={insertUrl} onChange={(event) => setInsertUrl(event.target.value)} placeholder="https://" /></Form.Item><Text type="secondary">{t('只插入 Markdown URL，不會上傳檔案。')}</Text></Form>
      </Modal>
    </div>
  );
}

function DecisionRow({ decision, documentTitle }: { decision: Decision; documentTitle?: string }) {
  const { t } = useI18n();
  return (
    <article className="decision-row"><div className="decision-row-icon"><SafetyCertificateOutlined /></div><div className="decision-row-body"><div className="decision-row-header"><strong>{decision.title}</strong><time>{dateText(decision.created_at)}</time></div>{documentTitle && <span className="decision-document-link"><FileTextOutlined /> {documentTitle}</span>}<MarkdownContent content={decision.body} /><div className="decision-provenance"><Text className="eyebrow">{t('來源追溯')}</Text><ReferenceList references={decision.source_refs} /></div><span className="decision-actor">{t('建立者')} {decision.actor_id}</span></div></article>
  );
}
