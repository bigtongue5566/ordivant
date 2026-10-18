# Ordivant 功能導覽 {#product-features}

這份導覽依照日常工作說明 Ordivant 的操作入口、操作後會留下什麼紀錄，以及目前的限制。Work、Knowledge 和 Code 都支援真人與 Agent 在同一產品流程中合作；一般真人操作不需要 LLM。Work 管理任務、真人執行和 Agent Run；Knowledge 管理共同草稿、文件版本和決策；Code 管理連接至 Gitea 的 repository 和 PR，並保存 Ordivant 討論與審查紀錄。先從[專案介紹](./overview.md)選擇適合的產品，再依下列情境操作。

本指南介紹 v0.5.0 的功能。若畫面沒有下述入口，請向管理員確認已安裝版本、產品權限及所需的整合設定。

## 真人與 Agent 協作 {#human-and-agent-collaboration}

### 情境 {#human-and-agent-collaboration-scenario}

團隊想先讓同事自行處理任務、共同編寫規格並審查 PR，之後再為適合自動化的工作加入 Agent。這些人工作業可以先於模型設定使用。

### 操作入口 {#human-and-agent-collaboration-steps}

1. 在 Work 建立任務時，選擇獲授權的真人同事或 Agent 作為負責者；也可留白讓同事認領。真人 Worker、Manager 或 Admin 可認領未指派或指派給自己的待執行任務，回報進度、提交證據或交接。提交者不能審查自己的成果。請依[Work 指南](./guide/work.md)操作。
2. 在 Knowledge 開啟最新版本的共同草稿；Writer 和 Manager 可以同時編輯，Reader 可閱讀。草稿伺服器確認保存後，才可發佈成不可變版本。Agent 透過 REST／MCP 參與同一草稿。請見[Knowledge 指南](./guide/knowledge.md)。
3. 在 Code 的 PR 詳情討論變更並提交 Ordivant 審查紀錄。每筆審查綁定當時的 PR head SHA；Gitea 仍負責 Git、合併與 Gitea 自身核准。請見[Code 指南](./guide/code.md)。

### 結果與界限 {#human-and-agent-collaboration-result}

人員以自己的 Identity 帳號工作，不需建立 Agent 來代表人，也不需模型金鑰。只有自主 Pi Agent Run 需要啟用 Runtime 並配置 Provider/model。Code 的 repository、branch、commit 和 PR 寫入需要 Gitea。Knowledge 斷線時，尚未確認保存的修改只留在目前瀏覽器分頁記憶體，關閉或重新載入可能遺失；發佈衝突需重新載入並檢查最新草稿。Ordivant Code 審查不是 Gitea approval、CI 結果或 Work 任務驗收。

## 任務規格與相依任務 {#work-task-design}

### 情境 {#work-task-design-scenario}

你要交付一份上線檢查報告，其中「整理服務清單」必須先完成，後續檢查才能開始。

### 入口與操作 {#work-task-design-steps}

1. 在 Work 選取已授權的 Project，進入「任務」，按「新增任務」。
2. 填寫任務名稱、目標、輸入資料、範圍、限制條件及驗收條件；每個驗收條件分行填寫。選擇優先級、獲授權的同事或 Agent 作為負責者，並設定獨立 reviewer；也可先不指派，讓同事認領。
3. 在「相依任務」選取必須先完成的 Task，再建立任務。開啟任務後可在「規格」頁籤檢查欄位與相依狀態；需要修改時按「編輯規格」。

![Work 專案任務清單](/screenshots/work-zh-TW.png)

![任務詳情與規格](/screenshots/task-zh-TW.png)

### 結果與界限 {#work-task-design-result}

相依任務會顯示在任務規格中；系統拒絕循環相依。前置任務經審查接受並完成前，後續任務不能開始。任務規格、Run／Execution、成果和審查是各自保留的紀錄；修改規格不會抹掉既有歷程。

## 求助與委派 {#work-help-and-delegation}

### 情境 {#work-help-scenario}

執行者需要另一位同事或 Agent 協助確認資料來源，或能把「整理測試案例」拆成可單獨審查的子工作。

### 入口與操作 {#work-help-steps}

