import { useRef, useState } from 'react';
import { Button, message } from 'antd';
import { LockOutlined, UnlockOutlined } from '@ant-design/icons';
import { api, createIdempotencyKey } from '../api';
import { useI18n } from '../i18n';
import type { Agent } from '../types';

export function AgentAvailabilityAction({ agent, canManage, onUpdated }: {
  agent: Agent;
  canManage: boolean;
  onUpdated: (agent: Agent) => void;
}) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const retry = useRef<{ status: 'available' | 'disabled'; key: string } | null>(null);
  const [messages, context] = message.useMessage();
  const disabled = agent.status === 'disabled';

  async function update() {
    if (!canManage || agent.status === 'archived' || pending.current) return;
    const status = disabled ? 'available' : 'disabled';
    if (retry.current?.status !== status) retry.current = { status, key: createIdempotencyKey() };
    pending.current = true;
    setBusy(true);
    try {
      const updated = await api.setAgentAvailability(agent.id, status, retry.current.key);
      retry.current = null;
      messages.success(t(disabled ? '{{name}} 已重新啟用。' : '{{name}} 已停用。', { name: updated.name }));
      onUpdated(updated);
    } catch (error) {
      messages.error(error instanceof Error ? error.message : t('Agent 狀態更新失敗，請重試。'));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return <>
    {context}
    <Button size="small" icon={disabled ? <UnlockOutlined /> : <LockOutlined />} loading={busy}
      disabled={!canManage || busy || agent.status === 'archived'}
      aria-label={t(disabled ? '重新啟用 {{name}}' : '停用 {{name}}', { name: agent.name })}
      onClick={() => void update()}>{t(disabled ? '重新啟用' : '停用')}</Button>
  </>;
}
