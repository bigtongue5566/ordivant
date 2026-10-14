<span id="ordivant-專案實作計畫"></span>
<span id="ordivant-项目实作计划"></span>

# Ordivant 專案實作計畫 {#ordivant-implementation-plan}

來源：使用者的規劃對話，並於 2026-10-06 使用者調整範圍後重新確認。產品為 **Ordivant Suite**，Work、Knowledge、Code 位於同一個 monorepo，並保有各自獨立部署的界線。Code 可選擇使用開源 Gitea；Work 可直接連線既有企業版控，不依賴 Code。技術組合：uv／Python、React、Pi Durable（僅 Work 使用）、PostgreSQL。

狀態快照（2026-10-08）：本機 Suite 的原生帳號、組織／Agent 模型設定及企業 SSO 均已完成。本次版本交付 Work Run 控制台、不可變的 Agent／工作流程範本、可持續執行的間隔工作流程、受限的外部 MCP 工具，以及每次 Run 各自隔離的 Docker 沙箱。Identity／Work／Knowledge／Code 分別有 28／41／10／20 項測試通過；Runtime 有 25 項，沙箱有 3 項。實際驗收包含 53 項完整容器檢查、20 項經授權的 gpt-6.1-sol 檢查、16 項收據／憑證檢查、9 項終端清理檢查、8 項 PostgreSQL 併發檢查、67 項 Docker 隔離檢查及 2 項當機復原檢查，以及 65 項桌面／行動瀏覽器檢查。開發模式 `5173` 和本機正式模式 `8088` 均已就緒，40 項環境保留／就緒檢查通過，資料庫與 Gitea 健康。已移除隔離的執行 QA 與較早的 SSO QA 容器，並保留具名 volumes。使用者會自行建立第一位管理員；主環境帳號、SSO 及既有模型／Provider 設定均已保留。本次版本依據 `docs/execution-contracts.md`；企業身分仍依據 `docs/sso-contracts.md`。驗收紀錄及 `docs/validation.md` 收錄證據與仍待客戶環境確認的專案。

以下原始驗收條件仍是 Work 模組的門檻。目前產品範圍、端點契約及整合 Suite 的驗收要求定義於 `docs/suite-contracts.md`；擴充產品範圍時以該檔案為準。

<span id="delivery-v01-suite-local-pilot"></span>

## 交付內容：v0.1 Suite 本機試行 {#delivery-v0-1-suite-local-pilot}

提供一個組織、兩個團隊、多個 Agent，並依專案範圍授權。交付可執行的 Work、Knowledge 和 Code 模組，而非靜態展示稿。SQLite 是有明確文件說明的快速入門模式；各產品的 SQLAlchemy 層也支援 PostgreSQL。產品不會讀取彼此的資料庫。每個 Work runtime 程式各自隔離 Pi 儲存空間。共用 Identity 支援標準 OIDC，以及可選的 Keycloak SAML／LDAP／AD broker。真實 Keycloak OIDC 與簽章 SAML 整合已驗證；每位客戶的身分租戶、目錄及既有企業版控憑證仍須分別設定並驗收。

## 驗收條件 {#acceptance-criteria}

1. 在連線的 React 工作區中建立及檢視專案、結構化任務、相依關係、Agent 與證據。
2. 兩個同時發出的 claim 嘗試只能有一個成功。執行逾期後，即使出現新的 claim，舊執行也不能再更新進度或提交結果。
3. 相依任務尚未完成時不得 claim；系統拒絕迴圈相依；已接受的成果會解除後續任務的阻擋。
4. Agent A 向 B 求助；B 收到並回覆，或執行委派任務；A 收到回覆並繼續工作；審查者 C 接受成果。
5. 重複的變更請求與事件傳遞不會建立重複任務、執行、訊息或成果物。
6. REST 和 MCP 執行相同的身分／專案／角色政策。Agent 不得冒用其他身分；執行中的 Agent 不得核准自己的工作。
7. 後端重新啟動後，稽核紀錄與執行歷程仍然存在。Pi Durable 持久化／續跑以確定性 fixture 測試；使用者授權的測試 Provider 則分別驗證已設定模型的即時工具執行、不含機密的收據及重啟後永續性。
8. UI 顯示錯誤／載入中／空白狀態，在小螢幕可用，並使用真實 API 資料。使用者能建立、檢視、協作及審查。
9. 文件說明安裝、啟動、MCP 連線、憑證、資料備份及限制。交付內容包含鎖定檔、驗收結果及更新後的任務清單。

