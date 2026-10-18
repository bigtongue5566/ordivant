# 共用 REST／Runtime 契約（v0.1） {#shared-rest-runtime-contract-v0-1}

使用者選定的 Run 執行控制台、自動工作流程、不可變 Agent 範本、外部 MCP 連線與隔離執行工作區，定義於[執行契約](execution-contracts.md)。真人與 Agent 的任務認領、Knowledge 共同草稿及 Code PR 協作細節見[真人與 Agent 協作契約](collaboration-contracts.md)。此擴充保留 Agent 租約、獨立審查與機密處理規則。

JSON 使用 UTF-8，時間戳記採 UTC ISO-8601，ID 為字串。清單端點回傳陣列，資源端點直接回傳物件。驗證錯誤採 FastAPI 格式；領域錯誤為 `{ "detail": { "code": "...", "message": "..." } }`。HTTP 401 表示未驗證，403 表示禁止存取，404 表示未知或無法存取，409 表示衝突，422 表示輸入無效。Agent 的變更請求支援 `Idempotency-Key`。相同金鑰、路由、操作者及本文會重播首次回應；本文變更時回報衝突。

## 身分驗證 {#auth}

- `GET /api/health` -> `{status:"ok", database:"sqlite"|"postgresql", mode:"development"|"production"}`。
- 人類使用者透過獨立 Identity 服務的 HttpOnly Cookie 登入，並接受 Origin／CSRF 檢查；詳見[驗證契約](auth-contracts.md)。兩種已設定模式都會停用 `POST /api/auth/local-session`。
- REST／MCP Agent 使用 `Authorization: Bearer <token>`。`principal`：`{id,name,kind:"human"|"agent"|"runtime",role:"admin"|"manager"|"worker"|"reviewer",organization_id,project_ids:string[]}`。瀏覽器使用者不輸入 Agent token。
- `GET /api/me` -> principal。`POST /api/agents` 會一次性回傳 Agent 物件及 `token`。Demo bootstrap 憑證可能存於被忽略的 `.data/bootstrap.json`；不可記錄 token 內容。

## 型別 {#types}

`Project`：`{id,key,name,description,organization_id,team_id,budget_usd,created_at}`。

`Agent`：`{id,principal_id,name,role:"worker"|"reviewer",team_id,capabilities:string[],project_ids:string[],status:"available"|"busy"|"offline"|"disabled"|"archived",runtime:"external"|"pi",model:string|null,model_config:ModelSelection|null,effective_model_config:ModelSelection|null,created_at}`。`principal_id` 為唯讀，用來將訊息／稽核操作者 ID 對應至 Agent 顯示名稱；任務指派使用 `id`。[模型契約](model-contracts.md)定義組織連線、加密憑證、預設值及 Agent 覆寫。

憑證簽發是明文記載的冪等例外：重送建立 Agent 的請求會回傳同一個 Agent，並簽發新的單次 token，因此原始 bearer token 不會進入回應快取。一般變更會重播原始回應。冪等路由包含實際資源 ID，而非路徑範本；重播時會重新檢查目前的專案存取權。

`Task`：`{id,key,project_id,title,description,goal,inputs,scope,constraints,acceptance_criteria:string[],priority:"urgent"|"high"|"medium"|"low",status,assignee_id:string|null,assignee_principal_id:string|null,reviewer_id:string|null,reviewer_principal_id:string|null,parent_task_id:string|null,dependency_ids:string[],labels:string[],blocked_reason:string|null,progress:number,handoff:string|null,budget_usd:number,created_at,updated_at,assignee:{id,principal_id,name,kind:"human"|"agent"}|null,reviewer:{id,principal_id,name,kind:"human"|"agent"}|null}`。每個負責人欄位只能指定一種身分；Agent 使用 `assignee_id`／`reviewer_id`，真人使用 `assignee_principal_id`／`reviewer_principal_id`。`inputs`、`scope`、`constraints` 是文字字串。

