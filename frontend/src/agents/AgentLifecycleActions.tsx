import { useRef, useState } from 'react';
import { Button, Modal, Space, message } from 'antd';
import { api, createIdempotencyKey } from '../api';
import { useI18n } from '../i18n';
import type { Agent } from '../types';

type Operation = { kind: 'archive' | 'delete'; key: string };

export function AgentLifecycleActions({ agent, canManage, onRetired }: {
  agent: Agent;
  canManage: boolean;
  onRetired: (agent: Agent, deleted: boolean) => void;
}) {
  const { t } = useI18n();
  const [operation, setOperation] = useState<Operation | null>(null);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const [messages, context] = message.useMessage();
  if (!canManage) return null;

  async function confirm() {
    if (!operation || pending.current) return;
    pending.current = true;
    setBusy(true);
    try {
      if (operation.kind === 'archive') {
        const archived = await api.archiveAgent(agent.id, operation.key);
        messages.success(t('Agent 已封存，歷史紀錄仍保留。'));
        setOperation(null);
        onRetired(archived, false);
      } else {
        await api.deleteAgent(agent.id, operation.key);
        messages.success(t('Agent 已永久刪除。'));
        setOperation(null);
        onRetired(agent, true);
      }
    } catch (error) {
      messages.error(error instanceof Error ? error.message : t('Agent 操作未完成，請重試。'));
      // Keep the confirmation and the same key after an uncertain network result.
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return <>
    {context}
    <Space size="small">
      <Button size="small" disabled={busy || agent.status === 'archived'} aria-label={t('封存 {{name}}', { name: agent.name })} onClick={() => setOperation({ kind: 'archive', key: createIdempotencyKey() })}>{t('封存 Agent')}</Button>
      <Button size="small" danger disabled={busy} aria-label={t('永久刪除 {{name}}', { name: agent.name })} onClick={() => setOperation({ kind: 'delete', key: createIdempotencyKey() })}>{t('永久刪除 Agent')}</Button>
    </Space>
    <Modal open={operation !== null} destroyOnClose confirmLoading={busy} closable={!busy} maskClosable={!busy}
      title={operation?.kind === 'archive' ? t('封存 {{name}}？', { name: agent.name }) : t('永久刪除 {{name}}？', { name: agent.name })}
      okText={operation?.kind === 'archive' ? t('確認封存') : t('確認永久刪除')}
      okButtonProps={{ danger: operation?.kind === 'delete' }} cancelText={t('取消')} cancelButtonProps={{ disabled: busy }}
      onOk={() => void confirm()} onCancel={() => { if (!pending.current) setOperation(null); }}>
      <p>{operation?.kind === 'archive'
        ? t('封存會撤銷 Agent 憑證並從預設名錄隱藏，保留任務、成果與稽核紀錄。封存後無法再指派或執行工作。')
        : t('只有未使用且沒有任務、協作或設定引用的 Agent 可以永久刪除。刪除無法復原；已有紀錄時請改用封存。')}</p>
      <p>{t('若仍有未結束的任務、Run 或啟用中的自動化引用，請先停止執行、交接或停用相關設定。')}</p>
    </Modal>
  </>;
}
