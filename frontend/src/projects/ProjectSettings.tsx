import { useEffect, useState } from 'react';
import { Alert, Button, Descriptions, Form, Input, InputNumber, Modal, Space, Switch, Table, Tabs, Tag } from 'antd';
import { api } from '../api';
import { authApi } from '../auth/client';
import { useAuth } from '../auth/AuthContext';
import { openOrganizationSettings } from '../auth/settingsNavigation';
import type { IdentityUser } from '../auth/types';
import type { Project, ProjectParticipant } from '../types';
import { useI18n, useLocalizedForm } from '../i18n';
import { useNavigationState } from '../shared/useNavigationState';
import { withProjectAccess } from './projectPermissions';
import './project-settings.css';

function errorText(error: unknown): string {
  return error instanceof Error && 'sourceMessage' in error ? String(error.sourceMessage) : error instanceof Error ? error.message : '請求失敗，請稍後重試。';
}
const snapshot = ({ name, description, budget_usd }: Project) => ({ name, description, budget_usd });

export function ProjectSettings({ project, participants, participantsBusy = false, canManage, onUpdated, onParticipantsChanged, onOpenAgents, onCreateCompanions }: {
  project: Project; participants: ProjectParticipant[]; participantsBusy?: boolean; canManage: boolean;
  onUpdated: (project: Project) => void; onParticipantsChanged: () => void;
  onOpenAgents: () => void; onCreateCompanions: () => void;
}) {
  const { t } = useI18n();
  const auth = useAuth();
  const isAdmin = auth.session?.user.role === 'admin';
  const [tab, setTab] = useNavigationState<string>('project-settings-tab', 'general', ['general', 'members', 'workspaces']);
  const [base, setBase] = useState(project);
  const [form] = Form.useForm();
  useLocalizedForm(form);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);

  async function reload() {
    setBusy(true); setError(''); setSaved(false);
    try {
      const latest = await api.get<Project>(`/api/projects/${encodeURIComponent(project.id)}`);
      setBase(latest); form.setFieldsValue(snapshot(latest)); onUpdated(latest);
    } catch (failure) { setError(errorText(failure)); }
    finally { setBusy(false); }
  }
  async function save(values: Pick<Project, 'name' | 'description' | 'budget_usd'>) {
    setBusy(true); setError(''); setSaved(false);
    try {
      const updated = await api.updateProject(project.id, { ...values, name: values.name.trim(), expected: snapshot(base) });
      setBase(updated); form.setFieldsValue(snapshot(updated)); onUpdated(updated); setSaved(true);
    } catch (failure) { setError(errorText(failure)); }
    finally { setBusy(false); }
  }
  return <div className="project-settings">
    <Tabs activeKey={tab} onChange={setTab} items={[
      { key: 'general', label: t('基本資料'), children: <section className="project-settings-general">
        {!canManage && <Alert type="info" showIcon message={t('只有此專案的管理者可修改基本資料。')} />}
        {error && <Alert type="error" showIcon message={t(error)} action={<Button disabled={busy} onClick={() => void reload()}>{t('重新載入設定')}</Button>} />}
        {saved && <Alert type="success" showIcon message={t('專案設定已儲存')} />}
        <Form form={form} layout="vertical" initialValues={snapshot(base)} onFinish={save} disabled={!canManage || busy} onValuesChange={() => setSaved(false)}>
          <Form.Item label={t('專案代碼')}><Input value={base.key} disabled /></Form.Item>
          <p className="project-settings-hint">{t('專案代碼用於任務識別，建立後不變更。')}</p>
          <Form.Item name="name" label={t('專案名稱')} rules={[{ required: true, whitespace: true, max: 200 }]}><Input maxLength={200} /></Form.Item>
          <Form.Item name="description" label={t('專案說明')} rules={[{ max: 20000 }]}><Input.TextArea rows={5} maxLength={20000} /></Form.Item>
          <Form.Item name="budget_usd" label={t('專案預算（USD）')} rules={[{ required: true, type: 'number', min: 0 }]}><InputNumber min={0} max={1e12} /></Form.Item>
          <p className="project-settings-hint">{t('預算為追蹤用途，不是模型費用的強制上限。')}</p>
          {canManage && <Button type="primary" htmlType="submit" loading={busy}>{t('儲存專案設定')}</Button>}
        </Form>
      </section> },
      { key: 'members', label: t('成員與權限'), children: <ProjectMembers projectId={project.id} participants={participants} participantsBusy={participantsBusy} isAdmin={isAdmin} onChanged={onParticipantsChanged} onOpenAgents={onOpenAgents} /> },
      { key: 'workspaces', label: t('相關工作區'), children: <section className="project-settings-general">
        <Alert type="info" showIcon message={t('三個模組分別管理資源與授權')} description={t('Work 專案、Knowledge 空間與 Code 專案是不同資源；同名不代表已連結或共用權限。')} />
        <Descriptions column={1} bordered size="small"><Descriptions.Item label={t('Work 專案')}>{base.key} · {base.name}</Descriptions.Item></Descriptions>
        <p>{t('可依需要建立對應的 Knowledge 空間與 Code 專案，並分別授予成員存取權。')}</p>
        {isAdmin && <Button onClick={onCreateCompanions}>{t('建立對應工作區')}</Button>}
      </section> },
    ]} />
  </div>;
}

