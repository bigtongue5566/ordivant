import type { ReactNode } from 'react';
import { useI18n } from '../i18n';

export type SettingsSection = { key: string; label: string; description: string; icon: ReactNode; content: ReactNode };
export type SettingsGroup = { label: string; sections: SettingsSection[] };

export function AccountSettingsLayout({ groups, activeKey, onChange, identity, notice }: {
  groups: SettingsGroup[];
  activeKey: string;
  onChange: (key: string) => void;
  identity: ReactNode;
  notice?: ReactNode;
}) {
  const { t } = useI18n();
  const sections = groups.flatMap(group => group.sections);
  const selected = sections.find(section => section.key === activeKey) ?? sections[0];
  if (!selected) return null;

  return <div className="auth-settings-workspace">
    <aside className="auth-settings-sidebar">
      <div className="auth-settings-identity">{identity}</div>
      <nav className="auth-settings-navigation" aria-label={t('設定導覽')}>
        {groups.map(group => <div className="auth-settings-nav-group" key={group.label}>
          <p>{group.label}</p>
          {group.sections.map(section => <button
            key={section.key}
            type="button"
            className={`auth-settings-nav-item${selected.key === section.key ? ' auth-settings-nav-active' : ''}`}
            aria-current={selected.key === section.key ? 'page' : undefined}
            onClick={() => onChange(section.key)}
          ><span aria-hidden="true">{section.icon}</span><span>{section.label}</span></button>)}
        </div>)}
      </nav>
      <label className="auth-settings-mobile-navigation">
        <span>{t('設定導覽')}</span>
        <select value={selected.key} onChange={event => onChange(event.target.value)}>
          {groups.map(group => <optgroup key={group.label} label={group.label}>
            {group.sections.map(section => <option key={section.key} value={section.key}>{section.label}</option>)}
          </optgroup>)}
        </select>
      </label>
    </aside>
    <section className="auth-settings-main" aria-labelledby="account-settings-section-title">
      {notice}
      <header className="auth-settings-page-heading">
        <h2 id="account-settings-section-title">{selected.label}</h2>
        <p>{selected.description}</p>
      </header>
      <div key={selected.key} className="auth-settings-page-content">{selected.content}</div>
    </section>
  </div>;
}
