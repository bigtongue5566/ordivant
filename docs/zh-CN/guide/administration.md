<span id="管理員、角色與企業登入"></span>
<span id="管理员、角色与企业登录"></span>

# 管理员、角色与企业登录 {#administrators-roles-and-enterprise-sign-in}

Ordivant 的浏览器登录由共用 Identity 服务提供；Work、Knowledge、Code 各自检查产品角色和资源范围。SSO 登录成功只创建用户的平台会话，不会直接授予 Agent token、Runtime 身份或 Gitea 凭证。

<span id="初始管理員與成員"></span>
<span id="初始管理员与成员"></span>

## 初始管理员与成员 {#first-administrator-and-members}

每个 Compose 项目／环境都有自己的 Identity 数据。第一次打开 Web 时，请为该环境创建第一位管理员；系统没有预设用户账号。管理员可邀请成员、禁用账号、撤销会话，并授予产品角色，以及 Work Project、Knowledge Space、Code Project 的明确资源范围。

如果管理员已设置 SMTP，Identity 会将邀请和本地账号恢复邮件放入持久队列并发送；否则不会尝试发送邮件，管理员须安全地通过其他方式提供一次性邀请码。邮件链接会过期且只能使用一次；本地账号仍可使用登录时提供的恢复码。普通成员只能查看明确授权的资源。创建新的 Project 或 Space 由管理员负责。

<span id="產品角色"></span>
<span id="产品角色"></span>

## 产品角色 {#product-roles}

| 产品 | 角色 | 主要权限 |
|---|---|---|
| Work | Manager | 管理已授权项目的工作与运行安排 |
| Work | Worker | 运行获授权任务并提交成果 |
| Work | Reviewer | 独立审查成果；不可接受自己的提交 |
| Knowledge | Manager | 管理已授权 Space 内的文档和决策；添加 Space 由 Identity 管理员创建 |
| Knowledge | Writer | 创建文档、发布新版本、记录决策 |
| Knowledge | Reader | 搜索与阅读已授权 Space |
| Code | Manager | 管理已授权 Code Project |
| Code | Writer | 在已授权 Project 创建 repository 及变更 |
| Code | Reader | 查阅 Project、repository、PR 和状态收据 |

Identity 的组织管理员（`admin`）可管理成员和授权；产品角色是另一层权限。同一人在三个产品可以有不同角色或范围。Agent 使用各自独立且受资源范围限制的身份；不能用一个产品的权限推导另一个产品的访问权。

<span id="設定企業-oidc"></span>
<span id="设置企业-oidc"></span>

## 设置企业 OIDC {#configure-enterprise-oidc}

1. 以管理员登录该环境，打开「账号与安全性 → 企业 SSO」。
2. 在企业 IdP 创建机密客户端类型的 OIDC Web 应用，启用 Authorization Code 与 PKCE S256。
3. 将 Ordivant 界面显示的完整 `Callback URL` 注册为 `Redirect URI`，不可使用通配符。
4. 输入该组织的 `Issuer`、`Client ID`、`Client Secret`、允许网域与成员布建政策；需要群组时，设置 IdP 的 `groups` claim 及明确的产品／范围对应。
5. 保存后运行连接测试，再以普通成员测试登录、产品访问及注销。确认管理员恢复路径可用后，才考虑启用 `SSO-only`。

成员依据受邀或明确设置的 JIT 政策加入；相同电子邮件网域本身不会授予全组织权限。Client Secret 会加密保存，表单不会回填明文。直接 OIDC 是登录协议；若企业只提供 SAML 或 LDAP／Active Directory，可选择 Keycloak broker。启用 required_acr 或 required_amr 时，成员登录政策必须是 SSO-only；Identity 会检查已验证 IdP 权杖中的 assurance claim，平台本身不提供 MFA 因子。详细设置见[企业登录说明](../enterprise-sso.md)。

## SCIM、MFA、邮件与审计治理 {#enterprise-provisioning-mfa-mail-audit}

管理员在右上角打开「账号与安全性」→「企业治理」，可查看 SCIM／邮件服务状态、设置群组权限对应与审计保留政策、导出 Identity 审计记录，以及查看或重试可重试的邮件。SCIM 端点会显示在此页面；部署管理员须另外提供 ORDIVANT_SCIM_TOKEN_FILE，并将该专用 bearer credential 配置在企业布建服务。SCIM 支持 Users 和 Groups；目前不支持 SCIM bulk 操作。

在保存群组授权之前，先按 IdP 提供的群组完整名称创建对应，再用权限编辑器选择明确的产品角色及资源 ID。SCIM 群组不会取得组织 admin；使用通配资源范围也会被拒绝。一般 SCIM User PATCH 若尝试修改由 SCIM 管理的产品权限，会返回 HTTP 409；不能通过一般 PATCH 手动切换权限管理来源。请修改 IdP 群组成员或这里的群组对应，再由 SCIM 同步。明确链接 OIDC 账号时，须使用 `managed_permissions=false`，保留 SCIM 作为群组权限的管理来源。SCIM 创建用户时若同一电子邮件已属于现有 Ordivant 账号，布建会返回冲突，不会自动认领、合并或改变账号；请先通过明确的管理员账号链接／迁移流程处理。SCIM 停用用户或改变群组授权会撤销其既有 Identity sessions。

