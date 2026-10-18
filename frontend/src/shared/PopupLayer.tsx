import { useLayoutEffect } from 'react';
import './PopupLayer.css';

type PopupRecord = {
  trigger: HTMLElement;
  host: HTMLDivElement;
  popup: HTMLElement | null;
  resizeObserver: ResizeObserver | null;
  hostObserver: MutationObserver | null;
  frame: number | null;
};

const supportedTriggers = [
  '.ant-select',
  '.ant-cascader',
  '.ant-cascader-picker',
  '.ant-tree-select',
  '.ant-picker',
  '.ant-dropdown-trigger',
  '.ant-dropdown-open',
  '.ant-popover-open',
  '.ant-popover-trigger',
  '.workspace-account-toggle', // Keep the account popup host stable when its open class changes.
].join(',');

const popupClassPrefixes = [
  'ant-select-dropdown',
  'ant-dropdown',
  'ant-cascader-dropdown',
  'ant-popover',
  'ant-picker-dropdown',
];

const records = new Map<HTMLElement, PopupRecord>();
let hostsByTrigger = new WeakMap<HTMLElement, HTMLDivElement>();
let lifecycleUsers = 0;
let bodyObserver: MutationObserver | null = null;

function findPopup(host: HTMLElement): HTMLElement | null {
  const candidates = [
    ...Array.from(host.children),
    ...Array.from(host.querySelectorAll<HTMLElement>('*')),
  ];
  for (const candidate of candidates) {
    if (!(candidate instanceof HTMLElement)) continue;
    const names = Array.from(candidate.classList);
    if (names.some((name) => name.endsWith('-popup'))) return candidate;
    if (names.some((name) => popupClassPrefixes.some((prefix) => name === prefix || name.startsWith(`${prefix}-`)))) {
      return candidate;
    }
  }
  return null;
}

function setPixelStyle(element: HTMLElement, property: string, value: number): void {
  const next = `${Math.max(0, value)}px`;
  if (element.style.getPropertyValue(property) !== next) {
    element.style.setProperty(property, next, 'important');
  }
}

function positionRecord(record: PopupRecord): void {
  if (!record.trigger.isConnected || !record.host.isConnected) {
    disposeRecord(record);
    return;
  }

  const popup = record.popup ?? findPopup(record.host);
  if (
    !popup ||
    !popup.isConnected ||
    popup.hidden ||
    Array.from(popup.classList).some((name) => name.endsWith('-hidden')) ||
    window.getComputedStyle(popup).display === 'none'
  ) {
    return;
  }

  const triggerRect = record.trigger.getBoundingClientRect();
  const viewportWidth = document.documentElement.clientWidth || window.innerWidth;
  const viewportHeight = document.documentElement.clientHeight || window.innerHeight;
  const edge = 8;
  const gap = 4;
  const maxWidth = Math.max(0, viewportWidth - edge * 2);
  setPixelStyle(popup, 'max-width', maxWidth);
  if (popup.classList.contains('workspace-account-popover')) {
    // Size the entire border box before measuring wrapped content and placement.
    setPixelStyle(popup, 'width', Math.min(triggerRect.width, maxWidth));
  }
  const popupRect = popup.getBoundingClientRect();
  const spaceBelow = Math.max(0, viewportHeight - triggerRect.bottom - gap - edge);
  const spaceAbove = Math.max(0, triggerRect.top - gap - edge);
  const naturalHeight = Math.max(popupRect.height, popup.scrollHeight, popup.offsetHeight);
  const openAbove = naturalHeight > spaceBelow && spaceAbove > spaceBelow;
  const availableHeight = Math.max(0, openAbove ? spaceAbove : spaceBelow);
  const popupHeight = Math.min(naturalHeight, availableHeight);
  const popupWidth = Math.min(Math.max(popupRect.width, popup.scrollWidth), Math.max(0, viewportWidth - edge * 2));

  const preferredLeft = triggerRect.left;
  const rightAlignedLeft = triggerRect.right - popupWidth;
  const left = Math.min(
    Math.max(edge, preferredLeft + popupWidth <= viewportWidth - edge ? preferredLeft : rightAlignedLeft),
    Math.max(edge, viewportWidth - popupWidth - edge),
  );
  const top = openAbove
    ? Math.max(edge, triggerRect.top - gap - popupHeight)
    : Math.min(triggerRect.bottom + gap, viewportHeight - edge - popupHeight);

  setPixelStyle(record.host, 'left', left);
  setPixelStyle(record.host, 'top', top);
  setPixelStyle(popup, 'max-height', availableHeight);
}

