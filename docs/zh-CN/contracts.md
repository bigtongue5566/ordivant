# 共用 REST／Runtime 契约（v0.1） {#shared-rest-runtime-contract-v0-1}

用户选定的 Run 运行控制台、自动工作流程、不可变 Agent 范本、外部 MCP 连接与隔离运行工作区，定义于[运行契约](execution-contracts.md)。真人与 Agent 的任务认领、Knowledge 共同草稿及 Code PR 协作细节见[真人与 Agent 协作契约](collaboration-contracts.md)。此扩充保留 Agent 租约、独立审查与机密处理规则。

JSON 使用 UTF-8，时间戳记采 UTC ISO-8601，ID 为字符串。清单端点回传数组，资源端点直接回传对象。验证错误采 FastAPI 格式；领域错误为 `{ "detail": { "code": "...", "message": "..." } }`。HTTP 401 表示未验证，403 表示禁止访问，404 表示未知或无法访问，409 表示冲突，422 表示输入无效。Agent 的变更请求支持 `Idempotency-Key`。相同密钥、路由、操作者及本文会重播首次回应；本文变更时回报冲突。

## 身分验证 {#auth}

- `GET /api/health` -> `{status:"ok", database:"sqlite"|"postgresql", mode:"development"|"production"}`。
- 人类用户通过独立 Identity 服务的 HttpOnly Cookie 登录，并接受 Origin／CSRF 检查；详见[验证契约](auth-contracts.md)。两种已设置模式都会停用 `POST /api/auth/local-session`。
- REST／MCP Agent 使用 `Authorization: Bearer <token>`。`principal`：`{id,name,kind:"human"|"agent"|"runtime",role:"admin"|"manager"|"worker"|"reviewer",organization_id,project_ids:string[]}`。浏览器用户不输入 Agent token。
- `GET /api/me` -> principal。`POST /api/agents` 会一次性回传 Agent 对象及 `token`。Demo bootstrap 凭证可能存于被忽略的 `.data/bootstrap.json`；不可记录 token 内容。

## 类型 {#types}

`Project`：`{id,key,name,description,organization_id,team_id,budget_usd,created_at}`。

`Agent`：`{id,principal_id,name,role:"worker"|"reviewer",team_id,capabilities:string[],project_ids:string[],status:"available"|"busy"|"offline"|"disabled",runtime:"external"|"pi",model:string|null,model_config:ModelSelection|null,effective_model_config:ModelSelection|null,created_at}`。`principal_id` 为唯读，用来将消息／稽核操作者 ID 对应至 Agent 显示名称；任务指派使用 `id`。[模型契约](model-contracts.md)定义组织连接、加密凭证、默认值及 Agent 覆写。

凭证签发是明文记载的幂等例外：重送创建 Agent 的请求会回传同一个 Agent，并签发新的单次 token，因此原始 bearer token 不会进入回应缓存。一般变更会重播原始回应。幂等路由包含实际资源 ID，而非路径范本；重播时会重新检查目前的项目访问权。

`Task`：`{id,key,project_id,title,description,goal,inputs,scope,constraints,acceptance_criteria:string[],priority:"urgent"|"high"|"medium"|"low",status,assignee_id:string|null,assignee_principal_id:string|null,reviewer_id:string|null,reviewer_principal_id:string|null,parent_task_id:string|null,dependency_ids:string[],labels:string[],blocked_reason:string|null,progress:number,handoff:string|null,budget_usd:number,created_at,updated_at,assignee:{id,principal_id,name,kind:"human"|"agent"}|null,reviewer:{id,principal_id,name,kind:"human"|"agent"}|null}`。每个负责人字段只能指定一种身份；Agent 使用 `assignee_id`／`reviewer_id`，真人使用 `assignee_principal_id`／`reviewer_principal_id`。`inputs`、`scope`、`constraints` 是文本字符串。

`Execution`：`{id,task_id,agent_id:string|null,claimed_by_principal_id:string|null,submitted_by_principal_id:string|null,executor_id,executor_kind:"human"|"agent",executor_name,status:"running"|"submitted"|"accepted"|"rejected"|"expired"|"released",lease_expires_at:string|null,started_at,finished_at:string|null,progress:number,summary:string|null,cost_usd:number,cost_source:"self_reported"|"measured"}`。真人执行没有 Agent 租约；Agent 的防护用 `lease_token` 只会出现在 claim／renew 回应，不会出现在一般清单。

`Artifact`：`{id,task_id,execution_id,kind:"document"|"url"|"test_report"|"file"|"summary",title,uri:string|null,content:string|null,created_at}`。

`Message`：`{id,project_id,task_id:string|null,sender_id,recipient_id:string|null,kind:"question"|"reply"|"help_request"|"decision"|"handoff",body,reply_to_id:string|null,status:"delivered"|"accepted"|"completed",created_at}`。

`AuditEvent`：`{id,project_id:string|null,actor_id,action,entity_type,entity_id,data:object,created_at}`。稽核数据绝不可包含机密或防护用 token。