1. 在任務清單開啟 Task 詳情，按「請求協作」，選擇獲授權的同事或 Agent 作為收件者，將問題或需要的資料寫在訊息內容後送出。討論會留在該 Task 的「協作」頁籤；收件者也可在 Work 的「協作收件匣」查看。
2. 收到訊息後可在任務討論串回覆；收件者或有權限的管理者可標記已接收或完成。問題、回覆、決議和交接都會保留在專案／任務脈絡中。
3. 若工作可以獨立交付，在 Task 詳情按「委派子任務」，選擇獲授權的同事或 Agent 作為負責者，填寫子任務名稱、目標、範圍、輸入、限制和驗收條件，再按「委派任務」。

### 結果與界限 {#work-help-result}

委派會建立一筆連結至父任務的獨立 Task，並保留自己的 Execution／Run、證據與審查歷程。具專案範圍的 Manager／Admin，或目前實際負責父任務執行紀錄的真人或 Agent，可委派子任務；子任務不會擴大任何人的專案權限，巢狀委派最多三層。求助與委派不是即時聊天，也不會自動替收件者建立其他專案的存取權。

## Run 與人工介入 {#runs-and-intervention}

### 情境 {#runs-intervention-scenario}

你已寫好任務規格，想讓 Pi 執行 Agent 實際執行，並在工具操作或結果有疑問時查看與控制進度。

### 入口與操作 {#runs-intervention-steps}

1. 開啟 Task 詳情。真人負責者直接按「認領任務」；沒有 Agent 租約，重新載入後可從執行紀錄繼續。需要自主執行時才選擇 Pi Agent 並按「派發給 Agent」，這會建立自動 Run。
2. 開啟 Work 的「Run 執行」，選擇 Run 查看狀態、答案、事件、工具結果、沙箱輸出及供應商回報的模型／用量。
3. 有管理權限時，可在 Run 詳情要求「暫停」、「恢復」或「停止」；失敗或停止的 Run 可建立新的「重跑」。重跑會保留舊 Run，並建立新的執行紀錄。
4. Run 提交後，回到 Task 的「執行與審核」檢查摘要及成果，由另一位符合權限的 reviewer 接受或退回。

![Run 執行控制台](/screenshots/run-zh-TW.png)

### 結果與界限 {#runs-intervention-result}

Run 的「已提交」表示模型回合已提交，不代表 Task 已完成；只有獨立審查接受才會完成 Task。真人執行是獨立於 Agent Run 的工作紀錄，不需要模型。暫停會等目前的模型或工具操作結束後才生效。停止不會撤銷外部服務已完成的操作；結果不明時，請先到上游服務核對再重跑。DEMO 不呼叫付費模型；沒有可確認的用量或美元金額時會顯示未知。

## Agent 範本與工作流程 {#agent-templates-and-workflows}

### Agent 範本：重用執行設定 {#agent-template-reuse}

在 Work 側欄開啟「自動化」→「Agent 範本」，建立範本時設定角色、能力標籤、指令、模型選項、可用工具連線、沙箱設定檔、最多模型回合及執行逾時。建立或編輯 Agent 時，在「Agent 範本版本」選擇要套用的精確版本，再視需要調整 Agent 的設定。修改既有範本要發佈新版本；已建立的 Agent 或 Run 會保留原先套用的版本／設定。

範本方便重用同一組工作方式，不會授予專案、模型 Provider 或工具的存取權。該 Agent 仍須先獲授權進入 Project；Provider 由 Work 組織管理員設定，工具連線也須由專案管理者設定。

### 工作流程：安排多步驟交付 {#workflow-sequencing}

1. 在「自動化」→「工作流程」按「新增流程」，加入步驟並為每步填寫名稱、目標、優先級、驗收條件，選擇負責 Agent 或候選能力，並指定 reviewer。
2. 在「相依步驟」選擇前置工作。互不相依的步驟可以同時執行；系統拒絕無效或形成循環的相依。
3. 按「手動啟動」，輸入本次「流程輸入」並啟動。每個步驟會建立對應 Task；沒有可用 Agent 或前置結果尚未通過審查時，步驟會等待。
4. 若工作按固定間隔重複，在流程的「排程」設定啟用狀態、啟動間隔及最多執行次數。可在「執行紀錄」查看流程 Instance。

流程每個 Instance 固定使用啟動時的流程版本；各步驟仍需分別審查接受後才能解除下游步驟。排程不會在前一次流程仍執行時重複啟動，服務停機錯過的時段也不會補跑。取消流程會停止尚未完成的步驟，已接受的成果保留。手動認領任務不會代替 Run 派送。