function schedulePosition(record: PopupRecord): void {
  if (record.frame !== null || !record.trigger.isConnected) return;
  record.frame = window.requestAnimationFrame(() => {
    record.frame = null;
    positionRecord(record);
  });
}

function syncPopup(record: PopupRecord): void {
  const popup = findPopup(record.host);
  if (popup !== record.popup) {
    if (record.popup) {
      record.popup.removeAttribute('data-ordivant-popup-root');
      record.resizeObserver?.unobserve(record.popup);
    }
    record.popup = popup;
    record.hostObserver?.disconnect();
    record.hostObserver?.observe(record.host, { childList: true });
    if (popup) {
      popup.dataset.ordivantPopupRoot = '';
      record.resizeObserver?.observe(popup);
      record.hostObserver?.observe(popup, { attributes: true, attributeFilter: ['class', 'hidden'] });
    }
  }
  if (popup) positionRecord(record);
}

function disposeRecord(record: PopupRecord): void {
  if (record.frame !== null) window.cancelAnimationFrame(record.frame);
  record.resizeObserver?.disconnect();
  record.hostObserver?.disconnect();
  record.host.remove();
  records.delete(record.trigger);
  hostsByTrigger.delete(record.trigger);
}

function observeRecord(record: PopupRecord): void {
  if (record.hostObserver || lifecycleUsers === 0) return;

  if (typeof ResizeObserver !== 'undefined') {
    record.resizeObserver = new ResizeObserver(() => schedulePosition(record));
    record.resizeObserver.observe(record.trigger);
  }

  record.hostObserver = new MutationObserver(() => syncPopup(record));
  record.hostObserver.observe(record.host, { childList: true });
  syncPopup(record);
}

function scheduleAll(): void {
  for (const record of records.values()) schedulePosition(record);
}

function startLifecycle(): () => void {
  lifecycleUsers += 1;
  if (lifecycleUsers === 1) {
    window.addEventListener('resize', scheduleAll);
    window.addEventListener('scroll', scheduleAll, true);
    window.visualViewport?.addEventListener('resize', scheduleAll);
    window.visualViewport?.addEventListener('scroll', scheduleAll);

    bodyObserver = new MutationObserver(() => {
      for (const record of records.values()) {
        if (!record.trigger.isConnected || !record.host.isConnected) disposeRecord(record);
      }
    });
    bodyObserver.observe(document.body, { childList: true, subtree: true });
    for (const record of records.values()) observeRecord(record);
  }

  return () => {
    lifecycleUsers = Math.max(0, lifecycleUsers - 1);
    if (lifecycleUsers !== 0) return;

    window.removeEventListener('resize', scheduleAll);
    window.removeEventListener('scroll', scheduleAll, true);
    window.visualViewport?.removeEventListener('resize', scheduleAll);
    window.visualViewport?.removeEventListener('scroll', scheduleAll);
    bodyObserver?.disconnect();
    bodyObserver = null;

    for (const record of [...records.values()]) disposeRecord(record);
    hostsByTrigger = new WeakMap();
  };
}

export function getPopupContainer(trigger?: HTMLElement): HTMLElement {
  const body = trigger?.ownerDocument.body ?? document.body;
  if (!trigger || !body || !trigger.isConnected) return body;

  const popoverTrigger = trigger.closest('.ant-popover-open, .ant-popover-trigger');
  const tooltipTrigger = trigger.closest('.ant-tooltip-open');
  if (tooltipTrigger && !popoverTrigger) return body;
  if (!trigger.closest(supportedTriggers)) return body;

  const existingHost = hostsByTrigger.get(trigger);
  if (existingHost?.isConnected) return existingHost;
  if (existingHost) hostsByTrigger.delete(trigger);

  const host = body.ownerDocument.createElement('div');
  host.className = 'ordivant-popup-host';
  host.dataset.ordivantPopupHost = '';
  body.appendChild(host);

  const record: PopupRecord = {
    trigger,
    host,
    popup: null,
    resizeObserver: null,
    hostObserver: null,
    frame: null,
  };
  records.set(trigger, record);
  hostsByTrigger.set(trigger, host);
  observeRecord(record);
  return host;
}

export function PopupLayer(): null {
  useLayoutEffect(() => startLifecycle(), []);
  return null;
}
