import { useCallback, useEffect, useState } from 'react';
import type { ColumnsType } from 'antd/es/table';
import { Alert, Button, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Typography, message } from 'antd';
import { DeleteOutlined, LinkOutlined, PlusOutlined, ReloadOutlined, SaveOutlined, SafetyOutlined } from '@ant-design/icons';
import { authApi } from './client';
import { useAuth } from './AuthContext';
import { PermissionEditor, usePermissionCatalogs } from './permissions';
import type { AuthPermissions, IdentityAuditEvent, IdentitySsoLink, IdentitySsoSettings, IdentitySsoSettingsWrite, IdentityUser } from './types';
import { formatDate, formatNumber, t, useI18n, useLocalizedForm } from '../i18n';

const { Text } = Typography;

const providerTemplates = {
  entra: { label: 'Microsoft Entra ID', issuer: '', issuerPlaceholder: 'https://login.microsoftonline.com/<tenant-id>/v2.0', scopes: ['openid', 'profile', 'email'] },
  google: { label: 'Google Workspace', issuer: 'https://accounts.google.com', issuerPlaceholder: 'https://accounts.google.com', scopes: ['openid', 'profile', 'email'] },
  okta: { label: 'Okta', issuer: '', issuerPlaceholder: 'https://<your-domain>.okta.com/oauth2/default', scopes: ['openid', 'profile', 'email'] },
  auth0: { label: 'Auth0', issuer: '', issuerPlaceholder: 'https://<your-domain>/', scopes: ['openid', 'profile', 'email'] },
  keycloak: { label: 'Keycloak', issuer: '', issuerPlaceholder: 'https://<your-host>/realms/<realm>', scopes: ['openid', 'profile', 'email'] },
  generic: { label: '通用 OIDC', issuer: '', issuerPlaceholder: 'https://identity.example.com/realms/company', scopes: ['openid', 'profile', 'email'] },
} as const;

type ProviderTemplate = keyof typeof providerTemplates;
type SettingsFormValues = Omit<IdentitySsoSettingsWrite, 'client_secret'> & { client_secret?: string };

const providerHints: Record<ProviderTemplate, string> = {
  entra: '請使用單一組織 tenant 的 Issuer。Email claim 依 tenant token 設定選用 email 或 preferred_username；email_verified 常未提供，只有管理員確認 tenant 與允許網域範圍後，才考慮關閉電子郵件驗證要求。',
  google: 'Google Workspace OIDC 預設不提供 groups claim。若需要群組授權，請先由身分服務或 broker 提供群組 claim，並設定下方群組 claim 欄位。',
  okta: '若要依群組授權，請在 Okta 設定 ID token mapper，將群組資訊放入 ID token，並確認 claim 名稱與下方群組 claim 欄位一致。',
  auth0: 'Auth0 群組 claim 常使用自訂 namespaced 名稱。請在 ID token 加入群組 claim，並將完整名稱填入下方群組 claim 欄位。',
  keycloak: '若要依群組授權，請在 Keycloak 設定 ID token mapper，將群組資訊放入 ID token，並確認 claim 名稱與下方群組 claim 欄位一致。',
  generic: '請依 OIDC 服務的實際 token claim 設定 Issuer、電子郵件與群組欄位；群組授權只會套用到你明確設定的資源。',
};

function errorText(error: unknown) {
  if (error instanceof Error && 'sourceMessage' in error) return String((error as Error & { sourceMessage: string }).sourceMessage);
  return error instanceof Error ? error.message : '請求失敗，請稍後重試。';
}

function detailsText(details: Record<string, unknown>) {
  return Object.entries(details).map(([key, value]) => `${key}: ${typeof value === 'string' ? value : JSON.stringify(value)}`).join(' · ') || '—';
}

