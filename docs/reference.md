<span id="架構與-api-索引"></span>
<span id="架构与-api-索引"></span>

# 架構與 API 索引 {#architecture-and-api-reference}

<span id="業務契約"></span>
<span id="业务契约"></span>

## 產品界線與整合規則 {#business-contracts}

Work、Knowledge、Code 可獨立部署，各自擁有業務 API、MCP、資料庫及授權範圍。Identity 提供共用帳號與登入；登入一次不代表自動取得每個產品或專案的權限。Runtime 執行 Work 派發的工作，沙箱執行器則負責隔離命令。所有業務授權仍由各產品的 Python 服務檢查。

| 服務 | 責任與界線 |
| --- | --- |
| Work | 專案、任務、相依性、租約、協作、審核與 Run；可直接引用既有企業 VCS，不需啟用 Code |
| Knowledge | 空間、文件、不可變版本、引用與決策；引用其他產品不會授予其存取權 |
| Code | 專案範圍內的 repository、branch、commit、PR 與狀態收據；Gitea 保存實際 Git 狀態 |
| Identity | 帳號、邀請、登入工作階段、產品授權與 OIDC SSO；使用獨立資料庫 |
| Runtime／沙箱 | 執行與逐字紀錄／隔離命令；不能取代 Work 的任務狀態與獨立審核 |

API 使用 UTF-8 JSON、字串 ID 與 UTC ISO-8601 時間。領域錯誤格式為 `{"detail":{"code":"...","message":"..."}}`；欄位驗證錯誤使用 FastAPI 格式。常見 HTTP 狀態為 `401` 未登入、`403` 無權限、`404` 不存在或不可存取、`409` 衝突、`422` 輸入不合法。

Agent 使用各產品限定範圍的 Bearer token；人類使用 Identity 的 Cookie 工作階段。Cookie 變更請求需遵循來源與 CSRF 檢查。操作者由憑證決定，不能在請求本文指定其他 `actor`。連接 Identity 的部署不提供舊的本機工作階段登入。

可重試的變更請使用 `Idempotency-Key`，並在重試時保持相同 key、路由及本文。相同操作者的相同請求會重播結果，變更本文會造成衝突；目前的授權仍會重新檢查。租約操作需提交目前有效的 fencing token，文件發布與檔案更新則需遵循 API 的版本檢查。完整欄位以實際部署的 OpenAPI 為準。

<span id="rest-文件"></span>
<span id="rest-文档"></span>

## REST 文件 {#rest-documentation}

原生開發模式啟動後，各 FastAPI 服務的 `/docs` 與 `/openapi.json` 提供目前版本的請求、回應及欄位結構。以下是預設設定；部署者可調整連接埠：

| 服務 | 開發 API 位址 | 套件網頁的代理前綴 |
| --- | --- | --- |
| Work | `http://127.0.0.1:8000/api` | `/api` |
| Knowledge | `http://127.0.0.1:8010/api` | `/knowledge-api` |
| Code | `http://127.0.0.1:8020/api` | `/code-api` |
| Identity | `http://127.0.0.1:8030/api/auth` | `/auth-api` |

下方業務端點使用服務本身的路徑。例如套件中 Knowledge 的 `GET /api/spaces` 經網頁來源呼叫時為 `GET /knowledge-api/spaces`。獨立產品模式的 `/api` 會指向選定產品。正式環境的 Nginx 只公開業務 API 前綴；請在受信任的開發環境查看結構描述，不要為此對外公開內部服務。

### Work 任務與執行 {#work-api}

| 端點 | 用途 |
| --- | --- |
| `GET/POST /api/projects`、`GET/POST /api/tasks` | 查詢及建立獲授權的專案／任務 |
| `GET /api/tasks/{task_id}/context` | 取得任務、相依性、訊息與證據脈絡 |
| `GET /api/projects/{project_id}/participants` | 列出可在該專案指派工作的已授權真人與 Agent |
| `POST /api/tasks/{task_id}/claim` | 真人以自己的登入身分認領未指派或指派給自己的任務；Agent 以 Bearer token 認領並取得租約 |
| `POST /api/tasks/{task_id}/renew` | 續期 Agent 租約；真人執行沒有租約 |
| `POST /api/tasks/{task_id}/progress`、`release` | 回報進度或釋出執行；真人不傳租約 token |
| `POST /api/tasks/{task_id}/submit`、`review` | 提交證據及由有權限的獨立審核者決定結果 |
| `POST /api/tasks/{task_id}/dispatch` | 派發 Agent 執行；取得 Run 後再追蹤執行狀態 |
| `GET /api/runs`、`GET /api/runs/{run_id}/events`、`POST /api/runs/{run_id}/control` | Run 清單、事件與控制 |
| `/api/agent-templates`、`/api/workflows`、`/api/workflow-runs` | Agent 範本、工作流程定義及工作流程執行 |
| `/api/tool-connections`、`/api/sandbox-profiles` | 管理獲允許的工具連線與沙箱設定 |

任務與 Run 是不同紀錄。執行成功不會自動使任務完成；仍需證據與獨立審核。執行模式、暫停／停止限制及工具設定見[執行指南](./execution-usage.md)。`/api/runtime/*` 是受限服務介面，不供一般 Agent 或瀏覽器呼叫。

真人認領會記錄真人執行者，不會建立 Agent 租約；重新載入可繼續進行中的工作。Agent 認領才使用到期時間與 fencing token。真人與 Agent 權限、指派及交接細節見[真人與 Agent 協作契約](./collaboration-contracts.md)。