![工作流程編輯器與排程設定](/screenshots/workflow-zh-TW.png)

## 模型繼承與 Agent 覆寫 {#model-inheritance-and-overrides}

### 情境 {#model-settings-scenario}

組織設定一個通用模型給大多數 Agent，只有程式碼審查 Agent 使用另一個已核准的模型。

### 入口與操作 {#model-settings-steps}

1. Work 組織管理員從側欄開啟「模型連線」，新增 Provider、HTTPS API 網址和 API key，登錄 Provider 支援的模型與選項，再選擇組織預設模型。
2. 在「Agent 名錄」新增或編輯 Agent；模型設定選擇「沿用組織預設」，或指定已設定的 Provider、模型、推理強度與輸出上限。
3. 儲存後檢查 Agent 名錄顯示的有效模型。已派發的工作沿用當時建立的模型快照；更新設定從之後的新派發開始生效。

### 結果與界限 {#model-settings-result}

Provider key 加密保存，重新開啟時不會顯示明文。外部 Runtime Agent 的模型名稱僅供辨識，Work 不會替它呼叫模型。若未設定模型，Pi Run 會以明確標示的 DEMO 模式執行；即時 Provider 呼叫失敗會回報失敗，不會冒充 DEMO 成功。Token 用量和供應商回報的模型不等於帳單；模型輸出上限也不是美元費用硬上限。費率與實際支出請以 Provider 帳戶確認。完整步驟見[模型連線指南](./model-usage.md)。

## Knowledge 文件版本與搜尋 {#knowledge-versioning-and-search}

### 情境 {#knowledge-versioning-scenario}

團隊要更新上線規格，但需要讓舊任務仍能指出它當時依據的版本。

### 入口與操作 {#knowledge-versioning-steps}

1. 開啟 Knowledge，選擇已授權的 Space，再進入「文件庫」。按「新增文件」，填寫標題、摘要、正文、標籤及可追溯來源。
2. 修訂文件時打開最新版本的「共同草稿」，選擇編輯。Writer／Manager 與 Agent 可同時更新正文，內容會合併；切換預覽檢查 Markdown。
3. 等待草稿顯示已連線和已保存，再按「發佈新版本」，輸入變更摘要並確認。發佈建立不可變版本；Reader 只可檢視。若版本衝突，重新載入草稿，檢查合併結果並等到已保存後再發佈。
4. 在文件檢視器切換版本，查看版本 URI、建立時間、SHA-256 及變更摘要；使用搜尋框比對標題或正文，或依標籤篩選。

![Knowledge 文件與版本](/screenshots/knowledge-zh-TW.png)

### 結果與界限 {#knowledge-versioning-result}

每次發佈都會新增不可變版本，舊版本和引用會保留。未經伺服器確認的離線修改只留在目前瀏覽器分頁記憶體；不可宣稱關閉頁面後仍保留。搜尋比對已保存的標題、正文和標籤，是文字搜尋，不提供向量搜尋或 RAG。

## Knowledge 決策與精確引用 {#knowledge-decisions-and-citations}

在 Knowledge 選擇 Space 後，進入「決策紀錄」並按「新增決策」，填寫標題、決策內容，可關聯文件和來源引用。這適合記下「為何採用此方案」及其依據；後續決策改變時新增一筆記錄，保留先前脈絡。

引用規格時，從文件的指定版本複製完整版本 URI，並將它放入 Work 任務輸入／證據，或 Code PR 的來源欄位。URI 指向特定版本，不會因文件之後更新而改指新版本。引用只記錄來源，不會授予讀取者 Knowledge Space 權限；要讀取內容仍須被授權。

版本 URI 格式如下：

~~~text
ordivant://knowledge/spaces/{space_id}/documents/{document_id}/versions/{version}
~~~

## Code 分支與 Pull Request {#code-pull-requests}

### 情境 {#code-pull-requests-scenario}

工程團隊要在 Gitea 中整理一項設定檔變更，並將規格來源和 Work 任務連結到 PR，交由團隊原本的流程審查。

### 入口與操作 {#code-pull-requests-steps}