`TaskContext`：`{task,executions:Execution[],artifacts:Artifact[],messages:Message[],events:AuditEvent[],dependencies:Task[]}`。

## REST {#rest}

- `GET/POST /api/projects`；创建本文为 `{key,name,description?,team_id?,budget_usd?}`。
- `GET /api/projects/{id}`；`GET /api/projects/{id}/context` -> `{project,tasks,agents,decisions}`。
- `GET /api/projects/{id}/participants` -> 可在此项目被指派工作的已授权人员与 Agent。
- `GET /api/projects/{id}/vcs/pulls/{provider}/{number}?repository=owner/repo` -> `{provider,repository,number,title,state,web_url,head_sha,head,base,checks,checks_available,source:"provider_api"}`。Work 会直接读取已设置的 GitHub／GitLab／Gitea；不需要 Code。先检查项目范围，再套用服务器端 repository 白名单。不回传上游凭证。设置缺漏时回传 503；检查项目无法取得时会明确标示，绝不回报为通过。此唯读操作不能接受任务或合并 PR。
- `GET /api/tasks?project_id=&status=&q=&ready_only=true`；`POST /api/tasks` 接受上方所有可编辑的任务字段；默认为 ready／medium。会强制检查操作者范围。
- `GET /api/tasks/{id}`；`PATCH /api/tasks/{id}` 可编辑规格／相依性／指派／预算字段；生命周期状态只能通过受保护的操作变更，管理者取消或将 backlog 改为 ready 除外。Agent 没有租约时不能修改运行中字段。
- `GET /api/tasks/{id}/context`；`GET /api/tasks/{id}/executions`。
- `POST /api/tasks/{id}/claim` 本文 `{lease_seconds?:300,agent_id?:string}`。真人以登入 Cookie 呼叫且不带 `agent_id`，可认领未指派或指派给自己的 ready 任务；只有 manager／admin 可明确带入有项目权限的 `agent_id` 代表该 Agent 认领。其他 Agent 由 Bearer token 识别。真人 execution 的 Agent 与租约字段为 null，重新载入可继续；Runtime 身分绝不可冒充任意用户。
- `POST /api/tasks/{id}/renew` 仅续期 Agent 租约，本文 `{execution_id,lease_token,lease_seconds?:300}`。
- `POST /api/tasks/{id}/progress` 本文 `{execution_id,lease_token?,progress,summary?,cost_usd?}` -> task。Agent 必须带目前 fencing token；真人不带 token，由 Python 验证本人仍是执行者且保有项目权限。
- `POST /api/tasks/{id}/block` 本文 `{execution_id,lease_token?,reason,handoff?}` -> task；关闭 execution 并释放租约。真人不使用租约 token。
- `POST /api/tasks/{id}/release` 本文 `{execution_id,lease_token?,handoff}` -> task 回到 ready，execution 为 released。真人可交接并释放工作，管理者可调用 `POST /api/tasks/{id}/unblock` `{}`。
- `POST /api/tasks/{id}/submit` 本文 `{execution_id,lease_token?,summary,artifacts:[{kind,title,uri?,content?}],cost_usd?:0}` -> TaskContext。至少需要一项证据 artifact，并将状态设为 in_review；真人不使用租约 token。
- `POST /api/tasks/{id}/review` 本文 `{decision:"accept"|"reject",comment}` -> TaskContext。仅 reviewer／manager／admin 可运行；提交者不能审查自己的结果，且若已指定审查者则必须遵守。拒绝时将任务设为 ready，并保留历程与证据。
- `POST /api/tasks/{id}/delegate` 本文 `{agent_id,title,goal,description?,inputs?,scope?,constraints?,acceptance_criteria:string[],priority?,budget_usd?:0}` -> 子 Task；操作者必须是范围内的管理者或父任务的作用中负责人；子任务指派给指定 Agent；委派不能授予访问权。嵌套深度上限为 3。
- `GET/POST /api/agents`；创建本文 `{name,role,team_id?,capabilities,project_ids,runtime?,model?,model_config?}`。`PATCH /api/agents/{id}` 仅 admin／manager 可停用或编辑能力／模型。明确传入 `model_config: null` 会清除覆写并恢复继承。
- `GET /api/messages?project_id=&task_id=&inbox=true` 的收件匣收件者为目前操作者；manager 可查看其获准项目中的讨论串。`POST /api/messages` 本文 `{project_id,task_id?,recipient_id?,kind,body,reply_to_id?}` -> Message。收件者与寄件者必须共用已授权项目。回复必须属于同一任务／项目，并自动完成父问题。
- `POST /api/messages/{id}/ack` 本文 `{status:"accepted"|"completed"}` 仅收件者可运行（manager 可操作，但会留下稽核记录）。
- `GET /api/events?project_id=&task_id=` -> 由新到旧排列的稽核数组，上限 200 笔。
- `GET /api/overview?project_id=` -> `{counts:{total,ready,in_progress,blocked,in_review,done},agents:{total,available,busy},cost_usd,budget_usd,activity:AuditEvent[]}`。

