# 真人与 Agent 协作契约 {#human-agent-contracts}

本次扩充以共用 Identity、产品资源范围及 Python 授权为基础。LLM 不得成为一般任务、文档或 Code 操作的前置条件。

## Work

- 保留既有 `assignee_id`、`reviewer_id` 作为 Agent ID；添加 `assignee_principal_id`、`reviewer_principal_id` 作为真人 Principal ID。每一种指派只能选真人或 Agent 其中之一。API 回传 `assignee` 与 `reviewer`，格式为 `{id,principal_id,name,kind:"human"|"agent"}` 或 null。
- `GET /api/projects/{id}/participants` 回传已授权、激活的真人与 Agent：`{id,principal_id,name,kind,role}` 数组。真人的 id 是本地 principal ID，Agent 的 id 是 Agent ID。Identity 服务的受保护 directory 提供已受邀但尚未登录 Work 的人员；不得要求同事先登录才可指派。
- 真人以自己的帐号调用既有 `POST /tasks/{id}/claim`，不带 `agent_id`。worker、manager、admin 可认领未指派或指派给自己的 ready 任务；不得代替其他真人认领，也不可认领自己被指定审查的任务。旧有管理者代运行 Agent 的明确 `agent_id` 路径保留。
- 真人 Execution 的 `agent_id`、`lease_token`、`lease_expires_at` 为 null；由 claimed_by_principal_id 表示运行者。真人工作持久保存，不使用 Agent 逾时租约。Agent 仍有防护 token 与租约。Execution 回传 `executor_id`、`executor_kind`、`executor_name`、`claimed_by_principal_id`、`submitted_by_principal_id`。
- 真人回报、提交、发布与受阻仍使用既有 action，body 的 lease_token 可省略；每次由 Python 检查目前帐号就是运行持有人及仍有项目权限。重新加载可从 context.executions 的 running 真人工作继续。
- 提交与独立审查保持分离，真人／Agent 均不得审查自己的提交。管理者可指派具 scope 的真人 worker／manager 或 Agent worker；真人 reviewer／manager 可被指定审查。其他人不能抢领已指派任务。
- 真人交接并发布会保存 handoff、结束旧运行、清除真人负责者并回到 ready，让同事接手认领。受阻与被退回则保留负责者。
- 任务消息、求助、委派与接收者均支持已授权真人与 Agent；人员委派不增加其他产品或项目的权限。自动 Pi 派发只接受 Agent 指派，不能覆盖真人任务。

## Knowledge

- 使用 Yjs 兼容的 CRDT，Python 使用 pycrdt。文档正文是根 `Y.Text("body")`。草稿与正式不可变版本分开保存于 PostgreSQL／SQLite；每次 update 成功持久化后才确认。
- `GET /api/documents/{id}/draft` 回传 `{document_id,base_version,revision,published_revision,title,body,update}`；update 是标准 base64 编码的 Yjs v1 update。reader 可读、writer／manager 可编辑。
- `POST /api/documents/{id}/draft/updates` 本文 `{update}`，与既有 Idempotency-Key／Bearer／Cookie CSRF 共用检查。Python 合并 CRDT update 并回传同一草稿结构。Agent 使用 REST／MCP 可读取并编辑同一草稿；禁止直接覆盖其他编辑者未发布的草稿。
- `POST /api/documents/{id}/draft/publish` 本文 `{expected_revision,change_summary,title?,source_refs?}`；授权 writer／manager 可把这个 revision 原子发布为新不可变版本，保留 CRDT ID 并更新 base_version／published_revision；回传既有 DocumentVersion。并行更新时回传 409，不悄悄丢弃内容。旧版本 API 与共同草稿的冲突要明确回报。
- `WS /api/documents/{id}/collaborate` 用相同 scope 检查。浏览器只使用 HttpOnly Cookie；首次消息 `{type:"authenticate",csrf_token}`，每次连接严格验证 Origin，定期重新验证 session／scope。不得在 URL 带凭证。未验证前不传文档或 presence。
- 服务器消息 `{type:"sync",draft:上述结构,participants:[{id,name,kind}]}`；client update `{type:"update",update,request_id}`，成功回 `{type:"ack",request_id,draft}`；presence `{type:"presence",participants}`；错误 `{type:"error",code,message,request_id?}`。服务器主动传已提交的最新 CRDT，并以 DB 轮询支持多进程与重启。重连须合并本地尚未确认的更新，UI 清楚表示未保存或失去权限；不能显示虚假的已保存。
- 更新大小、文档大小、频率与连接数有上限；reader 不能 update。presence 的身分由服务器取得，不能由 client 冒用。编辑与发布稽核标示真人或 Agent。

## Code 与验收 {#code-acceptance}

Code 保留 Gitea 作为 Git／PR／合并权威来源。Ordivant 另外保存真人及 Agent 共用的 PR 讨论与审查收据；不能冒充 Gitea 核准、CI 或 Work 验收。操作者由服务器验证，不由本文指定。

- `GET /api/repositories/{repository_id}/pulls/{number}/collaboration` 回传 `{pull_request_id,head_sha,proposer,comments,reviews}`；author／proposer 为 `{id,name,kind}`，无法从已验证的创建纪录识别 proposer 时为 null，不推测上游服务帐号就是操作者。
- `POST .../comments` 本文 `{body}`；`POST .../reviews` 本文 `{decision:"approve"|"request_changes"|"comment",comment,expected_head_sha}`。沿用 Idempotency-Key、scope 与 writer／manager／admin 权限，reader 只能读取。
- 审查读取 Gitea 目前 head，与 expected_head_sha 不符时回传 409；提案者不得核准或要求变更自己的 PR，已关闭 PR 只能留下 comment。历史保留 head_sha，GET 依目前 head 计算 is_current；代码变更使旧审查失效而不删除历史。
- REST 与 MCP 调用共用服务；本地讨论及审查与稽核、幂等收据在同一交易保存。Gitea API 失败不得使用假数据回复成功。

验收涵盖未设置 LLM 的两人指派／认领／成果／独立审查，两位文档编辑者与 Agent 的并行合并、断线重连、重启持久性、跨范围／reader／注销拒绝、Gitea PR 讨论与审查，以及三语 UI 与容器模式。不得使用真实用户密码或付费模型测试。
