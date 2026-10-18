import { useRef, useState } from 'react';
import { Alert, Button, Checkbox, Modal, Space, Typography } from 'antd';
import type { Project } from '../types';
import { useI18n } from '../i18n';
import { companionKey, createProjectCompanions } from '../products/shared/projectCompanions';
import type { CompanionProduct, CompanionResults } from '../products/shared/projectCompanions';

export function ProjectCompanionsModal({ project, onClose }: { project: Project; onClose: () => void }) {
  const { t } = useI18n();
  const [selected, setSelected] = useState<CompanionProduct[]>(['knowledge', 'code']);
  const [results, setResults] = useState<CompanionResults>({});
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const pending = selected.filter(product => !results[product]?.resource);
  const attempted = Object.keys(results).length > 0;

  async function createSelected() {
    if (inFlight.current || pending.length === 0) return;
    inFlight.current = true;
    setBusy(true);
    try {
      setResults(await createProjectCompanions(project, pending, results));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return <Modal
    title={t('要一起建立 Knowledge 與 Code 嗎？')}
    open
    closable={!busy}
    maskClosable={!busy}
    keyboard={!busy}
    onCancel={() => { if (!busy) onClose(); }}
    footer={<Space>
      <Button disabled={busy} onClick={onClose}>{attempted ? t('完成') : t('略過')}</Button>
      <Button type="primary" loading={busy} disabled={pending.length === 0} onClick={() => void createSelected()}>
        {attempted ? t('重試未完成項目') : t('建立所選項目')}
      </Button>
    </Space>}
  >
    <Typography.Paragraph>{t('Work 專案「{{name}}」已建立。是否使用相同名稱與描述建立下列項目？', { name: project.name })}</Typography.Paragraph>
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {(['knowledge', 'code'] as const).map(product => <div key={product}>
        <Checkbox
          checked={selected.includes(product)}
          disabled={busy || Boolean(results[product]?.resource)}
          onChange={event => setSelected(current => event.target.checked ? [...current, product] : current.filter(item => item !== product))}
        >{product === 'knowledge' ? t('Knowledge 空間') : t('Code 專案')}</Checkbox>
        <div><Typography.Text type="secondary">{t('代碼：{{key}}', { key: companionKey(project, product) })}</Typography.Text></div>
        {results[product]?.resource && <Alert type="success" showIcon message={t('已建立 {{name}}', { name: results[product]!.resource!.name })}
          action={<a href={product === 'knowledge' ? '/knowledge' : '/code'} target="_blank" rel="noreferrer">{t('開啟')}</a>} />}
        {results[product]?.error && <Alert type="error" showIcon message={t('尚未確認此項目建立成功')} description={t(results[product]!.error!)} />}
      </div>)}
      <Typography.Text type="secondary">{t('Code 專案代碼會轉為小寫，並將底線改為連字號。')}</Typography.Text>
      <Typography.Text type="secondary">{t('可只選其中一項或略過；未完成的項目可重試，Work 專案仍可正常使用。')}</Typography.Text>
    </Space>
  </Modal>;
}
