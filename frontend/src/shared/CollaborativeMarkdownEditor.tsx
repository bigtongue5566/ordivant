import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Avatar, Button, Segmented, Space, Spin, Tag, Tooltip } from 'antd';
import { CheckCircleOutlined, CloudSyncOutlined, ExclamationCircleOutlined, LockOutlined, SaveOutlined, WifiOutlined } from '@ant-design/icons';
import { markdown } from '@codemirror/lang-markdown';
import { EditorState, Compartment } from '@codemirror/state';
import { EditorView, highlightActiveLine, lineNumbers } from '@codemirror/view';
import * as Y from 'yjs';
import { Awareness } from 'y-protocols/awareness';
import { yCollab } from 'y-codemirror.next';
import { authRequestOptions } from '../auth/client';
import { MarkdownContent } from './MarkdownContent';
import { createProductApi, productApiPrefix } from '../products/shared/productApi';
import { useI18n } from '../i18n';
import './collaboration.css';

export type KnowledgeDraft = {
  document_id: string;
  base_version: number;
  revision: number;
  published_revision: number;
  title: string;
  body: string;
};

export type CollaborationConnection = 'loading' | 'connecting' | 'live' | 'reconnecting' | 'error' | 'permission_lost';

export type KnowledgeCollaborationState = {
  draft: KnowledgeDraft;
  connection: CollaborationConnection;
  pendingUpdates: number;
  permissionLost: boolean;
};

type DraftResponse = KnowledgeDraft & { update: string };
type Participant = { id: string; name: string; kind: 'human' | 'agent' };
type PendingUpdate = { update: Uint8Array; sent: boolean };
type DraftSession = { doc: Y.Doc; origin: object; draft: KnowledgeDraft | null; loaded: boolean; pending: Map<string, PendingUpdate> };
type SocketMessage = {
  type?: string;
  draft?: DraftResponse;
  participants?: Participant[];
  update?: string;
  request_id?: string;
  code?: string;
};

const knowledgeApi = createProductApi(productApiPrefix('knowledge'));
const sessions = new Map<string, DraftSession>();
const MAX_UPDATE_BYTES = 256 * 1024;
const UPDATE_BATCH_BYTES = 190 * 1024;
const MIN_UPDATE_INTERVAL = 1050;
let beforeUnloadInstalled = false;

function createId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function encodeBase64(value: Uint8Array): string {
  let binary = '';
  const chunkSize = 0x8000;
  for (let start = 0; start < value.length; start += chunkSize) {
    binary += String.fromCharCode(...value.subarray(start, start + chunkSize));
  }
  return btoa(binary);
}