`Execution`：`{id,task_id,agent_id:string|null,claimed_by_principal_id:string|null,submitted_by_principal_id:string|null,executor_id,executor_kind:"human"|"agent",executor_name,status:"running"|"submitted"|"accepted"|"rejected"|"expired"|"released",lease_expires_at:string|null,started_at,finished_at:string|null,progress:number,summary:string|null,cost_usd:number,cost_source:"self_reported"|"measured"}`。真人執行沒有 Agent 租約；Agent 的防護用 `lease_token` 只會出現在 claim／renew 回應，不會出現在一般清單。

`Artifact`：`{id,task_id,execution_id,kind:"document"|"url"|"test_report"|"file"|"summary",title,uri:string|null,content:string|null,created_at}`。

`Message`：`{id,project_id,task_id:string|null,sender_id,recipient_id:string|null,kind:"question"|"reply"|"help_request"|"decision"|"handoff",body,reply_to_id:string|null,status:"delivered"|"accepted"|"completed",created_at}`。

`AuditEvent`：`{id,project_id:string|null,actor_id,action,entity_type,entity_id,data:object,created_at}`。稽核資料絕不可包含機密或防護用 token。

`TaskContext`：`{task,executions:Execution[],artifacts:Artifact[],messages:Message[],events:AuditEvent[],dependencies:Task[]}`。

## REST {#rest}