1. 開啟 Code，選取已授權的 Code Project 和 repository。具寫入權限時，可建立私人 repository。
2. 在 repository 詳情建立 branch，使用「提交檔案」新增或更新 UTF-8 檔案並填寫 commit message。
3. 按「建立 PR」，選擇來源 branch 與目標 branch，寫上標題／描述，並加入 Work、Knowledge 或外部來源引用。
4. 在 PR 詳情查看 head SHA、來源、狀態與 check 收據；在 Ordivant 討論與審查區留評論、要求修改或記錄核准。按「在 Gitea 開啟」依組織流程完成正式審查和合併。

![Code repository 與 Pull Request](/screenshots/code-zh-TW.png)

### 結果與界限 {#code-pull-requests-result}

Code 的 repository、branch、commit 與 PR 由部署端連接的 Gitea 保存；尚未設定 Gitea 時，無法執行寫入操作。PR 詳情也會讀取目前 head SHA 的 Gitea 分支規則、核准、狀態檢查與 Actions；若為該 repository 設定 GitHub／GitLab 部署來源，也會列出相同 head SHA 的部署記錄。Code 讀取這些證據，不會啟動 CI 或建立部署；沒有 provider 設定時會明確顯示未設定。真人或 Agent 可在 Ordivant 討論與審查，但每筆審查綁定 PR head SHA，head 更新後舊審查會過期。Ordivant 紀錄不會同步成 Gitea approval，也不是 CI 或 Work Task 驗收。Code 的「回報狀態」會記錄為 Agent 回報，並不表示 CI 真正執行測試。具簽章驗證的 Gitea webhook 狀態會標明來源；仍需打開上游 check 紀錄確認測試內容。若只需要檢視既有 GitHub、GitLab 或 Gitea 的 PR 狀態，可使用已設定的 Work 唯讀整合，無須部署 Code。

## 權限、成員與企業 SSO {#permissions-and-sso}

### 情境 {#permissions-and-sso-scenario}

管理員要讓公司成員用企業登入，並只讓每個人看到負責的專案、知識空間和程式碼專案。

### 入口與操作 {#permissions-and-sso-steps}

1. 開啟「組織管理」→「企業 SSO」，選擇 OIDC Provider 範本，填入組織的 Issuer、Client ID、Client Secret、允許網域及僅限受邀或首次登入自動建立（JIT）的帳號政策。
2. 如使用群組授權，設定 IdP groups claim 和明確的群組→產品／資源範圍對應。儲存後先按「測試連線」，再以一般成員實際登入並確認授權範圍。
3. 若要強制成員使用企業登入，確認管理員復原入口可用後才啟用 SSO-only。管理員也可在「使用者與邀請」調整產品角色和資源範圍、撤銷 session，並在「身分稽核」查閱管理記錄。

### 結果與界限 {#permissions-and-sso-result}

組織管理員授予產品與資源範圍；Work、Knowledge、Code 的產品角色各自生效。Work 使用 Manager、Worker、Reviewer；Knowledge 使用 Manager、Writer、Reader；Code 使用 Manager、Writer、Reader。SSO 登入只建立平台 session，不會自動授予任何 Project、Space、Agent、Runtime 或 Gitea 權限。受邀成員須使用管理員建立的一次性邀請；Identity 已設定 SMTP 時會寄送邀請郵件，未設定時不會寄信，管理員須透過安全管道另行提供邀請碼。

目前以 OIDC 連接 IdP；SAML 或 LDAP／Active Directory 可經選用 Keycloak broker 接入，平台未提供原生 SAML 端點。Identity 提供 SCIM 2.0 Users／Groups，但不支援 bulk，也不會依 email 自動認領既有帳號；客戶 IdP／目錄仍須逐一驗收。SSO-only、群組同步與租戶設定應依[企業登入指南](./enterprise-sso.md)及[管理指南](./guide/administration.md)核對。

## 外部工具與隔離沙箱 {#tools-and-sandbox}

### 情境 {#tools-and-sandbox-scenario}

你想讓某個 Agent 查詢內部 MCP 服務，並在獨立工作區執行分析命令，不讓工作區讀取主機檔案。

### 設定外部 MCP 工具 {#external-mcp-tool-setup}

