import { t } from './index';

const messages: Record<string,string> = {
  "assignment_conflict": "每個負責角色只能選擇一位同事或 Agent。",
  "review_separation": "執行者與審查者必須是不同的身分。",
  "active_assignment": "請先交接或釋出任務，再變更負責者。",
  "dispatch_pending": "此任務已派發給 Agent，請先停止派發。",
  "human_work_has_no_lease": "真人工作不需要續期租約。",
  "human_assigned_task": "人員負責的任務不可派發給 Pi Agent。",
  "delegate_target_required": "委派需選擇一位有權限的同事或 Agent。",
  "stale_draft_revision": "共同草稿剛被更新，請重新同步後再發佈。",
  "stale_draft_base": "共同草稿的基底版本已變更，請重新同步。",
  "draft_has_unpublished_changes": "請先發佈共同草稿，再使用其他方式建立文件版本。",
  "empty_draft": "共同草稿正文不可為空白。",
  "invalid_draft_update": "共同編輯更新格式不正確。",
  "draft_update_too_large": "共同編輯更新或草稿超過允許大小。",
  "draft_state_too_large": "共同編輯更新或草稿超過允許大小。",
  "draft_document_too_large": "共同編輯更新或草稿超過允許大小。",
  "collaboration_capacity": "此文件的共同編輯連線已達上限，請稍後重試。",
  "collaboration_failed": "共同編輯更新暫時無法保存，請重新連線。",
  "rate_limited": "更新頻率超過上限，請稍後重試。",
  "request_id_conflict": "操作識別碼已用於不同的共同編輯內容。",
  "stale_pull_request_head": "PR head 已變更，請重新載入審查記錄。",
  "pull_request_closed": "PR 已關閉，無法再核准或要求變更。",
  "self_review_forbidden": "提案者不能審查自己的 PR。",
  "gitea_invalid_pull_request": "Gitea 回傳的 PR 資料不完整。",
  "unauthenticated": "登入已失效，請重新登入。",
  "forbidden": "你沒有執行此操作的權限。",
  "not_found": "找不到此資源，請重新整理清單。",
  "product_access_denied": "此帳號尚未取得此產品的使用權限。",
  "identity_user_inactive": "此帳號已停用。",
  "origin_not_allowed": "目前網站不在允許的來源清單中，請聯絡管理員。",
  "csrf_failed": "安全驗證已失效，請重新整理頁面。",
  "identity_unavailable": "帳號服務暫時無法連線，請稍後重試。",
  "identity_admin_required": "只有帳號管理員可以建立新的授權範圍。",
  "identity_binding_conflict": "帳號與本地身分的連結衝突，請聯絡管理員。",
  "identity_organization_required": "請先設定帳號服務對應的本地組織。",
  "identity_organization_missing": "帳號對應的本地組織不存在。",
  "identity_organization_conflict": "帳號服務的組織設定與既有連結不符。",
  "identity_cross_organization_scope": "授權範圍包含其他組織，無法套用。",
  "resource_conflict": "資料已存在或與其他請求衝突。",
  "conflict": "請求與既有資料衝突，請重新整理後確認。",
  "concurrent_update": "資料剛被其他人更新，請重新載入後重試。",
  "idempotency_conflict": "此操作識別碼已用於不同的請求內容。",
  "idempotency_key_required": "此操作缺少必要的 Idempotency-Key。",
  "invalid_idempotency_key": "操作識別碼的格式或長度不正確。",
  "workflow_exists": "此專案已有相同的 Workflow key。",
  "workflow_run_limit": "max_runs 不可低於已建立的排程執行次數。",
  "workflow_active": "此工作流程已有執行中的實例。",
  "workflow_step_not_ready": "此工作流程步驟尚未符合派發條件。",
  "agent_template_exists": "此 Agent 範本識別碼已存在。",
  "agent_model_config_invalid": "Agent 的模型設定無法使用，請更新設定。",
  "admitted_provider_unavailable": "此次派發選定的模型供應商已無法使用。",
  "provider_credential_unavailable": "無法解密模型供應商憑證，請聯絡管理員。",
  "model_key_unavailable": "模型設定的加密金鑰無法使用，請聯絡管理員。",
  "model_settings_revision_conflict": "模型設定已變更，請重新載入後再儲存。",
  "model_settings_revision_required": "更新模型設定時必須提供目前的版本。",
  "delivery_lease_invalid": "此派發的擁有權已變更，請重新整理。",
  "delivery_lease_expired": "此派發的租約已到期。",
  "delivery_token_invalid": "此派發的驗證憑證已失效。",
  "delivery_credential_unavailable": "此派發的 Agent 憑證已撤銷。",
  "agent_scope_invalid": "此次派發的 Agent 不屬於目前組織。",
  "execution_lease_lost": "執行租約已失效，無法恢復此 Run。",
  "run_completion_unsubmitted": "Run 必須包含已提交的成果與證據才能完成。",
  "run_sync_stale": "Run 同步版本已過期。",
  "run_sync_conflict": "相同 Run 同步版本的內容不一致。",
  "run_terminal": "此 Run 已結束，無法執行此操作。",
  "run_stopping": "此 Run 正在停止，請等待執行環境確認。",
  "run_mode_mismatch": "執行環境模式與派發設定不一致。",
  "run_not_retryable": "只有任務為待執行的失敗或中止 Run 才能重試。",
  "run_delivery_active": "此 Run 的派發尚未結束，請稍後再試。",
  "run_create_failed": "無法建立重試 Run，請稍後再試。",
  "run_control_conflict": "此 Run 的狀態已改變，無法套用目前操作。",
  "run_execution_mismatch": "此 Execution 不屬於選定的 Run。",
  "run_execution_changed": "此 Run 的執行擁有權已變更。",
  "dependency_cycle": "此依賴會造成循環或讓任務依賴自己。",
  "delegation_depth_exceeded": "子任務最多允許三層。",
  "agent_unavailable": "此 Agent 目前無法執行任務。",
  "task_not_ready": "此任務尚未就緒，或依賴尚未完成。",
  "dependencies_pending": "請先完成此任務的依賴。",
  "task_claimed": "此任務已被其他執行者領取。",
  "lease_invalid": "執行租約已失效或不屬於目前身分。",
  "lease_expired": "執行租約已到期。",
  "task_not_blocked": "只有受阻的任務可以解除阻礙。",
  "task_not_in_review": "此任務目前沒有待審核的成果。",
  "submission_missing": "找不到待審核的提交紀錄。",
  "dispatch_outstanding": "此任務已有尚未完成的派發。",
  "agent_busy": "此 Agent 正在執行其他工作。",
  "guarded_transition": "請使用對應的任務操作來變更此狀態。",
  "tool_redirect_rejected": "MCP 工具連線不允許重新導向。",
  "tool_connection_snapshot_invalid": "工具連線的專案授權範圍已變更。",
  "tool_probe_failed": "無法取得 MCP 工具清單，請檢查連線設定。",
  "invalid_vcs_reference": "版控來源、倉庫路徑或 PR/MR 編號無效。",
  "vcs_not_configured": "此專案尚未設定對應的版控連線。",
  "vcs_repository_scope": "此倉庫不在專案的版控授權範圍內。",
  "vcs_configuration_error": "版控連線設定無效，請聯絡管理員。",
  "vcs_upstream_error": "無法從上游版控服務取得證據，請稍後再試。",
  "vcs_pull_not_found": "上游版控服務找不到此 PR/MR。",
  "space_key_conflict": "此組織已有相同的知識空間識別碼。",
  "stale_version": "文件已有更新版本，請重新載入後再編輯。",
  "gitea_unavailable": "Gitea 暫時無法完成請求，請稍後再試。",
  "gitea_invalid_response": "Gitea 回傳的資料格式不正確。",
  "gitea_not_configured": "尚未設定 Gitea 連線，請聯絡管理員。",
  "reconciliation_required": "上游操作可能已完成，請重新整理確認，避免重複操作。",
  "invalid_branch": "分支名稱不是有效的 Git reference。",
  "pull_exists": "此來源與目標分支之間已有 Pull request。",
  "gitea_conflict": "上游操作發生衝突，請檢查倉庫目前狀態。",
  "operation_in_progress": "相同的上游操作仍在進行中，請稍後重新整理。",
  "repository_already_bound": "此倉庫已連結至另一個 Code 專案。",
  "branch_exists": "此分支已存在，無法由目前請求建立。",
  "file_sha_conflict": "檔案版本已變更，請重新載入後再提交。",
  "repository_exists": "Gitea 已有此倉庫，請改用連結既有倉庫。",
  "identity_configured": "請使用帳號登入，此環境已停用本地工作階段。",
  "local_session_disabled": "此環境已停用本地工作階段。",
  "loopback_required": "本地工作階段只能透過本機或授權代理使用。",
  "bootstrap_missing": "本地工作階段尚未初始化，請聯絡管理員。",
  "runtime_scope": "此憑證只能操作授權的執行環境控制。",
  "internal_error": "服務發生內部錯誤，請稍後重試。"
};

