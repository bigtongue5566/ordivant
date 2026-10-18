import type { IdentityAuditEvent, IdentityInvitation, IdentitySession, IdentitySessionRecord, IdentitySsoLink, IdentitySsoSettings, IdentitySsoSettingsWrite, IdentitySsoTestResult, IdentityStatus, IdentityUser } from './types';
import { t } from '../i18n';
import { describeApiError } from '../i18n/errors';
import type { PersonalAccessToken, ProductKey } from './types';

const authApiPrefix = import.meta.env.VITE_AUTH_API_PREFIX || '/auth-api';
const publicAuthPaths = new Set(['/status', '/me', '/setup', '/login', '/accept-invitation', '/recover', '/request-recovery']);
let csrfToken: string | null = null;

export class AuthApiError extends Error {
  constructor(public status: number, message: string, public code?: string, public sourceMessage = message) {
    super(message);
    this.name = 'AuthApiError';
  }
}

export function setAuthCsrfToken(value: string | null) {
  csrfToken = value;
}

export function authRequestOptions(init: RequestInit = {}): RequestInit {
  const headers = new Headers(init.headers);
  const method = (init.method ?? 'GET').toUpperCase();
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) headers.set('X-CSRF-Token', csrfToken);
  return { ...init, credentials: 'same-origin', headers };
}

export function announceAuthExpired() {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('ordivant-auth-expired'));
}

function describeError(payload: unknown, status: number): { message: string; code?: string } {
  const detail = typeof payload === 'object' && payload !== null && 'detail' in payload
    ? (payload as { detail: unknown }).detail
    : undefined;
  if (Array.isArray(detail)) {
    const validation = describeApiError(payload, status);
    return { message: validation.sourceMessage };
  }
  if (status >= 500) return { message: '帳號服務暫時無法連線，請稍後重試。' };
  if (status === 429) return { message: '嘗試次數過多，請稍後再試。' };
  if (typeof detail === 'object' && detail !== null) {
    const value = detail as { message?: unknown; code?: unknown };
    const code = typeof value.code === 'string' ? value.code : undefined;
    const translations: Record<string, string> = {
      scim_managed_user: '此外部帳號的權限由 SCIM 群組管理。',
      mail_not_retryable: '此郵件已寄出、已過期或目前無法重試。',
      invalid_mapping: '群組授權設定不正確，請指定確切的產品角色與資源。',
      invalid_cursor: '稽核查詢時間必須包含時區。',
      account_exists: '此電子郵件已經有帳號。',
      admin_required: '只有管理員可以管理使用者和邀請。',
      auth_throttled: '嘗試次數過多，請稍後再試。',
      csrf_invalid: '安全驗證已失效，請重新整理頁面後再試。',
      invalid_credentials: '電子郵件或密碼不正確，請再試一次。',
      invalid_current_password: '目前密碼不正確。',
      invalid_invitation: '邀請碼無效、已過期或已使用。',
      invalid_recovery: '復原碼無效、已使用或與此帳號不符。',
      account_link_required: '此企業帳號尚未與 Ordivant 帳號連結，請聯絡管理員。',
      client_secret_required: '更換簽發者或用戶端 ID 時，請重新輸入用戶端密鑰。',
      revision_conflict: 'SSO 設定已在另一個工作階段更新，請重新載入後再儲存。',
      sso_not_configured: '請先完成企業 SSO 必要設定，再啟用登入。',
      setup_required: '請先完成首次管理員設定，再啟用企業 SSO。',
      sso_disabled: '企業登入目前未啟用。',
      invitation_required: '此帳號尚未受邀使用 Ordivant，請聯絡管理員。',
      email_domain_not_allowed: '此電子郵件網域未列入允許清單。',
      email_unverified: '企業帳號的電子郵件尚未驗證。',
      sso_origin_mismatch: '請從系統指定的正式網址開始企業登入，頁面會自動切換。',
      last_admin: '此為最後一位管理員，無法停用帳號。',
      origin_not_allowed: '此登入頁面尚未列入服務允許來源，請聯絡系統管理員。',
      self_lockout: '無法停用目前登入的管理員帳號。',
      session_not_found: '找不到此登入工作階段，或它已被撤銷。',
      token_limit: '有效存取權杖已達上限，請先撤銷不再使用的權杖。',
      token_product_forbidden: '你或此權杖未獲授權使用所選產品。',
      access_token_not_found: '找不到此存取權杖。',
      setup_complete: '管理員帳號已建立，請使用帳號登入。',
      user_not_found: '找不到此使用者，清單可能已更新。',
      permissions_changed: '成員權限已由其他管理員更新，請重新載入後再儲存。',
    };
    return { message: (code && translations[code]) || (typeof value.message === 'string' ? value.message : `請求未完成（HTTP ${status}）。`), code };
  }
  if (typeof detail === 'string') return { message: detail };
  return { message: `請求未完成（HTTP ${status}）。` };
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  let response: Response;
  try {
    response = await fetch(`${authApiPrefix}${path}`, authRequestOptions({ ...init, headers, cache: 'no-store' }));
  } catch {
    const sourceMessage = '無法連線至帳號服務，請確認服務已啟動後重試。';
    throw new AuthApiError(0, t(sourceMessage), undefined, sourceMessage);
  }
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get('content-type') ?? '';
  const payload = contentType.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) {
    if (response.status === 401 && !publicAuthPaths.has(path)) announceAuthExpired();
    const error = describeError(payload, response.status);
    if (!error.code && response.status === 403) error.message = '此操作需要額外權限。';
    throw new AuthApiError(response.status, t(error.message), error.code, error.message);
  }
  return payload as T;
}

