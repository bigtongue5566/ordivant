<span id="架構與-api-索引"></span>
<span id="架构与-api-索引"></span>

# 架构与 API 索引 {#architecture-and-api-reference}

<span id="業務契約"></span>
<span id="业务契约"></span>

## 产品边界与集成规则 {#business-contracts}

Work、Knowledge、Code 可独立部署，各自拥有业务 API、MCP、数据库及授权范围。Identity 提供共用账号与登录；登录一次不代表自动取得每个产品或项目的权限。Runtime 执行 Work 派发的工作，沙箱执行器则负责隔离命令。所有业务授权仍由各产品的 Python 服务检查。

| 服务 | 责任与边界 |
| --- | --- |
| Work | 项目、任务、依赖、租约、协作、审核与 Run；可直接引用现有企业 VCS，无需启用 Code |
| Knowledge | 空间、文档、不可变版本、引用与决策；引用其他产品不会授予其访问权 |
| Code | 项目范围内的 repository、branch、commit、PR 与状态收据；Gitea 保存实际 Git 状态 |
| Identity | 账号、邀请、登录会话、产品授权与 OIDC SSO；使用独立数据库 |
| Runtime／沙箱 | 执行与逐字记录／隔离命令；不能取代 Work 的任务状态与独立审核 |

API 使用 UTF-8 JSON、字符串 ID 与 UTC ISO-8601 时间。领域错误格式为 `{"detail":{"code":"...","message":"..."}}`；字段验证错误使用 FastAPI 格式。常见 HTTP 状态为 `401` 未登录、`403` 无权限、`404` 不存在或不可访问、`409` 冲突、`422` 输入不合法。

Agent 使用各产品限定范围的 Bearer token；用户使用 Identity 的 Cookie 会话。Cookie 变更请求需遵循来源与 CSRF 检查。操作者由凭证决定，不能在请求正文指定其他 `actor`。连接 Identity 的部署不提供旧的本地会话登录。

可重试的变更请使用 `Idempotency-Key`，并在重试时保持相同 key、路由及正文。相同操作者的相同请求会重播结果，变更正文会造成冲突；当前授权仍会重新检查。租约操作需提交当前有效的 fencing token，文档发布与文件更新则需遵循 API 的版本检查。完整字段以实际部署的 OpenAPI 为准。

<span id="rest-文件"></span>
<span id="rest-文档"></span>

## REST 文档 {#rest-documentation}

原生开发模式启动后，各 FastAPI 服务的 `/docs` 与 `/openapi.json` 提供当前版本的请求、响应及字段结构。以下是默认设置；部署者可调整端口：

| 服务 | 开发 API 地址 | 套件网页的代理前缀 |
| --- | --- | --- |
| Work | `http://127.0.0.1:8000/api` | `/api` |
| Knowledge | `http://127.0.0.1:8010/api` | `/knowledge-api` |
| Code | `http://127.0.0.1:8020/api` | `/code-api` |
| Identity | `http://127.0.0.1:8030/api/auth` | `/auth-api` |

下方业务端点使用服务本身的路径。例如套件中 Knowledge 的 `GET /api/spaces` 经网页来源调用时为 `GET /knowledge-api/spaces`。独立产品模式的 `/api` 会指向选定产品。生产环境的 Nginx 只公开业务 API 前缀；请在受信任的开发环境查看结构描述，不要为此对外公开内部服务。

### Work 任务与执行 {#work-api}

| 端点 | 用途 |
| --- | --- |
| `GET/POST /api/projects`、`GET/POST /api/tasks` | 查询及创建获授权的项目／任务 |
| `GET /api/tasks/{task_id}/context` | 取得任务、依赖、消息与证据上下文 |
| `GET /api/projects/{project_id}/participants` | 列出可在该项目指派工作的已授权人员与 Agent |
| `POST /api/tasks/{task_id}/claim` | 真人以自己的登录身份认领；Agent 使用 Bearer token 认领并取得租约 |
| `POST /api/tasks/{task_id}/renew` | 续期 Agent 租约；真人工作没有租约 |
| `POST /api/tasks/{task_id}/progress`、`release` | 回报进度或释放执行；真人不传租约 token |
| `POST /api/tasks/{task_id}/submit`、`review` | 提交证据及由有权限的独立审核者决定结果 |
| `POST /api/tasks/{task_id}/dispatch` | 派发 Agent 执行；取得 Run 后再追踪执行状态 |
| `GET /api/runs`、`GET /api/runs/{run_id}/events`、`POST /api/runs/{run_id}/control` | Run 列表、事件与控制 |
| `/api/agent-templates`、`/api/workflows`、`/api/workflow-runs` | Agent 模板、工作流程定义及工作流程执行 |
| `/api/tool-connections`、`/api/sandbox-profiles` | 管理获允许的工具连接与沙箱设置 |

任务与 Run 是不同记录。执行成功不会自动使任务完成；仍需证据与独立审核。执行模式、暂停／停止限制及工具设置见[执行指南](./execution-usage.md)。`/api/runtime/*` 是受限服务接口，不供一般 Agent 或浏览器调用。

真人认领会记录真人执行者，不会建立 Agent 租约；重新载入可继续进行中的工作。Agent 认领才使用到期时间与 fencing token。真人与 Agent 的权限、指派及交接规则见[真人与 Agent 协作契约](./collaboration-contracts.md)。

### Knowledge 文档与版本 {#knowledge-api}

