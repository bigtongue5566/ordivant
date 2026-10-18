import { useEffect, useState } from 'react';
import { useNavigationState } from './shared/useNavigationState';
import { Alert, Button, Empty, Form, Input, InputNumber, Modal, Select, Segmented, Space, Switch, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ApiOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { api } from './api';
import { formatDate, formatNumber, useI18n, useLocalizedForm } from './i18n';
import type { SandboxLimits, SandboxProfile, ToolConnection, ToolConnectionTestResult, ToolDefinition } from './types';
import './ToolSettings.css';

const { Text, Title } = Typography;
type SettingsTab = 'connections' | 'sandbox';
type ConnectionFormValues = {
  name: string;
  endpoint: string;
  enabled: boolean;
  allowed_tools: string[];
  auth_token?: string;
};
type ProfileFormValues = { name: string; enabled: boolean } & SandboxLimits;

function errorText(error: unknown) {
  if (error instanceof Error) {
    if ('sourceMessage' in error) return String((error as Error & { sourceMessage: unknown }).sourceMessage ?? error.message);
    return error.message;
  }
  return '請求未完成。';
}

function dateText(value: string) {
  return formatDate(value, { hour12: false });
}

function safeFailureText(result: ToolConnectionTestResult) {
  if (result.ok) return '';
  return JSON.stringify(result, null, 2);
}

export function ToolSettings({ projectId, canAdmin }: { projectId: string; canAdmin: boolean }) {
  const { t } = useI18n();
  const [tab, setTab] = useNavigationState<SettingsTab>('tools-tab', 'connections', ['connections', 'sandbox']);
  return <section className="tool-settings-page">
    <Segmented className="tool-settings-tabs" value={tab} onChange={(value) => setTab(value as SettingsTab)} options={[{ value: 'connections', label: t('工具連線') }, { value: 'sandbox', label: t('Sandbox 設定檔') }]} />
    {tab === 'connections' && <ToolConnections projectId={projectId} canAdmin={canAdmin} />}
    {tab === 'sandbox' && <SandboxProfiles projectId={projectId} canAdmin={canAdmin} />}
  </section>;
}

function ToolConnections({ projectId, canAdmin }: { projectId: string; canAdmin: boolean }) {
  const { t } = useI18n();
  const [connections, setConnections] = useState<ToolConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editor, setEditor] = useState<ToolConnection | null | 'new'>(null);
  const [originalEndpoint, setOriginalEndpoint] = useState('');
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [form] = Form.useForm<ConnectionFormValues>();
  useLocalizedForm(form);
  const [testingId, setTestingId] = useState('');
  const [testResults, setTestResults] = useState<Record<string, ToolConnectionTestResult>>({});
  const [testErrors, setTestErrors] = useState<Record<string, string>>({});
  const [selectedResultId, setSelectedResultId] = useState('');
  const [messageApi, messageContext] = message.useMessage();

  async function loadConnections() {
    setLoading(true);
    setError('');
    try { setConnections(await api.toolConnections(projectId)); }
    catch (loadError) { setError(errorText(loadError)); }
    finally { setLoading(false); }
  }
  useEffect(() => { void loadConnections(); }, [projectId]);

  function openNew() {
    form.resetFields();
    form.setFieldsValue({ name: '', endpoint: '', enabled: false, allowed_tools: [], auth_token: '' });
    setEditor('new');
    setSelectedResultId('');
    setOriginalEndpoint('');
    setFormError('');
  }

  function openEdit(connection: ToolConnection) {
    form.resetFields();
    form.setFieldsValue({ name: connection.name, endpoint: connection.endpoint, enabled: connection.enabled, allowed_tools: connection.allowed_tools, auth_token: '' });
    setEditor(connection);
    setSelectedResultId(connection.id);
    setOriginalEndpoint(connection.endpoint);
    setFormError('');
  }

  async function saveConnection(values: ConnectionFormValues) {
    const endpoint = values.endpoint.trim();
    if (editor !== 'new' && editor?.key_configured && endpoint !== originalEndpoint && !values.auth_token?.trim()) {
      setFormError('更換已設定憑證的端點時，請輸入新的連線 Token。');
      return;
    }
    setSaving(true);
    setFormError('');
    const body = {
      ...(editor === 'new' ? { project_id: projectId } : {}),
      name: values.name.trim(),
      endpoint,
      enabled: values.enabled,
      allowed_tools: values.allowed_tools ?? [],
      ...(values.auth_token?.trim() ? { auth_token: values.auth_token } : {}),
    };
    try {
      if (editor === 'new') await api.createToolConnection(body);
      else if (editor) await api.updateToolConnection(editor.id, body);
      setEditor(null);
      form.setFieldValue('auth_token', undefined);
      await loadConnections();
      messageApi.success(t('工具連線已儲存。'));
    } catch (saveError) { setFormError(errorText(saveError)); }
    finally {
      form.setFieldValue('auth_token', undefined);
      setSaving(false);
    }
  }

  async function testConnection(connection: ToolConnection) {
    setTestingId(connection.id);
    setSelectedResultId(connection.id);
    setTestResults((current) => { const next = { ...current }; delete next[connection.id]; return next; });
    setTestErrors((current) => ({ ...current, [connection.id]: '' }));
    try {
      const result = await api.testToolConnection(connection.id);
      setTestResults((current) => ({ ...current, [connection.id]: result }));
      if (result.ok) messageApi.success(t('連線成功，找到 {{count}} 個工具。', { count: formatNumber(result.tools.length) }));
    } catch (testError) {
      const description = errorText(testError);
      setTestErrors((current) => ({ ...current, [connection.id]: description }));
    } finally { setTestingId(''); }
  }

  const columns: ColumnsType<ToolConnection> = [
    { title: t('連線'), key: 'connection', render: (_: unknown, item) => <div className="tool-name-cell"><strong>{item.name}</strong><code>{item.endpoint}</code></div> },
    { title: t('狀態'), dataIndex: 'enabled', key: 'enabled', width: 100, render: (enabled: boolean) => enabled ? <Tag color="green">{t('啟用')}</Tag> : <Tag>{t('停用')}</Tag> },
    { title: t('認證'), dataIndex: 'key_configured', key: 'key_configured', width: 110, render: (configured: boolean) => configured ? <Tag color="blue">{t('Token 已設定')}</Tag> : <Tag>{t('未設定')}</Tag> },
    { title: t('工具允許清單'), dataIndex: 'allowed_tools', key: 'allowed_tools', render: (items: string[]) => items?.length ? items.join(' · ') : t('尚未允許工具') },
    { title: '', key: 'actions', width: 205, render: (_: unknown, item) => <Space wrap>{canAdmin && <Button size="small" icon={<ApiOutlined />} loading={testingId === item.id} onClick={() => void testConnection(item)}>{t('測試 tools/list')}</Button>}{canAdmin && <Button size="small" onClick={() => openEdit(item)}>{t('編輯')}</Button>}</Space> },
  ];

  const activeResultId = editor === 'new' ? '' : editor ? editor.id : selectedResultId;
  const testResult = activeResultId ? testResults[activeResultId] : undefined;
  const discoveredTools = testResult?.ok ? testResult.tools : [];
  const currentTestError = activeResultId ? testErrors[activeResultId] : '';
  return <div className="tool-settings-panel">
    {messageContext}
    <div className="tool-settings-heading"><div><Title level={4}>{t('專案工具連線')}</Title><Text type="secondary">{t('只註冊已允許的 MCP tools；端點與認證由 Work 服務測試。')}</Text></div><Space><Button icon={<ReloadOutlined />} loading={loading} onClick={() => void loadConnections()}>{t('重新整理')}</Button>{canAdmin && <Button type="primary" icon={<PlusOutlined />} onClick={openNew}>{t('新增連線')}</Button>}</Space></div>
    {error && <Alert className="tool-settings-alert" type="error" showIcon message={t('工具連線無法載入')} description={t(error)} action={<Button size="small" onClick={() => void loadConnections()}>{t('重試')}</Button>} />}
    <div className="tool-settings-table-shell"><Table<ToolConnection> rowKey="id" columns={columns} dataSource={connections} loading={loading} pagination={{ pageSize: 12, showSizeChanger: false }} scroll={{ x: 760 }} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={error ? t('無法顯示連線') : t('此專案尚無工具連線')}>{canAdmin && !error && <Button size="small" type="primary" onClick={openNew}>{t('新增連線')}</Button>}</Empty> }} /></div>
    {activeResultId && currentTestError && <Alert className="tool-settings-alert" type="error" showIcon message={t('工具連線測試失敗')} description={t(currentTestError)} />}
    {activeResultId && testResult && (testResult.ok ? <section className="tool-test-result">
      <div className="tool-settings-subheading"><strong>{t('已發現的 MCP tools')}</strong><Tag color="green">{t('tools/list 成功')}</Tag></div>
      {testResult.tools.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('連線可用，目前沒有公開工具')} /> : <div className="tool-discovery-list">{testResult.tools.map((tool) => <article key={tool.name}>
        <div><code>{tool.name}</code><Text type="secondary">{tool.description || t('沒有描述')}</Text></div>
        <details><summary>{t('輸入 schema')}</summary><pre>{JSON.stringify(tool.input_schema, null, 2)}</pre></details>
      </article>)}</div>}
    </section> : <Alert className="tool-settings-alert" type="error" showIcon message={t('工具連線測試未通過')} description={<pre className="tool-safe-result">{safeFailureText(testResult)}</pre>} />)}

    <Modal className="tool-editor-modal" title={editor === 'new' ? t('新增工具連線') : t('編輯連線 · {{name}}', { name: editor?.name ?? '' })} open={Boolean(editor)} onCancel={() => setEditor(null)} onOk={() => form.submit()} confirmLoading={saving} okText={t('儲存連線')} cancelText={t('取消')} width={680} destroyOnClose>
      <Form form={form} layout="vertical" onFinish={(values) => void saveConnection(values)}>
        {formError && <Alert className="tool-settings-alert" type="error" showIcon message={t('連線未儲存')} description={t(formError)} />}
        <Alert className="tool-security-note" type="info" showIcon message={t('Token 僅寫入加密儲存')} description={t('Token 不會從服務端回填。留白會保留現有 Token；更換已設定 Token 的端點時需輸入新值。請勿在端點網址放入帳密。')} />
        <Form.Item name="name" label={t('連線名稱')} rules={[{ required: true, whitespace: true }]}><Input maxLength={120} /></Form.Item>
        <Form.Item name="endpoint" label={t('MCP Streamable HTTP 端點')} rules={[{ required: true, whitespace: true, max: 2000 }, { validator: async (_, value: string) => {
          if (!value) return;
          try {
            const url = new URL(value);
            if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.hash) throw new Error();
          } catch { throw new Error(t('請輸入有效的 HTTP(S) endpoint；不可包含帳密或 fragment。')); }
        } }]}><Input placeholder="https://tools.example.com/mcp" autoComplete="url" /></Form.Item>
        <div className="tool-form-inline"><Form.Item name="enabled" label={t('連線狀態')} valuePropName="checked"><Switch checkedChildren={t('啟用')} unCheckedChildren={t('停用')} /></Form.Item><Form.Item name="auth_token" label={t('新連線 Token')}><Input.Password autoComplete="new-password" visibilityToggle={false} placeholder={editor !== 'new' && editor?.key_configured ? t('留白保留目前 Token') : t('輸入選用 Token')} /></Form.Item></div>
        <Form.Item name="allowed_tools" label={t('允許的工具')} rules={[{ validator: async (_, value: string[]) => { if ((value?.length ?? 0) > 100) throw new Error(t('Allowlist 最多 {{count}} 項', { count: formatNumber(100) })); } }]}><Select mode="tags" maxCount={100} allowClear tokenSeparators={[',']} placeholder={t('輸入工具名稱後按 Enter')} options={discoveredTools.map((tool: ToolDefinition) => ({ value: tool.name, label: tool.name }))} /></Form.Item>
        {discoveredTools.length > 0 && <Text className="tool-field-note" type="secondary">{t('最近一次 tools/list 已找到 {{count}} 個工具；Allowlist 仍需明確選取。', { count: formatNumber(discoveredTools.length) })}</Text>}
      </Form>
    </Modal>
  </div>;
}

