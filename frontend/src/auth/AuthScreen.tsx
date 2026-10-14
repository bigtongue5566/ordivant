import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Form, Input, Spin, Typography } from 'antd';
import { LockOutlined, LoginOutlined, MailOutlined, UserOutlined } from '@ant-design/icons';
import { ProductSwitcher, type ProductKey as SwitcherProductKey } from '../products/shared/ProductSwitcher';
import { useI18n, useLocalizedForm } from '../i18n';
import { authApi } from './client';
import { useAuth } from './AuthContext';
import './auth.css';

const { Paragraph, Text, Title } = Typography;
type AuthProduct = SwitcherProductKey;
type AuthMode = 'login' | 'admin-login' | 'setup' | 'recover' | 'invite';

const callbackMessages: Record<string, string> = {
  invalid_state: '企業登入工作階段已失效，請重新開始登入。',
  configuration_changed: '企業登入設定在登入期間變更，請重新開始。',
  sso_error: '企業身分服務未完成登入，請重試或聯絡管理員。',
  sso_disabled: '企業登入目前未啟用。',
  account_link_required: '此企業帳號尚未與 Ordivant 帳號連結，請聯絡管理員。',
  invitation_required: '此企業帳號尚未獲邀使用 Ordivant，請聯絡管理員。',
  email_domain_not_allowed: '此企業電子郵件網域未列入允許清單。',
  email_unverified: '企業身分服務尚未確認此電子郵件。',
};