## 任務清單 {#task-ledger}

| ID | 負責者 | 交付內容 | 狀態 |
|---|---|---|---|
| ORD-001 | PM | 架構、契約、範圍及驗收計畫 | 已完成 |
| ORD-002 | luna-backend | Work 持久化、身分／RBAC、任務、租約、協作、證據、稽核及 MCP | 已完成；19 項單元測試，以及 REST／MCP／PostgreSQL 驗收通過 |
| ORD-003 | luna-frontend | Work 操作工作區、任務看板／檢視器、Agent、協作、證據與審查 | 已完成；型別檢查／建置、瀏覽器建立專案／任務及 390px 規格編輯通過；協作／審查 API 通過 |
| ORD-004 | luna-runtime | Pi Durable adapter、持久派送、受限平台工具及復原 | 已完成；2 項單元測試及實際 Harness／outbox／重新啟動驗收通過 |
| ORD-005 | PM | 本機 runner、seed 流程、環境／文件、整合及瀏覽器／API 驗收 | 已完成；原生與容器整合、正式模式完整流程，以及連線 Work／Knowledge／Code 的瀏覽器檢查通過 |
| ORD-006 | luna-runtime | 獨立 Knowledge 後端：不可變版本、搜尋、決策、來源追溯、API／MCP | 已完成；5 項單元測試、整合版本／CAS 流程及僅 Knowledge 的容器驗收通過 |
| ORD-007 | luna-backend | 獨立 Code 後端：Gitea 儲存庫／分支／提交／PR／檢查、簽章 webhook、API／MCP | 已完成；15 項單元測試、真實 Gitea 整合及僅 Code 的正式模式驗收通過 |
| ORD-008 | luna-frontend | Suite 導覽，以及可獨立建置的 Knowledge／Code 工作區 | 已完成；四種建置、真實產品瀏覽器流程、公開 Gitea 網址、來源追溯選取及 390px 表單檢查通過 |
| ORD-009 | PM | 獨立 API／MCP 啟動，以及真實 Gitea 的 SQLite／PostgreSQL Suite 驗收 | 已完成；兩份 Suite 報告及獨立 Work PostgreSQL 報告通過 |
| ORD-010 | PM | Compose 整合，以及前端、API 和 runtime 的開發／正式映像 | 已完成；六個應用程式映像（含 Identity）、開發／正式完整流程、Knowledge／Code 獨立部署及持久化檢查通過 |
| ORD-011 | luna-runtime | 容器 worker helper、runtime 啟動／就緒整合及操作文件 | 已完成；兩個 helper 均可啟動；五項來源熱重載條件與逐位元組還原檢查通過，包含 Windows bind mount 上的 TypeScript 輪詢 |
| ORD-012 | luna-backend | 後端容器 QA：開發 proxy 驗證、正式模式存取控制及 403 案例 | 開發 proxy 驗證／直接 403，以及正式模式本機 403／範圍讀取通過 |
| ORD-013 | luna-reload-qa | 可重現的五來源開發熱重載驗收 | 已完成；所有 API worker PID、Pi 編譯輸出／server PID、Vite 來源／HMR 及還原後 SHA-256 檢查通過 |
| ORD-014 | luna-production-qa / PM | 透過 Nginx 和內部 Pi runtime 驗收正式模式完整流程 | 已完成；Suite／Git／MCP／Pi、本機 session 403、Work 在其他產品停止時運作，以及重啟持久化檢查通過 |
| ORD-015 | luna-code-standalone / luna-identity-bridge | 不含 Gitea 的僅 Code 部署，以及具範圍限制的官方 MCP 檢查 | 已完成；Code API／PostgreSQL／web 加上 Identity API／PostgreSQL、明確 Gitea 503、9 個 MCP 工具、範圍及重新啟動檢查通過 |
| ORD-016 | luna-identity | 獨立 Identity API／資料庫：帳號、密碼登入、邀請、復原、session 及管理控制 | 已完成；11 項安全測試、鎖定檔／wheel／建置檢查，以及真實 HTTP 生命週期驗收通過 |
| ORD-017 | luna-identity-bridge | 共用人員驗證、獨立產品主體、範圍授權、CSRF／Origin 與 bearer 相容性 | 已完成；每個產品 5 項 bridge 測試、55 項開發／正式驗收，以及五服務獨立部署通過 |
| ORD-018 | luna-login-ui / PM | 原生登入／設定、邀請／復原、帳號／session 管理、管理員權限及滑鼠操作下拉選單 | 已完成；四個產品建置、實際滑鼠操作產品／狀態／優先順序／範圍選取，以及 390px 帳號／登出檢查通過 |
| ORD-019 | PM | Identity Compose／原生工具、契約／文件、隔離驗證驗收及業務回歸 | 已完成；開發／正式環境就緒，每種模式 55 項 HTTP 檢查，正式 REST／MCP／Git／Pi 回歸、使用者首次管理員頁面及 QA 清理均已驗證 |
| ORD-020 | luna-model-backend | 組織模型連線、加密憑證、Agent 繼承／覆寫、具 fencing 的範圍限制 runtime 交接 | 已完成；Work 31 項測試，revision／RBAC／錯誤遮蔽／金鑰保留／null snapshot 檢查，以及隔離 cookie HTTP 驗收通過 |
| ORD-021 | luna-model-runtime | Pi Responses Provider 設定、實際模型／用量／工具收據、兩次租約 heartbeat 及憑證復原 | 已完成；使用實際 Pi adapter 的 5 項測試、真實 gpt-6.1-sol 平台工具執行、用量明細及完成收據重新啟動通過 |
| ORD-022 | luna-model-ui | 管理員模型設定，以及 Agent 建立／編輯時的模型選取 | 已完成；四種建置、實際滑鼠操作設定儲存／建立／編輯／重新載入，以及 390px 彈出層／持久化檢查通過 |
| ORD-023 | PM | 模型契約／操作匯入、容器整合、即時端點／工具／審查驗收及文件 | 已完成；開發／即時及正式 DEMO 回歸、金鑰／暫時 token 紀錄檢查和隔離 QA 清理通過；詳見 model-validation.md |
| ORD-024 | luna-sso-backend | 企業 OIDC、加密設定、範圍限制的佈建／群組授權、生命週期撤銷及稽核 | 已完成；28 項安全測試、鎖定檔／編譯檢查及真實協定／生命週期驗收通過 |
| ORD-025 | luna-sso-ui | 共用企業登入、Provider 範本、政策／連結及稽核管理 | 已完成；六個 Provider 範本、TypeScript／四種建置、實際桌面／390px 滑鼠檢查、立即更新狀態、僅 SSO 模式復原及僅管理員可建立範圍通過 |
| ORD-026 | luna-sso-qa / PM | 真實 Keycloak OIDC 與 SAML broker、隔離 PostgreSQL／瀏覽器驗收、容器整合及操作文件 | 已完成；136 項真實 HTTP 檢查、27 項儲存／日誌／重新啟動檢查、OIDC／SAML 瀏覽器驗收、主環境就緒及隔離 QA 清理通過；詳見 sso-validation.md |
| ORD-027 | luna-run-backend | 授權的 Run 檢視／控制、不可變 Agent／工作流程範本、持久排程器及專案工具／設定檔設定 | 已完成；41 項業務／安全測試及 8 項實際 PostgreSQL 併發檢查；REST／MCP 共用業務授權 |
| ORD-028 | luna-run-runtime | 實際 Pi 事件／控制閘門、受限外部 MCP 工具及隔離 Docker 執行器 | 已完成；25 項 Runtime 與 3 項沙箱測試、真實模型／工具收據、67 項實際執行器檢查、2 項當機復原檢查，以及終端同步前清理回歸檢查通過 |
| ORD-029 | luna-run-ui | Run 檢視器／控制、版本化自動化編輯器及工具／沙箱管理 | 已完成；TypeScript／四種產品建置及 65 項實際桌面／行動滑鼠檢查通過，包含 server 回覆遺失後重試，以及實際收據／stdout／exit 0／7 |
| ORD-030 | PM | 共用契約、沙箱 Compose／helper，以及本機 API／容器／滑鼠驗收 | 已完成；完整容器 53 項、即時 20 項、憑證 16 項、最後清理 9 項及主環境保留／就緒 40 項檢查通過；兩個本機環境均已更新，並移除本專案擁有的 QA；詳見 execution-validation.md |

