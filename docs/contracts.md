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

`Agent`：`{id,principal_id,name,role:"worker"|"reviewer",team_id,capabilities:string[],project_ids:string[],status:"available"|"busy"|"offline"|"disabled",runtime:"external"|"pi",model:string|null,model_config:ModelSelection|null,effective_model_config:ModelSelection|null,created_at}`。`principal_id` 為唯讀，用來將訊息／稽核操作者 ID 對應至 Agent 顯示名稱；任務指派使用 `id`。[模型契約](model-contracts.md)定義組織連線、加密憑證、預設值及 Agent 覆寫。

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
- `GET /api/messages?project_id=&task_id=&inbox=true` 的收件匣收件者為目前操作者；manager 可檢視其獲准專案中的討論串。`POST /api/messages` 本文 `{project_id,task_id?,recipient_id?,kind,body,reply_to_id?}` -> Message。收件者與寄件者必須共用已授權專案。回覆必須屬於同一任務／專案，並自動完成父問題。
- `POST /api/messages/{id}/ack` 本文 `{status:"accepted"|"completed"}` 僅收件者可執行（manager 可操作，但會留下稽核記錄）。
- `GET /api/events?project_id=&task_id=` -> 由新到舊排列的稽核陣列，上限 200 筆。
- `GET /api/overview?project_id=` -> `{counts:{total,ready,in_progress,blocked,in_review,done},agents:{total,available,busy},cost_usd,budget_usd,activity:AuditEvent[]}`。

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