- `GET/POST /api/projects`；建立本文為 `{key,name,description?,team_id?,budget_usd?}`。
- `GET /api/projects/{id}`；`GET /api/projects/{id}/context` -> `{project,tasks,agents,decisions}`。
- `GET /api/projects/{id}/participants` -> 此專案已授權的真人與 Agent，供管理者指派任務。
- `GET /api/projects/{id}/vcs/pulls/{provider}/{number}?repository=owner/repo` -> `{provider,repository,number,title,state,web_url,head_sha,head,base,checks,checks_available,source:"provider_api"}`。Work 會直接讀取已設定的 GitHub／GitLab／Gitea；不需要 Code。先檢查專案範圍，再套用伺服器端 repository 白名單。不回傳上游憑證。設定缺漏時回傳 503；檢查項目無法取得時會明確標示，絕不回報為通過。此唯讀操作不能接受任務或合併 PR。
- `GET /api/tasks?project_id=&status=&q=&ready_only=true`；`POST /api/tasks` 接受上方所有可編輯的任務欄位；預設為 ready／medium。會強制檢查操作者範圍。
- `GET /api/tasks/{id}`；`PATCH /api/tasks/{id}` 可編輯規格／相依性／指派／預算欄位；生命週期狀態只能透過受保護的操作變更，管理者取消或將 backlog 改為 ready 除外。Agent 沒有租約時不能修改執行中欄位。
- `GET /api/tasks/{id}/context`；`GET /api/tasks/{id}/executions`。
- `POST /api/tasks/{id}/claim` 本文 `{lease_seconds?:300,agent_id?:string}`。真人以登入 Cookie 呼叫且不帶 `agent_id`，可認領未指派或指派給自己的 ready 任務；Manager／admin 可明確帶入有專案權限的 `agent_id`，代表該 Agent 認領。Agent 身分由 Bearer token 推斷。真人 execution 的 `agent_id` 與租約欄位為 null，重載頁面可繼續；Runtime 身分絕不可冒充任意使用者。
- `POST /api/tasks/{id}/renew` 僅續期 Agent 租約，本文 `{execution_id,lease_token,lease_seconds?:300}`。
- `POST /api/tasks/{id}/progress` 本文 `{execution_id,lease_token?,progress,summary?,cost_usd?}` -> task。Agent 必須帶目前 fencing token；真人不帶 token，由 Python 驗證本人仍是執行者且保有專案權限。
- `POST /api/tasks/{id}/block` 本文 `{execution_id,lease_token?,reason,handoff?}` -> task；關閉 execution 並釋放租約。真人不使用租約 token。
- `POST /api/tasks/{id}/release` 本文 `{execution_id,lease_token?,handoff}` -> task 回到 ready，execution 為 released。真人可交接並釋出工作，管理者可呼叫 `POST /api/tasks/{id}/unblock` `{}`。
- `POST /api/tasks/{id}/submit` 本文 `{execution_id,lease_token?,summary,artifacts:[{kind,title,uri?,content?}],cost_usd?:0}` -> TaskContext。至少需要一項證據 artifact，並將狀態設為 in_review；真人不使用租約 token。
- `POST /api/tasks/{id}/review` 本文 `{decision:"accept"|"reject",comment}` -> TaskContext。僅 reviewer／manager／admin 可執行；提交者不能審查自己的結果，且若已指定審查者則必須遵守。拒絕時將任務設為 ready，並保留歷程與證據。
- `POST /api/tasks/{id}/delegate` 本文 `{agent_id,title,goal,description?,inputs?,scope?,constraints?,acceptance_criteria:string[],priority?,budget_usd?:0}` -> 子 Task；操作者必須是範圍內的管理者或父任務的作用中負責人；子任務指派給指定 Agent；委派不能授予存取權。巢狀深度上限為 3。
- `GET/POST /api/agents`；建立本文 `{name,role,team_id?,capabilities,project_ids,runtime?,model?,model_config?}`。`PATCH /api/agents/{id}` 僅 admin／manager 可停用或編輯能力／模型。明確傳入 `model_config: null` 會清除覆寫並恢復繼承。
- `GET /api/agents?project_id=&include_archived=false` 預設隱藏已封存 Agent。`POST /api/agents/{id}/archive` 與 `DELETE /api/agents/{id}` 必須提供 `Idempotency-Key`，操作者需為同組織的 manager/admin，並有該 Agent 所屬全部專案的權限。未結束的任務（含指定審核）、執行中或排隊中的執行，以及啟用中的規則／排程引用都會阻擋操作。只有沒有業務歷史或設定引用的 Agent 才能永久刪除；專用憑證、成員資格、設定及未使用的身分會在同一交易移除。封存設定 `status:"archived"`、停用身分並撤銷 token，同時保留證據及名稱；PATCH 不允許重新啟用或編輯。兩種操作均保留稽核收據；Agent 刪除後，重試仍依快取的組織與專案範圍重新驗證權限。MCP 的 `find_agents(include_archived)`、`archive_agent` 與 `delete_agent` 使用相同 REST 檢查，無需 LLM。既有狀態欄位可容納新值，不需資料庫結構遷移。
- `GET /api/messages?project_id=&task_id=&inbox=true` 的收件匣收件者為目前操作者；manager 可檢視其獲准專案中的討論串。`POST /api/messages` 本文 `{project_id,task_id?,recipient_id?,kind,body,reply_to_id?}` -> Message。收件者與寄件者必須共用已授權專案。回覆必須屬於同一任務／專案，並自動完成父問題。
- `POST /api/messages/{id}/ack` 本文 `{status:"accepted"|"completed"}` 僅收件者可執行（manager 可操作，但會留下稽核記錄）。
- `GET /api/events?project_id=&task_id=` -> 由新到舊排列的稽核陣列，上限 200 筆。
- `GET /api/overview?project_id=` -> `{counts:{total,ready,in_progress,blocked,in_review,done},agents:{total,available,busy},cost_usd,budget_usd,activity:AuditEvent[]}`。

## P0/P1 規劃與企業契約 {#p0-p1-planning-enterprise-contracts}