export function EnterpriseSsoPanel() {
  const { t } = useI18n();
  const [form] = Form.useForm<SettingsFormValues>();
  useLocalizedForm(form);
  const [mappingForm] = Form.useForm<{ group: string }>();
  useLocalizedForm(mappingForm);
  const [settings, setSettings] = useState<IdentitySsoSettings | null>(null);
  const [settingsBusy, setSettingsBusy] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [settingsError, setSettingsError] = useState('');
  const [testResult, setTestResult] = useState<Awaited<ReturnType<typeof authApi.testSso>> | null>(null);
  const [template, setTemplate] = useState<ProviderTemplate>('generic');
  const [groupMappings, setGroupMappings] = useState<IdentitySsoSettings['group_mappings']>([]);
  const [defaultPermissions, setDefaultPermissions] = useState<AuthPermissions>({});
  const [mappingOpen, setMappingOpen] = useState(false);
  const [mappingIndex, setMappingIndex] = useState<number | null>(null);
  const [mappingPermissions, setMappingPermissions] = useState<AuthPermissions>({});
  const [links, setLinks] = useState<IdentitySsoLink[]>([]);
  const [users, setUsers] = useState<IdentityUser[]>([]);
  const [linksBusy, setLinksBusy] = useState(true);
  const [linksError, setLinksError] = useState('');
  const [linking, setLinking] = useState(false);
  const [linkForm] = Form.useForm<{ user_id: string; subject: string; managed_permissions: boolean }>();
  useLocalizedForm(linkForm);
  const [messageApi, contextHolder] = message.useMessage();
  const auth = useAuth();
  const { catalogs, reload: reloadCatalogs } = usePermissionCatalogs();

  const loadSettings = useCallback(async () => {
    setSettingsBusy(true);
    setSettingsError('');
    try {
      const loaded = await authApi.ssoSettings();
      setSettings(loaded);
      setGroupMappings(loaded.group_mappings ?? []);
      setDefaultPermissions(loaded.default_permissions ?? {});
      form.setFieldsValue({ ...loaded, client_secret: '' });
    } catch (error) {
      setSettingsError(errorText(error));
    } finally {
      setSettingsBusy(false);
    }
  }, [form]);

  const loadLinks = useCallback(async () => {
    setLinksBusy(true);
    setLinksError('');
    try {
      const [result, directory] = await Promise.all([authApi.ssoLinks(), authApi.users()]);
      setLinks(result.links);
      setUsers(directory.users);
    } catch (error) {
      setLinksError(errorText(error));
    } finally {
      setLinksBusy(false);
    }
  }, []);

  useEffect(() => {
    void loadSettings();
    void loadLinks();
    return () => form.resetFields(['client_secret']);
  }, [form, loadSettings, loadLinks]);

  function applyTemplate(value: ProviderTemplate) {
    setTemplate(value);
    const preset = providerTemplates[value];
    form.setFieldsValue({ issuer_url: preset.issuer || form.getFieldValue('issuer_url'), scopes: [...preset.scopes], email_claim: 'email', groups_claim: 'groups' });
  }

  async function saveSettings(values: SettingsFormValues) {
    if (!settings) return;
    const { client_secret: rawSecret, ...editable } = values;
    const clientSecret = rawSecret?.trim();
    const body: IdentitySsoSettingsWrite = {
      ...editable,
      revision: settings.revision,
      default_permissions: defaultPermissions ?? {},
      group_mappings: groupMappings,
      ...(clientSecret ? { client_secret: clientSecret } : {}),
    };
    setSaving(true);
    setSettingsError('');
    setTestResult(null);
    try {
      const updated = await authApi.updateSsoSettings(body);
      setSettings(updated);
      setGroupMappings(updated.group_mappings ?? []);
      setDefaultPermissions(updated.default_permissions ?? {});
      form.setFieldsValue({ ...updated, client_secret: '' });
      if (await auth.refreshStatus()) messageApi.success(t('企業 SSO 設定已儲存。'));
      else messageApi.warning(t('設定已儲存，但登入狀態尚未同步；請重新載入確認。'));
    } catch (error) {
      setSettingsError(errorText(error));
    } finally {
      form.resetFields(['client_secret']);
      setSaving(false);
    }
  }

  async function testConnection() {
    setTesting(true);
    setSettingsError('');
    setTestResult(null);
    try {
      setTestResult(await authApi.testSso());
    } catch (error) {
      setSettingsError(errorText(error));
    } finally {
      setTesting(false);
    }
  }

  function openMapping(index: number | null) {
    setMappingIndex(index);
    setMappingPermissions(index === null ? {} : groupMappings[index].permissions);
    mappingForm.setFieldsValue({ group: index === null ? '' : groupMappings[index].group });
    setMappingOpen(true);
  }

  function closeMapping() {
    setMappingOpen(false);
    setMappingIndex(null);
    setMappingPermissions({});
    mappingForm.resetFields();
  }

  async function saveMapping() {
    let group: string;
    try {
      ({ group } = await mappingForm.validateFields());
    } catch {
      return;
    }
    const normalized = group.trim();
    if (groupMappings.some((item, index) => item.group === normalized && index !== mappingIndex)) {
      mappingForm.setFields([{ name: 'group', errors: [t('此群組已經有一筆對應設定。')] }]);
      return;
    }
    setGroupMappings((current) => {
      const next = [...current];
      const entry = { group: normalized, permissions: mappingPermissions };
      if (mappingIndex === null) next.push(entry);
      else next[mappingIndex] = entry;
      return next;
    });
    closeMapping();
  }

  const mappingColumns: ColumnsType<IdentitySsoSettings['group_mappings'][number]> = [
    { title: t('企業群組'), dataIndex: 'group', key: 'group', render: (group: string) => <Text className="auth-sso-group-name">{group}</Text> },
    { title: t('產品權限'), key: 'permissions', render: (_value, item) => permissionSummary(item.permissions) },
    { title: '', key: 'actions', width: 112, render: (_value, _item, index) => <Space size={4}><Button size="small" onClick={() => openMapping(index)}>{t('編輯')}</Button><Button size="small" danger icon={<DeleteOutlined />} aria-label={t('移除群組對應')} onClick={() => setGroupMappings((current) => current.filter((_entry, itemIndex) => itemIndex !== index))} /></Space> },
  ];

  const linkColumns: ColumnsType<IdentitySsoLink> = [
    { title: t('Ordivant 帳號'), key: 'user', render: (_value, link) => <div className="auth-user-cell"><strong>{users.find((user) => user.id === link.user_id)?.name ?? t('找不到使用者')}</strong><span>{users.find((user) => user.id === link.user_id)?.email ?? link.user_id}</span></div> },
    { title: t('身分服務'), dataIndex: 'issuer', key: 'issuer', width: 220, render: (issuer: string) => <Text className="auth-sso-issuer" title={issuer}>{issuer}</Text> },
    { title: t('企業主體 ID'), dataIndex: 'subject', key: 'subject', render: (subject: string) => <Text className="auth-sso-subject">{subject}</Text> },
    { title: t('權限同步'), dataIndex: 'managed_permissions', key: 'managed_permissions', width: 94, render: (managed: boolean) => <Tag color={managed ? 'blue' : 'default'}>{t(managed ? '群組管理' : '手動管理')}</Tag> },
    { title: '', key: 'actions', width: 74, render: (_value, link) => <Popconfirm title={t('解除企業帳號連結？')} description={t('此帳號之後將無法透過此企業主體登入。')} okText={t('解除')} cancelText={t('取消')} onConfirm={() => void unlinkSubject(link)}><Button size="small" danger icon={<DeleteOutlined />} aria-label={t('解除企業帳號連結')} /></Popconfirm> },
  ];

  async function createLink(values: { user_id: string; subject: string; managed_permissions: boolean }) {
    setLinking(true);
    setLinksError('');
    try {
      await authApi.createSsoLink({ ...values, subject: values.subject.trim() });
      linkForm.resetFields();
      await loadLinks();
      messageApi.success(t('企業帳號已明確連結。'));
    } catch (error) {
      setLinksError(errorText(error));
    } finally {
      setLinking(false);
    }
  }

  async function unlinkSubject(link: IdentitySsoLink) {
    setLinksError('');
    try {
      await authApi.deleteSsoLink(link.id);
      await loadLinks();
      messageApi.success(t('企業帳號連結已解除，相關登入工作階段已撤銷。'));
    } catch (error) {
      setLinksError(errorText(error));
    }
  }

  const preset = providerTemplates[template];
  const userOptions = users.map((user) => ({ value: user.id, label: `${user.name} · ${user.email}` }));

  return (
    <div className="auth-settings-panel auth-sso-panel">
      {contextHolder}
      {settingsError && <Alert className="auth-drawer-alert" type="error" showIcon message={t('企業 SSO 操作失敗')} description={t(settingsError)} action={<Button size="small" icon={<ReloadOutlined />} onClick={() => void loadSettings()}>{t('重新載入')}</Button>} />}
      {settingsBusy ? <div className="auth-sso-loading"><Text type="secondary">{t('載入企業身分設定中…')}</Text></div> : settings ? <>
        <div className="auth-section-heading"><div><strong>{t('企業 OpenID Connect')}</strong><span>{t('每個環境使用一組企業身分服務設定。')}</span></div><Tag color={settings.enabled ? 'green' : 'default'}>{t(settings.enabled ? '已啟用' : '未啟用')}</Tag></div>
        <Alert className="auth-sso-note" type="info" showIcon icon={<SafetyOutlined />} message={t('支援標準 OIDC 的企業身分服務')} description={t('可使用 Microsoft Entra ID、Google Workspace、Okta、Auth0、Keycloak 或其他 OIDC 服務。SAML、LDAP 或 Active Directory 可先透過 Keycloak broker 轉接；本平台不直接接收這些協定。')} />
        <div className="auth-sso-template-row">
          <Text strong>{t('設定範本')}</Text>
          <Select value={template} options={Object.entries(providerTemplates).map(([value, item]) => ({ value, label: t(item.label) }))} onChange={(value: ProviderTemplate) => applyTemplate(value)} />
        </div>
        <Text className="auth-sso-provider-hint">{t(providerHints[template])}</Text>
        <Form form={form} layout="vertical" onFinish={(values) => void saveSettings(values)} requiredMark={false} disabled={saving}>
          <div className="auth-sso-grid">
            <Form.Item name="display_name" label={t('登入按鈕名稱')} rules={[{ required: true, whitespace: true, message: t('請輸入登入按鈕名稱') }]}><Input maxLength={64} placeholder={t('企業帳號')} /></Form.Item>
            <Form.Item name="client_id" label={t('用戶端 ID')}><Input autoComplete="off" /></Form.Item>
          </div>
          <Form.Item name="issuer_url" label={t('Issuer URL')} rules={[{ type: 'url', message: t('請輸入有效的 issuer URL') }]} extra={preset.issuerPlaceholder}><Input autoComplete="url" placeholder={preset.issuerPlaceholder} /></Form.Item>
          <Form.Item name="client_secret" label={t('用戶端密鑰')} extra={t(settings.client_secret_configured ? '已儲存密鑰。留空會保留目前密鑰；更換 issuer 或用戶端 ID 時必須輸入新密鑰。' : '輸入一次後會加密儲存；儲存後此欄位會清空。')}><Input.Password autoComplete="new-password" visibilityToggle /></Form.Item>
          <div className="auth-sso-grid">
            <Form.Item name="scopes" label={t('OIDC scopes')} extra={t('至少需要 openid；使用空白或逗號分隔。')}><Select mode="tags" tokenSeparators={[' ', ',']} options={[{ value: 'openid' }, { value: 'profile' }, { value: 'email' }]} /></Form.Item>
            <Form.Item name="allowed_email_domains" label={t('允許的電子郵件網域')} extra={t('啟用前需填入精確網域，例如 example.com；不支援萬用字元。')}><Select mode="tags" tokenSeparators={[',', ' ']} placeholder="example.com" /></Form.Item>
          </div>
          <div className="auth-sso-grid">
            <Form.Item name="email_claim" label={t('電子郵件 claim')} rules={[{ required: true, whitespace: true }]}><Input placeholder="email" /></Form.Item>
            <Form.Item name="groups_claim" label={t('群組 claim')}><Input placeholder="groups" /></Form.Item>
          </div>
          <Form.Item name="require_email_verified" label={t('要求企業服務確認電子郵件')} valuePropName="checked"><Switch checkedChildren={t('要求')} unCheckedChildren={t('不要求')} /></Form.Item>
          <Form.Item name="required_acr" label={t('允許的登入強度（acr）')} extra={t('填入身分服務實際提供的強度值；登入時必須符合其中一個。')}><Select mode="tags" /></Form.Item>
          <Form.Item name="required_amr" label={t('必要驗證方式（amr）')} extra={t('例如 mfa；必須全部出現在已驗證的登入權杖中。設定登入強度時，成員須使用僅企業登入政策。')}><Select mode="tags" /></Form.Item>
          <Form.Item name="provisioning" label={t('帳號建立方式')} rules={[{ required: true }]} extra={t('僅限允許網域內的已驗證帳號。JIT 帳號會套用下方預設與群組授權；沒有產品授權就無法進入產品。')}><Select options={[{ value: 'invited_only', label: t('僅限受邀成員') }, { value: 'jit', label: t('首次登入自動建立成員（JIT）') }]} /></Form.Item>
          <div className="auth-sso-subsection"><div className="auth-section-heading"><div><strong>{t('預設產品權限')}</strong><span>{t('JIT 新帳號套用；只會授予明確選取的資源。')}</span></div></div><PermissionEditor value={defaultPermissions} catalogs={catalogs} onChange={setDefaultPermissions} /><Button size="small" onClick={() => void reloadCatalogs()}>{t('重新載入資源')}</Button></div>
          <div className="auth-sso-subsection"><div className="auth-section-heading"><div><strong>{t('群組權限對應')}</strong><span>{t('使用群組 claim 的完整名稱；對應權限只套用到列出的產品與資源。')}</span></div><Button size="small" icon={<PlusOutlined />} onClick={() => openMapping(null)}>{t('新增群組')}</Button></div><Table rowKey="group" size="small" dataSource={groupMappings} columns={mappingColumns} pagination={false} locale={{ emptyText: t('尚未設定群組對應') }} scroll={{ x: 450 }} /></div>
          <Form.Item name="login_policy" label={t('登入政策')} rules={[{ required: true }]} extra={t('SSO-only 會停用成員的本機密碼登入與復原；管理員仍保留明確的本機密碼復原入口。')}><Select options={[{ value: 'password_and_sso', label: t('允許本機密碼與企業登入') }, { value: 'sso_only', label: t('僅允許企業登入（管理員除外）') }]} /></Form.Item>
          <Form.Item name="enabled" label={t('啟用企業登入')} valuePropName="checked"><Switch checkedChildren={t('開啟')} unCheckedChildren={t('關閉')} /></Form.Item>
          {settings.redirect_uri && <div className="auth-sso-callback"><Text strong>{t('Callback URL')}</Text><Text code copyable>{settings.redirect_uri}</Text><Text type="secondary">{t('請將此網址登記在企業身分服務的允許回呼網址中。')}</Text></div>}
          <Space wrap className="auth-sso-actions"><Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saving}>{t('儲存設定')}</Button><Button icon={<SafetyOutlined />} loading={testing} disabled={!settings.issuer_url || !settings.client_id || !settings.client_secret_configured} onClick={() => void testConnection()}>{t('測試連線')}</Button></Space>
        </Form>
        {testResult && <Alert className="auth-sso-test-result" type="success" showIcon message={t('企業身分服務連線成功')} description={<div className="auth-sso-test-details"><span>{t('Issuer：')} {testResult.issuer}</span><span>{t('授權端點：')} {testResult.authorization_endpoint}</span><span>{t('簽章演算法：')} {testResult.supported_algs.join(', ') || '—'}</span></div>} />}
        <div className="auth-sso-subsection auth-sso-links"><div className="auth-section-heading"><div><strong>{t('明確連結既有帳號')}</strong><span>{t('不會依電子郵件自動合併。填入企業服務提供的穩定 subject，初次登入時電子郵件仍須符合。')}</span></div></div>
          {linksError && <Alert className="auth-drawer-alert" type="error" showIcon message={t('帳號連結操作失敗')} description={t(linksError)} action={<Button size="small" onClick={() => void loadLinks()}>{t('重試')}</Button>} />}
          <Form form={linkForm} layout="vertical" initialValues={{ managed_permissions: false }} onFinish={(values) => void createLink(values)} requiredMark={false}>
            <div className="auth-sso-link-form"><Form.Item name="user_id" label={t('Ordivant 帳號')} rules={[{ required: true }]}><Select showSearch optionFilterProp="label" options={userOptions} placeholder={t('選擇既有帳號')} /></Form.Item><Form.Item name="subject" label={t('企業 subject（sub claim）')} rules={[{ required: true, whitespace: true, message: t('請輸入穩定的 subject') }]} extra={t('請從企業身分服務取得穩定的 sub 值。')}><Input autoComplete="off" /></Form.Item></div>
            <Form.Item name="managed_permissions" label={t('後續權限管理')} valuePropName="checked" extra={t('開啟後，之後登入會依企業群組同步此帳號權限；關閉則保留 Ordivant 管理員手動權限。')}><Switch checkedChildren={t('群組同步')} unCheckedChildren={t('手動管理')} /></Form.Item>
            <Button htmlType="submit" icon={<LinkOutlined />} loading={linking} disabled={!settings.issuer_url}>{t('連結企業帳號')}</Button>
          </Form>
          <Table<IdentitySsoLink> rowKey="id" size="small" dataSource={links} columns={linkColumns} loading={linksBusy} pagination={false} locale={{ emptyText: t('尚未連結企業帳號') }} scroll={{ x: 760 }} />
        </div>
      </> : null}
      <Modal title={t(mappingIndex === null ? '新增群組權限' : '編輯群組權限')} open={mappingOpen} onCancel={closeMapping} onOk={() => void saveMapping()} okText={t('套用群組權限')} cancelText={t('取消')} width="min(720px, calc(100vw - 24px))" destroyOnClose className="auth-permissions-modal auth-sso-mapping-modal">
        <Form form={mappingForm} layout="vertical"><Form.Item name="group" label={t('企業群組完整名稱')} rules={[{ required: true, whitespace: true, message: t('請輸入 group claim 的完整值') }]}><Input autoComplete="off" /></Form.Item></Form>
        <PermissionEditor value={mappingPermissions} catalogs={catalogs} onChange={setMappingPermissions} />
      </Modal>
    </div>
  );

}

