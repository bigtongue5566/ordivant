import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Input, List, Select, Space, Switch, Typography } from 'antd';
import { DownloadOutlined, UploadOutlined } from '@ant-design/icons';
import { createProductApi, productApiPrefix } from './productApi';
import { authRequestOptions } from '../../auth/client';
import { getProductCredential } from './productCredentials';
import { useI18n, formatDate, formatNumber } from '../../i18n';
import type { ProductKey } from './ProductSwitcher';

export function collaborationPrefix(product: ProductKey) {
  return product === 'work' ? import.meta.env.VITE_WORK_API_PREFIX || '/api' : productApiPrefix(product);
}
type Attachment = { id: string; filename: string; size: number; sha256: string; actor_id: string; created_at: string };
type Participant = { id: string; name: string; kind: string };
type Discussion = { id: string; actor_id: string; body: string; created_at: string };

export function CollaborationPanel({ product, kind, resourceId, canWrite = false }: { product: ProductKey; kind: 'task' | 'document' | 'pull'; resourceId: string; canWrite?: boolean }) {
  const { t } = useI18n();
  const prefix = collaborationPrefix(product);
  const api = useMemo(() => createProductApi(prefix), [prefix]);
  const path = `/collaboration/${kind}/${resourceId}`;
  const [files, setFiles] = useState<Attachment[]>([]);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [discussions, setDiscussions] = useState<Discussion[]>([]);
  const [following, setFollowing] = useState(false);
  const [body, setBody] = useState('');
  const [mentions, setMentions] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function load() {
    const [attachments, people, subscription, history] = await Promise.all([
      api.get<Attachment[]>(`${path}/attachments`), api.get<Participant[]>(`${path}/participants`),
      api.get<{ subscribed: boolean }>(`${path}/subscription`), api.get<Discussion[]>(`${path}/discussion`),
    ]);
    setFiles(attachments); setParticipants(people); setFollowing(subscription.subscribed); setDiscussions(history);
  }
  useEffect(() => { setFiles([]); setDiscussions([]); setBody(''); setMentions([]); setError(''); void load().catch(err => setError(err.message)); }, [path, api]);
  async function perform(action: () => Promise<unknown>) {
    setBusy(true); setError('');
    try { await action(); await load(); window.dispatchEvent(new Event('ordivant-notifications-changed')); }
    catch (err) { setError(err instanceof Error ? err.message : t('請求失敗，請稍後重試。')); }
    finally { setBusy(false); }
  }
  async function upload(file: File) {
    if (file.size > 10 * 1024 * 1024 || file.size === 0) { setError(t('每個附件大小須介於 1 byte 與 10 MiB。')); return; }
    await perform(async () => {
      const encoded = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = reject; reader.readAsDataURL(file); });
      await api.post(`${path}/attachments`, { filename: file.name, content_base64: encoded });
    });
  }
  async function download(file: Attachment) {
    await perform(async () => {
      const credential = getProductCredential(prefix);
      const response = await fetch(`${prefix}/collaboration/attachments/${file.id}/download`, authRequestOptions({ headers: credential ? { Authorization: `Bearer ${credential}` } : {} }));
      if (!response.ok) throw new Error(t('附件下載失敗，請確認仍有此資源的存取權限。'));
      const url = URL.createObjectURL(await response.blob()); const link = document.createElement('a');
      link.href = url; link.download = file.filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
  return <Card size="small" title={t('附件與協作通知')} style={{ marginTop: 16 }} extra={<Space><Typography.Text>{t('追蹤更新')}</Typography.Text><Switch aria-label={t('追蹤更新')} checked={following} disabled={busy} onChange={value => void perform(() => api.post(`${path}/subscription`, { subscribed: value }))} /></Space>}>
    {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}
    <Typography.Paragraph type="secondary">{t('追蹤此資源可收到更新；提及同事或 Agent 時，通知會出現在他們的通知中心。')}</Typography.Paragraph>
    <List size="small" dataSource={files} locale={{ emptyText: t('尚無附件') }} renderItem={file => <List.Item actions={[<Button key="download" icon={<DownloadOutlined />} size="small" disabled={busy} onClick={() => void download(file)}>{t('下載')}</Button>]}><List.Item.Meta title={file.filename} description={`${formatNumber(file.size)} bytes · SHA-256 ${file.sha256.slice(0, 16)}…`} /></List.Item>} />
    {canWrite && <label style={{ display: 'inline-flex', cursor: busy ? 'wait' : 'pointer', marginBlock: 12 }}><UploadOutlined /><span style={{ marginInline: 8 }}>{t('上傳附件（每個最多 10 MiB）')}</span><input aria-label={t('上傳附件（每個最多 10 MiB）')} type="file" disabled={busy} onChange={event => { const file = event.target.files?.[0]; if (file) void upload(file); event.target.value = ''; }} style={{ maxWidth: 210 }} /></label>}
    <List size="small" dataSource={discussions} locale={{ emptyText: t('尚無協作留言') }} renderItem={item => <List.Item><List.Item.Meta title={`${participants.find(person => person.id === item.actor_id)?.name || t('成員')} · ${formatDate(item.created_at)}`} description={<span style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{item.body}</span>} /></List.Item>} />
    {canWrite && <Space direction="vertical" style={{ width: '100%' }}><Input.TextArea aria-label={t('協作留言')} value={body} onChange={e => setBody(e.target.value)} maxLength={8000} placeholder={t('輸入協作留言')} /><Select mode="multiple" aria-label={t('提及同事或 Agent')} value={mentions} onChange={setMentions} style={{ width: '100%' }} placeholder={t('提及同事或 Agent')} options={participants.map(person => ({ value: person.id, label: `${person.name}${person.kind === 'agent' ? ' · Agent' : ''}` }))} /><Button disabled={!body.trim()} loading={busy} onClick={() => void perform(async () => { await api.post(`${path}/discussion`, { body, mention_ids: mentions }); setBody(''); setMentions([]); })}>{t('傳送協作留言')}</Button></Space>}
  </Card>;
}