export function AuthScreen({ product, productName }: { product: AuthProduct; productName: string }) {
  const { t } = useI18n();
  const auth = useAuth();
  const [form] = Form.useForm();
  useLocalizedForm(form);
  const [mailLink] = useState(() => new URLSearchParams(window.location.hash.slice(1)));
  const [mode, setMode] = useState<AuthMode>(auth.phase === 'setup' ? 'setup' : mailLink.get('auth') === 'invite' ? 'invite' : mailLink.get('auth') === 'recover' ? 'recover' : 'login');
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');
  const [formNotice, setFormNotice] = useState('');
  const [invitationFromUrl] = useState(() => mailLink.get('auth') === 'invite' ? mailLink.get('code') ?? '' : new URLSearchParams(window.location.search).get('invite') ?? '');
  const [enterpriseLoginFromUrl] = useState(() => new URLSearchParams(window.location.search).get('enterprise_login') === '1');
  const autoSsoStarted = useRef(false);
  const ssoStartInProgress = useRef(false);

  useEffect(() => {
    if (!mailLink.get('auth')) return;
    form.setFieldsValue({ email: mailLink.get('email') ?? '', recovery_code: mailLink.get('auth') === 'recover' ? mailLink.get('code') ?? '' : '', invitation_code: invitationFromUrl });
    window.history.replaceState(null, '', window.location.pathname + window.location.search);
  }, [form, invitationFromUrl, mailLink]);

  async function requestRecoveryMail() {
    const email = form.getFieldValue('email');
    if (!email) { setFormError('請先輸入電子郵件，再索取復原郵件。'); return; }
    setBusy(true);
    setFormError(''); setFormNotice('');
    try {
      await authApi.requestRecovery(email);
      setFormNotice('若帳號符合復原條件且已設定郵件服務，系統會寄送一次性復原連結。');
    } catch (error) { setFormError(error instanceof Error ? error.message : '帳號請求失敗，請稍後重試。'); }
    finally { setBusy(false); }
  }

  useEffect(() => {
    if (auth.phase === 'setup') setMode('setup');
    else if (auth.phase === 'login' && mode === 'setup') setMode('login');
  }, [auth.phase, mode]);

  useEffect(() => {
    if (!invitationFromUrl) return;
    const url = new URL(window.location.href);
    url.searchParams.delete('invite');
    window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
  }, [invitationFromUrl]);

  useEffect(() => {
    const url = new URL(window.location.href);
    const code = url.searchParams.get('auth_error');
    if (!code) return;
    setFormError(callbackMessages[code] ?? '企業登入未完成，請重試或聯絡管理員。');
    url.searchParams.delete('auth_error');
    window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
  }, []);

  function changeMode(next: AuthMode) {
    form.resetFields();
    setFormError('');
    setFormNotice('');
    setMode(next);
  }

  async function beginSsoLogin() {
    form.resetFields(['password']);
    const sso = auth.sso;
    if (!sso?.enabled || !sso.configured) {
      setFormError('企業登入尚未完成設定，請聯絡系統管理員。');
      return;
    }
    if (sso.public_origin && window.location.origin !== sso.public_origin) {
      window.location.replace(`${sso.public_origin.replace(/\/$/, '')}/${product}?enterprise_login=1`);
      return;
    }
    if (ssoStartInProgress.current) return;
    ssoStartInProgress.current = true;
    setBusy(true);
    setFormError('');
    try {
      const result = await authApi.oidcStart({ return_to: `/${product}` });
      window.location.assign(result.authorization_url);
    } catch (error) {
      setFormError(error instanceof Error && 'sourceMessage' in error ? String((error as Error & { sourceMessage: string }).sourceMessage) : error instanceof Error ? error.message : '無法開始企業登入，請稍後重試。');
      ssoStartInProgress.current = false;
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!enterpriseLoginFromUrl || auth.phase === 'checking' || autoSsoStarted.current) return;
    const sso = auth.sso;
    if (sso?.public_origin && window.location.origin !== sso.public_origin) {
      window.location.replace(`${sso.public_origin.replace(/\/$/, '')}/${product}?enterprise_login=1`);
      return;
    }
    const url = new URL(window.location.href);
    url.searchParams.delete('enterprise_login');
    window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
    autoSsoStarted.current = true;
    if (!sso?.enabled || !sso.configured) {
      setFormError('企業登入尚未完成設定，請聯絡系統管理員。');
      return;
    }
    void beginSsoLogin();
  }, [auth.phase, auth.sso, enterpriseLoginFromUrl, product]);

  if (auth.phase === 'checking') {
    return <div className="auth-loading"><Spin size="large" /><Text>{t('正在檢查帳號服務')}</Text></div>;
  }

  async function submit(values: Record<string, string>) {
    setBusy(true);
    setFormError('');
    try {
      if (mode === 'setup' || mode === 'login' || mode === 'admin-login') {
        if (values.password !== values.confirm_password && mode === 'setup') {
          setFormError('兩次輸入的密碼不一致。');
          return;
        }
        if (mode === 'setup') await auth.setup({ name: values.name.trim(), email: values.email.trim(), password: values.password });
        else await auth.login({ email: values.email.trim(), password: values.password });
      } else if (mode === 'recover') {
        if (values.new_password !== values.confirm_password) {
          setFormError('兩次輸入的新密碼不一致。');
          return;
        }
        await auth.recover({ email: values.email.trim(), recovery_code: values.recovery_code.trim(), new_password: values.new_password });
      } else {
        if (values.password !== values.confirm_password) {
          setFormError('兩次輸入的密碼不一致。');
          return;
        }
        await auth.acceptInvitation({ invitation_code: values.invitation_code.trim(), password: values.password });
        window.history.replaceState(null, '', `${window.location.pathname}${window.location.hash}`);
      }
      form.resetFields();
    } catch (error) {
      const text = error instanceof Error && 'sourceMessage' in error ? String((error as Error & { sourceMessage: string }).sourceMessage) : error instanceof Error ? error.message : '帳號請求失敗，請稍後重試。';
      setFormError(text);
      if (mode === 'setup' && 'status' in (error as object) && (error as { status?: number }).status === 409) {
        setTimeout(() => { void auth.refresh(); setMode('login'); }, 0);
      }
    } finally {
      form.resetFields(['password', 'new_password', 'confirm_password', 'recovery_code', 'invitation_code']);
      setBusy(false);
    }
  }

  const showError = formError || (auth.phase === 'error' ? auth.error : '');
  const setupMode = mode === 'setup';
  const loginMode = mode === 'login' || mode === 'admin-login';
  const adminRecoveryMode = mode === 'admin-login';
  const ssoOnly = auth.sso?.enabled && auth.sso.login_policy === 'sso_only';
  const ssoOnlyDefaultMode = loginMode && ssoOnly && !adminRecoveryMode;
  const recoverMode = mode === 'recover';
  const inviteMode = mode === 'invite';

  return (
    <div className="auth-page">
      <main className="auth-panel">
        <div className="auth-brand-row">
          <span className="brand-mark">O</span>
          <div><strong>Ordivant</strong><span>{productName}</span></div>
        </div>
        <ProductSwitcher active={product} compact />
        <div className="auth-heading">
          <Text className="eyebrow">{productName.toUpperCase()}</Text>
          <Title level={2}>{t(setupMode ? '建立管理員帳號' : recoverMode ? '使用復原碼重設密碼' : inviteMode ? '接受帳號邀請' : ssoOnlyDefaultMode ? '企業帳號登入' : adminRecoveryMode ? '管理員密碼登入' : '登入 Ordivant')}</Title>
          <Paragraph>{t(setupMode ? '首次設定只會建立一位管理員，請使用你自己的密碼。' : recoverMode ? '輸入電子郵件與一組尚未使用的復原碼。' : inviteMode ? '設定密碼後即可使用邀請所授予的產品權限。' : ssoOnlyDefaultMode ? '使用 {{name}} 登入。' : adminRecoveryMode ? '此入口僅供 Ordivant 管理員在企業登入故障時使用。' : '使用你的 Ordivant 帳號繼續。', { name: auth.sso?.display_name || t('企業帳號') })}</Paragraph>
        </div>
        {auth.notice && <Alert className="auth-alert" type="warning" showIcon message={t(auth.notice)} />}
        {auth.phase === 'error' && <Alert className="auth-alert" type="error" showIcon message={t('帳號服務目前無法連線')} description={t(auth.error)} action={<Button size="small" onClick={() => void auth.refresh()}>{t('重試')}</Button>} />}
        {showError && auth.phase !== 'error' && <Alert className="auth-alert" type="error" showIcon message={t(showError)} />}
        {formNotice && <Alert className="auth-alert" type="success" showIcon message={t(formNotice)} />}
        <div className="auth-service-state"><span className={`health-dot ${auth.phase === 'error' ? 'health-bad' : 'health-good'}`} />{t(auth.phase === 'error' ? '帳號服務暫時無法連線' : setupMode ? '首次設定' : '帳號服務')}</div>
        <Form form={form} layout="vertical" onFinish={(values) => void submit(values as Record<string, string>)} requiredMark={false}>
          {setupMode && <Form.Item name="name" label={t('姓名')} rules={[{ required: true, whitespace: true, message: t('請輸入姓名') }]}><Input prefix={<UserOutlined />} autoComplete="name" maxLength={120} /></Form.Item>}
          {(loginMode && !ssoOnlyDefaultMode || setupMode || recoverMode) && <Form.Item name="email" label={t('電子郵件')} rules={[{ required: true, type: 'email', message: t('請輸入有效的電子郵件') }]}><Input prefix={<MailOutlined />} autoComplete="email" inputMode="email" /></Form.Item>}
          {inviteMode && <Form.Item name="invitation_code" label={t('邀請碼')} initialValue={invitationFromUrl} rules={[{ required: true, min: 32, message: t('請輸入完整邀請碼') }]}><Input.Password prefix={<LockOutlined />} autoComplete="off" /></Form.Item>}
          {recoverMode && <Form.Item name="recovery_code" label={t('一次性復原碼')} rules={[{ required: true, min: 12, message: t('請輸入完整復原碼') }]}><Input.Password prefix={<LockOutlined />} autoComplete="off" /></Form.Item>}
          {loginMode && !ssoOnlyDefaultMode && <Form.Item name="password" label={t(adminRecoveryMode ? '管理員密碼' : '密碼')} rules={[{ required: true, message: t('請輸入密碼') }]}><Input.Password prefix={<LockOutlined />} autoComplete="current-password" /></Form.Item>}
          {setupMode && <Form.Item name="password" label={t('設定密碼')} rules={[{ required: true, min: 12, message: t('密碼至少 12 個字元') }]}><Input.Password prefix={<LockOutlined />} autoComplete="new-password" /></Form.Item>}
          {recoverMode && <Form.Item name="new_password" label={t('新密碼')} rules={[{ required: true, min: 12, message: t('密碼至少 12 個字元') }]}><Input.Password prefix={<LockOutlined />} autoComplete="new-password" /></Form.Item>}
          {inviteMode && <Form.Item name="password" label={t('設定密碼')} rules={[{ required: true, min: 12, message: t('密碼至少 12 個字元') }]}><Input.Password prefix={<LockOutlined />} autoComplete="new-password" /></Form.Item>}
          {(setupMode || recoverMode || inviteMode) && <Form.Item name="confirm_password" label={t('再次輸入密碼')} rules={[{ required: true, message: t('請再次輸入密碼') }]}><Input.Password prefix={<LockOutlined />} autoComplete="new-password" /></Form.Item>}
          {!ssoOnlyDefaultMode && <Button htmlType="submit" type="primary" size="large" block loading={busy} disabled={auth.phase === 'error'}>
            {t(setupMode ? '建立管理員' : recoverMode ? '重設密碼並登入' : inviteMode ? '接受邀請並登入' : adminRecoveryMode ? '管理員登入' : '登入')}
          </Button>}
        </Form>
        {auth.sso?.enabled && auth.sso.configured && <div className="auth-enterprise-login"><Button type={ssoOnlyDefaultMode ? 'primary' : 'default'} size="large" block icon={<LoginOutlined />} loading={busy} onClick={() => void beginSsoLogin()}>{t('使用 {{name}} 登入', { name: auth.sso.display_name || t('企業帳號') })}</Button>{ssoOnly && adminRecoveryMode && <Text className="auth-admin-recovery-note">{t('此密碼入口僅供本機 Ordivant 管理員復原使用。')}</Text>}</div>}
        <div className="auth-mode-links">
          {(!ssoOnly || adminRecoveryMode) && !setupMode && <Button type="link" loading={busy} onClick={() => void requestRecoveryMail()}>{t('寄送密碼復原郵件')}</Button>}
          {auth.phase === 'setup' && mode !== 'setup' && <Button type="link" onClick={() => changeMode('setup')}>{t('首次管理員設定')}</Button>}
          {mode !== 'login' && auth.phase !== 'setup' && <Button type="link" onClick={() => changeMode('login')}>{t('返回登入')}</Button>}
          {ssoOnly && !adminRecoveryMode && loginMode && <Button type="link" onClick={() => changeMode('admin-login')}>{t('管理員密碼登入')}</Button>}
          {(!ssoOnly || adminRecoveryMode) && auth.phase !== 'setup' && !recoverMode && <Button type="link" onClick={() => changeMode('recover')}>{t('使用復原碼')}</Button>}
          {(!ssoOnly || adminRecoveryMode) && !inviteMode && <Button type="link" onClick={() => changeMode('invite')}>{t('接受邀請')}</Button>}
          {adminRecoveryMode && <Button type="link" onClick={() => changeMode('login')}>{t('返回企業登入')}</Button>}
        </div>
        <Text className="auth-footnote">{t('登入狀態由伺服器管理，登出後工作階段立即失效。')}</Text>
      </main>
    </div>
  );
}
