import type { ReactNode } from 'react';
import { useI18n } from '../../i18n';

export type SidebarItem = { key: string; label: string; icon: ReactNode; count?: number; onClick?: () => void };
export type SidebarGroup = { label: string; items: SidebarItem[] };

export function SidebarNavigation({ groups, active, onChange }: {
  groups: SidebarGroup[]; active: string; onChange: (key: string) => void;
}) {
  const { t } = useI18n();
  const available = groups.filter(group => group.items.length);
  const selectItem = (key: string) => {
    const item = available.flatMap(group => group.items).find(entry => entry.key === key);
    if (item?.onClick) item.onClick();
    else onChange(key);
  };
  return <div className="sidebar-navigation">
    <nav className="sidebar-navigation-desktop" aria-label={t('主要導覽')}>
      {available.map(group => <div className="sidebar-nav-group" key={group.label}>
        <div className="rail-label">{group.label}</div>
        <div className="rail-nav">{group.items.map(item => <button key={item.key} type="button"
          className={`nav-item${active === item.key ? ' nav-item-active' : ''}`}
          aria-current={active === item.key ? 'page' : undefined} onClick={() => selectItem(item.key)}>
          <span className="nav-item-icon" aria-hidden>{item.icon}</span><span className="nav-item-label">{item.label}</span>
          {!!item.count && item.count > 0 && <span className="nav-count">{item.count > 99 ? '99+' : item.count}</span>}
        </button>)}</div>
      </div>)}
    </nav>
    <label className="sidebar-navigation-mobile"><span>{t('前往頁面')}</span>
      <select aria-label={t('主要導覽')} value={active} onChange={event => { selectItem(event.target.value); event.target.value = active; }}>
        {available.map(group => <optgroup key={group.label} label={group.label}>{group.items.map(item =>
          <option key={item.key} value={item.key}>{item.label}{item.count ? ` (${item.count > 99 ? '99+' : item.count})` : ''}</option>
        )}</optgroup>)}
      </select>
    </label>
  </div>;
}
