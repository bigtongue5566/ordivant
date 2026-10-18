import type { AuthPermissions } from '../auth/types';

/** Change one Work grant while preserving other projects and product permissions. */
export function withProjectAccess(current: AuthPermissions, projectId: string, enabled: boolean): AuthPermissions {
  const work = current.work;
  if (!enabled && !work) return { ...current };
  const scopes = work?.scope_ids ?? [];
  return { ...current, work: { role: work?.role ?? 'worker', scope_ids: enabled ? [...new Set([...scopes, projectId])] : scopes.filter(id => id !== projectId) } };
}
