import { useEffect, useState } from 'react';
import { Alert, Badge, Button, Drawer, Input, List, Space, Tabs, Tag, Typography } from 'antd';
import { BellOutlined, SearchOutlined } from '@ant-design/icons';
import { useAuth } from '../../auth/AuthContext';
import { authRequestOptions } from '../../auth/client';
import { useI18n, formatDate } from '../../i18n';
import type { ProductKey } from './ProductSwitcher';
import { collaborationPrefix } from './CollaborationPanel';
import { getProductCredential } from './productCredentials';

type Notice = { id: string; resource_kind: string; resource_id: string; title: string; actor_id: string | null; body: string; event: string; created_at: string; read: boolean; product: ProductKey };
type SearchResult = { id: string; title: string; excerpt: string; product: ProductKey; source: string; resource_kind?: string };

export function CollaborationCenter({ product, showLabels = false, onOpen }: { product: ProductKey; showLabels?: boolean; onOpen?: () => void }) {
  const { t } = useI18n();
  const auth = useAuth();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState('notifications');
  const [notices, setNotices] = useState<Notice[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState('');
  const standalone = ['work', 'knowledge', 'code'].includes(import.meta.env.MODE);
  const products = (standalone ? [product] : (['work', 'knowledge', 'code'] as ProductKey[])).filter(item => item === product || auth.session?.user.role === 'admin' || auth.session?.user.permissions[item]);
  async function request<T>(product: ProductKey, path: string, init: RequestInit = {}): Promise<T> {
    const prefix = collaborationPrefix(product);
    const credential = getProductCredential(prefix);
    const response = await fetch(`${prefix}${path}`, authRequestOptions({ ...init, signal: AbortSignal.timeout(10000), headers: { 'Content-Type': 'application/json', ...(credential ? { Authorization: `Bearer ${credential}` } : {}), ...(init.method ? { 'Idempotency-Key': crypto.randomUUID() } : {}) } }));
    if (!response.ok) throw new Error(t('{{product}} 暫時無法查詢（{{status}}）', { product, status: String(response.status) }));
    return response.json();
  }
  async function load(silent = false) {
    if (!silent) { setBusy(true); setErrors([]); }
    const settled = await Promise.allSettled(products.map(async product => (await request<Omit<Notice, 'product'>[]>(product, '/collaboration/notifications')).map(item => ({ ...item, product }))));
    setNotices(settled.flatMap(result => result.status === 'fulfilled' ? result.value : []));
    if (!silent) { setErrors(settled.flatMap(result => result.status === 'rejected' ? [String(result.reason.message)] : [])); setBusy(false); }
  }
  const productKey = products.join(',');
  useEffect(() => {
    const refresh = () => { if (!document.hidden) void load(true); };
    refresh();
    const timer = window.setInterval(refresh, 30000);
    window.addEventListener('ordivant-notifications-changed', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => { window.clearInterval(timer); window.removeEventListener('ordivant-notifications-changed', refresh); document.removeEventListener('visibilitychange', refresh); };
  }, [productKey, auth.session?.user.id]);
  async function search() {
    if (!query.trim()) return;
    setBusy(true); setErrors([]); setResults([]);
    const settled = await Promise.allSettled(products.map(async product => {
      const rows = await request<Array<{ id: string; title: string; excerpt?: string; snippet?: string; summary?: string; description?: string; source?: string; resource_kind?: string }>>(product,
        `${product === 'work' ? '/tasks' : product === 'knowledge' ? '/documents' : '/search'}?q=${encodeURIComponent(query.trim())}`);
      return rows.slice(0, 100).map(item => ({ id: item.id, title: item.title, excerpt: item.excerpt || item.snippet || item.summary || item.description || '', product, source: item.source || product, resource_kind: item.resource_kind }));
    }));
    setResults(settled.flatMap(result => result.status === 'fulfilled' ? result.value : []));
    setErrors(settled.flatMap(result => result.status === 'rejected' ? [String(result.reason.message)] : [])); setBusy(false);
  }
  function link(product: ProductKey, id: string, kind?: string) { return `/${product}?resource=${encodeURIComponent(id)}${kind ? `&kind=${encodeURIComponent(kind)}` : ''}`; }
  return <>
    <Badge count={notices.filter(item => !item.read).length} size="small"><Button type="text" size="small" aria-label={t('通知中心')} icon={<BellOutlined />} onClick={() => { setOpen(true); setTab('notifications'); void load(); onOpen?.(); }}>{showLabels && t('通知')}</Button></Badge>
    <Button type="text" size="small" aria-label={t('全域搜尋')} icon={<SearchOutlined />} onClick={() => { setOpen(true); setTab('search'); setErrors([]); onOpen?.(); }}>{showLabels && t('搜尋')}</Button>
    <Drawer width={620} title={t('協作中心')} open={open} onClose={() => setOpen(false)}>
      {errors.map(error => <Alert key={error} type="warning" showIcon message={error} style={{ marginBottom: 12 }} />)}
      <Tabs activeKey={tab} onChange={setTab} items={[
        { key: 'notifications', label: t('通知中心'), children: <><Button loading={busy} onClick={() => void load()}>{t('重新載入')}</Button><List loading={busy} dataSource={[...notices].sort((a,b) => b.created_at.localeCompare(a.created_at))} locale={{ emptyText: t('目前沒有可檢視的通知') }} renderItem={item => <List.Item actions={[!item.read && <Button key="read" size="small" onClick={() => void request(item.product, `/collaboration/notifications/${item.id}/read`, { method: 'POST' }).then(() => load()).catch(err => setErrors([err.message]))}>{t('標為已讀')}</Button>]}><List.Item.Meta title={<Space><Tag>{item.product}</Tag><a href={link(item.product, item.resource_id)}>{item.title}</a></Space>} description={<><Typography.Text type="secondary">{formatDate(item.created_at)} · {t(item.event.startsWith('discussion.') ? '協作留言' : item.event === 'attachment.created' ? '新增附件' : '資源已更新')}{item.actor_id === null ? ` · ${t('外部系統')}` : ''}</Typography.Text><div style={{ whiteSpace: 'pre-wrap' }}>{item.body}</div></>} /></List.Item>} /></> },
        { key: 'search', label: t('全域搜尋'), children: <><Input.Search aria-label={t('搜尋工作、文件與程式碼協作')} placeholder={t('搜尋工作、文件與程式碼協作')} value={query} onChange={event => setQuery(event.target.value)} onSearch={() => void search()} loading={busy} allowClear /><Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>{t('僅搜尋目前帳號可存取的內容。離線服務會個別列出，搜尋不需要 LLM。')}</Typography.Paragraph><List loading={busy} dataSource={results} locale={{ emptyText: t('輸入關鍵字以搜尋所有可用模組') }} renderItem={item => <List.Item><List.Item.Meta title={<Space><Tag>{item.product}</Tag><a href={link(item.product, item.id, item.resource_kind)}>{item.title}</a></Space>} description={item.excerpt.slice(0, 240)} /></List.Item>} /></> },
      ]} />
    </Drawer>
  </>;
}
