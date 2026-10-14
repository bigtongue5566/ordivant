# 驗收紀錄 {#validation-record}

日期：2026-10-08（Asia/Taipei）。狀態：本機 Suite 已包含原生帳號、組織／Agent 模型設定，以及可選用 Keycloak SAML／LDAP／AD broker 的企業 OIDC。最新 Work 版本交付 Run 控制與收據、版本化 Agent 與工作流程範本、持久化間隔排程、外部 MCP 連線，以及每次執行各自隔離的 Docker sandbox。實際模型／工具執行、獨立審查、容器重新啟動、並行處理、工作區清理，以及桌面／行動版瀏覽器檢查均已通過。兩個既有本機環境均已更新，並保留其帳號／SSO／模型／專案資料。下方較早的試點、模型與 SSO 驗收門檻仍屬歷史證據；目前的執行契約與結果見 `docs/execution-contracts.md` 和 `docs/execution-validation.md`。本紀錄日期之後，Identity 的 SMTP／SCIM 實作完成 11 項隔離檢查；客戶專屬 IdP／目錄與正式營運驗收仍待完成，詳見[現行 P0/P1 清單](project-plan.md#p0-p1-acceptance-ledger)。

## 必要驗收門檻 {#required-gates}

| 驗收門檻 | 證據 | 狀態 |
|---|---|---|
| 可重現的相依套件 | backend/uv.lock、frontend/package-lock.json、runtime/package-lock.json | 已通過／已安裝 |
| Work 業務與授權風險 | Work 單元測試 | 已通過：41 項測試，涵蓋 Identity bridge、模型設定、Run 控制／同步、不可變範本、工作流程排程與工具／設定檔範圍 |
| Knowledge 業務與授權風險 | Knowledge 單元測試 | 已通過：10 項測試，包含 Identity bridge 涵蓋範圍 |
| Code 業務與授權風險 | Code 單元測試 | 已通過：20 項測試，包含 Identity bridge 涵蓋範圍 |
| 人類帳號安全性與生命週期 | Identity 單元測試、lock 檢查與 Docker 建置 | 已通過：28 項測試；涵蓋本機帳號生命週期、簽章 OIDC claims、PKCE／state／nonce、subject 連結、佈建、政策／撤銷、backchannel 重播、trusted proxy 與增量遷移 |
| Pi Durable adapter 與復原單元檢查 | Runtime 單元測試 | 已通過：25 項測試，包含已設定的 Responses／cache、實際 SDK 工具事件、lease 序列化、控制閘門、完全相同本文的重試、即時執行復原，以及延遲／失敗的終端清理 |
| 前端 TypeScript 與產品建置 | `npm run typecheck`；`npm run build`、`npm run build:work`、`npm run build:knowledge`、`npm run build:code` | 已通過，包含 Knowledge／Code 可重試的 health 檢查 |
| 獨立 API／MCP 程序啟動 | Work、Knowledge 與 Code 黑箱啟動檢查 | 已通過 |
| REST 協作與並行認領 | SQLite Work 驗收 | 已通過：並行認領中恰有一項成功；求助、委派、審查者分離、冪等性與範圍檢查均通過 |
| 官方 MCP SDK 探索與選定往返呼叫 | Work MCP 驗收；`.data/validation/20261008-021346-6e1664/report.json` | 已通過：最新官方 SDK 探索列出 29 個工具，並實際往返驗證協作／認領／範圍／相依性／審查，以及 Pi DEMO 派送。較早的試點列出 18 個工具；兩者都不表示每個已註冊工具都曾被呼叫 |
| 限定範圍的 outbox -> Pi -> 證據 -> 審查者流程 | 實際 Pi Durable Harness、outbox 與重新啟動復原 | 已通過 |
| PostgreSQL Work 業務資料庫 | `.data/validation/20261006-023924-a991c9/report.json` | 已通過 |
| 使用真實 Gitea 的完整 SQLite Suite | `.data/validation/suite-20261006-023713-2dc030/report.json` | 已通過；完整 provenance 流程、實際 PR、簽章 webhook 重播、重新啟動後持久性，以及停止 peers 時的 Work 均通過 |
| 使用真實 Gitea 的完整 PostgreSQL Suite | `.data/validation/suite-20261006-023940-7a147c/report.json` | 已通過；完整 provenance 流程、實際 PR、簽章 webhook 重播、重新啟動後持久性，以及停止 peers 時的 Work 均通過 |
| 前端／後端／runtime 開發與 production 映像 | PM 容器映像建置 | 已通過：共六個應用程式映像，包含獨立 Identity；既有第三方資料庫／Gitea／broker 映像仍分別固定版本 |
| 開發容器端對端、dev proxy 驗證與直接 403 | `.data/validation/containers-ordivant-dev-85eff4cd-20261006-025843-d04d7a/report.json` | 已通過：PostgreSQL、Suite／MCP／Pi、停止 peers 時的 Work、重新啟動後持久性與 dev proxy 檢查 |
| Production 初始基本門檻 | `.data/validation/containers-ordivant-prod-85eff4cd-20261006-025955-5d0de6/report.json` | 已通過：8088 Web、API prefixes、PostgreSQL、production local 403、範圍讀取與重新啟動後持久性；完整 production 驗收記錄如下 |
| 透過 Nginx 的 Production 完整流程 | `.data/validation/containers-ordivant-prod-85eff4cd-20261006-220058-bd14cd/report.json` | 已通過：實際 Suite／Git／MCP 流程、內部 Pi Durable 派送、全部 local-session 403 檢查、停止 peers 時的 Work、API 重新啟動與流程／seed 持久性 |
| 僅 Knowledge 的容器驗收 | `.data/validation/standalone-knowledge-ordivant-knowledge-qa-20261006-031232-1c2cc5/report.json` | 已通過：僅有 Knowledge API、PostgreSQL 與 Web；建立／重播／精確 SHA／搜尋／reader 403、容器內官方 MCP 的 8 個工具與指定版本讀取、重新啟動及最後 readiness |
| 未設定 Gitea 的 Code-only 容器驗收 | `.data/validation/standalone-code-ordivant-code-qa-20261006-220447-410767/report.json` | 已通過：僅有 Code API、PostgreSQL 與 Web；獨立 bundle、範圍／reader 403、專案持久性、明確的 Git 寫入 503、官方 MCP 的 9 個工具及 repository／event 讀取；13 個條件全部通過 |
| Dev／prod helper 啟動 | PM Compose helper 檢查 | 已通過：兩種 helper 變體都成功完成 `up` |
| 五個來源檔案的開發熱重新載入 | `.data/validation/hot-reload-acceptance-20261006T135822Z-26cbb8.json` | 已通過：三個 API worker PID 改變、Pi 原始碼成功編譯且 server 子程序 PID 從 458 變為 732、Vite 回傳標記／HMR、所有 health 均為 200，五個來源檔案都已還原至原始 SHA-256 |
| 產品部署獨立性 | 上方 PM Compose 驗收；下方 authentication 版本 | 已通過：Work 可在 peers 停止時運作；每個獨立產品都有自己的 API／資料庫／Web，以及獨立 Identity API／資料庫 |
| 瀏覽器：Work 建立專案與完整結構化任務 | 已連線的應用程式 | 已通過 |
| 瀏覽器：Knowledge 建立 v1、發布 v2、保留 v1 SHA／歷史記錄並建立決策 | 已連線的應用程式 | 已通過實際 API 驗證 |
| 瀏覽器：Code 真實 repository／branch／commit／PR／status 與公開 URL | `.data/validation/browser/code-provenance-390.jpg`；`browser/report.json` | 已通過：實際私有 repository 與 UTF-8 commit、PR、位於 127.0.0.1:3002 的 Gitea URL、精確 Knowledge 版本 provenance，以及清楚標記為 agent_reported 的狀態 |
| 瀏覽器：390px 視窗 | `.data/validation/browser/report.json` 及 Work／Knowledge／Code 截圖 | 已通過：文件沒有水平溢位；Work 規格編輯已儲存，Knowledge 搜尋／歷史／表單及 Code branch／PR／provenance 表單均可操作 |
| 開發模式原生登入 HTTP 驗收 | `.data/validation/auth-ad6c32a4/report.json` | 已通過：55 項檢查；三個 Cookie principal、明確成員範圍、重新啟動後持久性與 Identity 中斷時採取 fail-closed |
| Production 原生登入 HTTP 驗收 | `.data/validation/auth-1b5fc8b5/report.json` | 已通過：透過 Nginx 完成 55 項檢查；邀請／復原僅可使用一次、密碼變更、工作階段撤銷、權限變更、節流、CSRF／Origin 與停用帳號 |
| 啟用 Identity 後的 Production 業務回歸 | `.data/validation/containers-ordivant-prod-85eff4cd-20261006-233819-4246ee/report.json` | 已通過：Suite／Git／MCP／Pi、拒絕所有舊版 local-session endpoints、停止 peers 時的 Work 與重新啟動後持久性 |
| 啟用 Identity 的 Knowledge-only 部署 | `.data/validation/standalone-knowledge-ordivant-knowledge-qa-20261006-234154-96dbda/report.json` | 已通過：五個服務、24 項檢查、首次人類使用者設定就緒、範圍限定的 bearer／MCP 與重新啟動後持久性 |
| 啟用 Identity 的 Code-only 部署 | `.data/validation/standalone-code-ordivant-code-qa-20261006-234312-7e2f48/report.json` | 已通過：五個服務、首次人類使用者設定就緒、範圍限定的 bearer／MCP、未設定時明確拒絕 Git 寫入並回傳 503，以及重新啟動後持久性 |
| 瀏覽器：原生驗證與實際滑鼠下拉選單操作 | `.data/validation/auth-browser/report.json` 及截圖 | 已通過：三種產品選擇器、Work 狀態／緊急任務持久性、Drawer／Modal 上方的權限彈出選單、390px 彈出選單邊界、行動版帳號控制項與重新整理後仍有效的登出 |
| 組織模型設定／範圍限定的 Agent 覆寫 | `.data/validation/model-settings-76ed3fd4/report.json` | 已通過：僅使用管理員 Cookie、Origin／CSRF、revision、保留金鑰／錯誤遮蔽、catalog、繼承與設為 null 清除；未呼叫 provider |
| 模型設定與 Agent 表單的滑鼠操作 | `.data/validation/model-browser/report.json` 及截圖 | 已通過：桌面／行動版設定儲存、新增覆寫、編輯繼承、重新載入、Modal 彈出選單指標命中，以及 390px 無溢位 |
| 即時 gpt-6.1-sol endpoint 與工具往返呼叫 | `.data/validation/live-probe-388b5ccd/report.json` | 已通過：models 探索、實際 Responses 完成事件，以及由合成模型發起的 function-call 往返呼叫 |
| 即時 Work／Pi／工具／證據／審查及重新啟動 | `.data/validation/live-work-08fdbdb1/report.json` | 已通過：27 項條件、新的範圍限定 Agent／專案派送、get_task_context／report_progress、回傳的模型、包含 token／cache 的收據、拒絕自行審查、獨立測試審查者與持久化的已完成提交 |
| Provider 與派送憑證記錄檢查 | `.data/validation/live-work-08fdbdb1/record-checks.json` | 已通過：金鑰已加密、確認後撤銷、Pi 或冪等記錄中沒有金鑰／派送 token，近期服務記錄也沒有 provider key |
| 更新後的 production runtime fallback 回歸 | `.data/validation/model-production-runtime.json` | 已通過：未設定 provider 時，使用實際 Pi 執行明確標記的 DEMO，並完成證據與獨立審查；provider 連線仍未設定 |
| 真實企業 OIDC 與 SAML broker | `.data/validation/sso-32eb71e9/report.json` | 已通過：136 項檢查；實際簽章 provider 流程、精確產品範圍、JIT／邀請／連結、群組撤銷、SSO-only、停用成員、簽章 backchannel 登出與敏感資訊遮蔽 |
| 企業加密儲存、記錄與重新啟動 | `.data/validation/sso-84b63356/storage-report.json` | 已通過：27 項檢查；PostgreSQL／加密／雜湊流程狀態、私有持久化金鑰、不儲存 provider token／code、實際重新啟動 Identity／Keycloak 與不含秘密的記錄 |
| 企業登入／設定與滑鼠操作 | `.data/validation/sso-browser/report.json` 及截圖 | 已通過：OIDC／SAML 與共用工作階段、六種範本、連線測試、儲存後立即更新狀態、390px 下拉選單命中／邊界、由 IdP 管理的密碼介面、SSO-only 管理員復原，以及僅管理員可建立 Project／Space |
| 更新後主環境的開發／本機 production 就緒狀態 | `.data/validation/sso-browser/main-environments.json` | 已通過：兩個 origin、三個 health prefixes 與 Identity 狀態均回傳 200；主環境仍需完成初始設定，且未設定 SSO |
| Run 控制、範本與完整工作流程執行 | `.data/validation/execution-e8f561d8/report.json`；`execution-postgres.json` | 已通過：53 項完整容器檢查及 8 項實際 PostgreSQL 並行檢查，包含停止／重試／歷史、經審查的相依項目、實際間隔排程、取消與啟動時權限授予 |
| 實際即時 MCP／模型／sandbox 執行 | `.data/validation/execution-55faa750/live-report.json` | 已通過：使用已授權的 gpt-6.1-sol 連線完成 20 項檢查，包含協作式暫停／繼續、實際 MCP sum=42、真實 Python stdout／exit 0 與 7、獨立審查及重新啟動後的收據 |
| Runtime 記錄與終端清理 | `.data/validation/execution-55faa750/record-checks.json`；`execution-cleanup.json` | 已通過：16 項憑證／記錄檢查及 9 項實際清理檢查；金鑰已加密、暫時 token 已撤銷、取得真實 Pi 結果、沒有剩餘自有工作，且 terminal sync 前已完成清理 |
| Docker sandbox 隔離／復原 | `.data/validation/sandbox-integration.json`；`sandbox-crash-recovery.json` | 已通過：67 項實際隔離／資源／路徑／逾時檢查，以及 executor 收到 SIGKILL 並重新啟動後的 2 項自有工作清理檢查；Docker 仍是共用核心的隔離邊界 |
| 執行功能的桌面／行動版瀏覽器操作 | `.data/validation/execution-browser/report.json`；`execution-run-browser/report.json`；`execution-live-browser/report.json` | 已通過：45 + 10 + 10 項檢查；實際滑鼠下拉選單／表單操作、已提交請求失去回覆後的復原、歷史／控制操作，以及桌面與 390px 行動版上實際收據／stdout／結束代碼 |
| 最新主環境本機資料保留／就緒檢查 | `.data/validation/execution-local-before.json`；`execution-local-after.json` | 已通過：5173／8088 上的 40 項檢查；帳號數／初始設定／SSO／模型／provider／專案快照未變，API／產品回傳 200，runtime／sandbox／產品容器皆健康 |

Suite 驗收流程涵蓋：Knowledge 不可變 v1 與精確引用 -> Work 任務 A／B 及獨立審查者 C -> 真實私有 Gitea repository、branch、commit 與 PR -> 六案例 fixture pytest -> 簽章 webhook 重播 -> Knowledge v2 -> CAS 結果 `[201, 409]` -> 重新啟動後持久性 -> 停止 Knowledge 與 Code peers，讓 Work 直接讀取 Gitea PR／checks 並結束任務。開發與 production 容器都通過此流程。Production MCP bridge 透過 Nginx 保留各產品 API prefix；Pi 驗收在 Work 容器內對內部 runtime 服務執行，沒有公開其連接埠。已連線的瀏覽器檢查另外確認 Work 專案／任務建立與規格編輯、Knowledge v1／v2／歷史記錄／決策／搜尋，以及 Code repository／branch／commit／PR／status 與精確版本來源選取。瀏覽器狀態收據是 Agent 手動回報，不是外部 CI 執行結果。

Windows bind mount 需要以 polling 方式運作 TypeScript runtime watcher；`compose.dev.yaml` 同時設定 watch-file 與 watch-directory polling。驗收 harness 會觀察編譯輸出與變更後的 server 子程序 PID。Vite health probe 接受 HTML（`Accept: */*`），接著檢查 source／HMR，並還原所有原始 source 位元組。

帳號驗收使用專用 `ordivant-auth-qa` 專案、loopback 連接埠 `8092`、合成 fixture 與獨立 volume。檢查涵蓋首次成員並行綁定、通用驗證失敗訊息、目前密碼檢查、一次性復原、帳號停用及最後一位管理員保護。代理程式未初始化主環境的開發與 production Identity 資料庫；使用者會在網頁自行建立第一位管理員。重現方式記載於[帳號驗收](auth-validation.md)。

本紀錄不包含任何憑證值。產生的測試資料與完整診斷資訊保留在 git 忽略的 `.data/validation/` 目錄。詳細報告留在本機；此摘要省略憑證與含秘密的值。

驗收後，透過 helper 的 `down` 動作停止暫時使用的 `ordivant-knowledge-qa`、`ordivant-code-qa` 與 `ordivant-auth-qa` 容器／network；其具名 volume 與本機 secrets 仍保留。開發 Suite 與本機 production-target Suite 維持執行。最後檢查時，其 API、資料庫、Web 與 Gitea 容器均健康；開發 runtime 也透過 HTTP health endpoint 確認正常。使用者的兩個 Identity instance 仍回報 `setup_required: true`；Work 顯示原生的首次管理員設定表單。

企業身分版本使用獨立的 `ordivant-sso-qa` 專案（連接埠 `8092/8093`），以及含公開合成 fixture 的兩個真實 Keycloak realm。它不會在使用者的主環境安裝任何人類帳號或企業 provider。瀏覽器操作使用已授權的合成 QA 帳號；臨時 viewport／tab 已清理，並保留使用者原本的 tab。QA 容器／network 已停止，具名 volume 則保留。通用 OIDC 互通性與簽章 SAML broker 往返流程已驗證；客戶自己的 Entra／Google／Okta／Auth0 tenant 與真實 LDAP／AD 目錄，仍須各自設定並驗收。詳見 [SSO 驗收](sso-validation.md)與[企業設定](enterprise-sso.md)。

模型版本驗證了使用者明確授權的 HTTPS endpoint、要求／回傳的 `gpt-6.1-sol`、實際由 Pi 模型呼叫的 Work 工具、證據與獨立測試審查。最後一次執行回報輸入 17,157 tokens（其中 10,496 為快取）、輸出 97、合計 17,254；金額仍未知。Provider 發票／底層路由、硬性預算限制、客戶專屬企業 IdP tenant、已設定的企業 GitHub／GitLab 即時憑證、外部 CI、備份還原、負載測試及 production 可觀測性均未驗證。較早的 Pi 測試仍明確標示為 demo。測試模型連線只在開發環境設定。詳見[模型驗收](model-validation.md)與[模型使用方式](model-usage.md)。未執行遠端部署、發布或 push。

執行功能版本的另一場已授權即時執行回報輸入 40,000 tokens（其中 16,128 為快取）、輸出 744、合計 40,744；美元成本仍未知。MCP 測試 endpoint 與 sandbox 內容均為合成資料，但其實際呼叫、輸出與結束狀態已驗證；DEMO 檢查仍分開標示。暫停功能會在工具邊界協作執行，工作流程以分鐘為間隔排程，外部工具使用 Bearer 驗證的 Streamable HTTP，工作容器則無網路。核准政策、硬性金額配額、互動式 MCP OAuth、任意 repository／network checkout，以及 VM 隔離仍屬後續工作。驗收後已移除自有的 `ordivant-execution-qa` 容器／network，並保留具名 volume 與報告；主開發／本機 production 資料庫、Gitea 與服務仍健康。詳見[執行功能使用方式](execution-usage.md)與[執行功能驗收](execution-validation.md)。

## P0/P1 本機驗收快照（2026-10-15） {#p0-p1-local-acceptance-2026-10-15}

以下結果來自尚未推送或發布的本機工作樹；前面的記錄維持各自日期的歷史驗收結果。

| 範圍 | 結果 |
|---|---|
| Backend／Runtime 測試 | 220 項通過：Work 82、Identity 38、Knowledge 32、Code 40、Sandbox 3、Runtime 25 |
| 工具權限防護檢查 | 20 項通過、1 項略過 |
| Work／Knowledge | Work 真實 PostgreSQL API 53 項及瀏覽器 51 項通過；Knowledge 真實 PostgreSQL authoring 4 組及瀏覽器 336 項通過。四個 API 服務重啟後健康；4 個資料庫共 103 張表、4,836 筆資料的逐表 row count 與完整資料 hash 前後一致，協作 context API 讀回 7/7 通過 |
| Code | 真實 Gitea API 65 項及瀏覽器 34 項通過；沒有驗證 GitHub／GitLab deployment provider 或 CI 成功結果 |
| 企業身分 | 真實 STARTTLS SMTP／SCIM 30 項及瀏覽器 10 項通過，包含稽核 API 游標分頁；客戶 IdP／SCIM 租戶仍待驗收 |
| 整合與 i18n | 整合／產品 smoke、四個產品 build 通過；1,750 項訊息、3 種語言與 7 項語系行為檢查通過 |

QA 確認未設定 LLM provider 時 provider 清單為空；真人認領、提交證據、獨立審查與共同 Markdown 編輯可在沒有 LLM 時運作。本批沒有執行付費 LLM，也沒有驗證客戶 IdP／SCIM 租戶或 GitHub／GitLab deployment provider／CI 成功結果。