## 架構決策 {#architecture-decisions}

- FastAPI service 是業務狀態的唯一真實來源。SQLAlchemy 支援 SQLite 本機快速入門，也支援 PostgreSQL 試行部署。
- 公開 REST 字首為 `/api`。MCP 透過 stdio 另行提供（使用者端 HTTP bridge 使用 Agent 憑證）；未來可加入可串流的 HTTP，而不重複實作業務邏輯。
- 人員驗證在兩種模式都使用獨立 Identity service：密碼登入、邀請、復原及伺服器管理的 cookie session。Agent REST／MCP 使用各自簽發、以雜湊儲存的不透明 token。Identity 設定完成後，兩種模式都會停用舊的本機 session 端點；詳見 `auth-contracts.md`。
- 每個組織環境可設定一個企業 OIDC Provider，使用 Authorization Code + PKCE、精確的 subject 連結、邀請／JIT 成員資格，以及明確的資源／群組授權。SSO 不會根據 Provider claim 指派管理員角色。SAML 和 LDAP／AD 使用可選的 Keycloak broker；詳見 `sso-contracts.md`。
- 所有 Agent 變更都從驗證資訊記錄操作者身分，絕不採用未受信任請求本文中的身分欄位。所有物件都會依允許的專案與組織範圍過濾。
- 租約包含 execution id 及不可猜測的 fencing token。每次執行中的變更都會驗證兩者的擁有權及租約是否過期。
- 工作流程狀態：`backlog`、`ready`、`in_progress`、`blocked`、`in_review`、`done`、`cancelled`。
- 一般情況下，只有透過審查才能轉為 done。指派任務不會授予專案存取權。
- Outbox 事件會與業務狀態一起原子化持久儲存，並由 runtime worker 領取。Runtime request id 等於 outbox id；回呼具冪等性。
- 每個 Pi SQLite 儲存空間只由一個 runtime 擁有。已設定模型／Provider 的身分會明確呈現；具確定性的 demo 模式則分開處理並清楚標示。

