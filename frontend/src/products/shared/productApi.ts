import { t } from '../../i18n';
import { describeApiError } from '../../i18n/errors';
import type { ProductHealth, ProductPrincipal } from './types';
import { announceAuthExpired, authRequestOptions } from '../../auth/client';
import { getProductCredential, setProductCredential } from './productCredentials';

export class ProductApiError extends Error {
  constructor(public status: number, message: string, public code?: string, public sourceMessage = message) {
    super(t(message));
    this.name = 'ProductApiError';
  }
}

function createRequestId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function createProductApi(prefix: string) {
  let token: string | null = null;

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    if (!headers.has('Content-Type') && init.body) headers.set('Content-Type', 'application/json');
    const credential = token || getProductCredential(prefix);
    if (credential) headers.set('Authorization', `Bearer ${credential}`);
    if (init.method && init.method !== 'GET' && !headers.has('Idempotency-Key')) headers.set('Idempotency-Key', createRequestId());

    let response: Response;
    try {
      response = await fetch(`${prefix}${path}`, authRequestOptions({ ...init, headers }));
    } catch {
      throw new ProductApiError(0, '無法連線至此產品 API，請確認該服務已啟動。');
    }

    if (response.status === 204) return undefined as T;
    const contentType = response.headers.get('content-type') ?? '';
    const payload = contentType.includes('application/json') ? await response.json() : await response.text();
    if (!response.ok) {
      const { message, code, sourceMessage } = describeApiError(payload, response.status);
      if (response.status === 401) {
        const usedBearerToken = Boolean(credential);
        token = null;
        setProductCredential(prefix, null);
        if (!usedBearerToken) announceAuthExpired();
      }
      throw new ProductApiError(response.status, message, code, sourceMessage);
    }
    return payload as T;
  }

  return {
    setToken(value: string | null) { token = value; setProductCredential(prefix, value); },
    get<T>(path: string) { return request<T>(path, { method: 'GET' }); },
    post<T>(path: string, body: unknown, options: { idempotencyKey?: string; signal?: AbortSignal } = {}) {
      return request<T>(path, {
        method: 'POST', body: JSON.stringify(body), signal: options.signal,
        headers: options.idempotencyKey ? { 'Idempotency-Key': options.idempotencyKey } : undefined,
      });
    },
    patch<T>(path: string, body: unknown) { return request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }); },
    me() { return request<ProductPrincipal>('/me', { method: 'GET' }); },
    health() { return request<ProductHealth>('/health', { method: 'GET' }); },
  };
}

export function productApiPrefix(product: 'knowledge' | 'code'): string {
  const isStandaloneBuild = import.meta.env.MODE === product;
  if (product === 'knowledge') {
    return import.meta.env.VITE_KNOWLEDGE_API_PREFIX || (isStandaloneBuild ? '/api' : '/knowledge-api');
  }
  return import.meta.env.VITE_CODE_API_PREFIX || (isStandaloneBuild ? '/api' : '/code-api');
}
