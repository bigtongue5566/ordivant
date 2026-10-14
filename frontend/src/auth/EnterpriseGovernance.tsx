import { useEffect, useState } from 'react';
import { Alert, Button, Form, Input, InputNumber, Popconfirm, Space, Table, Tag, Typography } from 'antd';
import { authApi, authRequestOptions } from './client';
import { PermissionEditor, usePermissionCatalogs } from './permissions';
import type { AuthPermissions } from './types';
import { useI18n, formatDate } from '../i18n';

type Policy = { audit_retention_days: number; scim_group_mappings: Record<string, AuthPermissions>; scim_enabled: boolean; mail_enabled: boolean; mail_transport_ready: boolean; scim_endpoint: string };
type Mail = { id: string; kind: string; recipient: string; status: string; attempts: number; created_at: string; last_error: string | null };

export function EnterpriseGovernance() {
  const { t } = useI18n();
  const [policy, setPolicy] = useState<Policy>();
  const [mails, setMails] = useState<Mail[]>([]);
  const [name, setName] = useState('');
  const [grants, setGrants] = useState<AuthPermissions>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const { catalogs } = usePermissionCatalogs();
  async function load() {
    try { const [value, queue] = await Promise.all([authApi.get<Policy>('/enterprise'), authApi.get<Mail[]>('/mail-outbox')]); setPolicy(value); setMails(queue); }
    catch (err) { setError(err instanceof Error ? err.message : t('請求失敗，請稍後重試。')); }
  }
  useEffect(() => { void load(); }, []);
  async function perform(fn: () => Promise<unknown>) {
    setBusy(true); setError('');
    try { await fn(); await load(); }
    catch (err) { setError(err instanceof Error ? err.message : t('請求失敗，請稍後重試。')); }
    finally { setBusy(false); }
  }
  async function save(mappings = policy?.scim_group_mappings) {
    if (!policy) return;
    await perform(() => authApi.put('/enterprise', { audit_retention_days: policy.audit_retention_days, scim_group_mappings: mappings }));
  }
  async function exportAudit() {
    await perform(async () => {
      const chunks: string[] = [];
      const params = new URLSearchParams({ limit: '1000' });
      const seenCursors = new Set<string>();
      let bytes = 0;
      let rows = 0;
      while (true) {
        const response = await fetch(`${import.meta.env.VITE_AUTH_API_PREFIX || '/auth-api'}/audit/export?${params}`, authRequestOptions({ signal: AbortSignal.timeout(15000) }));
        if (!response.ok) throw new Error(t('稽核匯出失敗，請重新登入後再試。'));
        const chunk = await response.text();
        bytes += new TextEncoder().encode(chunk).length;
        rows += chunk.split('\n').filter(Boolean).length;
        if (rows > 100000 || bytes > 50 * 1024 * 1024) throw new Error(t('稽核資料超出瀏覽器匯出上限，請使用 API 游標分頁匯出。'));
        chunks.push(chunk);
        const nextBefore = response.headers.get('X-Next-Before');
        const nextId = response.headers.get('X-Next-Before-Id');
        if (!nextBefore && !nextId) break;
        const cursor = `${nextBefore}:${nextId}`;
        if (!nextBefore || !nextId || seenCursors.has(cursor) || chunks.length >= 1000) throw new Error(t('稽核匯出失敗，請重新登入後再試。'));
        seenCursors.add(cursor);
        params.set('before', nextBefore);
        params.set('before_id', nextId);
      }
      const url = URL.createObjectURL(new Blob(chunks, { type: 'application/x-ndjson' })); const anchor = document.createElement('a');
      anchor.href = url; anchor.download = 'ordivant-identity-audit.jsonl'; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
  return <div className="auth-settings-panel">
    {error && <Alert type="error" showIcon message={error} />}
    {!policy ? <Button loading={!error} onClick={() => { setError(''); void load(); }}>{t('重新載入')}</Button> : <>
      <Typography.Title level={5}>{t('帳號佈建與郵件')}</Typography.Title>
      <Space wrap><Tag color={policy.scim_enabled ? 'green' : 'default'}>{t(policy.scim_enabled ? 'SCIM 已啟用' : 'SCIM 尚未啟用')}</Tag><Tag color={policy.mail_transport_ready ? 'green' : 'default'}>{t(policy.mail_transport_ready ? '郵件服務可用' : '郵件服務尚未設定')}</Tag></Space>
      <Typography.Paragraph type="secondary">{t('SCIM 帳號與群組使用專用佈建憑證；群組只取得明確指定的產品與資源權限。企業帳號的登入由身分服務負責。')}</Typography.Paragraph>
      <Typography.Text code>{policy.scim_endpoint}</Typography.Text>
      <Table size="small" rowKey="name" pagination={false} dataSource={Object.keys(policy.scim_group_mappings).map(name => ({ name }))} columns={[
        { title: t('企業群組'), dataIndex: 'name' },
        { title: t('操作'), render: (_, row) => <Space><Button size="small" onClick={() => { setName(row.name); setGrants(policy.scim_group_mappings[row.name]); }}>{t('編輯')}</Button><Button size="small" onClick={() => { const mappings = { ...policy.scim_group_mappings }; delete mappings[row.name]; void save(mappings); }}>{t('移除')}</Button></Space> },
      ]} />
      <Form layout="vertical"><Form.Item label={t('企業群組')}><Input value={name} onChange={e => setName(e.target.value)} maxLength={160} /></Form.Item>
        <PermissionEditor value={grants} onChange={setGrants} catalogs={catalogs} />
        <Button loading={busy} disabled={!name.trim()} onClick={() => void save({ ...policy.scim_group_mappings, [name.trim()]: grants })}>{t('儲存群組授權')}</Button>
        <Form.Item label={t('稽核保留天數')}><InputNumber min={30} max={3650} value={policy.audit_retention_days} onChange={value => value && setPolicy({ ...policy, audit_retention_days: value })} /></Form.Item>
      </Form>
      <Space wrap><Button loading={busy} onClick={() => void save()}>{t('儲存保留政策')}</Button><Button loading={busy} onClick={() => void exportAudit()}>{t('匯出稽核紀錄')}</Button><Popconfirm title={t('刪除超過保留期限的稽核紀錄？請先匯出保存。')} onConfirm={() => perform(() => authApi.post('/audit/retention', {}))}><Button danger>{t('套用保留期限')}</Button></Popconfirm></Space>
      <Typography.Paragraph type="secondary">{t('瀏覽器匯出最多 100,000 筆或 50 MiB；更多紀錄請使用 API 游標分頁。')}</Typography.Paragraph>
      <Typography.Title level={5}>{t('郵件寄送紀錄')}</Typography.Title>
      <Table size="small" rowKey="id" dataSource={mails} scroll={{ x: 500 }} columns={[
        { title: t('電子郵件'), dataIndex: 'recipient' }, { title: t('狀態'), render: (_, row) => t(({ pending: '待寄送', sending: '寄送中', sent: '已寄送', failed: '寄送失敗', expired: '已過期' } as Record<string, string>)[row.status] || row.status) },
        { title: t('建立時間'), render: (_, row) => formatDate(row.created_at) },
        { title: t('操作'), render: (_, row) => ['pending', 'failed'].includes(row.status) && <Button size="small" loading={busy} onClick={() => void perform(() => authApi.post(`/mail-outbox/${row.id}/retry`, {}))}>{t('重試寄送')}</Button> },
      ]} />
    </>}
  </div>;
}