## 待处理队列／Runtime {#outbox-runtime}

`POST /api/tasks/{id}/dispatch` 本文 `{agent_id}`；manager／admin 或父任务作用中负责人可调用，回传 `{id,project_id,task_id,agent_id,type:"run_task",payload:object,status:"pending",created_at}`。Agent 必须是 pi Runtime、已获准访问项目、任务为 ready 且相依任务已完成。每个任务只能有一笔待处理 dispatch。

Runtime 凭证与 Agent 凭证不同。`POST /api/runtime/outbox/claim` `{worker_id,limit?:5}` -> outbox 数组（字段也包含 `delivery_token`、`attempts`；以限时方式独占持有）。`POST /api/runtime/outbox/{id}/ack` `{worker_id,delivery_token,status:"delivered"|"failed",error?:string}`。Delivery token 可阻挡过期的确认。只有 Runtime／admin 可 claim，只有拥有者可 ack。Runtime 对外调用平台工具时，须使用各 Agent 凭证限定范围，不能使用 Runtime 权限。

Runtime 本机 HTTP API 使用 8090：`GET /health` -> engine／mode 与可用状态；`POST /runs` 本文 `{request_id,task_id,agent_id,prompt,model?}` -> `{request_id,conversation_id,submission_id,status}`；`GET /runs/{request_id}` -> 已持久化的状态／答案；`POST /runs/{request_id}/resume`；`POST /runs/{request_id}/abort`。绑定 loopback；development 以外必须设置 `ORDIVANT_RUNTIME_TOKEN`。

Runtime dispatcher 会轮询 Python outbox，并以 event ID 作为 Pi requestId。受防护且不经缓存的服务器交接会在内存中提供获指派 Agent 的凭证及已设置 Provider 的 key。支持新创建的 Agent，会同时续期 delivery 与 execution 租约，并在确认时撤销 delivery credential。已设置的 dispatch 使用即时 Responses 调用；未设置者使用文档所述的 demo fallback。模型调用失败时绝不可改用 fallback。`demo` 使用确定性 Provider，但仍使用实际 Pi Harness／storage。[模型契约](model-contracts.md)定义选取快照、收据及机密处理方式。

## MCP {#mcp}

官方 Python SDK FastMCP stdio 进程：`uv run --project backend python -m ordivant.mcp_server`；环境变量 `ORDIVANT_API_URL=http://127.0.0.1:8000`、`ORDIVANT_API_TOKEN=<scoped agent token>`。精简的异步 httpx bridge 调用 REST，以共用授权／幂等／租约检查。工具：`get_project_context`、`create_task`、`update_task`、`find_ready_tasks`、`claim_task`、`renew_lease`、`report_progress`、`get_task_context`、`block_task`、`release_task`、`submit_result`、`review_result`、`find_agents`、`request_help`、`send_message`、`read_inbox`、`delegate_task`。提供 context resources 与 task／review prompts。变更工具可接受选填的 `request_id`，并传为 `Idempotency-Key`。调用端不能指定操作者身分。

另提供 `get_vcs_pull_request(project_id,provider,repository,number)`。仅 Work 使用的 `ORDIVANT_VCS_CONFIG` 指向被忽略的 JSON：`{ "projects": { "WORK_PROJECT_ID": { "github": { "api_url": "https://api.github.com", "token": "OPTIONAL_PROVIDER_TOKEN", "repositories": ["owner/repository"] } } } }`。GitLab 使用其 `/api/v4` API base，Gitea 使用 `/api/v1`。私人企业运行个体使用已设置的 HTTPS base 与最低权限唯读 token。HTTP 默认只允许 loopback；营运者可通过 `ORDIVANT_VCS_HTTP_HOSTS` 明确列出受信任的私人服务主机。Compose 在隔离的本机容器网络中只允许 `gitea`。请求本文不能提供 API URL 或更改此政策。设置依项目与精确 repository 为单位；持有全域服务 token 不会让所有 Work 操作者取得所有 repository 的访问权。

## 本机 Seed {#local-seed}

明确运行 `uv run --project backend python -m ordivant.seed` 会创建一个示范 org、engineering 与 operations 团队、一位 manager 人类用户、worker Agent `planner`、`builder`、`analyst`，以及 reviewer `reviewer`；第二个受范围限制的项目用来证明隔离有效。主要项目 key 为 ORD。Seed 会创建包含 ready／in_progress／blocked／in_review／done 任务、相依性、消息与证据的小型拟真项目。重复 Seed 具幂等性。`.data/bootstrap.json` -> `{manager_token,runtime_token,agents:{planner:{id,token},builder:{id,token},analyst:{id,token},reviewer:{id,token}},project_id,isolated_project_id}`；`.data` 路径以 repository 根目录为基准。这些是产生的开发凭证，不得纳入版控或打印。