function permissionSummary(permissions: AuthPermissions) {
  const roleLabels: Record<string, string> = { manager: '管理者', worker: '工作者', reviewer: '審核者', writer: '編輯者', reader: '讀者' };
  const labels = (Object.entries(permissions) as Array<[keyof AuthPermissions, AuthPermissions[keyof AuthPermissions]]>)
    .filter(([, value]) => Boolean(value))
    .map(([product, value]) => `${product}: ${t(roleLabels[value?.role ?? ''] ?? value?.role ?? '')} (${formatNumber(value?.scope_ids.length ?? 0)})`);
  return <Text className="auth-sso-permission-summary">{labels.join(' · ') || t('無產品權限')}</Text>;
}

const auditActionLabels: Record<string, string> = {
  'sso.login_success': '企業登入成功',
  'sso.login_failure': '企業登入失敗',
  'sso.settings_changed': '更新企業登入設定',
  'sso.connection_test_failure': '企業登入連線測試失敗',
  'sso.connection_test_success': '企業登入連線測試成功',
  'sso.provisioned': '建立企業成員',
  'sso.link_created': '連結企業帳號',
  'sso.link_deleted': '解除企業帳號連結',
  'sso.backchannel_logout': '企業端撤銷登入',
  'sso.backchannel_logout_failure': '企業端撤銷登入失敗',
  'local.login_success': '本機帳號登入成功',
  'local.login_failure': '本機帳號登入失敗',
  'local.password_changed': '變更本機密碼',
  'local.password_recovered': '復原本機密碼',
  'local.recovery_failure': '本機密碼復原失敗',
  'admin.setup': '建立初始管理員',
  'admin.user_updated': '更新帳號或權限',
  'invitation.created': '建立成員邀請',
  'invitation.accepted': '接受成員邀請',
  'session.logout': '登出',
  'session.logout_all': '登出全部工作階段',
};