function describeError(payload: unknown, status: number, translate = t): { message: string; code?: string } {
  const detail = typeof payload === 'object' && payload !== null && 'detail' in payload ? (payload as { detail: unknown }).detail : null;
  if (Array.isArray(detail)) {
    const validation: Record<string,string> = { missing: '必填欄位未填寫', string_too_short: '輸入長度超出允許範圍', string_too_long: '輸入長度超出允許範圍', greater_than: '數值超出允許範圍', greater_than_equal: '數值超出允許範圍', less_than: '數值超出允許範圍', less_than_equal: '數值超出允許範圍', literal_error: '輸入值不是允許的選項', enum: '輸入值不是允許的選項' };
    return { message: detail.map((value: unknown) => {
      const item = typeof value === 'object' && value !== null ? value as { type?: string; loc?: unknown[] } : {};
      const field = Array.isArray(item.loc) ? item.loc.filter(value => typeof value === 'string' && !['body','query','path'].includes(value)).join('.') : '';
      const text = translate(validation[item.type ?? ''] ?? '輸入資料不符合格式，請檢查表單。');
      return field ? `${field}: ${text}` : text;
    }).join('; ') };
  }
  const code = typeof detail === 'object' && detail !== null && 'code' in detail && typeof detail.code === 'string' ? detail.code : undefined;
  if (code && messages[code]) return { message: translate(messages[code]), code };
  if (status === 401) return { message: translate(messages.unauthenticated), code };
  if (status === 403) return { message: translate(messages.forbidden), code };
  if (status === 404) return { message: translate(messages.not_found), code };
  if (status === 422) return { message: translate('輸入資料不符合格式，請檢查表單。'), code };
  if (status === 429) return { message: translate('請求次數過多，請稍後重試。'), code };
  if (status >= 500) return { message: translate(messages.internal_error), code };
  return { message: code ? translate('請求失敗（HTTP {{status}}，{{code}}）。', { status, code }) : translate('請求失敗（HTTP {{status}}）。', { status }), code };
}

export function describeApiError(payload: unknown, status: number): { message: string; code?: string; sourceMessage: string } {
  const result = describeError(payload, status);
  const source = describeError(payload, status, (text, values = {}) => { const source = typeof text === 'string' ? text : text.source; return source.replace(/\{\{(\w+)\}\}/g, (placeholder: string, key: string) => Object.hasOwn(values, key) ? String(values[key]) : placeholder); });
  const detail = typeof payload === 'object' && payload !== null && 'detail' in payload ? payload.detail : null;
  // Dynamic field paths and HTTP codes remain in Error.message/code for diagnostics;
  // persistent UI alerts keep a stable key that can be translated after a locale change.
  const sourceMessage = Array.isArray(detail) ? '輸入資料不符合格式，請檢查表單。'
    : (status < 500 && ![401,403,404,422,429].includes(status) && !(result.code && messages[result.code])) ? '請求未完成。' : source.message;
  return { ...result, sourceMessage };
}