function decodeBase64(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

function mergeDraft(session: DraftSession, incoming: DraftResponse, origin: unknown): KnowledgeDraft {
  if (incoming.update) Y.applyUpdate(session.doc, decodeBase64(incoming.update), origin);
  const previous = session.draft;
  const newest = previous && previous.revision > incoming.revision ? previous : incoming;
  const draft: KnowledgeDraft = {
    document_id: incoming.document_id,
    base_version: Math.max(previous?.base_version ?? 0, incoming.base_version),
    revision: Math.max(previous?.revision ?? 0, incoming.revision),
    published_revision: Math.max(previous?.published_revision ?? 0, incoming.published_revision),
    title: newest.title,
    body: session.doc.getText('body').toString(),
  };
  session.draft = draft;
  session.loaded = true;
  return draft;
}

function snapshotDraft(session: DraftSession): KnowledgeDraft | null {
  if (!session.draft) return null;
  const draft = { ...session.draft, body: session.doc.getText('body').toString() };
  session.draft = draft;
  return draft;
}

function websocketUrl(documentId: string): string {
  const prefix = productApiPrefix('knowledge').replace(/\/+$/, '');
  const url = new URL(`${prefix}/documents/${encodeURIComponent(documentId)}/collaborate`, window.location.href);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.username = '';
  url.password = '';
  url.search = '';
  url.hash = '';
  return url.toString();
}

function getSession(sessionId: string): DraftSession {
  const existing = sessions.get(sessionId);
  if (existing) return existing;
  const created: DraftSession = { doc: new Y.Doc(), origin: {}, draft: null, loaded: false, pending: new Map() };
  sessions.set(sessionId, created);
  return created;
}

function ensurePendingWarning() {
  if (beforeUnloadInstalled || typeof window === 'undefined') return;
  beforeUnloadInstalled = true;
  window.addEventListener('beforeunload', (event) => {
    if (![...sessions.values()].some((session) => session.pending.size > 0)) return;
    event.preventDefault();
    event.returnValue = '';
  });
}

function hasPermissionCode(code?: string): boolean {
  const normalized = (code ?? '').toLowerCase();
  return ['unauthorized', 'forbidden', 'permission', 'session', 'scope', 'csrf', 'auth'].some((part) => normalized.includes(part));
}

function participantInitial(name: string): string {
  return Array.from(name.trim())[0]?.toLocaleUpperCase() ?? '?';
}

export function CollaborativeMarkdownEditor({
  documentId,
  actorId,
  canEdit,
  refreshKey = 0,
  onStateChange,
}: {
  documentId: string;
  actorId: string;
  canEdit: boolean;
  refreshKey?: number;
  onStateChange?: (state: KnowledgeCollaborationState | null) => void;
}) {
  const { t } = useI18n();
  const mountRef = useRef<HTMLDivElement>(null);
  const canEditRef = useRef(canEdit);
  canEditRef.current = canEdit;
  const editabilityRef = useRef<(() => void) | null>(null);
  const reloadDraftRef = useRef<(() => void) | null>(null);
  const lastRefreshKey = useRef(refreshKey);
  const onStateChangeRef = useRef(onStateChange);
  onStateChangeRef.current = onStateChange;
  const permissionLostRef = useRef(false);
  const [connection, setConnection] = useState<CollaborationConnection>('loading');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [permissionLost, setPermissionLost] = useState(false);
  const [pendingUpdates, setPendingUpdates] = useState(0);
  const [draft, setDraft] = useState<KnowledgeDraft | null>(null);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [serverError, setServerError] = useState(false);
  const [retry, setRetry] = useState(0);
  const [pane, setPane] = useState<'edit' | 'preview'>('edit');

  const refreshView = useCallback((session: DraftSession) => {
    const currentDraft = snapshotDraft(session);
    setDraft(currentDraft);
    setPendingUpdates(session.pending.size);
  }, []);

  useEffect(() => {
    const sessionId = `${actorId}:${documentId}`;
    const session = getSession(sessionId);
    const ytext = session.doc.getText('body');
    const providerOrigin = session.origin;
    const editability = new Compartment();
    let stopped = false;
    let socket: WebSocket | null = null;
    let retryTimer = 0;
    let saveTimer = 0;
    let retryAttempt = 0;
    let lastSentAt = 0;
    let resendQueue: string[] = [];
    let connectedBefore = false;
    let authenticated = false;
    let synced = false;
    let editor: EditorView | null = null;
    let awareness: Awareness | null = null;

    permissionLostRef.current = false;
    setPermissionLost(false);
    setLoading(!session.loaded);
    setLoadError(false);
    setServerError(false);
    setParticipants([]);
    setConnection(session.loaded ? 'connecting' : 'loading');
    setDraft(snapshotDraft(session));
    setPendingUpdates(session.pending.size);
    ensurePendingWarning();

    const updateEditability = () => {
      const editable = canEditRef.current && !permissionLostRef.current;
      editor?.dispatch({
        effects: editability.reconfigure([
          EditorView.editable.of(editable),
          EditorState.readOnly.of(!editable),
        ]),
      });
    };
    editabilityRef.current = updateEditability;

    const createEditor = () => {
      if (!mountRef.current || editor) return;
      awareness = new Awareness(session.doc);
      editor = new EditorView({
        state: EditorState.create({
          doc: ytext.toString(),
          extensions: [
            lineNumbers(),
            highlightActiveLine(),
            markdown(),
            EditorView.lineWrapping,
            editability.of([
              EditorView.editable.of(canEditRef.current),
              EditorState.readOnly.of(!canEditRef.current),
            ]),
            yCollab(ytext, awareness),
          ],
        }),
        parent: mountRef.current,
      });
    };

    const markPermissionLost = () => {
      permissionLostRef.current = true;
      setPermissionLost(true);
      setConnection('permission_lost');
      updateEditability();
      if (socket && socket.readyState < WebSocket.CLOSING) socket.close();
    };

    const send = (message: object) => {
      if (!socket || socket.readyState !== WebSocket.OPEN || !synced) return false;
      try {
        socket.send(JSON.stringify(message));
        return true;
      } catch {
        return false;
      }
    };

    const scheduleNextUpdate = (debounce = false) => {
      if (saveTimer) window.clearTimeout(saveTimer);
      const untilAllowed = Math.max(0, MIN_UPDATE_INTERVAL - (Date.now() - lastSentAt));
      saveTimer = window.setTimeout(sendNextUpdate, Math.max(untilAllowed, debounce ? 800 : 0));
    };

    const sendNextUpdate = () => {
      if (!synced || !socket || socket.readyState !== WebSocket.OPEN) return;
      const wait = MIN_UPDATE_INTERVAL - (Date.now() - lastSentAt);
      if (lastSentAt > 0 && wait > 0) {
        saveTimer = window.setTimeout(sendNextUpdate, wait);
        return;
      }

      let requestId = resendQueue.shift();
      let item = requestId ? session.pending.get(requestId) : undefined;
      if (!item) {
        requestId = undefined;
        const queued: Array<[string, PendingUpdate]> = [];
        let size = 0;
        for (const entry of session.pending.entries()) {
          const pending = entry[1];
          if (pending.sent) continue;
          if (pending.update.length > MAX_UPDATE_BYTES) {
            setServerError(true);
            return;
          }
          if (queued.length > 0 && size + pending.update.length > UPDATE_BATCH_BYTES) break;
          queued.push(entry);
          size += pending.update.length;
        }
        if (queued.length === 0) return;
        const update = Y.mergeUpdates(queued.map(([, pending]) => pending.update));
        if (update.length > MAX_UPDATE_BYTES) {
          setServerError(true);
          return;
        }
        for (const [pendingId] of queued) session.pending.delete(pendingId);
        requestId = createId();
        item = { update, sent: true };
        session.pending.set(requestId, item);
      }

      if (!send({ type: 'update', update: encodeBase64(item.update), request_id: requestId })) {
        item.sent = false;
        if (requestId && resendQueue[0] !== requestId) resendQueue.unshift(requestId);
      } else {
        item.sent = true;
        lastSentAt = Date.now();
      }
      refreshView(session);
      if (resendQueue.length > 0 || [...session.pending.values()].some((pending) => !pending.sent)) {
        scheduleNextUpdate();
      }
    };

    const scheduleQueued = () => scheduleNextUpdate(true);

    const onDocumentUpdate = (update: Uint8Array, origin: unknown) => {
      if (origin === providerOrigin || permissionLostRef.current) return;
      session.pending.set(createId(), { update, sent: false });
      refreshView(session);
      scheduleQueued();
    };
    session.doc.on('update', onDocumentUpdate);

    const setRemoteParticipants = (items: unknown) => {
      if (!Array.isArray(items)) return;
      setParticipants(items.filter((item): item is Participant => (
        typeof item === 'object' && item !== null
        && typeof (item as Participant).id === 'string'
        && typeof (item as Participant).name === 'string'
        && ['human', 'agent'].includes((item as Participant).kind)
      )));
    };

    const connect = () => {
      if (stopped || permissionLostRef.current) return;
      setConnection(connectedBefore ? 'reconnecting' : 'connecting');
      authenticated = false;
      synced = false;
      resendQueue = [];
      try {
        socket = new WebSocket(websocketUrl(documentId));
      } catch {
        scheduleReconnect();
        return;
      }
      const activeSocket = socket;
      activeSocket.onopen = () => {
        if (stopped || activeSocket !== socket) return;
        const csrfToken = new Headers(authRequestOptions({ method: 'POST' }).headers).get('X-CSRF-Token');
        if (!csrfToken) {
          markPermissionLost();
          return;
        }
        authenticated = true;
        activeSocket.send(JSON.stringify({ type: 'authenticate', csrf_token: csrfToken }));
      };
      activeSocket.onmessage = (event) => {
        if (stopped || activeSocket !== socket || !authenticated) return;
        let message: SocketMessage;
        try {
          message = JSON.parse(String(event.data)) as SocketMessage;
        } catch {
          setServerError(true);
          return;
        }
        if (message.type === 'sync' && message.draft) {
          try {
            const nextDraft = mergeDraft(session, message.draft, providerOrigin);
            session.draft = { ...nextDraft, body: ytext.toString() };
            setDraft(session.draft);
            setPendingUpdates(session.pending.size);
            setRemoteParticipants(message.participants);
            setServerError(false);
            setConnection('live');
            if (!synced) {
              synced = true;
              connectedBefore = true;
              retryAttempt = 0;
              resendQueue = [...session.pending.entries()].filter(([, item]) => item.sent).map(([requestId]) => requestId);
              scheduleNextUpdate();
            }
          } catch {
            setServerError(true);
          }
          return;
        }
        if (message.type === 'presence') {
          setRemoteParticipants(message.participants);
          return;
        }
        if (message.type === 'update' && message.update) {
          try {
            Y.applyUpdate(session.doc, decodeBase64(message.update), providerOrigin);
            refreshView(session);
          } catch {
            setServerError(true);
          }
          return;
        }
        if (message.type === 'ack' && message.request_id) {
          if (!message.draft) {
            setServerError(true);
            return;
          }
          try {
            mergeDraft(session, message.draft, providerOrigin);
          } catch {
            setServerError(true);
            return;
          }
          session.pending.delete(message.request_id);
          refreshView(session);
          setServerError(false);
          return;
        }
        if (message.type === 'error') {
          if (hasPermissionCode(message.code)) markPermissionLost();
          else {
            setServerError(true);
            if (message.code === 'rate_limited' && message.request_id) {
              const rejected = session.pending.get(message.request_id);
              if (rejected) rejected.sent = false;
              if (saveTimer) window.clearTimeout(saveTimer);
              saveTimer = window.setTimeout(sendNextUpdate, 60_000);
            }
          }
        }
      };
      activeSocket.onerror = () => {
        if (!stopped && activeSocket === socket && !permissionLostRef.current) setConnection('reconnecting');
      };
      activeSocket.onclose = (event) => {
        if (stopped || activeSocket !== socket || permissionLostRef.current) return;
        authenticated = false;
        synced = false;
        if ([4001, 4003, 4401, 4403].includes(event.code)) {
          markPermissionLost();
          return;
        }
        scheduleReconnect();
      };
    };

    function scheduleReconnect() {
      if (stopped || permissionLostRef.current) return;
      setConnection(connectedBefore ? 'reconnecting' : 'connecting');
      const delay = Math.min(1000 * 2 ** retryAttempt, 15000);
      retryAttempt += 1;
      retryTimer = window.setTimeout(connect, delay);
    }

    const loadDraft = async () => {
      setLoading(!session.loaded);
      setLoadError(false);
      try {
        const response = await knowledgeApi.get<DraftResponse>(`/documents/${encodeURIComponent(documentId)}/draft`);
        if (stopped) return;
        const nextDraft = mergeDraft(session, response, providerOrigin);
        setDraft(nextDraft);
        setPendingUpdates(session.pending.size);
        setLoading(false);
        createEditor();
        if (!new Headers(authRequestOptions({ method: 'POST' }).headers).get('X-CSRF-Token')) {
          markPermissionLost();
          return;
        }
        if (!socket || socket.readyState > WebSocket.OPEN) connect();
      } catch (error) {
        if (stopped) return;
        setLoading(false);
        setLoadError(true);
        const status = error && typeof error === 'object' && 'status' in error ? Number((error as { status: unknown }).status) : 0;
        if (status === 401 || status === 403) markPermissionLost();
        else setConnection('error');
      }
    };
    reloadDraftRef.current = () => { void loadDraft(); };

    const csrfToken = new Headers(authRequestOptions({ method: 'POST' }).headers).get('X-CSRF-Token');
    if (!csrfToken) {
      markPermissionLost();
      setLoading(false);
      setLoadError(true);
    } else {
      void loadDraft();
    }

    return () => {
      stopped = true;
      if (retryTimer) window.clearTimeout(retryTimer);
      if (saveTimer) window.clearTimeout(saveTimer);
      socket?.close();
      session.doc.off('update', onDocumentUpdate);
      editor?.destroy();
      awareness?.destroy();
      if (editabilityRef.current === updateEditability) editabilityRef.current = null;
      if (reloadDraftRef.current) reloadDraftRef.current = null;
      if (session.pending.size === 0) {
        session.doc.destroy();
        sessions.delete(sessionId);
      }
    };
  }, [actorId, documentId, refreshView, retry]);

  useEffect(() => { editabilityRef.current?.(); }, [canEdit, permissionLost]);
  useEffect(() => {
    if (lastRefreshKey.current === refreshKey) return;
    lastRefreshKey.current = refreshKey;
    reloadDraftRef.current?.();
  }, [refreshKey]);
  useEffect(() => {
    if (!draft) {
      onStateChangeRef.current?.(null);
      return;
    }
    onStateChangeRef.current?.({ draft, connection, pendingUpdates, permissionLost });
  }, [connection, draft, pendingUpdates, permissionLost]);

  const hasUnsaved = pendingUpdates > 0;
  const connectionLabel: Record<CollaborationConnection, string> = {
    loading: '載入共同草稿',
    connecting: '建立連線',
    live: '已連線',
    reconnecting: '連線中斷，正在重新連線',
    error: '連線失敗',
    permission_lost: '編輯權限已失效',
  };
  const statusIcon = permissionLost
    ? <LockOutlined />
    : connection === 'live' && !hasUnsaved
      ? <CheckCircleOutlined />
      : connection === 'error' || serverError
        ? <ExclamationCircleOutlined />
        : connection === 'reconnecting'
          ? <CloudSyncOutlined />
          : <WifiOutlined />;

  return (
    <section className="collab-editor" aria-label={t('共同 Markdown 草稿')}>
      <div className="collab-toolbar">
        <Space wrap size={8} className="collab-status-group">
          <Tag className={`collab-connection collab-connection-${connection}`} icon={statusIcon}>{t(connectionLabel[connection])}</Tag>
          <Tag className={`collab-save-status${hasUnsaved || serverError ? ' collab-save-pending' : ' collab-save-ok'}`} icon={hasUnsaved || serverError ? <SaveOutlined /> : <CheckCircleOutlined />}>
            {hasUnsaved ? t('尚有 {{count}} 筆變更待保存', { count: pendingUpdates }) : serverError ? t('保存失敗，變更仍保留') : t('已保存')}
          </Tag>
          {!canEdit && <Tag>{t('唯讀')}</Tag>}
        </Space>
        <div className="collab-presence" aria-label={t('線上協作者')}>
          {participants.length > 0 ? (
            <Avatar.Group max={{ count: 5, style: { color: '#51456f', backgroundColor: '#ebe7f3' } }}>
              {participants.map((participant) => (
                <Tooltip key={participant.id} title={`${participant.name} · ${t(participant.kind === 'agent' ? 'Agent' : '真人')}`}>
                  <Avatar className={`collab-avatar collab-avatar-${participant.kind}`}>{participantInitial(participant.name)}</Avatar>
                </Tooltip>
              ))}
            </Avatar.Group>
          ) : <span>{t('目前沒有其他協作者線上')}</span>}
        </div>
        <Segmented
          aria-label={t('共同草稿檢視模式')}
          value={pane}
          onChange={(value) => setPane(value as 'edit' | 'preview')}
          options={[{ label: t('編輯'), value: 'edit' }, { label: t('預覽'), value: 'preview' }]}
        />
      </div>

      {permissionLost && <Alert className="collab-alert" type="error" showIcon message={t('目前帳號已無此文件的協作權限')} description={t('本機尚未確認的變更仍保留在此工作階段；請聯絡管理員恢復權限。')} action={<Button size="small" onClick={() => setRetry((value) => value + 1)}>{t('重試')}</Button>} />}
      {loadError && <Alert className="collab-alert" type="error" showIcon message={t('共同草稿無法載入')} description={t('確認 Knowledge 服務與文件權限後重試。')} action={<Button size="small" onClick={() => setRetry((value) => value + 1)}>{t('重試')}</Button>} />}
      {serverError && !permissionLost && <Alert className="collab-alert" type="warning" showIcon message={t('共同草稿尚未保存')} description={t('未確認的內容會保留，連線恢復後會再次同步。')} action={<Button size="small" onClick={() => setRetry((value) => value + 1)}>{t('重試')}</Button>} />}
      {loading && <div className="collab-loading"><Spin size="small" />{t('正在載入共同草稿')}</div>}

      <div className="collab-panel" hidden={pane !== 'edit' || loading || loadError}>
        <div className="collab-codemirror" ref={mountRef} />
      </div>
      <div className="collab-panel collab-preview" hidden={pane !== 'preview' || loading || loadError}>
        {draft?.body ? <MarkdownContent content={draft.body} /> : <p>{t('共同草稿尚無正文')}</p>}
      </div>
    </section>
  );
}