export function IdentityAuditPanel() {
  const { t } = useI18n();
  const [events, setEvents] = useState<IdentityAuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await authApi.identityAudit(100);
      setEvents(result.events);
    } catch (loadError) {
      setError(errorText(loadError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const columns: ColumnsType<IdentityAuditEvent> = [
    { title: t('時間'), dataIndex: 'created_at', key: 'created_at', width: 160, render: (value: string) => formatDate(value) },
    { title: t('事件'), dataIndex: 'action', key: 'action', width: 150, render: (action: string) => t(auditActionLabels[action] ?? action) },
    { title: t('使用者 ID'), dataIndex: 'user_id', key: 'user_id', width: 150, render: (value: string | null) => value || t('系統') },
    { title: t('詳細資料'), dataIndex: 'details', key: 'details', render: (details: Record<string, unknown>) => <Text className="auth-audit-details" title={detailsText(details)}>{detailsText(details)}</Text> },
  ];

  return <div className="auth-settings-panel auth-audit-panel"><div className="auth-section-heading"><div><strong>{t('身分與權限事件')}</strong><span>{t('保留最近 100 筆管理與登入紀錄。')}</span></div><Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>{t('重新整理')}</Button></div>{error && <Alert type="error" showIcon message={t('無法載入身分稽核紀錄')} description={t(error)} action={<Button size="small" onClick={() => void load()}>{t('重試')}</Button>} />}<Table<IdentityAuditEvent> rowKey="id" size="small" dataSource={events} columns={columns} loading={loading} pagination={{ pageSize: 10, hideOnSinglePage: true }} scroll={{ x: 650 }} locale={{ emptyText: t('尚無身分稽核事件') }} /></div>;
}