function post<T>(path: string, body: unknown) {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) });
}

export const authApi = {
  get: <T>(path: string) => request<T>(path),
  put: <T>(path: string, body: unknown) => request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  post: <T>(path: string, body: unknown) => post<T>(path, body),
  requestRecovery: (email: string) => post<{ accepted: boolean }>('/request-recovery', { email }),
  status: () => request<IdentityStatus>('/status'),
  me: () => request<IdentitySession>('/me'),
  setup: (body: { name: string; email: string; password: string }) => post<IdentitySession>('/setup', body),
  login: (body: { email: string; password: string }) => post<IdentitySession>('/login', body),
  acceptInvitation: (body: { invitation_code: string; password: string }) => post<IdentitySession>('/accept-invitation', body),
  recover: (body: { email: string; recovery_code: string; new_password: string }) => post<IdentitySession>('/recover', body),
  logout: () => post<void>('/logout', {}),
  logoutAll: () => post<void>('/logout-all', {}),
  changePassword: (body: { current_password: string; new_password: string }) => post<IdentitySession>('/change-password', body),
  sessions: () => request<{ sessions: IdentitySessionRecord[] }>('/sessions'),
  revokeSession: (id: string) => request<void>(`/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  accessTokens: () => request<{ tokens: PersonalAccessToken[] }>('/access-tokens'),
  createAccessToken: (body: { name: string; products: ProductKey[]; expires_in_days: number }) => post<{ token: string; access_token: PersonalAccessToken }>('/access-tokens', body),
  revokeAccessToken: (id: string) => request<void>(`/access-tokens/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  users: () => request<{ users: IdentityUser[] }>('/users'),
  invite: (body: { email: string; name: string; role: IdentityUser['role']; permissions: IdentityUser['permissions'] }) => post<IdentityInvitation>('/invitations', body),
  updateUser: (id: string, body: { active?: boolean; name?: string; permissions?: IdentityUser['permissions']; expected_permissions?: IdentityUser['permissions'] }) => request<IdentityUser>(`/users/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) }),
  oidcStart: (body: { return_to: '/work' | '/knowledge' | '/code' }) => post<{ authorization_url: string }>('/oidc/start', body),
  ssoSettings: () => request<IdentitySsoSettings>('/sso/settings'),
  updateSsoSettings: (body: IdentitySsoSettingsWrite) => request<IdentitySsoSettings>('/sso/settings', { method: 'PUT', body: JSON.stringify(body) }),
  testSso: () => post<IdentitySsoTestResult>('/sso/test', {}),
  ssoLinks: () => request<{ links: IdentitySsoLink[] }>('/sso/links'),
  createSsoLink: (body: { user_id: string; subject: string; managed_permissions?: boolean }) => post<IdentitySsoLink>('/sso/links', body),
  deleteSsoLink: (id: string) => request<void>(`/sso/links/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  identityAudit: (limit = 100) => request<{ events: IdentityAuditEvent[] }>(`/audit?limit=${encodeURIComponent(String(limit))}`),
};