Docker Compose 部署可选用只读的 `compose.enterprise.yaml`，分别挂载 Identity 与 Code 的机密目录。SCIM token 与 SMTP 密码文件放在 Identity 挂载目录；Code 部署配置及其 token 文件放在 Code 目录。操作步骤见[容器部署指南](../containers.md#enterprise-secret-mounts)与[Code 部署证据设置](code.md#upstream-governance-and-deployment-evidence)。不要把机密值写入 `.env`。

MFA 由企业 IdP 执行。在「账号与安全性」→「企业 SSO」设置必须符合的登录强度 acr 值，以及必须包含的验证方式 amr（例如 mfa），然后要求成员使用 SSO-only 登录。acr 必须符合列表中的某一个值，amr 必须包含全部指定方式；请先确认 IdP 实际签发的已验证登录权杖包含这些 claims，再测试普通成员和管理员恢复路径。

发送邀请与账号恢复邮件之前，部署管理员须设置 SMTP host、port、sender、TLS，以及需要时的账号与密码文件（ORDIVANT_SMTP_HOST、ORDIVANT_SMTP_PORT、ORDIVANT_SMTP_SENDER、ORDIVANT_SMTP_STARTTLS、ORDIVANT_SMTP_USERNAME、ORDIVANT_SMTP_PASSWORD_FILE）。生产环境要求 STARTTLS；缺少必要设置时 Identity 不会发送邮件。到「企业治理」查看邮件队列状态；待发送或失败项目可以重试，过期邮件不可重试。资源追踪与协作中心通知只显示在 Ordivant，不会通过此 SMTP 通道发送。

审计导出是受管理员权限保护的 JSONL 文件，内容只含 Identity 审计允许导出的字段，不是 Work、Knowledge、Code 三个产品事件的合并导出。界面会自动分页，但最多导出 100,000 条或 50 MiB；超过任一上限时会拒绝生成不完整文件。更大的导出请使用 Identity 管理员 API：`GET /auth-api/audit/export` 接受 `limit=1..10000`。后续页使用响应标头 `X-Next-Before` 与 `X-Next-Before-Id` 的值，成对作为 `before` 和 `before_id` 复合游标。先导出需要保存的记录，再设置 30 至 3650 天保留期并明确选择应用；应用后会删除超出期限的 Identity 审计行。

<span id="agent-與模型連線"></span>
<span id="agent-与模型连接"></span>

## Agent 与模型连接 {#agents-and-model-connections}

组织管理员先设置模型供应商、API 网址、密钥及模型，再选择组织默认值。创建或编辑 Agent 时，可继承默认值或选用其他已设置模型。已保存的密钥与工具访问令牌不会回填明文；要更换时请输入新的值。操作步骤见[模型设置](../model-usage.md)与[Run 及工具指南](../execution-usage.md)。

正式环境使用前，请检查 TLS、可信任的网站来源（Origin）、允许的成员布建策略、Project／Space 授权范围，以及恢复码的保管方式。SSO 不会取代各产品的服务器端授权。

## 使用者 API 与 MCP {#personal-api-and-mcp-access}

在右上角开启「帐号与安全性 → API 与 MCP」，输入用途名称、允许的产品与有效期限，再建立个人存取权杖。完整权杖只显示一次；清单只显示前缀、到期时间与上次使用时间。此处也提供目前环境的 API 和 MCP 连线范例。

权杖透过 `Authorization: Bearer <PERSONAL_ACCESS_TOKEN>` 使用。它代表你的真人帐号，沿用目前的产品角色及 Project／Space 范围，不会取得 Agent 身分或额外权限。管理员可建立资源；一般成员只能操作获授权的资源。三个产品的本机 API 根网址如下：

以下以默认 Docker Compose 的 `http://127.0.0.1:8088` 为例；如果使用不同端口或 HTTPS 域名，请改为自己环境的网址。界面会根据当前网站生成对应示例。

| 产品 | 本机 API 根网址 | 起始操作 |
|---|---|---|
| Work | `http://127.0.0.1:8088/api` | `GET /me`、`GET /projects` |
| Knowledge | `http://127.0.0.1:8088/knowledge-api` | `GET /me`、`GET /spaces` |
| Code | `http://127.0.0.1:8088/code-api` | `GET /me`、`GET /projects` |

例如先确认 Work 身分：

```sh
curl "http://127.0.0.1:8088/api/me" -H "Authorization: Bearer <PERSONAL_ACCESS_TOKEN>"
```

MCP 使用本机 stdio bridge，需安装 uv 并取得 Ordivant 原始码。把介面的设定范例加入支援 stdio 的 MCP 用户端；替换原始码目录与权杖后，以各产品自己的 Python 专案启动：

| 产品 | 专案目录 | 模组 | 环境变数 |
|---|---|---|---|
| Work | `backend` | `ordivant.mcp_server` | `ORDIVANT_API_URL`、`ORDIVANT_API_TOKEN` |
| Knowledge | `products/knowledge/backend` | `ordivant_knowledge.mcp_server` | `ORDIVANT_KNOWLEDGE_API_URL`、`ORDIVANT_KNOWLEDGE_API_TOKEN` |
| Code | `products/code/backend` | `ordivant_code.mcp_server` | `ORDIVANT_CODE_API_URL`、`ORDIVANT_CODE_API_TOKEN` |

启动命令形式为 `uv run --project <专案绝对路径> python -m <模组>`。网址使用上表的 API 根网址；权杖须允许对应产品。先呼叫 `get_me` 确认身分，再使用 Work 的 `list_projects`、Knowledge 的 `list_spaces` 或 Code 的 `list_code_projects`。建立资源的工具分别为 `create_project`、`create_space`、`create_code_project`；这些工具及既有业务工具都交由 REST API 执行相同授权。变更操作接受 `request_id`，重试同一次操作时请重用该值。

可随时在权杖清单撤销连线；到期、帐号停用或产品权限变更会影响后续请求。变更密码或完成帐号复原也会撤销既有权杖。「登出所有装置」只撤销浏览器工作阶段；外部工具须另外撤销权杖。权杖不能管理或建立其他权杖，管理操作仍需浏览器登入及 CSRF 验证。