本節補充目前規劃中的 Work、Knowledge、共用協作與企業 API 保證。人類與 Agent 共用產品資源授權；各服務只讀取自己的資料庫。使用者操作及 REST／MCP 正常流程不需要 LLM。每項功能的整合驗收狀態見[專案計畫的 P0/P1 驗收清單](project-plan.md#p0-p1-acceptance-ledger)。

### Work 規劃 {#p0-p1-work-planning-contract}

Task 規劃欄位包括 `work_type`、同專案且不可循環的 `epic_id`、`start_at`、`due_at`、`sprint_id`、`milestone_id`、非負 `estimate_points`、`rank`、`stage_id` 及依專案定義驗證的 `custom_fields`。這些欄位是規劃中繼資料，不是執行狀態。任務清單依 rank 和建立時間排序，篩選依類型、Sprint、里程碑、負責者及逾期狀態。

`GET /api/projects/{id}/planning` 回傳 Sprint、里程碑、自訂欄位、階段、規則與表單。`POST /api/projects/{id}/sprints` 與 `PATCH /api/sprints/{sprint_id}` 管理 Sprint；里程碑、自訂欄位、階段、規則、表單分別使用 `/api/projects/{id}/milestones`、`/fields`、`/stages`、`/rules`、`/forms` 建立，並透過各資源 ID 的 PATCH 修改。`POST /api/projects/{id}/reorder` 只調整專案內唯一任務 ID 的 rank。規劃設定需要既有 manager/admin 權限；每個專案同時最多一個 active Sprint，關閉 Sprint 不會完成任務。已使用的自訂欄位不可更換 key 或型別；階段的 category 必須等於任務目前狀態。

只有 backlog、ready、cancelled 的既有核准轉移可由看板規劃操作；in_progress、blocked、in_review、done 仍由執行與獨立審查控制。規則只在一般任務建立／更新時同步觸發，可加標籤、指派負責人或將 backlog 轉成 ready；須確認建立規則的 manager 目前仍有權限，且每個事件／規則去重、不遞迴、不呼叫 LLM、不派發 Agent。

登入中的專案成員可透過 `GET /api/forms/{id}` 和 `POST /api/forms/{id}/submit` 提交提報；提交建立待整理 backlog 任務，不授予匿名或額外專案權限。`POST/GET /api/tasks/{id}/worklogs` 由登入主體記錄正數分鐘和開始時間；不能替他人或 Agent 偽造工時。每週容量是管理員明確設定的分鐘數，不會推估；使用率以該週已記錄工時對照設定容量。週期由任務首次 execution start 計至 `task.review.accept`，包含重做和等待獨立審查，並非工時。`GET /api/projects/{id}/reports` 回報已觀察到的週期／工時與容量，不提供未支援的預測。CSV 匯入需有界限並原子驗證，錯誤不得留下部分寫入；匯出須防止試算表公式注入。`/api/saved-queries` 儲存操作者自己的篩選，讀取時仍重新檢查目前權限。

### Knowledge 編輯 {#p0-p1-knowledge-authoring-contract}

文件 `parent_id` 只能指向同 Space 文件並拒絕循環。預設清單排除 archived；封存父文件若仍有子文件必須先移動子文件，不能靜默遺失階層。`PATCH /api/documents/{id}/organization` 使用既有 Space 權限，沒有文件級 ACL。

`GET/POST /api/documents/{id}/comments` 建立文件留言、同文件一層回覆和選用的已發佈版本引用；`PATCH /api/document-comments/{id}` 解決或重新開啟留言。引用保留原文字句與版本，版本更新後須標示 stale；留言是有上限的純文字並安全顯示。讀者可檢視，具 writer 權限者可留言與處理留言。`GET/POST /api/spaces/{id}/templates` 列出／建立 Space 範本；內建 PRD、meeting、ADR、SOP 可供文件建立時選用。

`GET /api/documents/{id}/diff?from_version=N&to_version=M` 只讀比較使用者可讀取的不可變版本。`POST /api/documents/{id}/restore` 必須帶目標版本與 expected current version，以 compare-and-swap 新增版本；舊版本不改寫，若目前版本已變或共用草稿尚有未發佈協作者修改即拒絕。共同草稿以 Y.Text Markdown 作唯一 canonical 內容；工具列及即時預覽仍編輯同一份 Markdown，不是第二套 WYSIWYG/block 內容。

### 共用協作與搜尋 {#p0-p1-shared-collaboration-contract}

各產品的 `/api/collaboration/{kind}/{id}` 提供附件清單／新增、訂閱、參與者、討論留言及通知；下載使用 `/api/collaboration/attachments/{attachment_id}/download`，通知使用 `/api/collaboration/notifications` 和單筆 read 操作。8 個共用 MCP 工具使用相同服務授權，不可繞過 REST 的資源範圍。產品服務每次列出或下載時重新驗證資源權限；附件大小有界、保存雜湊且不可變，檔名安全處理，不會因提交 URL 而抓取外部內容。提及只能選目前有權參與資源的 principal。狀態與通知同一交易提交；權限撤銷後通知導向會重新驗證且不洩漏資源正文。

共用中心聚合的是 Work、Knowledge、Code 各自服務提供的通知與搜尋結果，不跨讀資料庫。搜尋只回傳目前可存取的項目，並個別回報不可用的服務。追蹤與協作通知顯示於平台，不代表有 SMTP 寄件；寄件只適用已設定 SMTP 的 Identity 邀請／復原 outbox。

### Identity、SCIM 與上游 Git 邊界 {#p0-p1-identity-and-git-contract}

SCIM 2 Users／Groups 位於 `/api/scim/v2`，使用獨立部署憑證。佈建建立已存在 email 的使用者時必須回報衝突；不能依 email 自動認領或合併既有 Ordivant 帳號。群組只授予企業治理中明確配置的產品角色與 resource IDs，不能授予 admin；停用使用者及授權變更會撤銷現有 sessions。一般 SCIM user PATCH 不可直接改權限；明確 SSO 帳號連結要以 `managed_permissions=false` 保留 SCIM 群組權限的管理來源。SCIM bulk 不支援。

OIDC `required_acr` 與 `required_amr` 只驗證外部 IdP 簽發且已驗證的 claims：`acr` 必須匹配設定值其中之一，`amr` 必須包含全部指定方式。設定 assurance 要求時成員必須走 SSO-only；第二因素由 IdP 實際執行，平台不自行產生 MFA。SMTP 邀請／復原信件透過持久 outbox 送出；未設定寄件服務時不寄信。管理員可查看佇列及重試未過期項目。稽核匯出受 admin 保護、有筆數／時間界限並篩選機密欄位；保留設定只有明確套用時才刪除到期舊紀錄。

P1 Git 接受條件要求 provider 證據包含上游 URL、commit SHA 和來源；真實 checks／actions／pipelines／deployment 只能由上游結果證實，Agent receipt 不可當 CI。Code 的 `ORDIVANT_CODE_DEPLOYMENT_CONFIG_FILE` 由部署端提供 JSON；`providers[]` 可設定 `provider` (`github`／`gitlab`)、`token_file` 和以本機 repository UUID 為 key 的 `repositories` 對應。GitHub 對應使用 `owner`／`name`，GitLab 使用 `project`；API 主機固定為 `api.github.com` 與 `gitlab.com/api/v4`，不接受自訂主機。此 provider 只讀取符合當前 PR head SHA 的部署記錄，不會啟動 pipeline 或部署；沒有 provider／credential 時必須明確顯示不可用。inline comment 綁定精確 PR head、檔案與行號，head SHA 變更時標示 stale。Merge 治理以實際上游 branch protection、review 和 checks 為準，Ordivant 本地審查不能冒充上游核准。

## 待處理佇列／Runtime {#outbox-runtime}

`POST /api/tasks/{id}/dispatch` 本文 `{agent_id}`；manager／admin 或父任務作用中負責人可呼叫，回傳 `{id,project_id,task_id,agent_id,type:"run_task",payload:object,status:"pending",created_at}`。Agent 必須是 pi Runtime、已獲准存取專案、任務為 ready 且相依任務已完成。每個任務只能有一筆待處理 dispatch。

Runtime 憑證與 Agent 憑證不同。`POST /api/runtime/outbox/claim` `{worker_id,limit?:5}` -> outbox 陣列（欄位也包含 `delivery_token`、`attempts`；以限時方式獨占持有）。`POST /api/runtime/outbox/{id}/ack` `{worker_id,delivery_token,status:"delivered"|"failed",error?:string}`。Delivery token 可阻擋過期的確認。只有 Runtime／admin 可 claim，只有擁有者可 ack。Runtime 對外呼叫平台工具時，須使用各 Agent 憑證限定範圍，不能使用 Runtime 權限。

Runtime 本機 HTTP API 使用 8090：`GET /health` -> engine／mode 與可用狀態；`POST /runs` 本文 `{request_id,task_id,agent_id,prompt,model?}` -> `{request_id,conversation_id,submission_id,status}`；`GET /runs/{request_id}` -> 已持久化的狀態／答案；`POST /runs/{request_id}/resume`；`POST /runs/{request_id}/abort`。綁定 loopback；development 以外必須設定 `ORDIVANT_RUNTIME_TOKEN`。

Runtime dispatcher 會輪詢 Python outbox，並以 event ID 作為 Pi requestId。受防護且不經快取的伺服器交接會在記憶體中提供獲指派 Agent 的憑證及已設定 Provider 的 key。支援新建立的 Agent，會同時續期 delivery 與 execution 租約，並在確認時撤銷 delivery credential。已設定的 dispatch 使用即時 Responses 呼叫；未設定者使用文件所述的 demo fallback。模型呼叫失敗時絕不可改用 fallback。`demo` 使用確定性 Provider，但仍使用實際 Pi Harness／storage。[模型契約](model-contracts.md)定義選取快照、收據及機密處理方式。

## MCP {#mcp}

官方 Python SDK FastMCP stdio 程序：`uv run --project backend python -m ordivant.mcp_server`；環境變數 `ORDIVANT_API_URL=http://127.0.0.1:8000`、`ORDIVANT_API_TOKEN=<scoped agent token>`。精簡的非同步 httpx bridge 呼叫 REST，以共用授權／冪等／租約檢查。工具：`get_project_context`、`create_task`、`update_task`、`find_ready_tasks`、`claim_task`、`renew_lease`、`report_progress`、`get_task_context`、`block_task`、`release_task`、`submit_result`、`review_result`、`find_agents`、`request_help`、`send_message`、`read_inbox`、`delegate_task`。提供 context resources 與 task／review prompts。變更工具可接受選填的 `request_id`，並傳為 `Idempotency-Key`。呼叫端不能指定操作者身分。

另提供 `get_vcs_pull_request(project_id,provider,repository,number)`。僅 Work 使用的 `ORDIVANT_VCS_CONFIG` 指向被忽略的 JSON：`{ "projects": { "WORK_PROJECT_ID": { "github": { "api_url": "https://api.github.com", "token": "OPTIONAL_PROVIDER_TOKEN", "repositories": ["owner/repository"] } } } }`。GitLab 使用其 `/api/v4` API base，Gitea 使用 `/api/v1`。私人企業執行個體使用已設定的 HTTPS base 與最低權限唯讀 token。HTTP 預設只允許 loopback；營運者可透過 `ORDIVANT_VCS_HTTP_HOSTS` 明確列出受信任的私人服務主機。Compose 在隔離的本機容器網路中只允許 `gitea`。請求本文不能提供 API URL 或更改此政策。設定依專案與精確 repository 為單位；持有全域服務 token 不會讓所有 Work 操作者取得所有 repository 的存取權。

## 本機 Seed {#local-seed}

明確執行 `uv run --project backend python -m ordivant.seed` 會建立一個示範 org、engineering 與 operations 團隊、一位 manager 人類使用者、worker Agent `planner`、`builder`、`analyst`，以及 reviewer `reviewer`；第二個受範圍限制的專案用來證明隔離有效。主要專案 key 為 ORD。Seed 會建立包含 ready／in_progress／blocked／in_review／done 任務、相依性、訊息與證據的小型擬真專案。重複 Seed 具冪等性。`.data/bootstrap.json` -> `{manager_token,runtime_token,agents:{planner:{id,token},builder:{id,token},analyst:{id,token},reviewer:{id,token}},project_id,isolated_project_id}`；`.data` 路徑以 repository 根目錄為基準。這些是產生的開發憑證，不得納入版控或列印。

## 專案設定更新 {#project-settings-update}

`PATCH /api/projects/{id}` 與 MCP `update_project` 共用專案成員資格及 manager/admin 授權檢查。本文為 `{name,description,budget_usd,expected:{name,description,budget_usd}}`，`expected` 必填且須符合目前資料，否則回傳 409 `project_settings_changed`。名稱去除首尾空白後須為 1–200 字元，說明最多 20,000 字元，預算須為有限的非負數；代碼、組織與團隊不可修改。成功回傳 Project，變更寫入 `project.updated` 稽核。支援冪等金鑰，重播時重新檢查現有角色與專案存取權。MCP 的 `request_id` 對應該金鑰。