### Knowledge 文件與版本 {#knowledge-api}

| 端點 | 用途 |
| --- | --- |
| `GET/POST /api/spaces` | 知識空間 |
| `GET /api/documents?space_id=&q=&tag=`、`POST /api/documents` | 搜尋及建立文件 |
| `GET /api/documents/{document_id}/versions` | 取得版本歷史 |
| `GET /api/documents/{document_id}/versions/{version_number}` | 讀取可引用的精確版本 |
| `POST /api/documents/{document_id}/versions` | 舊發布入口；網頁編輯器導引至共同草稿 |
| `GET /api/documents/{document_id}/draft`、`POST /api/documents/{document_id}/draft/updates` | 讀取共同草稿與送出 CRDT 更新 |
| `WS /api/documents/{document_id}/collaborate` | 以登入工作階段同步草稿及真人 presence |
| `POST /api/documents/{document_id}/draft/publish` | 將已保存的共同草稿發布為不可變版本 |
| `GET/POST /api/decisions`、`GET /api/events` | 決策及獲授權的稽核紀錄 |

已發布版本不可變更。只可發布仍在線、已保存且沒有待確認更新的草稿；未收到確認的離線編輯只保留在目前瀏覽器記憶體，關閉頁面可能遺失。Agent REST／MCP 可讀寫同一共同草稿。來源引用保留精確版本與 URI，不會擴大存取權。操作流程見[Knowledge 指南](./guide/knowledge.md)。

### Code 與版本控制 {#code-api}

| 端點 | 用途 |
| --- | --- |
| `GET/POST /api/projects`、`GET/POST /api/repositories` | 專案及綁定的 repository |
| `POST /api/repositories/{repository_id}/branches`、`files` | 建立分支及提交檔案 |
| `GET/POST /api/repositories/{repository_id}/pulls` | 查詢及建立 PR |
| `GET /api/repositories/{repository_id}/pulls/{number}` | PR 詳情、來源引用與狀態收據 |
| `GET /api/repositories/{repository_id}/pulls/{number}/collaboration` | Ordivant 討論、審查紀錄與目前 PR head |
| `POST /api/repositories/{repository_id}/pulls/{number}/comments` | 留下 Ordivant 本地 PR 討論 |
| `POST /api/repositories/{repository_id}/pulls/{number}/reviews` | 針對指定 head SHA 留下 Ordivant 審查 |
| `POST /api/repositories/{repository_id}/checks` | 回報明確標示為 Agent 自報的 commit 狀態 |

Code 的 Git 操作需設定 Gitea；Ordivant 討論與審查是本地紀錄，綁定 PR head SHA，不等同 Gitea 核准或 CI 結果。Gitea 負責 Git、合併及其自身的核准；此版本不提供 PR 合併或刪除 API，也不包含 CI runner。`agent_reported` 收據不能當成實際 CI 執行證據。詳見[Code 指南](./guide/code.md)與[真人與 Agent 協作契約](./collaboration-contracts.md)。

### 模型設定 {#model-settings}

`GET/PUT /api/model-settings` 限組織管理員使用；`GET /api/model-catalog` 提供已授權操作者可選的模型，均不回傳 API key。設定包含 `providers`、組織 `default` 與 `revision`。更新既有設定必須提交讀取到的 `revision`，以防覆蓋他人的修改。

Agent 的 `model_config` 可覆寫預設，設為 `null` 則繼承組織設定。選擇包含 `provider_id`、`model_id`、`reasoning_effort`、`max_output_tokens`；實際派發會保存不含秘密的設定快照。模型失敗不會切換成 DEMO。模型限制是管理員提供的設定值，未知用量或費用不會假造。完整操作見[模型指南](./model-usage.md)。

### Identity 與 SSO {#identity-api}

Identity 原生端點以 `/api/auth` 為前綴，套件網頁使用 `/auth-api`。`status`／`setup` 用於第一次建立管理員，`login`／`me`／`logout`／`sessions` 管理工作階段，`invitations`／`users` 管理成員。產品授權由管理員設定，仍由各產品逐次檢查。

`sso/settings` 與 `sso/test` 供管理員設定 OIDC，`oidc/start` 與 `oidc/callback` 完成登入。平台直接支援 OIDC；SAML 或 LDAP／AD 可透過選配的 Keycloak 代理，原生 SAML 與 SCIM 尚未提供。設定及供應商限制見[企業 SSO](./enterprise-sso.md)與[帳號指南](./human-login.md)。

## MCP

Work／Knowledge／Code 的 MCP stdio 橋接程序會呼叫各自的 REST API，並使用各自受範圍限制的 Agent token。變更操作中的 `request_id` 會對應至 `Idempotency-Key`；呼叫者不能在請求本文偽造 `actor`。啟動範例見[貢獻指南](../CONTRIBUTING.md)，依產品使用 `ordivant.mcp_server`、`ordivant_knowledge.mcp_server` 或 `ordivant_code.mcp_server`。

Runtime 連接外部工具時使用 MCP Streamable HTTP。詳見[外部工具指南](./execution-usage.md#external-mcp-tools)。

<span id="原始碼與開發"></span>
<span id="源代码与开发"></span>

## 原始碼與開發 {#source-and-development}

[GitHub 原始碼](https://github.com/ordivant-ai/ordivant)與[貢獻指南](../CONTRIBUTING.md)提供開發與測試入口。網站發布操作與整合文件；PM 台帳、開發契約及驗收紀錄留在倉庫供維護者使用。部署資料、憑證及私人測試輸出不可提交至公開倉庫。