## 介面設計 {#interface-design}

視覺方向：平靜、精準的操作工作區，採用溫暖中性色表面、石墨色導覽、紫羅蘭色操作，以及精簡易讀的任務資訊。
內容規劃：以專案／任務工作區為主、導覽為輔；任務檢視器呈現結構化規格、執行、協作及審查證據。
互動方向：快速切換檢視、抽屜／對話方塊採用剋制的進場效果，並清楚呈現 hover／focus 狀態；尊重減少動態效果的偏好。

## 擴充 Suite 驗收門檻 {#expanded-suite-gates}

- Knowledge 發布不可變的精確版本規格與決策；文字檢索回傳可追溯的引用。
- Code 呼叫真實 Gitea API 管理 repository／branch／commit／PR／status，並驗證有簽章且去重後的 webhook。
- 每項產品都有各自具範圍限制的身分、資料庫、REST API 及 MCP 入口。
- 前端各產品模式可分別建置／部署；即使另兩項產品停止運作，Work 仍可使用。
- 完整來源追溯鏈：Knowledge v1 -> Work task/delegation -> Code PR/evidence -> Work review -> Knowledge v2。

## 公開版本交付（2026-10-08） {#public-release-handoff-2026-10-08}

公開 repository 為 `ordivant-ai/ordivant`，採用 MIT 授權。VitePress 文件網站包含安裝、產品指南、維運、疑難排解及 API 契約。公開 CI 會檢查五個 Python 專案、Runtime、四種前端模式及合成 REST／MCP 整合；Pages 會建置網站並驗證本機連結。付費服務驗收須由操作人員明確設定並在隔離 QA 環境執行；不會預設提供私人 Provider，也不會自動查詢主環境憑證。

版本來源從 Git index 匯出到乾淨目錄，並以新的 Compose project 啟動。全部 12 項服務均進入健康狀態；真實 Knowledge／Work／Gitea／MCP／Pi DEMO、獨立審查、產品隔離及重新啟動後永續性均通過。Gitleaks 掃描來源匯出內容，未偵測到機密。過往被忽略的 QA 報告不會隨版本釋出。下列企業驗收門檻刻意保留為未完成專案，但不影響已宣告的 v0.1 範圍。