1. 部署管理員先將 MCP 主機加入允許清單。Work 專案管理者在「工具與沙箱」新增連線，填入 HTTPS URL 和 Bearer token，選擇可用工具並按「測試 tools/list」。
2. 在 Agent 範本或「Agent 名錄」的執行設定中，只選擇該 Agent 需要使用的專案連線，再派發 Run。
3. 在 Run 詳情的事件中查看實際觀察到的工具呼叫與結果。

Token 會加密保存，之後不再顯示；目前使用 Bearer token，不支援互動式 MCP OAuth。部署預設不允許任意外部主機；私人 HTTP 或內網目標需部署管理員明確設定。外部工具可能修改上游資料，結果不明時不會自動重做；停止 Run 也不能撤銷已完成的操作。

### 設定沙箱 {#sandbox-setup}

在「工具與沙箱」為專案建立沙箱設定檔，調整命令時間、記憶體、CPU、程序數、輸出量和工作區大小，再將設定檔套用到 Agent。派發 Run 後，工具命令會在該 Run 自己的暫存工作區執行。

沙箱不連網也無法讀取主機目錄；不能線上下載依賴或任意 clone repository，只能用環境預先提供的命令和套件。Run 結束、停止或逾時後工作區會清理；要保留的檔案或測試輸出必須先提交為成果。Docker 沙箱與主機共用 kernel，不等同 VM／microVM 隔離。

![工具連線與沙箱設定](/screenshots/tools-zh-TW.png)

## Work 規劃與提報 {#work-planning-and-intake}

在 Work 側欄開啟「規劃工作區」，團隊可用看板與 Backlog 排序處理 task、story、bug 和 epic，依 Sprint、里程碑、負責者或到期日篩選，並儲存自己的查詢。管理者可設定自訂欄位、階段、事件規則和提報表單；已登入的專案成員透過表單提出需求，送出後會建立 backlog 任務。工時與報表呈現已記錄的觀察資料，CSV 匯入先整批驗證，匯出會防止公式注入。這些規劃設定不會代替執行／審查流程，也不會派發 Agent；完整操作與限制見[Work 指南](./guide/work.md)。

## Knowledge 頁面樹與註解 {#knowledge-page-tree-and-comments}

新增文件時可選 PRD、會議、ADR、SOP 範本或同 Space 的父文件；Reader 預設搜尋不顯示封存頁面。Writer／Manager 可新增帶版本引用的留言、回覆並解決討論、比較版本或以舊版建立新的還原版本。共同草稿保留 Markdown 作為唯一內容來源，工具列插入格式、連結、圖片 URL 或表格並即時預覽；這不是完整 WYSIWYG 編輯器。詳見[Knowledge 指南](./guide/knowledge.md)。

## 附件、追蹤通知與跨產品搜尋 {#shared-attachments-notifications-search}

Work Task、Knowledge 文件與 Code PR 可使用附件與協作面板，查看／上傳有權限的附件、追蹤更新、留言及提及合資格成員。共用協作中心可查看通知並標記已讀，也可跨帳號目前有權限的產品搜尋工作、文件與程式碼協作；服務無法連線時會清楚列出錯誤。附件受單檔大小限制，通知只在平台顯示，不透過 SMTP 寄送；全文搜尋不需要 LLM。

## 企業佈建、MFA 與稽核 {#enterprise-provisioning-mfa-audit}

管理員在「組織管理」的「企業治理」管理 SCIM 群組到產品／資源的明確授權、郵件佇列、稽核保留和 JSONL 匯出。SCIM 必須使用部署管理員設定的專用憑證；它不會依相同 email 自動認領或合併既有帳號，群組也不能授予 admin。若要求 MFA，Identity 會依外部 IdP 已驗證的 OIDC acr／amr claims 執行登入政策；實際第二因素由 IdP 提供。SMTP 未設定時不會寄送邀請或復原郵件。設定步驟見[管理指南](./guide/administration.md)與[企業登入指南](./enterprise-sso.md)。

## 後續操作指南 {#next-steps}

- [建立第一個專案](./guide/first-project.md)與[設定團隊](./guide/team-setup.md)
- [Work 任務、執行與審查](./guide/work.md)及[Run、工作流程、工具和沙箱操作](./execution-usage.md)
- [模型連線與 Agent 設定](./model-usage.md)
- [Knowledge 文件與引用](./guide/knowledge.md)及[Code PR](./guide/code.md)
- [管理員與企業登入](./guide/administration.md)、[企業 SSO 設定](./enterprise-sso.md)
