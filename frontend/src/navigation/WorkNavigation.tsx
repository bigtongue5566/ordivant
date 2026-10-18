import { AppstoreOutlined, AuditOutlined, BranchesOutlined, InboxOutlined, PlayCircleOutlined, SettingOutlined, TeamOutlined, ToolOutlined, UnorderedListOutlined } from '@ant-design/icons';
import { SidebarNavigation } from '../products/shared/SidebarNavigation';
import { useI18n } from '../i18n';
import { openOrganizationSettings } from '../auth/settingsNavigation';

export type WorkSection = 'tasks' | 'planning' | 'runs' | 'automation' | 'tools' | 'overview' | 'agents' | 'inbox' | 'audit' | 'model-settings' | 'project-settings';

export function WorkNavigation({ active, onChange, isAdmin, unreadCount }: {
  active: WorkSection; onChange: (section: WorkSection) => void; isAdmin: boolean; unreadCount: number;
}) {
  const { t } = useI18n();
  return <SidebarNavigation active={active} onChange={key => onChange(key as WorkSection)} groups={[
    { label: t('專案工作'), items: [
      { key: 'overview', label: t('專案總覽'), icon: <AppstoreOutlined /> },
      { key: 'tasks', label: t('任務'), icon: <UnorderedListOutlined /> },
      { key: 'planning', label: t('規劃工作區'), icon: <AppstoreOutlined /> },
      { key: 'inbox', label: t('協作收件匣'), icon: <InboxOutlined />, count: unreadCount },
    ] },
    { label: t('Agent 與執行'), items: [
      { key: 'agents', label: t('Agent 名錄'), icon: <TeamOutlined /> },
      { key: 'runs', label: t('Run 執行'), icon: <PlayCircleOutlined /> },
      { key: 'automation', label: t('自動化'), icon: <BranchesOutlined /> },
    ] },
    { label: t('專案管理'), items: [
      { key: 'tools', label: t('工具與沙箱'), icon: <ToolOutlined /> },
      { key: 'audit', label: t('操作稽核'), icon: <AuditOutlined /> },
      { key: 'project-settings', label: t('專案設定'), icon: <SettingOutlined /> },
    ] },
    { label: t('組織管理'), items: [
      ...(isAdmin ? [{ key: 'model-settings', label: t('模型連線'), icon: <SettingOutlined /> }] : []),
      ...(isAdmin ? [{ key: 'organization-settings', label: t('組織管理'), icon: <TeamOutlined />, onClick: openOrganizationSettings }] : []),
    ] },
  ]} />;
}
