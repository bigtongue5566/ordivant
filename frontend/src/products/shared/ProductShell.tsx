import { useI18n } from '../../i18n';
import type { ReactNode } from 'react';
import { Typography } from 'antd';
import type { ProductPrincipal } from './types';
import { ProductSwitcher, type ProductKey } from './ProductSwitcher';
import { WorkspaceAccount } from './WorkspaceAccount';
import { SidebarNavigation } from './SidebarNavigation';
import { WorkspaceScope } from './WorkspaceScope';
import { TeamOutlined } from '@ant-design/icons';
import { useAuth } from '../../auth/AuthContext';
import { openOrganizationSettings } from '../../auth/settingsNavigation';
import '../../sidebar.css';

const { Text, Title } = Typography;

export type ProductNavItem = { key: string; label: string; icon: ReactNode; count?: number };

export function ProductShell({
  product,
  productLabel,
  principal,
  sectionLabel,
  navigation,
  activeSection,
  onSectionChange,
  mode,
  serviceStatus,
  headerExtra,
  title,
  eyebrow,
  actions,
  children,
}: {
  product: Exclude<ProductKey, 'work'>;
  productLabel: string;
  principal: ProductPrincipal;
  sectionLabel: string;
  navigation: ProductNavItem[];
  activeSection: string;
  onSectionChange: (key: string) => void;
  mode: string;
  serviceStatus: 'ok' | 'error' | 'checking';
  headerExtra?: ReactNode;
  title: string;
  eyebrow?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const { t } = useI18n();
  const auth = useAuth();
  const roles: Record<string,string> = { admin: '管理員', manager: '管理者', writer: '編輯者', reader: '讀者', member: '成員' };
  return (
    <div className={`app-shell product-shell product-${product}`}>
      <aside className="side-rail">
        <div className="side-brand"><span className="brand-mark">O</span><div><strong>Ordivant</strong><span>{t('團隊與 Agent 協作')}</span></div></div>
        <ProductSwitcher active={product} showLanguage={false} />
        {headerExtra && <WorkspaceScope kind={product === 'knowledge' ? 'space' : 'project'}>{headerExtra}</WorkspaceScope>}
        <SidebarNavigation groups={[
          { label: sectionLabel, items: navigation },
          ...(auth.session?.user.role === 'admin' ? [{ label: t('管理與設定'), items: [{ key: 'organization-settings', label: t('組織管理'), icon: <TeamOutlined />, onClick: openOrganizationSettings }] }] : []),
        ]} active={activeSection} onChange={onSectionChange} />
        <div className="rail-bottom">
          <WorkspaceAccount product={product} productLabel={productLabel} name={principal.name} role={principal.role} roleLabel={t(roles[principal.role] ?? principal.role)} serviceStatus={serviceStatus} />
        </div>
      </aside>
      <main className="main-pane">
        <header className="topbar product-topbar">
          <nav className="workspace-breadcrumb" aria-label={t('目前位置')}><span>{productLabel}</span>{eyebrow && <><span aria-hidden>/</span><strong title={eyebrow}>{eyebrow}</strong></>}</nav>
          <div className="topbar-right"><Text className={`product-mode${serviceStatus === 'error' ? ' product-mode-error' : ''}`}>{serviceStatus === 'error' ? t('離線') : mode === 'development' ? 'DEV' : mode === 'production' ? 'PROD' : 'API'}</Text></div>
        </header>
        <div className="workspace-content product-content">
          <div className="page-heading"><div>{eyebrow && <Text className="eyebrow">{eyebrow}</Text>}<Title level={2}>{title}</Title></div>{actions}</div>
          {children}
        </div>
      </main>
    </div>
  );
}