## 尚待完成的企業驗收門檻 {#remaining-enterprise-gates}

候選功能、目前實作界線與建議優先順序記錄在[功能缺口研究](feature-gap-research.md)。該研究不會將候選功能標示為已實作，也不會將其加入已完成的任務清單。

- SCIM 2.0 Users／Groups、SMTP outbox、OIDC acr／amr 驗證及 Identity 稽核匯出／保留已加入目前程式，但客戶 IdP／目錄佈建及企業租戶生命週期整合驗收仍待完成。原生 SAML 端點與 Keycloak SAML broker 是不同實作。
- 更多正式環境 Provider／模型組合、已確認的費率／發票整合，以及硬性成本上限。使用者授權的測試 Provider／gpt-6.1-sol 合成即時執行及 token 收據記錄在 `model-validation.md`；這不代表一般帳單控制已完成。
- 既有 GitHub／GitLab／Jira 的正式同步憑證、MCP gateway、外部 A2A、物件儲存及備份還原演練。
- 可擴充套件的派送所有權／分片、負載測試及營運監控。

不能只因為存在介面或佔位元件，就將這些門檻標記為已完成。

## P0/P1 驗收清單 {#p0-p1-acceptance-ledger}

這份清單補充 2026-10-15 P0/P1 契約的交付界線。本機整合與驗收已完成；未驗證的客戶 IdP／SCIM 租戶及 GitHub／GitLab 部署 provider／CI 仍不在通過範圍內，這份清單也不代表功能已發布至 v0.2.0 或可用於其他部署。

2026-10-15 本機驗收快照（尚未推送或發布）：backend／Runtime 共 220 項測試通過（Work 82、Identity 38、Knowledge 32、Code 40、Sandbox 3、Runtime 25）；tool guards 20 項通過、1 項略過。Work 真實 PostgreSQL API 53 項及瀏覽器 51 項、Code 真實 Gitea API 65 項及瀏覽器 34 項、Knowledge 真實 PostgreSQL authoring 4 組及瀏覽器 336 項、Enterprise STARTTLS SMTP／SCIM 30 項及瀏覽器 10 項（含稽核 API 游標分頁）通過。整合與產品 smoke、四個產品 build、i18n 1,750 項／3 語系／7 項行為檢查通過。四個 API 服務重啟後健康；4 個資料庫共 103 張資料表、4,836 筆資料的逐表 row count 與完整資料 hash 均一致，沒有異動或非預期表格；既有協作 context API 讀回 7/7 通過。

| ID | 範圍 | 狀態 |
|---|---|---|
| P0-1 | Work 規劃欄位、同專案 Epic 防循環、Sprint／里程碑／欄位／階段設定與 rank 排序 | 本機驗收通過：真實 PostgreSQL API 53 項及瀏覽器 51 項；資料庫重啟持久性比對通過 |
| P0-2 | Work／Knowledge／Code 資源附件、提及、訂閱、通知、通知中心與協作中心跨產品搜尋；SMTP 邀請／復原 outbox | 本機驗收通過：tool guards 20 項通過、1 項略過；整合與產品 smoke、Work／Knowledge UI 及協作 context 讀回 7/7 通過 |
| P0-3 | Knowledge 頁面樹與封存、引用錨定留言／回覆／解決、Space 範本、Markdown 格式工具、版本差異與還原 | 本機驗收通過：真實 PostgreSQL authoring 4 組、瀏覽器 336 項及資料庫重啟持久性比對通過 |
| P1-1 | 專案提報表單、自訂欄位、階段與同步事件規則 | 本機驗收通過：Work 真實 PostgreSQL API 53 項、瀏覽器 51 項及資料庫重啟持久性比對通過 |
| P1-2 | 授權範圍內搜尋、個人儲存查詢、具作者歸屬的工時、觀察報表及安全原子 CSV | 本機驗收通過：Work 真實 PostgreSQL API 53 項、瀏覽器 51 項及資料庫重啟持久性比對通過 |
| P1-3 | 上游 Git checks／actions／pipelines／部署證據、head SHA 綁定 inline review 與真實 branch protection | 本機真實 Gitea API 65 項及瀏覽器 34 項通過；GitHub／GitLab 部署 provider 成功結果與外部 CI 未驗證 |
| P1-4 | SCIM Users／Groups、外部 IdP ACR／AMR MFA 政策、郵件寄送及受控稽核保留／匯出 | 本機驗收通過：STARTTLS SMTP／SCIM 30 項及瀏覽器 10 項，含稽核 API 游標分頁；客戶 IdP／SCIM 租戶仍待驗收 |

