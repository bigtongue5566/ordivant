import type { ReactNode } from 'react';
import { FolderOpenOutlined } from '@ant-design/icons';
import { useI18n } from '../../i18n';

export function WorkspaceScope({ kind = 'project', children }: { kind?: 'project' | 'space'; children: ReactNode }) {
  const { t } = useI18n();
  const label = t(kind === 'space' ? '目前空間' : '目前專案');
  return <section className="workspace-scope" aria-label={label}>
    <div className="workspace-scope-caption"><FolderOpenOutlined aria-hidden /><span>{label}</span></div>
    <div className="workspace-scope-controls">{children}</div>
  </section>;
}
