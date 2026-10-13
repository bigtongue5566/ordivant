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
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import {
  FileAddOutlined,
  FileTextOutlined,
  HistoryOutlined,
  PlusOutlined,
  SearchOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { ProductApiError, createProductApi, productApiPrefix } from '../shared/productApi';
import { ProductLogin } from '../shared/ProductLogin';
import { ProductShell } from '../shared/ProductShell';
import { MarkdownContent, MarkdownPreview } from '../../shared/MarkdownContent';
import { CollaborativeMarkdownEditor, type KnowledgeCollaborationState } from '../../shared/CollaborativeMarkdownEditor';
import { AuthProvider, useAuth } from '../../auth/AuthContext';
import { AuthAccessDenied } from '../../auth/AuthAccessDenied';
import { ReferenceFields, ReferenceList } from '../shared/References';
import type { Decision, DocumentContext, DocumentHit, DocumentVersion, ProductHealth, ProductPrincipal, Space as KnowledgeSpace } from '../shared/types';
import { formatDate, formatNumber, useI18n, useLocalizedForm } from '../../i18n';

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;
const knowledgeApi = createProductApi(productApiPrefix('knowledge'));

type KnowledgeSection = 'documents' | 'decisions';

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
  const [documents, setDocuments] = useState<DocumentHit[]>([]);
  const [documentsBusy, setDocumentsBusy] = useState(false);
  const [documentsError, setDocumentsError] = useState('');
  const [query, setQuery] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const [documentId, setDocumentId] = useState('');
  const [documentContext, setDocumentContext] = useState<DocumentContext | null>(null);
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
  const [publishOpen, setPublishOpen] = useState(false);
  const [decisionOpen, setDecisionOpen] = useState(false);
  const [spaceSaving, setSpaceSaving] = useState(false);
  const [documentSaving, setDocumentSaving] = useState(false);
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
  const listRequestId = useRef(0);
  const healthRequestId = useRef(0);
  const currentSpace = spaces.find((item) => item.id === spaceId) ?? null;
  const canWrite = Boolean(principal && ['admin', 'manager', 'writer'].includes(principal.role));
  const canCreateSpace = auth.session?.user.role === 'admin';
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
        setSpaceId((existing) => result.some((space) => space.id === existing) ? existing : result[0]?.id ?? '');
      })
      .catch((error) => { if (current) setSpacesError(errorMessage(error)); })
      .finally(() => { if (current) setSpaceBusy(false); });
    return () => { current = false; };
  }, [principal, spacesReload]);

  const loadDocuments = useCallback(async () => {
    if (!spaceId) {
      setDocuments([]);
      return;
    }
    const requestId = ++listRequestId.current;
    const params = new URLSearchParams({ space_id: spaceId });
    if (query.trim()) params.set('q', query.trim());
    if (tagFilter.trim()) params.set('tag', tagFilter.trim());
    setDocumentsBusy(true);
    setDocumentsError('');
    try {
      const result = await knowledgeApi.get<DocumentHit[]>(`/documents?${params.toString()}`);
      if (requestId === listRequestId.current) {
        setDocuments(result);
        setDocumentId((existing) => result.some((document) => document.id === existing) ? existing : result[0]?.id ?? '');
      }
    } catch (error) {
      if (requestId === listRequestId.current) setDocumentsError(errorMessage(error));
    } finally {
      if (requestId === listRequestId.current) setDocumentsBusy(false);
    }
  }, [query, spaceId, tagFilter]);

  useEffect(() => {
    if (!principal || !spaceId || section !== 'documents') return;
    const timer = window.setTimeout(() => { void loadDocuments(); }, query ? 240 : 0);
    return () => window.clearTimeout(timer);
  }, [loadDocuments, principal, query, section, spaceId]);

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
    if (!id) return;
    setDocumentBusy(true);
    try {
      const results = await Promise.allSettled([
        knowledgeApi.get<DocumentContext>(`/documents/${encodeURIComponent(id)}`),
        knowledgeApi.get<DocumentVersion[]>(`/documents/${encodeURIComponent(id)}/versions`),
      ]);
      const contextResult = results[0];
      const historyResult = results[1];
      if (contextResult.status === 'rejected') throw contextResult.reason;
      setDocumentContext(contextResult.value);
      setSelectedVersion(contextResult.value.version);
      setHistory(historyResult.status === 'fulfilled' ? historyResult.value : contextResult.value.history);
    } finally {
      setDocumentBusy(false);
    }
  }, [documentId]);

  useEffect(() => {
    if (!documentId || section !== 'documents') {
      setDocumentContext(null);
      setHistory([]);
      setSelectedVersion(null);
      return;
    }
    let current = true;
    setDocumentContext(null);
    setHistory([]);
    setSelectedVersion(null);
    setDocumentBusy(true);
    loadDocumentContext(documentId)
      .catch((error) => { if (current) messageApi.error(errorMessage(error)); })
      .finally(() => { if (current) setDocumentBusy(false); });
    return () => { current = false; };
  }, [documentId, loadDocumentContext, messageApi, section]);

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
  }, [auth.session]);

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
    documentForm.setFieldsValue({ tags: [], source_refs: [] });
    setFormError('');
    setCreateDocumentOpen(true);
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
        tags: values.tags ?? [],
        change_summary: values.change_summary ?? t('初版建立'),
        source_refs: values.source_refs ?? [],
      });
      setCreateDocumentOpen(false);
      documentForm.resetFields();
      setSection('documents');
      await loadDocuments();
      setDocumentId(created.document.id);
      messageApi.success(t('文件與 v1 已建立。'));
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setDocumentSaving(false);
    }
  }

  async function selectExactVersion(versionNumber: number) {
    if (!documentId) return;
    setDocumentBusy(true);
    try {
      const version = await knowledgeApi.get<DocumentVersion>(`/documents/${encodeURIComponent(documentId)}/versions/${versionNumber}`);
      setSelectedVersion(version);
    } catch (error) {
      messageApi.error(errorMessage(error));
    } finally {
      setDocumentBusy(false);
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
        headerExtra={<Space size={7}><Select aria-label={t('選擇 Knowledge space')} className="product-scope-select" placeholder={t('選擇 Space')} value={spaceId || undefined} loading={spaceBusy} onChange={(value) => { if (value !== spaceId) setCollaborationState(null); setSpaceId(value); setDocumentId(''); }} options={spaces.map((space) => ({ value: space.id, label: `${space.key} · ${space.name}` }))} notFoundContent={t('沒有可存取的 Space')} />{canCreateSpace && <Button aria-label={t('建立 Space')} icon={<PlusOutlined />} onClick={() => { spaceForm.resetFields(); setFormError(''); setSpaceModalOpen(true); }}>{t('新增 Space')}</Button>}</Space>}
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
        {!spaceId ? (
          <div className="product-empty-state"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t(spaceBusy ? '正在載入 Space' : canCreateSpace ? '目前沒有可存取的 Knowledge space' : '目前沒有可存取的 Knowledge space，請聯絡管理員授予 Space 存取權或建立新 Space。')} />{canCreateSpace && <Button type="primary" icon={<PlusOutlined />} onClick={() => { spaceForm.resetFields(); setSpaceModalOpen(true); }}>{t('建立 Space')}</Button>}</div>
        ) : section === 'documents' ? (
          <>
            {documentsError && <Alert className="product-page-alert" type="error" showIcon message={t('文件搜尋失敗')} description={t(documentsError)} action={<Button size="small" onClick={() => void loadDocuments()}>{t('重試')}</Button>} />}
            <div className="knowledge-tools"><Input allowClear prefix={<SearchOutlined />} aria-label={t('搜尋文件文字')} placeholder={t('搜尋標題或正文')} value={query} onChange={(event) => setQuery(event.target.value)} /><Input allowClear aria-label={t('依標籤篩選')} placeholder={t('標籤篩選')} value={tagFilter} onChange={(event) => setTagFilter(event.target.value)} /><span>{t('文字搜尋')} · {documentsBusy ? t('搜尋中') : t('{{count}} 份文件', { count: formatNumber(documents.length) })}</span></div>
            <div className="knowledge-workspace">
              <aside className="knowledge-document-list" aria-label={t('文件搜尋結果')}>
                <div className="knowledge-list-heading"><span>{t('搜尋結果')}</span><span>{formatNumber(documents.length)}</span></div>
                {documentsBusy && !documents.length && <div className="product-inline-loading"><Spin size="small" /></div>}
                {!documentsBusy && documents.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t(query || tagFilter ? '沒有符合條件的文件' : '此 Space 尚無文件')}>{canWrite && !query && !tagFilter && <Button size="small" type="primary" onClick={openCreateDocument}>{t('建立文件')}</Button>}</Empty>}
                {documents.map((document) => <button type="button" key={document.id} className={`knowledge-document-item${document.id === documentId ? ' knowledge-document-active' : ''}`} onClick={() => { if (document.id !== documentId) setCollaborationState(null); setDocumentId(document.id); }}><span className="document-item-top"><strong>{document.title}</strong><Tag>v{document.version ?? document.current_version}</Tag></span><MarkdownPreview className="document-item-summary" content={document.snippet || document.summary || t('尚無摘要')} /><span className="document-item-bottom"><span>{document.tags?.slice(0, 3).map((tag) => `#${tag}`).join(' ') || t('無標籤')}</span><time>{dateText(document.updated_at)}</time></span></button>)}
              </aside>
              <main className="knowledge-reader">
                {documentBusy && !documentContext && <div className="product-inline-loading"><Spin /></div>}
                {!documentId && !documentsBusy && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('選取一份文件以檢視版本與來源')} />}
                {documentId && !documentContext && !documentBusy && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('文件脈絡無法載入')} />}
                {documentContext && selectedVersion && <DocumentReader context={documentContext} selectedVersion={selectedVersion} history={history} busy={documentBusy} actorId={principal.id} canWrite={canWrite} canPublish={canPublishDraft && selectedVersion.version === documentContext.document.current_version} collaborationState={collaborationState?.draft.document_id === documentContext.document.id ? collaborationState : null} refreshKey={draftRefreshKey} onCollaborationStateChange={setCollaborationState} onVersion={selectExactVersion} onPublish={openPublish} onCreateDecision={() => { decisionForm.resetFields(); decisionForm.setFieldsValue({ document_id: documentContext.document.id, source_refs: [] }); setFormError(''); setDecisionOpen(true); }} />}
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
        <Form form={documentForm} layout="vertical" onFinish={(values) => void createDocument(values)}>
          <Form.Item name="title" label={t('文件標題')} rules={[{ required: true, whitespace: true }]}><Input maxLength={200} /></Form.Item>
          <Form.Item name="summary" label={t('摘要')}><TextArea rows={2} /></Form.Item>
          <Form.Item name="body" label={t('正文（Markdown）')} rules={[{ required: true, whitespace: true, message: t('正文不得空白') }]}><TextArea rows={12} spellCheck /></Form.Item>
          <Form.Item name="tags" label={t('標籤')}><Select mode="tags" tokenSeparators={[',']} placeholder={t('輸入標籤後按 Enter')} /></Form.Item>
          <Form.Item name="change_summary" label={t('版本說明')}><Input placeholder={t('初版建立')} /></Form.Item>
          <Divider orientation="left" plain>{t('來源與 provenance')}</Divider><ReferenceFields />
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