驗收前置條件已通過：REST 與 MCP 經同一服務授權；管理設定與資源讀寫重驗目前權限；涵蓋循環、跨 Space／Project、併發唯一性、冪等、過期或 stale 版本、未發佈共同草稿及原有資料升級保留。QA 已明確驗證沒有已設定的 LLM provider 時 provider 清單為空；真人認領、提交證據、獨立審查及共同 Markdown 編輯可正常運作。四個 API 服務重啟後健康；4 個資料庫共 103 張表、4,836 筆資料逐表 row count 與完整資料 hash 完全一致，沒有異動或非預期表格；既有協作 context API 讀回 7/7 通過。這批沒有執行付費 LLM，也未驗證客戶 IdP／SCIM 租戶或 GitHub／GitLab 部署 provider／CI 成功結果。不得以 Agent 自報值冒充已驗證支出或 CI。

企業驗收另需證明：SMTP 未設定時不會寄信，測試郵件只投遞至合成 sink；SCIM 不會依 email 認領既有帳號、一般 user PATCH 不可變更權限、明確 SSO 連結使用 `managed_permissions=false` 保留 SCIM 群組權限來源、停用會撤銷 session 且群組不能授予 admin；MFA 只接受符合設定的已驗證 IdP acr／amr；稽核匯出有界且不含機密。Git checks、review 與 deployment 結果必須對得上真實上游 URL／SHA／來源，head 改變後 inline comment 清楚標示過期。以上狀態代表本機整合驗收，不代表已發布至 v0.2.0 或通過客戶專屬 IdP／SCIM 租戶及 GitHub／GitLab 部署 provider／CI 驗收。

## 國際化交付（2026-10-08） {#internationalization-delivery-2026-10-08}

應用程式與公開文件目前支援繁體中文（`zh-TW`）、簡體中文（`zh-CN`）及英文（`en`）。共用導覽會在各產品和分頁之間保留瀏覽器的語言偏好。應用程式文字、Ant Design 元件、日期、數字及 API 錯誤呈現會依選定語言更新；使用者撰寫的內容及 API 識別碼保持原樣。切換語言時，已開啟的表單會保留草稿，並重新驗證既有錯誤。

驗收結果：1,247 則語系目錄訊息通過完整性／插值／來源文字檢查及 7 項語系行為檢查；四種前端目標皆完成建置；Identity、Work、Knowledge、Code 及行動版面共完成 121 項隔離瀏覽器檢查；文件完成 46 項瀏覽器檢查；產生 109 個 HTML 頁面（每種語言 36 篇文章，另有 404 頁），檢查 5,030 個本機參照，連結錯誤為 0。瀏覽器報告保留於忽略的 `.data/validation/`。這些介面檢查不需呼叫付費模型。維護方式及可重複執行的命令見[語言與翻譯](i18n.md)。

## 國際化修正與組織移轉（2026-10-09） {#internationalization-correction-2026-10-09}

第一輪文件驗收只涵蓋導覽與部分文章，未攔截容器、契約及驗收紀錄的英文正文。修正版已完整翻譯三語對應文章，並將每份文件的段落與表格加入建置前檢查。三語採用相同的章節識別碼，保留舊書籤，切換語言時仍會停在對應章節。

修正版通過 108 份文件來源檢查、8 項漏翻回歸檢查，以及 388 項實際文件瀏覽器檢查。平台補齊共用品牌、離線狀態與 Agent 執行環境文案；1,250 則目錄訊息、四種前端建置與 127 項隔離瀏覽器檢查均通過。這次驗收沒有呼叫付費模型。

原始碼已移轉至 `ordivant-ai/ordivant`。文件站倉庫為 `ordivant-ai/ordivant-ai.github.io`，使用 GitHub Pages 原生工作流程讀取公開來源的精確 revision，建置並發布至 <https://ordivant-ai.github.io/>。發布方式與來源版本查核見[語言與翻譯](i18n.md)。
