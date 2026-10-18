import { useEffect, useId, useRef, useState } from 'react';
import { Avatar, Popover } from 'antd';
import { MoreOutlined } from '@ant-design/icons';
import { AccountControl } from '../../auth/AccountSettings';
import { LanguageSelect } from '../../i18n/LanguageSelect';
import { useI18n } from '../../i18n';
import { getPopupContainer } from '../../shared/PopupLayer';
import type { ProductKey } from './ProductSwitcher';

export function WorkspaceAccount({ product, productLabel, name, role, roleLabel, serviceStatus }: {
  product: ProductKey; productLabel: string; name: string; role: string; roleLabel: string;
  serviceStatus: 'ok' | 'error' | 'checking';
}) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const controlsId = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const statusLabel = serviceStatus === 'ok' ? t('{{product}} API 已連線', { product: productLabel })
    : serviceStatus === 'error' ? t('{{product}} API 無法連線', { product: productLabel }) : t('檢查服務中');
  useEffect(() => {
    if (!expanded) return;
    const timer = window.setTimeout(() => document.getElementById(controlsId)?.querySelector<HTMLButtonElement>('button')?.focus(), 0);
    const dismiss = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented) return;
      setExpanded(false);
      trigger.current?.focus();
    };
    document.addEventListener('keydown', dismiss);
    return () => { window.clearTimeout(timer); document.removeEventListener('keydown', dismiss); };
  }, [expanded, controlsId]);
  return <div className="workspace-account">
    <AccountControl product={product} productLabel={productLabel} displayName={name} businessRole={role} variant="sidebar"
      onAction={() => setExpanded(false)} renderControls={controls => <Popover placement="topLeft" trigger="click" arrow={false}
        getPopupContainer={getPopupContainer}
        open={expanded} onOpenChange={setExpanded} classNames={{ root: 'workspace-account-popover' }} transitionName=""
        content={<div className="workspace-account-tools" id={controlsId} role="dialog" aria-label={t('帳號選單')}>
          {controls}<LanguageSelect />
        </div>}>
        <button ref={trigger} type="button" className="workspace-account-toggle" aria-label={`${name} · ${t('帳號選單')}`}
          aria-haspopup="dialog" aria-expanded={expanded} aria-controls={expanded ? controlsId : undefined}>
          <span className="workspace-account-avatar"><Avatar size={30}>{name.slice(0, 1).toUpperCase()}</Avatar>
            <span className={`health-dot ${serviceStatus === 'ok' ? 'health-good' : serviceStatus === 'error' ? 'health-bad' : ''}`}
              role="status" aria-label={statusLabel} title={statusLabel} />
          </span>
          <span className="workspace-user"><strong>{name}</strong><span>{roleLabel}</span></span><MoreOutlined aria-hidden />
        </button>
      </Popover>} />
  </div>;
}
