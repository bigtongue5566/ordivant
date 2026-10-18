import { useCallback, useEffect, useState, type ReactNode } from 'react';
import type { ColumnsType } from 'antd/es/table';
import { Alert, Avatar, Button, Descriptions, Form, Input, Modal, Select, Switch, Table, Tag, Tooltip, Typography, message } from 'antd';
import { ApiOutlined, AuditOutlined, ControlOutlined, LockOutlined, LoginOutlined, LogoutOutlined, SettingOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons';
import { authApi } from './client';
import { useAuth } from './AuthContext';
import type { AuthPermissions, IdentitySessionRecord, IdentityUser, ProductKey } from './types';
import { PermissionEditor, usePermissionCatalogs } from './permissions';
import { EnterpriseSsoPanel, IdentityAuditPanel } from './SsoSettings';
import { EnterpriseGovernance } from './EnterpriseGovernance';
import { CollaborationCenter } from '../products/shared/CollaborationCenter';
import { AccessTokensPanel } from './AccessTokensPanel';
import { AccountSettingsLayout, type SettingsGroup } from './AccountSettingsLayout';
import { useNavigationState } from '../shared/useNavigationState';
import { organizationSettingsEvent } from './settingsNavigation';
import { formatDate, useI18n, useLocalizedForm } from '../i18n';
import './auth.css';
import './account-settings.css';

const { Text, Paragraph } = Typography;

function errorText(error: unknown) {
  if (error instanceof Error && 'sourceMessage' in error) return String((error as Error & { sourceMessage: string }).sourceMessage);
  return error instanceof Error ? error.message : '請求失敗，請稍後重試。';
}

function dateText(value: string) {
  return formatDate(value);
}

function businessRoleLabel(role: string, t: (source: string) => string) {
  const labels: Record<string, string> = { admin: '管理員', manager: '管理者', worker: '工作者', reviewer: '審核者', writer: '編輯者', reader: '讀者', member: '成員' };
  return t(labels[role] ?? role);
}

function permissionsDiffer(left: AuthPermissions, right: AuthPermissions) {
  return (['work', 'knowledge', 'code'] as ProductKey[]).some((product) => {
    const first = left[product];
    const second = right[product];
    if (first?.role !== second?.role) return true;
    const firstScopes = [...(first?.scope_ids ?? [])].sort();
    const secondScopes = [...(second?.scope_ids ?? [])].sort();
    return firstScopes.length !== secondScopes.length || firstScopes.some((scope, index) => scope !== secondScopes[index]);
  });
}

export function AccountControl({
  product,
  productLabel,
  displayName,
  businessRole,
  variant = 'toolbar',
  renderControls,
  onAction,
}: {
  product: ProductKey;
  productLabel: string;
  displayName: string;
  businessRole: string;
  variant?: 'toolbar' | 'sidebar';
  renderControls?: (controls: ReactNode) => ReactNode;
  onAction?: () => void;
}) {
  const { t } = useI18n();
  const [settingsSection, setSettingsSection] = useNavigationState<string>('settings', '', ['', 'profile', 'security', 'api-mcp', 'users', 'sso', 'identity-audit', 'governance']);
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState('');
  const [messageApi, contextHolder] = message.useMessage();
  const auth = useAuth();
  const isAdmin = auth.session?.user.role === 'admin';
  const settingsTitle = t('帳號設定');
  const organizationSection = ['users', 'sso', 'identity-audit', 'governance'].includes(settingsSection);

  useEffect(() => {
    if (!isAdmin) return;
    const open = () => setSettingsSection('users');
    window.addEventListener(organizationSettingsEvent, open);
    return () => window.removeEventListener(organizationSettingsEvent, open);
  }, [isAdmin, setSettingsSection]);

  async function signOut() {
    setSigningOut(true);
    setSignOutError('');
    try {
      await auth.logout();
    } catch (error) {
      const text = errorText(error);
      setSignOutError(text);
      messageApi.error(t('伺服器登出未完成：{{message}}', { message: text }));
    } finally {
      setSigningOut(false);
    }
  }

  const settingsGroups: SettingsGroup[] = [
    { label: t('個人設定'), sections: [
      { key: 'profile', label: t('帳號'), description: t('查看個人資料、登入來源與目前的存取權限。'), icon: <UserOutlined />, content: <ProfilePanel businessRole={businessRole} /> },
      { key: 'security', label: t('安全性'), description: t('管理密碼與已登入的工作階段，保護你的帳號。'), icon: <LockOutlined />, content: <SecurityPanel onLogout={signOut} /> },
      { key: 'api-mcp', label: t('API 與 MCP'), description: t('建立個人存取權杖，連接工具與外部程式。'), icon: <ApiOutlined />, content: <AccessTokensPanel product={product} /> },
    ] },
  ];
  const organizationGroups: SettingsGroup[] = isAdmin ? [{ label: t('組織管理'), sections: [
      { key: 'users', label: t('使用者與邀請'), description: t('邀請同事加入，管理帳號與各產品的存取權限。'), icon: <TeamOutlined />, content: <AdminPanel /> },
      { key: 'sso', label: t('企業 SSO'), description: t('設定企業登入、群組權限與身分帳號連結。'), icon: <LoginOutlined />, content: <EnterpriseSsoPanel /> },
      { key: 'governance', label: t('企業治理'), description: t('管理帳號佈建、稽核保留期限與郵件寄送。'), icon: <ControlOutlined />, content: <EnterpriseGovernance /> },
      { key: 'identity-audit', label: t('身分稽核'), description: t('檢視登入、帳號與權限的異動紀錄。'), icon: <AuditOutlined />, content: <IdentityAuditPanel /> },
    ] }] : [];

  const controls = <div className={`auth-account-control${variant === 'sidebar' ? ' auth-account-control-sidebar' : ''}`} data-product={product}>
        <CollaborationCenter product={product} showLabels={variant === 'sidebar'} onOpen={onAction} />
        <Tooltip title={settingsTitle}>
          <Button type="text" size="small" icon={<SettingOutlined />} aria-label={settingsTitle} onClick={() => { setSettingsSection('profile'); onAction?.(); }}>{variant === 'sidebar' && settingsTitle}</Button>
        </Tooltip>
        <Tooltip title={t('登出')}>
          <Button type="text" size="small" icon={<LogoutOutlined />} aria-label={t('{{product}} 登出', { product: productLabel })} loading={signingOut} onClick={() => { onAction?.(); void signOut(); }}>{variant === 'sidebar' && t('登出')}</Button>
        </Tooltip>
      </div>;

  return (
    <>
      {contextHolder}
      {renderControls ? renderControls(controls) : controls}
      <Modal title={settingsTitle} open={Boolean(settingsSection) && !organizationSection} onCancel={() => setSettingsSection('')} footer={null} width="min(1180px, calc(100vw - 48px))" className="auth-settings-modal" maskClosable={false} destroyOnClose>
        <AccountSettingsLayout notice={signOutError && <Alert className="auth-drawer-alert" type="error" showIcon message={t('登出失敗，工作階段仍有效')} description={t(signOutError)} />} groups={settingsGroups} activeKey={settingsSection} onChange={setSettingsSection} identity={<>
          <Avatar size={36}>{displayName.slice(0, 1).toUpperCase()}</Avatar>
          <div><strong>{displayName}</strong><span>{auth.session?.user.email}</span><Tag color={isAdmin ? 'purple' : 'default'}>{t(isAdmin ? '管理員' : '成員')}</Tag></div>
        </>} />
      </Modal>
      {isAdmin && <Modal title={t('組織管理')} open={organizationSection} onCancel={() => setSettingsSection('')} footer={null} width="min(1180px, calc(100vw - 48px))" className="auth-settings-modal auth-organization-modal" maskClosable={false} destroyOnClose>
        <AccountSettingsLayout groups={organizationGroups} activeKey={settingsSection} onChange={setSettingsSection} identity={<>
          <Avatar size={36} icon={<TeamOutlined />} />
          <div><strong>{t('組織管理')}</strong><span>{displayName}</span><Tag color="purple">{t('管理員')}</Tag></div>
        </>} />
      </Modal>}
    </>
  );
}

function ProfilePanel({ businessRole }: { businessRole: string }) {
  const { t } = useI18n();
  const auth = useAuth();
  return (
    <div className="auth-settings-panel">
      <Descriptions size="small" column={1} colon={false}>
        <Descriptions.Item label={t('姓名')}>{auth.session?.user.name}</Descriptions.Item>
        <Descriptions.Item label={t('電子郵件')}>{auth.session?.user.email}</Descriptions.Item>
        <Descriptions.Item label={t('Suite 角色')}>{t(auth.session?.user.role === 'admin' ? '管理員' : '成員')}</Descriptions.Item>
        <Descriptions.Item label={t('目前產品角色')}>{businessRoleLabel(businessRole || '尚未授權', t)}</Descriptions.Item>
        <Descriptions.Item label={t('登入來源')}>{auth.session?.authentication?.method === 'oidc' ? t('企業 SSO · {{provider}}', { provider: auth.session.authentication.provider_name || auth.sso?.display_name || 'OIDC' }) : t('Ordivant 帳號')}</Descriptions.Item>
        <Descriptions.Item label={t('權限管理')}>{t(auth.session?.user.permissions_source === 'scim' ? '由 SCIM 群組同步' : auth.session?.user.permissions_source === 'sso' ? '由企業群組同步' : '由管理員設定')}</Descriptions.Item>
        <Descriptions.Item label={t('工作階段到期')}>{auth.session ? dateText(auth.session.expires_at) : '—'}</Descriptions.Item>
      </Descriptions>
      <Paragraph type="secondary">{t('產品角色與可存取資源由各產品 API 分別授權。')}</Paragraph>
    </div>
  );
}

function SecurityPanel({ onLogout }: { onLogout: () => Promise<void> }) {
  const { t } = useI18n();
  const auth = useAuth();
  const [sessions, setSessions] = useState<IdentitySessionRecord[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [revoking, setRevoking] = useState('');
  const [loggingOutAll, setLoggingOutAll] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [formError, setFormError] = useState('');
  const [form] = Form.useForm();
  useLocalizedForm(form);

  const loadSessions = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const result = await authApi.sessions();
      setSessions(result.sessions);
    } catch (loadError) {
      setError(errorText(loadError));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { void loadSessions(); }, [loadSessions]);

  async function revokeSession(session: IdentitySessionRecord) {
    setRevoking(session.id);
    setError('');
    try {
      await authApi.revokeSession(session.id);
      if (session.current) auth.clearSession('此工作階段已撤銷，請重新登入。');
      else await loadSessions();
    } catch (revokeError) {
      setError(errorText(revokeError));
    } finally {
      setRevoking('');
    }
  }

  async function logoutAll() {
    setLoggingOutAll(true);
    setError('');
    try {
      await authApi.logoutAll();
      auth.clearSession('所有工作階段已登出。');
    } catch (logoutError) {
      setError(errorText(logoutError));
    } finally {
      setLoggingOutAll(false);
    }
  }

  async function changePassword(values: { current_password: string; new_password: string; confirm_password: string }) {
    if (values.new_password !== values.confirm_password) {
      setFormError('兩次輸入的新密碼不一致。');
      return;
    }
    setChangingPassword(true);
    setFormError('');
    try {
      const next = await authApi.changePassword({ current_password: values.current_password, new_password: values.new_password });
      auth.updateSession(next);
      form.resetFields();
      await loadSessions();
    } catch (passwordError) {
      setFormError(errorText(passwordError));
    } finally {
      form.resetFields(['current_password', 'new_password', 'confirm_password']);
      setChangingPassword(false);
    }
  }

  const columns: ColumnsType<IdentitySessionRecord> = [
    { title: t('工作階段'), key: 'session', render: (_value, session) => <div className="auth-session-cell"><strong>{t(session.current ? '目前工作階段' : '已登入裝置')}</strong><span>{t('最近活動 {{date}}', { date: dateText(session.last_seen_at) })}</span></div> },
    { title: t('到期時間'), dataIndex: 'expires_at', key: 'expires_at', render: value => <time className="auth-session-date">{dateText(value)}</time>, width: 205 },
    { title: '', key: 'action', width: 88, render: (_value, session) => <Button size="small" danger loading={revoking === session.id} onClick={() => void revokeSession(session)}>{t('撤銷')}</Button> },
  ];

  return (
    <div className="auth-settings-panel">
      {error && <Alert className="auth-drawer-alert" type="error" showIcon message={t('帳號操作失敗')} description={t(error)} action={<Button size="small" onClick={() => void loadSessions()}>{t('重試')}</Button>} />}
      {formError && <Alert className="auth-drawer-alert" type="error" showIcon message={t(formError)} />}
      {auth.session?.user.credential_type === 'sso' ? <Alert type="info" showIcon message={t('此帳號由企業身分服務管理')} description={t('請透過企業身分服務更新密碼與多重要素驗證。Ordivant 不提供此帳號的密碼或復原碼操作。')} /> : <section className="auth-password-section">
        <div className="auth-section-heading"><div><strong>{t('更改密碼')}</strong><span>{t('完成後會撤銷其他已登入工作階段。')}</span></div></div>
        <Form form={form} layout="vertical" onFinish={(values) => void changePassword(values)} requiredMark={false}>
          <Form.Item name="current_password" label={t('目前密碼')} rules={[{ required: true, message: t('請輸入目前密碼') }]}><Input.Password autoComplete="current-password" /></Form.Item>
          <Form.Item name="new_password" label={t('新密碼')} rules={[{ required: true, min: 12, message: t('密碼至少 12 個字元') }]}><Input.Password autoComplete="new-password" /></Form.Item>
          <Form.Item name="confirm_password" label={t('再次輸入新密碼')} rules={[{ required: true, message: t('請再次輸入新密碼') }]}><Input.Password autoComplete="new-password" /></Form.Item>
          <Button type="primary" htmlType="submit" loading={changingPassword}>{t('更新密碼')}</Button>
        </Form>
      </section>}
      <div className="auth-section-heading auth-session-heading"><div><strong>{t('已登入工作階段')}</strong><span>{t('撤銷不再使用的登入。')}</span></div><Button size="small" danger loading={loggingOutAll} onClick={() => void logoutAll()}>{t('登出全部')}</Button></div>
      <Table<IdentitySessionRecord> rowKey="id" size="small" dataSource={sessions} columns={columns} loading={busy} pagination={false} scroll={{ x: 570 }} locale={{ emptyText: t('沒有其他工作階段') }} />
      <Button className="auth-reload-sessions" size="small" onClick={() => void loadSessions()}>{t('重新整理工作階段')}</Button>
      <Button className="auth-drawer-signout" icon={<LogoutOutlined />} onClick={() => void onLogout()}>{t('登出此帳號')}</Button>
    </div>
  );
}

function AdminPanel() {
  const { t } = useI18n();
  const auth = useAuth();
  const [users, setUsers] = useState<IdentityUser[]>([]);
  const [usersBusy, setUsersBusy] = useState(true);
  const [usersError, setUsersError] = useState('');
  const { catalogs, reload: loadCatalogs } = usePermissionCatalogs();
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteBusy, setInviteBusy] = useState(false);
  const [inviteError, setInviteError] = useState('');
  const [inviteForm] = Form.useForm();
  useLocalizedForm(inviteForm);
  const [invitePermissions, setInvitePermissions] = useState<AuthPermissions>({});
  const [inviteCredential, setInviteCredential] = useState<{ code: string; expiresAt: string } | null>(null);
  const [credentialVisible, setCredentialVisible] = useState(false);
  const [credentialError, setCredentialError] = useState('');
  const [editingUser, setEditingUser] = useState<IdentityUser | null>(null);
  const [editPermissions, setEditPermissions] = useState<AuthPermissions>({});
  const [editName, setEditName] = useState('');
  const [editBusy, setEditBusy] = useState(false);
  const [editError, setEditError] = useState('');
  const [togglingUser, setTogglingUser] = useState('');
  const [messageApi, contextHolder] = message.useMessage();

  const loadUsers = useCallback(async () => {
    setUsersBusy(true);
    setUsersError('');
    try {
      const result = await authApi.users();
      setUsers(result.users);
    } catch (loadError) {
      setUsersError(errorText(loadError));
    } finally {
      setUsersBusy(false);
    }
  }, []);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  async function setUserActive(user: IdentityUser, active: boolean) {
    setTogglingUser(user.id);
    setUsersError('');
    try {
      const updated = await authApi.updateUser(user.id, { active });
      setUsers((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (updateError) {
      setUsersError(errorText(updateError));
    } finally {
      setTogglingUser('');
    }
  }

  async function createInvitation(values: { name: string; email: string; role: IdentityUser['role'] }) {
    setInviteBusy(true);
    setInviteError('');
    try {
      const invitation = await authApi.invite({ ...values, email: values.email.trim(), name: values.name.trim(), permissions: invitePermissions });
      setInviteCredential({ code: invitation.invitation_code, expiresAt: invitation.expires_at });
      setCredentialVisible(false);
      inviteForm.resetFields();
      setInvitePermissions({});
      setInviteOpen(false);
    } catch (creationError) {
      setInviteError(errorText(creationError));
    } finally {
      setInviteBusy(false);
    }
  }

  function openEdit(user: IdentityUser) {
    setEditingUser(user);
    setEditName(user.name);
    setEditPermissions(user.permissions ?? {});
    setEditError('');
  }

  async function saveUser() {
    if (!editingUser) return;
    setEditBusy(true);
    setEditError('');
    try {
      const permissionChanges = permissionsDiffer(editPermissions, editingUser.permissions ?? {});
      const updated = await authApi.updateUser(editingUser.id, { name: editName.trim(), ...(permissionChanges ? { permissions: editPermissions } : {}) });
      setUsers((current) => current.map((item) => item.id === updated.id ? updated : item));
      setEditingUser(null);
      messageApi.success(t('使用者設定已更新。'));
    } catch (saveError) {
      setEditError(errorText(saveError));
    } finally {
      setEditBusy(false);
    }
  }

  const columns: ColumnsType<IdentityUser> = [
    { title: t('使用者'), key: 'user', render: (_value, user) => <div className="auth-user-cell"><strong>{user.name}</strong><span>{user.email}</span><span>{user.credential_type === 'sso' ? t('企業登入 · {{mode}}', { mode: t(user.permissions_source === 'scim' ? 'SCIM 群組管理' : user.permissions_source === 'sso' ? '群組管理' : '手動管理') }) : t('Ordivant 帳號登入')}</span></div> },
    { title: t('角色'), dataIndex: 'role', key: 'role', width: 84, render: (role: IdentityUser['role']) => <Tag color={role === 'admin' ? 'purple' : 'default'}>{t(role === 'admin' ? '管理員' : '成員')}</Tag> },
    { title: t('啟用'), dataIndex: 'active', key: 'active', width: 72, render: (active: boolean, user) => <Tooltip title={t(user.id === auth.session?.user.id ? '無法停用目前登入的帳號' : active ? '停用帳號' : '啟用帳號')}><Switch size="small" checked={active} disabled={user.id === auth.session?.user.id || togglingUser === user.id} loading={togglingUser === user.id} onChange={(value) => void setUserActive(user, value)} /></Tooltip> },
    { title: '', key: 'actions', width: 78, render: (_value, user) => <Button size="small" onClick={() => openEdit(user)}>{t('管理')}</Button> },
  ];

  const credentialDialog = inviteCredential;

  return (
    <div className="auth-settings-panel auth-admin-panel">
      {contextHolder}
      <div className="auth-section-heading"><div><strong>{t('使用者與邀請')}</strong><span>{t('邀請碼只顯示一次，過期後需重新簽發。')}</span></div><Button type="primary" size="small" onClick={() => { setInviteError(''); setInviteOpen(true); }}>{t('新增邀請')}</Button></div>
      {usersError && <Alert className="auth-drawer-alert" type="error" showIcon message={t('使用者清單或更新失敗')} description={t(usersError)} action={<Button size="small" onClick={() => void loadUsers()}>{t('重試')}</Button>} />}
      <Table<IdentityUser> rowKey="id" size="small" dataSource={users} columns={columns} loading={usersBusy} pagination={{ pageSize: 6, hideOnSinglePage: true }} scroll={{ x: 430 }} />
      <div className="auth-scope-refresh"><Text type="secondary">{t('產品資源目錄透過各產品 API 載入。離線產品的授權欄位會保留且暫時鎖定。')}</Text><Button size="small" onClick={() => void loadCatalogs()}>{t('重新載入資源')}</Button></div>

      <Modal title={t('邀請使用者')} open={inviteOpen} onCancel={() => setInviteOpen(false)} onOk={() => inviteForm.submit()} confirmLoading={inviteBusy} okText={t('建立邀請')} cancelText={t('取消')} width={700} destroyOnClose className="auth-permissions-modal">
        {inviteError && <Alert className="auth-drawer-alert" type="error" showIcon message={t(inviteError)} />}
        <Form form={inviteForm} layout="vertical" onFinish={(values) => void createInvitation(values)} initialValues={{ role: 'member' }}>
          <Form.Item name="name" label={t('姓名')} rules={[{ required: true, whitespace: true, message: t('請輸入姓名') }]}><Input maxLength={120} autoComplete="name" /></Form.Item>
          <Form.Item name="email" label={t('電子郵件')} rules={[{ required: true, type: 'email', message: t('請輸入有效的電子郵件') }]}><Input autoComplete="email" /></Form.Item>
          <Form.Item name="role" label={t('Suite 角色')} rules={[{ required: true }]}><Select options={[{ value: 'member', label: t('成員') }, { value: 'admin', label: t('管理員') }]} /></Form.Item>
        </Form>
        <PermissionEditor value={invitePermissions} catalogs={catalogs} onChange={setInvitePermissions} />
      </Modal>

      <Modal title={t('產品角色與資源')} open={Boolean(editingUser)} onCancel={() => setEditingUser(null)} onOk={() => void saveUser()} confirmLoading={editBusy} okText={t('儲存')} cancelText={t('取消')} width={700} destroyOnClose className="auth-permissions-modal">
        {editError && <Alert className="auth-drawer-alert" type="error" showIcon message={t(editError)} />}
        {editingUser?.credential_type === 'sso' && editingUser.permissions_source === 'sso' && <Alert className="auth-drawer-alert" type="warning" showIcon message={t('變更產品權限會改由 Ordivant 管理')} description={t('只有調整產品角色或資源範圍時，才會停止依企業群組同步權限；只修改姓名不會改變管理方式。')} />}
        <Form layout="vertical"><Form.Item label={t('顯示名稱')}><Input value={editName} maxLength={120} onChange={(event) => setEditName(event.target.value)} /></Form.Item></Form>
        {editingUser?.permissions_source === 'scim' ? <Alert type="info" message={t('此帳號的產品權限由 SCIM 群組管理，請至企業治理或身分服務調整。')} /> : <PermissionEditor value={editPermissions} catalogs={catalogs} onChange={setEditPermissions} />}
      </Modal>

      <Modal
        title={t('一次性邀請碼')}
        open={Boolean(credentialDialog)}
        closable={false}
        keyboard={false}
        maskClosable={false}
        className="auth-recovery-modal"
        footer={<Button type="primary" disabled={!credentialVisible} onClick={() => { setInviteCredential(null); setCredentialVisible(false); }}>{t('我已安全保存邀請碼')}</Button>}
      >
        <Paragraph>{t('請先顯示並安全交付給受邀者。關閉後，系統不會再次顯示此代碼。')}</Paragraph>
        <div className="auth-recovery-toolbar"><Text type="secondary">{t('有效期限：{{date}}', { date: credentialDialog ? dateText(credentialDialog.expiresAt) : '' })}</Text><Button size="small" onClick={() => setCredentialVisible((value) => !value)}>{t(credentialVisible ? '隱藏' : '顯示')}</Button></div>
        <div className={`auth-one-time-code${credentialVisible ? ' auth-one-time-code-visible' : ''}`}>{credentialVisible ? credentialDialog?.code : '********************'}</div>
        {credentialError && <Alert className="auth-drawer-alert" type="error" showIcon message={credentialError} />}
        <Button size="small" disabled={!credentialVisible} onClick={() => void (async () => {
          try { await navigator.clipboard.writeText(credentialDialog?.code ?? ''); setCredentialError(''); messageApi.success(t('邀請碼已複製。')); }
          catch { setCredentialError('無法使用剪貼簿，請解鎖顯示後手動複製。'); }
        })()}>{t('複製邀請碼')}</Button>
      </Modal>
    </div>
  );
}