| 端点 | 用途 |
| --- | --- |
| `GET/POST /api/spaces` | 知识空间 |
| `GET /api/documents?space_id=&q=&tag=`、`POST /api/documents` | 搜索及创建文档 |
| `GET /api/documents/{document_id}/versions` | 取得版本历史 |
| `GET /api/documents/{document_id}/versions/{version_number}` | 读取可引用的精确版本 |
| `POST /api/documents/{document_id}/versions` | 旧发布入口；网页编辑器会引导至共同草稿 |
| `GET /api/documents/{document_id}/draft`、`POST /api/documents/{document_id}/draft/updates` | 读取共同草稿并提交 CRDT 更新 |
| `WS /api/documents/{document_id}/collaborate` | 使用登录会话同步草稿和真人 presence |
| `POST /api/documents/{document_id}/draft/publish` | 将已保存的共同草稿发布为不可变版本 |
| `GET/POST /api/decisions`、`GET /api/events` | 决策及获授权的审计记录 |

已发布版本不可变更。只有编辑器在线、更新均已保存且没有待确认更新时才能发布；未收到确认的离线编辑只保留在当前浏览器内存中，关闭页面可能丢失。Agent 可通过 REST/MCP 访问同一份共同草稿。来源引用保留精确版本与 URI，不会扩大访问权。操作流程见[Knowledge 指南](./guide/knowledge.md)。

### Code 与版本控制 {#code-api}

| 端点 | 用途 |
| --- | --- |
| `GET/POST /api/projects`、`GET/POST /api/repositories` | 项目及绑定的 repository |
| `POST /api/repositories/{repository_id}/branches`、`files` | 创建分支及提交文件 |
| `GET/POST /api/repositories/{repository_id}/pulls` | 查询及创建 PR |
| `GET /api/repositories/{repository_id}/pulls/{number}` | PR 详情、来源引用与状态收据 |
| `GET /api/repositories/{repository_id}/pulls/{number}/collaboration` | Ordivant 讨论、审查记录与当前 PR head |
| `POST /api/repositories/{repository_id}/pulls/{number}/comments` | 添加 Ordivant 本地 PR 讨论 |
| `POST /api/repositories/{repository_id}/pulls/{number}/reviews` | 针对预期 head SHA 记录 Ordivant 审查 |
| `POST /api/repositories/{repository_id}/checks` | 回报明确标示为 Agent 自报的 commit 状态 |

Code 的 Git 操作需要设置 Gitea。Ordivant 讨论与审查是绑定 PR head SHA 的本地记录，不等同 Gitea 核准或 CI 结果。Gitea 仍负责 Git、合并及其自身的核准流程。此版本不提供 PR 合并或删除 API，也不包含 CI runner。`agent_reported` 收据不能当成实际 CI 执行证据。详见[Code 指南](./guide/code.md)和[真人与 Agent 协作契约](./collaboration-contracts.md)。

### 模型设置 {#model-settings}

`GET/PUT /api/model-settings` 限组织管理员使用；`GET /api/model-catalog` 提供已授权操作者可选的模型，均不返回 API key。设置包含 `providers`、组织 `default` 与 `revision`。更新现有设置必须提交读取到的 `revision`，以防覆盖他人的修改。

Agent 的 `model_config` 可覆盖默认值，设为 `null` 则继承组织设置。选择包含 `provider_id`、`model_id`、`reasoning_effort`、`max_output_tokens`；实际派发会保存不含秘密的设置快照。模型失败不会切换成 DEMO。模型限制是管理员提供的设置值，未知用量或费用不会伪造。完整操作见[模型指南](./model-usage.md)。

### Identity 与 SSO {#identity-api}

Identity 原生端点以 `/api/auth` 为前缀，套件网页使用 `/auth-api`。`status`／`setup` 用于第一次创建管理员，`login`／`me`／`logout`／`sessions` 管理会话，`invitations`／`users` 管理成员。产品授权由管理员设置，仍由各产品逐次检查。

`sso/settings` 与 `sso/test` 供管理员设置 OIDC，`oidc/start` 与 `oidc/callback` 完成登录。平台直接支持 OIDC；SAML 或 LDAP／AD 可通过可选的 Keycloak 代理，平台没有原生 SAML 端点。Identity 在 `/api/scim/v2` 提供 SCIM 2.0 Users／Groups；不支持 bulk，也不会按 email 自动认领现有账号。每个客户 IdP tenant 仍须单独验证。设置及供应商限制见[企业 SSO](./enterprise-sso.md)、[管理指南](./guide/administration.md)与[账号指南](./human-login.md)。

## MCP

Work／Knowledge／Code 的 MCP stdio 桥接程序会调用各自的 REST API，并使用各自受范围限制的 Agent token。变更操作中的 `request_id` 会对应至 `Idempotency-Key`；调用者不能在请求正文伪造 `actor`。启动示例见[贡献指南](../../CONTRIBUTING.md)，依产品使用 `ordivant.mcp_server`、`ordivant_knowledge.mcp_server` 或 `ordivant_code.mcp_server`。

Runtime 连接外部工具时使用 MCP Streamable HTTP。详见[外部工具指南](./execution-usage.md#external-mcp-tools)。

<span id="原始碼與開發"></span>
<span id="源代码与开发"></span>

## 源代码与开发 {#source-and-development}

[GitHub 源代码](https://github.com/ordivant-ai/ordivant)与[贡献指南](../../CONTRIBUTING.md)提供开发与测试入口。网站发布操作与集成文档；PM 台账、开发契约及验收记录留在仓库供维护者使用。部署数据、凭证及私人测试输出不可提交至公开仓库。