function ProjectMembers({ projectId, participants, participantsBusy, isAdmin, onChanged, onOpenAgents }: {
  projectId: string; participants: ProjectParticipant[]; participantsBusy: boolean; isAdmin: boolean; onChanged: () => void; onOpenAgents: () => void;
}) {
  const { t } = useI18n();
  const [users, setUsers] = useState<IdentityUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState('');
  const [feedback, setFeedback] = useState('');
  const [modal, modalContext] = Modal.useModal();
  useEffect(() => {
    if (!isAdmin) return;
    let current = true;
    setLoading(true); setError('');
    authApi.users().then(result => { if (current) setUsers(result.users); })
      .catch(failure => { if (current) setError(errorText(failure)); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [isAdmin, revision]);

  async function changeAccess(user: IdentityUser, enabled: boolean) {
    const confirmed = await modal.confirm({
      title: t(enabled ? '授予此專案存取權？' : '移除此專案存取權？'),
      content: <><p>{user.name}</p><p>{t('權限變更會撤銷該成員目前的登入；其他產品與專案授權會保留。')}</p>
        {user.permissions_source === 'sso' && <p>{t('此操作會改由 Ordivant 管理此帳號的產品權限，停止企業群組權限同步。')}</p>}
        {!user.permissions.work && enabled && <p>{t('尚無 Work 角色的成員會以工作者身分加入。')}</p>}</>,
      okText: t('確認'), cancelText: t('取消'), okButtonProps: { danger: !enabled },
    });
    if (!confirmed) return;
    setSaving(user.id); setError(''); setFeedback('');
    try {
      const updated = await authApi.updateUser(user.id, { permissions: withProjectAccess(user.permissions, projectId, enabled), expected_permissions: user.permissions });
      setUsers(current => current.map(entry => entry.id === user.id ? updated : entry));
      setFeedback('專案存取權已更新'); onChanged();
    } catch (failure) { setError(errorText(failure)); }
    finally { setSaving(''); }
  }
  const roleLabel = (role: string) => t(({ admin: '管理員', manager: '管理者', worker: '工作者', reviewer: '審核者' } as Record<string, string>)[role] ?? '尚未授權');
  return <section className="project-settings-members">
    {modalContext}
    <Alert type="info" showIcon message={t('存取範圍依專案區分，Work 角色以產品為單位')} description={t('同一位成員在獲授權的 Work 專案使用相同角色。目前不支援各專案獨立角色或 Work 唯讀角色。')} />
    {error && <Alert type="error" showIcon message={t(error)} />}
    {feedback && <Alert type="success" showIcon message={t(feedback)} />}
    {isAdmin ? <>
      <div className="project-settings-toolbar"><span>{t('系統管理員可在此授予或移除此專案存取權。')}</span><Space wrap><Button disabled={Boolean(saving)} onClick={() => setRevision(value => value + 1)}>{t('重新載入成員')}</Button><Button onClick={openOrganizationSettings}>{t('管理組織成員')}</Button></Space></div>
      <Table<IdentityUser> rowKey="id" size="small" loading={loading} dataSource={users} pagination={{ pageSize: 10 }} scroll={{ x: 650 }} columns={[
        { title: t('成員'), key: 'member', render: (_, user) => <div><strong>{user.name}</strong><div>{user.email}</div>{!user.active && <Tag>{t('已停用')}</Tag>}{user.permissions_source === 'scim' && <Tag>{t('由 SCIM 群組同步')}</Tag>}</div> },
        { title: t('Work 角色'), key: 'role', render: (_, user) => roleLabel(user.role === 'admin' ? 'admin' : user.permissions.work?.role ?? '') },
        { title: t('此專案存取權'), key: 'access', width: 150, render: (_, user) => <Switch aria-label={t('{{name}} 的專案存取權', { name: user.name })} checked={user.role === 'admin' || Boolean(user.permissions.work?.scope_ids.includes(projectId))} loading={saving === user.id} disabled={loading || Boolean(saving) || user.role === 'admin' || user.permissions_source === 'scim'} onChange={enabled => void changeAccess(user, enabled)} /> },
      ]} />
      <p className="project-settings-hint">{t('管理員可存取組織內所有專案。SCIM 管理的成員須由佈建群組調整；變更 Work 角色請至組織管理。')}</p>
    </> : <>
      <p>{t('成員存取權由系統管理員或企業群組管理。')}</p>
      <Table rowKey="principal_id" size="small" loading={participantsBusy} dataSource={participants.filter(person => person.kind === 'human')} columns={[{ title: t('成員'), dataIndex: 'name' }, { title: t('Work 角色'), dataIndex: 'role', render: roleLabel }]} />
    </>}
    <h3>{t('專案 Agent')}</h3>
    <Table rowKey="principal_id" size="small" loading={participantsBusy} dataSource={participants.filter(person => person.kind === 'agent')} columns={[{ title: t('Agent'), dataIndex: 'name' }, { title: t('角色'), dataIndex: 'role', render: roleLabel }]} />
    <Button onClick={onOpenAgents}>{t('開啟此專案的 Agent 名錄')}</Button>
  </section>;
}