function SandboxProfiles({ projectId, canAdmin }: { projectId: string; canAdmin: boolean }) {
  const { t } = useI18n();
  const [profiles, setProfiles] = useState<SandboxProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editor, setEditor] = useState<SandboxProfile | null | 'new'>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [form] = Form.useForm<ProfileFormValues>();
  useLocalizedForm(form);
  const [messageApi, messageContext] = message.useMessage();

  async function loadProfiles() {
    setLoading(true);
    setError('');
    try { setProfiles(await api.sandboxProfiles(projectId)); }
    catch (loadError) { setError(errorText(loadError)); }
    finally { setLoading(false); }
  }
  useEffect(() => { void loadProfiles(); }, [projectId]);

  function openNew() {
    form.resetFields();
    form.setFieldsValue({ name: '', enabled: false });
    setEditor('new');
    setFormError('');
  }
  function openEdit(profile: SandboxProfile) {
    form.resetFields();
    form.setFieldsValue({ name: profile.name, enabled: profile.enabled, ...profile.limits });
    setEditor(profile);
    setFormError('');
  }

  async function saveProfile(values: ProfileFormValues) {
    setSaving(true);
    setFormError('');
    const body = {
      ...(editor === 'new' ? { project_id: projectId } : {}),
      name: values.name.trim(),
      enabled: values.enabled,
      limits: {
        timeout_seconds: Number(values.timeout_seconds),
        memory_mb: Number(values.memory_mb),
        cpu_count: Number(values.cpu_count),
        pids_limit: Number(values.pids_limit),
        output_bytes: Number(values.output_bytes),
        workspace_mb: Number(values.workspace_mb),
      },
    };
    try {
      if (editor === 'new') await api.createSandboxProfile(body);
      else if (editor) await api.updateSandboxProfile(editor.id, body);
      setEditor(null);
      await loadProfiles();
      messageApi.success(t('Sandbox profile 已儲存。'));
    } catch (saveError) { setFormError(errorText(saveError)); }
    finally { setSaving(false); }
  }

  const columns: ColumnsType<SandboxProfile> = [
    { title: t('設定檔'), key: 'name', render: (_: unknown, item) => <div className="tool-name-cell"><strong>{item.name}</strong><span>{t('更新 {{date}}', { date: dateText(item.updated_at) })}</span></div> },
    { title: t('狀態'), dataIndex: 'enabled', key: 'enabled', width: 90, render: (enabled: boolean) => enabled ? <Tag color="green">{t('啟用')}</Tag> : <Tag>{t('停用')}</Tag> },
    { title: t('資源限制'), key: 'limits', render: (_: unknown, item) => <span className="tool-limit-values">{formatNumber(item.limits.memory_mb)} MB · {formatNumber(item.limits.cpu_count)} CPU · {formatNumber(item.limits.timeout_seconds)}s</span> },
    { title: t('Workspace 與 Output'), key: 'workspace', render: (_: unknown, item) => <span className="tool-limit-values">{formatNumber(item.limits.workspace_mb)} MB · {formatNumber(item.limits.output_bytes)} bytes</span> },
    { title: '', key: 'actions', width: 90, render: (_: unknown, item) => canAdmin ? <Button size="small" onClick={() => openEdit(item)}>{t('編輯')}</Button> : null },
  ];

  return <div className="tool-settings-panel">
    {messageContext}
    <div className="tool-settings-heading"><div><Title level={4}>{t('每個 Run 的 Sandbox 設定檔')}</Title><Text type="secondary">{t('每個 Run 使用隔離的暫存 workspace；服務重啟會清除並回報。')}</Text></div><Space><Button icon={<ReloadOutlined />} loading={loading} onClick={() => void loadProfiles()}>{t('重新整理')}</Button>{canAdmin && <Button type="primary" icon={<PlusOutlined />} onClick={openNew}>{t('新增 Profile')}</Button>}</Space></div>
    <Alert className="sandbox-policy-note" type="info" showIcon message={t('隔離政策固定')} description={t('無網路、固定 operator image、非 root、唯讀 root filesystem、移除 capabilities、no-new-privileges；不開放 host mount、Docker socket 或自訂 image。')} />
    {error && <Alert className="tool-settings-alert" type="error" showIcon message={t('Sandbox profiles 無法載入')} description={t(error)} action={<Button size="small" onClick={() => void loadProfiles()}>{t('重試')}</Button>} />}
    <div className="tool-settings-table-shell"><Table<SandboxProfile> rowKey="id" columns={columns} dataSource={profiles} loading={loading} pagination={{ pageSize: 12, showSizeChanger: false }} scroll={{ x: 700 }} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={error ? t('無法顯示 profiles') : t('此專案尚無 Sandbox profile')}>{canAdmin && !error && <Button size="small" type="primary" onClick={openNew}>{t('新增 Profile')}</Button>}</Empty> }} /></div>

    <Modal className="tool-editor-modal" title={editor === 'new' ? t('新增 Sandbox profile') : t('編輯 Sandbox · {{name}}', { name: editor?.name ?? '' })} open={Boolean(editor)} onCancel={() => setEditor(null)} onOk={() => form.submit()} confirmLoading={saving} okText={t('儲存 Profile')} cancelText={t('取消')} width={720} destroyOnClose>
      <Form form={form} layout="vertical" onFinish={(values) => void saveProfile(values)}>
        {formError && <Alert className="tool-settings-alert" type="error" showIcon message={t('Profile 未儲存')} description={t(formError)} />}
        <Form.Item name="name" label={t('Profile 名稱')} rules={[{ required: true, whitespace: true }]}><Input maxLength={120} /></Form.Item>
        <Form.Item name="enabled" label={t('Profile 狀態')} valuePropName="checked"><Switch checkedChildren={t('啟用')} unCheckedChildren={t('停用')} /></Form.Item>
        <div className="tool-limits-grid">
          <Form.Item name="timeout_seconds" label={t('最長執行秒數')} rules={[{ required: true, type: 'number', min: 1, max: 120 }]}><InputNumber className="full-width" min={1} max={120} precision={0} /></Form.Item>
          <Form.Item name="memory_mb" label={t('記憶體（MB）')} rules={[{ required: true, type: 'number', min: 64, max: 1024 }]}><InputNumber className="full-width" min={64} max={1024} precision={0} /></Form.Item>
          <Form.Item name="cpu_count" label={t('CPU 數')} rules={[{ required: true, type: 'number', min: 0.25, max: 2 }]}><InputNumber className="full-width" min={0.25} max={2} step={0.25} precision={2} /></Form.Item>
          <Form.Item name="pids_limit" label={t('PID 上限')} rules={[{ required: true, type: 'number', min: 16, max: 128 }]}><InputNumber className="full-width" min={16} max={128} precision={0} /></Form.Item>
          <Form.Item name="output_bytes" label={t('輸出上限（bytes）')} rules={[{ required: true, type: 'number', min: 1024, max: 65536 }]}><InputNumber className="full-width" min={1024} max={65536} precision={0} /></Form.Item>
          <Form.Item name="workspace_mb" label={t('Workspace（MB）')} rules={[{ required: true, type: 'number', min: 1, max: 128 }]}><InputNumber className="full-width" min={1} max={128} precision={0} /></Form.Item>
        </div>
      </Form>
    </Modal>
  </div>;
}