function DocumentReader({
  context,
  selectedVersion,
  history,
  busy,
  actorId,
  canWrite,
  canPublish,
  collaborationState,
  refreshKey,
  onCollaborationStateChange,
  onVersion,
  onPublish,
  onCreateDecision,
}: {
  context: DocumentContext;
  selectedVersion: DocumentVersion;
  history: DocumentVersion[];
  busy: boolean;
  actorId: string;
  canWrite: boolean;
  canPublish: boolean;
  collaborationState: KnowledgeCollaborationState | null;
  refreshKey: number;
  onCollaborationStateChange: (state: KnowledgeCollaborationState | null) => void;
  onVersion: (version: number) => void;
  onPublish: () => void;
  onCreateDecision: () => void;
}) {
  const { t } = useI18n();
  const isLatest = selectedVersion.version === context.document.current_version;
  return (
    <div className="document-reader-content">
      <div className="reader-toolbar"><div className="citation-uri">{selectedVersion.uri}</div><Space><Select aria-label={t('選擇文件版本')} value={selectedVersion.version} loading={busy} onChange={(version) => onVersion(version)} options={history.slice().sort((a, b) => b.version - a.version).map((version) => ({ value: version.version, label: `v${formatNumber(version.version)}${version.version === context.document.current_version ? ` · ${t('最新')}` : ''}` }))} />{canWrite && isLatest && <Tooltip title={!canPublish ? t('待共同草稿已同步後才能發佈') : undefined}><Button type="primary" disabled={!canPublish} onClick={onPublish}>{t('發佈新版本')}</Button></Tooltip>}</Space></div>
      {!isLatest && <Alert className="historical-version-alert" type="warning" showIcon icon={<HistoryOutlined />} message={t('正在檢視不可變更的歷史版本 v{{version}}', { version: formatNumber(selectedVersion.version) })} />}
      <div className="reader-document-head"><div><div className="document-version-kicker">{context.document.space_id.slice(0, 8)} · {isLatest ? t('共同草稿') : t('版本')} {isLatest ? collaborationState ? formatNumber(collaborationState.draft.revision) : '…' : formatNumber(selectedVersion.version)}</div><Title level={3}>{isLatest ? collaborationState?.draft.title ?? selectedVersion.title : selectedVersion.title}</Title><Paragraph>{context.document.summary}</Paragraph></div><div className="reader-head-actions">{canWrite && <Button icon={<SafetyCertificateOutlined />} onClick={onCreateDecision}>{t('記錄決策')}</Button>}</div></div>
      <Space wrap className="document-tags">{context.document.tags?.map((tag) => <Tag key={tag}>{tag}</Tag>)}</Space>
      {busy && <div className="reader-loading"><Spin size="small" /> {t('載入版本')}</div>}
      <div hidden={!isLatest}>
        <CollaborativeMarkdownEditor key={`${actorId}:${context.document.id}`} documentId={context.document.id} actorId={actorId} canEdit={canWrite && isLatest} refreshKey={refreshKey} onStateChange={onCollaborationStateChange} />
      </div>
      {!isLatest && <article className="markdown-content"><MarkdownContent content={selectedVersion.body} /></article>}
      <section className="version-metadata"><div><span>{t('版本建立')}</span><strong>{dateText(selectedVersion.created_at)}</strong></div><div><span>{t('編輯者')}</span><strong>{selectedVersion.author_id}</strong></div><div><span>{t('內容 SHA-256')}</span><code>{selectedVersion.content_sha256}</code></div><div><span>{t('變更摘要')}</span><strong>{selectedVersion.change_summary || '—'}</strong></div></section>
      <section className="provenance-section"><div className="knowledge-subhead"><h3>{t('來源引用')}</h3><span>{formatNumber(selectedVersion.source_refs.length)}</span></div><ReferenceList references={selectedVersion.source_refs} /></section>
      <section className="version-history-section"><div className="knowledge-subhead"><h3>{t('不可變版本歷程')}</h3><span>{formatNumber(history.length)}</span></div>{history.slice().sort((a, b) => b.version - a.version).map((version) => <button type="button" key={version.id} className={`version-history-row${version.version === selectedVersion.version ? ' version-history-current' : ''}`} onClick={() => onVersion(version.version)}><span className="version-history-number">v{formatNumber(version.version)}</span><span className="version-history-summary">{version.change_summary || t('沒有變更摘要')}<small>{dateText(version.created_at)} · SHA-256 {version.content_sha256.slice(0, 12)}…</small></span>{version.version === context.document.current_version && <Tag color="green">{t('最新')}</Tag>}</button>)}</section>
      {context.decisions.length > 0 && <section className="version-history-section"><div className="knowledge-subhead"><h3>{t('相關決策')}</h3><span>{formatNumber(context.decisions.length)}</span></div>{context.decisions.map((decision) => <div className="inline-decision" key={decision.id}><strong>{decision.title}</strong><MarkdownContent content={decision.body} /><ReferenceList references={decision.source_refs} /></div>)}</section>}
    </div>
  );
}

function DecisionRow({ decision, documentTitle }: { decision: Decision; documentTitle?: string }) {
  const { t } = useI18n();
  return (
    <article className="decision-row"><div className="decision-row-icon"><SafetyCertificateOutlined /></div><div className="decision-row-body"><div className="decision-row-header"><strong>{decision.title}</strong><time>{dateText(decision.created_at)}</time></div>{documentTitle && <span className="decision-document-link"><FileTextOutlined /> {documentTitle}</span>}<MarkdownContent content={decision.body} /><div className="decision-provenance"><Text className="eyebrow">{t('來源追溯')}</Text><ReferenceList references={decision.source_refs} /></div><span className="decision-actor">{t('建立者')} {decision.actor_id}</span></div></article>
  );
}
