import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { authApi } from './client';
import { useAuth } from './AuthContext';
import type { PersonalAccessToken, ProductKey } from './types';
import { accessTokenExamples } from './accessTokenExamples';
import { productApiPrefix } from '../products/shared/productApi';
import { formatDate, useI18n, useLocalizedForm } from '../i18n';

function errorText(error: unknown) {
  return error instanceof Error && 'sourceMessage' in error ? String(error.sourceMessage)
    : error instanceof Error ? error.message : '請求失敗，請稍後重試。';
}

export function AccessTokensPanel({ product }: { product: ProductKey }) {
  const { t } = useI18n();
  const { session } = useAuth();
  const [tokens, setTokens] = useState<PersonalAccessToken[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [revoking, setRevoking] = useState('');
  const [error, setError] = useState('');
  const [issued, setIssued] = useState<{ token: string; access_token: PersonalAccessToken } | null>(null);
  const [exampleProduct, setExampleProduct] = useState(product);
  const inFlight = useRef(false);
  const [form] = Form.useForm();
  useLocalizedForm(form);
  const allowedProducts = (['work', 'knowledge', 'code'] as const).filter(key => session?.user.role === 'admin' || session?.user.permissions[key]);
  const standalone = ['work', 'knowledge', 'code'].includes(import.meta.env.MODE);
  const exampleProducts = standalone ? allowedProducts.filter(key => key === product) : allowedProducts;
  const prefixes = { work: import.meta.env.VITE_WORK_API_PREFIX || '/api', knowledge: productApiPrefix('knowledge'), code: productApiPrefix('code') };
  const endpoint = new URL(prefixes[exampleProduct], window.location.origin).href.replace(/\/$/, '');
  const examples = accessTokenExamples(exampleProduct, endpoint);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try { setTokens((await authApi.accessTokens()).tokens); }
    catch (err) { setError(errorText(err)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function create(values: { name: string; products: ProductKey[]; expires_in_days: number }) {
    if (inFlight.current) return;
    inFlight.current = true;
    setSaving(true);
    setError('');
    try {
      const result = await authApi.createAccessToken(values);
      setIssued(result);
      setTokens(current => [result.access_token, ...current]);
      form.resetFields();
    } catch (err) { setError(errorText(err)); }
    finally { inFlight.current = false; setSaving(false); }
  }
  async function revoke(id: string) {
    setRevoking(id);
    setError('');
    try {
      await authApi.revokeAccessToken(id);
      if (issued?.access_token.id === id) setIssued(null);
      await load();
    } catch (err) { setError(errorText(err)); }
    finally { setRevoking(''); }
  }
  const columns: ColumnsType<PersonalAccessToken> = [
    { title: t('名稱'), dataIndex: 'name', render: (name, token) => <><strong>{name}</strong><div><Typography.Text type="secondary">{token.prefix}…</Typography.Text></div></> },
    { title: t('產品'), dataIndex: 'products', render: (items: ProductKey[]) => items.map(item => <Tag key={item}>{item === 'work' ? 'Work' : item === 'knowledge' ? 'Knowledge' : 'Code'}</Tag>) },
    { title: t('到期時間'), dataIndex: 'expires_at', render: (value: string, token) => <>{formatDate(value)}<div>{token.revoked_at ? <Tag>{t('已撤銷')}</Tag> : Date.parse(value) <= Date.now() ? <Tag>{t('已到期')}</Tag> : <Tag color="green">{t('有效')}</Tag>}</div></> },
    { title: t('上次使用'), dataIndex: 'last_used_at', render: (value: string | null) => formatDate(value) },
    { title: '', key: 'action', render: (_, token) => <Popconfirm title={t('撤銷此權杖？使用它的 API 與 MCP 連線會立即失效。')} onConfirm={() => revoke(token.id)} okText={t('撤銷')} cancelText={t('取消')} disabled={Boolean(token.revoked_at) || Boolean(revoking)}>
      <Button size="small" danger disabled={Boolean(token.revoked_at) || Boolean(revoking)} loading={revoking === token.id}>{t('撤銷')}</Button>
    </Popconfirm> },
  ];
  return <div className="auth-settings-panel">
    <Typography.Paragraph>{t('建立個人存取權杖，讓外部工具透過 API 或 MCP 以你的身分操作平台。')}</Typography.Paragraph>
    <Alert type="info" showIcon message={t('權杖沿用你在所選產品的目前權限，無法擴大可存取的資源。')} description={t('可隨時撤銷；帳號停用、權限調整與到期會立即影響後續請求。')} />
    {error && <Alert type="error" showIcon message={t(error)} />}
    <Form form={form} layout="vertical" initialValues={{ products: allowedProducts.includes(product) ? [product] : [], expires_in_days: 30 }} onFinish={values => void create(values)}>
      <Form.Item name="name" label={t('權杖名稱')} rules={[{ required: true, whitespace: true, message: t('請輸入權杖名稱') }]}><Input maxLength={100} autoComplete="off" placeholder={t('例如本機 MCP 或自動化腳本')} /></Form.Item>
      <Form.Item name="products" label={t('允許的產品')} rules={[{ required: true, type: 'array', min: 1, message: t('請至少選擇一個產品') }]}>
        <Select mode="multiple" options={allowedProducts.map(key => ({ value: key, label: key === 'work' ? 'Work' : key === 'knowledge' ? 'Knowledge' : 'Code' }))} />
      </Form.Item>
      <Form.Item name="expires_in_days" label={t('有效期限')}><Select options={[{ value: 7, label: t('7 天') }, { value: 30, label: t('30 天') }, { value: 90, label: t('90 天') }, { value: 365, label: t('365 天') }]} /></Form.Item>
      <Button type="primary" htmlType="submit" loading={saving} disabled={allowedProducts.length === 0}>{t('建立存取權杖')}</Button>
    </Form>
    <Space><Typography.Title level={5}>{t('我的存取權杖')}</Typography.Title><Button size="small" onClick={() => void load()} loading={loading}>{t('重新整理')}</Button></Space>
    <Table rowKey="id" size="small" loading={loading} dataSource={tokens} columns={columns} scroll={{ x: 620 }} pagination={{ pageSize: 5 }} />
    <Typography.Title level={5}>{t('連線範例')}</Typography.Title>
    <Select aria-label={t('連線範例的產品')} value={exampleProduct} onChange={setExampleProduct} options={exampleProducts.map(key => ({ value: key, label: key === 'work' ? 'Work' : key === 'knowledge' ? 'Knowledge' : 'Code' }))} />
    <Typography.Paragraph type="secondary">{t('將範例中的 PERSONAL_ACCESS_TOKEN 換成你的權杖；MCP 設定另須將 ORDIVANT_REPO 換成本機原始碼目錄。')}</Typography.Paragraph>
    <Typography.Text strong>API</Typography.Text><pre className="access-token-example">{examples.api}</pre>
    <Typography.Text strong>MCP (stdio)</Typography.Text><pre className="access-token-example">{examples.mcp}</pre>
    <Modal title={t('存取權杖只顯示這一次')} open={Boolean(issued)} onCancel={() => setIssued(null)} footer={<Button type="primary" onClick={() => setIssued(null)}>{t('已保存，關閉')}</Button>} destroyOnClose>
      <Typography.Paragraph>{t('請現在複製並安全保存。關閉後無法再次查看完整權杖；遺失時請撤銷並重新建立。')}</Typography.Paragraph>
      {issued && <Input.Password readOnly value={issued.token} autoComplete="off" aria-label={t('新建存取權杖')} />}
      <Button onClick={() => { if (issued) void navigator.clipboard.writeText(issued.token).catch(() => setError('無法複製，請手動選取權杖。')); }}>{t('複製權杖')}</Button>
    </Modal>
  </div>;
}
