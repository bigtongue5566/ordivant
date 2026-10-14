# 企业身分修订（2026-10-07） {#enterprise-identity-revision-2026-10-07}

本契约记录 2026-10-07 的 OIDC 企业身分修订：在共用 Identity 服务中提供可配置的 provider 范本、范围受限的布建、群组授权、生命周期撤销与身分稽核。SAML 与 LDAP／AD 身分提供者使用选配的 Keycloak broker；平台没有原生 SAML 端点。当时尚不支持 SCIM；2026-10-15 的 SCIM 与 assurance 扩充见下方契约。不得声称未设置的供应商租户已经测试。

## 责任范围 {#ownership}

- PM 负责本契约、根目录 Compose／工具、集成与最终验收。
- SSO backend worker 负责 `products/identity/backend/**`，包含相依套件、lockfile 与具实质意义的安全性测试。
- SSO frontend worker 负责 `frontend/src/auth/**`，包含添加的 SSO 设置／稽核组件。最后的权限调整也只将新 scope 创建可见性、handler 保护及空状态文本指派到 `frontend/src/App.tsx`、`frontend/src/products/knowledge/KnowledgeApp.tsx`、`frontend/src/products/code/CodeApp.tsx`。保留其他 worker 的变更；既有 scope 的业务授权维持不变。
- SSO QA worker 仅负责 `scripts/sso_acceptance.py`、`scripts/sso_fixture.py` 与 `tests/fixtures/sso/**`。创建 fixture realm／client 导入设置，涵盖直接 OIDC，以及联邦至 broker realm 的上游 Keycloak SAML realm。PM 负责启动真实 Keycloak fixture 的 Compose overlay。
- 所有 worker 开始前先阅读 `docs/contracts.md`、`docs/project-plan.md`、`docs/auth-contracts.md` 与本契约。共用数据结构若要变更，先向 PM 提出。

## 设置与 API {#configuration-and-api}

每个 Identity 环境（一个本机组织）设置一个 OIDC provider。所有添加公开路由位于 `/api/auth` 下；浏览器使用 `/auth-api`。设置会持久化、采 singleton 并以 revision fence 保护；仅限 admin，变更操作须通过 Origin + CSRF。Client secret 使用专用且持久化的 `/data/sso.key` 加密；绝不回传、记录或放入验证错误／稽核。若 issuer／client ID 相同，client_secret 为空或省略时保留既有值；变更任一项都必须明确提供替换值。绝不可依 IdP claims 推导 admin 角色。

`GET /sso/settings` 与 `PUT /sso/settings` 回传：

```json
{
  "revision": 0,
  "enabled": false,
  "display_name": "企業帳號",
  "issuer_url": "",
  "client_id": "",
  "client_secret_configured": false,
  "redirect_uri": "http://127.0.0.1:5173/auth-api/oidc/callback",
  "scopes": ["openid", "profile", "email"],
  "allowed_email_domains": [],
  "email_claim": "email",
  "require_email_verified": true,
  "groups_claim": "groups",
  "provisioning": "invited_only",
  "default_permissions": {},
  "group_mappings": [],
  "login_policy": "password_and_sso"
}
```

PUT 接受这些可编辑字段及只能写入的 `client_secret`；不接受衍生字段 `redirect_uri` 与 `client_secret_configured`。首次写入时也必须提供目前 revision（0），revision 过期时回传 409。`group_mappings` 项目为 `{group:string,permissions:Permissions}`，使用既有产品角色与精确资源 ID。合并默认权限及相符群组权限时，scope ID 去除重复。Work 角色优先级为 manager > reviewer > worker；Knowledge／Code 为 manager > writer > reader。不得授予万用资源、Suite admin 权限或来自 claim 的操作者身分。

`enabled=true` 必须有有效的 issuer、client ID、已保存的 secret、非空的 allowed_email_domains，且已完成首次 admin 设置。`login_policy=sso_only` 必须先激活 SSO。固定公开 callback 从 `ORDIVANT_SSO_PUBLIC_ORIGIN` 或第一个精确的 `ORDIVANT_AUTH_ORIGINS` origin 推导，且必须位于受信任 origins 清单中。Request Host 与 query parameters 绝不可决定 callback origin。

`POST /sso/test`（admin + CSRF）使用已保存设置，不启动登录，只验证 discovery／JWKS，并回传 `{status:"ok",issuer,authorization_endpoint,redirect_uri,supported_algs:string[]}`。若失败，回报真实且安全的上游／设置错误；不可捏造通过数据。

`GET /status` 保留 setup_required，并添加 `sso:{enabled,display_name,login_policy,configured,public_origin}`。不得回传 secret 或私人 discovery response。`public_origin` 是受信任的标准浏览器 origin，避免别名使浏览器 binding Cookie 无法使用。若 Frontend 从不同 origin 触发 SSO，须先带一次性 `enterprise_login=1` flag 前往标准产品路径；取得 status 并确认 SSO 已激活后，才能消耗 flag 并开始登录。Backend start 要求此标准 Origin，否则回传 sso_origin_mismatch。`User` 添加 `credential_type:"local"|"sso"` 及 `permissions_source:"manual"|"sso"`；不可破坏产品 introspection bridge 的 schema。Session JSON 添加 `authentication:{method:"password"|"oidc",provider_name?:string}`。SSO-only 用户不能变更／复原密码，也不会收到本机 recovery codes。

## 登录流程 {#login-flow}

- `POST /oidc/start` 使用 `{return_to:"/work"|"/knowledge"|"/code"}`，须有受信任的 Origin，回传 `{authorization_url}`，并设置一个独立的 HttpOnly／SameSite=Lax／依设置决定 Secure 的浏览器 binding Cookie。必须已激活 SSO 且完成初始设置。对 start／callback 实施速率限制。使用 Authorization Code + PKCE S256 + 随机 state + nonce。
- 只持久化 state 哈希与浏览器 binding、nonce 哈希、加密后且短期有效的 PKCE verifier、固定 return path、设置 revision 及到期时间（五分钟）。State 通过原子条件写入，只能消耗一次。拒绝缺少／错误的 binding、已到期或 Provider 设置已变更的要求。此机制须支持 PostgreSQL，且进程重启后仍有效。
- `GET /oidc/callback` 验证 binding／state、在服务器端交换 code、依 discovery JWKS 验证已签署的 ID token，然后创建既有的 Suite HttpOnly 工作阶段。Provider token 不得放入浏览器保存、API JSON、URL redirect、数据库或 log。成功与失败时都清除 binding Cookie。
- Callback 以 303 重新导向至受信任的公开 origin 与已保存产品路径。失败只能使用有界的 `auth_error` code；绝不可使用原始 Provider error／code／token。若 Provider 拒绝但 state 有效，仍须消耗 state；无效 state 不得造成外部重新导向。API／服务器访问 log 不得记录 callback query string。
- 明确只允许 RS256／ES256；验证签章、精确 issuer、audience、必要时的 azp、expiry、nbf／iat、nonce、非空且稳定的 sub，以及范式后有效的电子邮件。默认要求 `email_verified=true`。特定租户的 Entra 部署可先选择精确 tenant issuer 与允许网域，再明确选择停用此要求；不可默默推定电子邮件拥有权，也不可只凭电子邮件链接既有用户。
- Discovery issuer 必须与设置完全相符。验证所有 URL；拒绝凭证、fragment、无效 port、link-local／metadata／unspecified 目标、非预期 endpoint host 及 redirect。除了明确信任的本机测试／私人 HTTP host，其他连接一律使用 HTTPS；设置严格逾时与回应大小上限；停用 trust_env。
- Google OIDC discovery 的 backchannel endpoint 合法使用 oauth2.googleapis.com 与 www.googleapis.com；将这两个精确且只允许 HTTPS 的供应商 host 加入内置 endpoint host allowlist。其他不同 host 必须由营运者明确列入 allowlist。Provider 范本只是设置辅助，不代表仿真了 Provider 集成。
- Google 文档仅列出两种已签署 ID token issuer 写法：`https://accounts.google.com` 与 `accounts.google.com`。只有设置的 canonical issuer 是 `https://accounts.google.com` 时，才接受这两个精确别名；identity binding 仍使用 canonical issuer，并将旧版 verified-email 字符串 `"true"` 范式。其他 issuer 与 verified-email 字符串一律严格处理。使用已签署 token fixture 验证此行为；不可泛用 issuer 前缀比对。
- `ORDIVANT_SSO_HTTP_HOSTS` 以逗号分隔受信任 HTTP hostname（本机允许 loopback）；`ORDIVANT_SSO_ALLOWED_ENDPOINT_HOSTS` 明确允许使用不同于 issuer host 的 discovery endpoint。`ORDIVANT_SSO_BACKCHANNEL_OVERRIDES` JSON 将精确的公开 issuer prefix 对应至受信任的内部 issuer prefix，只用于容器网络路由。仍须验证公开 discovery issuer／endpoints／token issuer，再只针对符合项目改写 backchannel HTTP 的 prefix。Production 默认没有 override。
- Reverse proxy 速率限制使用 `ORDIVANT_AUTH_TRUSTED_PROXY_HOSTS`（明确列出的 hostname／IP）。只有 socket peer 符合已解析的受信任 proxy 时，才可用一个有效 X-Real-IP 作为节流身分。Compose 只信任 web；Nginx 将 X-Real-IP 覆写为 remote_addr。忽略直接／不受信任用户端提供的 forwarding header。不可一概信任所有来源 IP。

## 账号布建与生命周期 {#provisioning-and-lifecycle}

- 将 issuer + sub 保留为具唯一数据库 constraint 的稳定身分。第一位 admin 一律在本机明确创建。绝不可依 IdP 电子邮件自动合并既有本机账号；应回传 account_link_required。
- `invited_only`：已验证且符合允许条件的电子邮件可原子消耗一笔有效 member 邀请，并创建具有明确权限的 SSO-only member。因 IdP 已证明电子邮件，无须邀请代码。Admin 邀请不能自动创建 SSO 管理员。拒绝未知／未受邀身分。
- `jit`：已验证且符合允许条件的身分可依默认／相符群组权限创建 SSO-only member；若没有授权，账号就没有产品访问权。后续每次 SSO 登录都同步此类账号的受管理权限；权限缩减／变更时撤销既有工作阶段。群组缺席时移除先前由群组授予的权限。新登录绝不可重新激活已停用用户。
- 既有手动授权仍维持手动。管理者编辑权限时，SSO 管理的 member 会改为手动权限，避免下次登录时暗中覆写管理者的变更。`POST /sso/links` admin + CSRF `{user_id,subject,managed_permissions?:false}` 明确将既有用户链接至目前 issuer；初次登录时，电子邮件须符合该用户。`GET /sso/links` admin 回传 `{links:[{id,user_id,issuer,subject,managed_permissions}]}`。`DELETE /sso/links/{id}` admin + CSRF 会解除链接并撤销受影响用户的 SSO 工作阶段。每个 issuer／subject 仅能有一个链接，不可默默重新指派。
- `sso_only` 拒绝非 admin 使用密码登录、复原或以密码接受邀请，并撤销既有非 admin 密码工作阶段。本机 admin 密码登录仍保留作为明确的复原途径。停用／变更 Provider 身分时撤销受影响的 OIDC 工作阶段；已停用用户／权限变更使用三个产品既有的即时撤销机制。
- `POST /oidc/backchannel-logout` 接受表单 logout_token，仅免除浏览器 Origin／CSRF 检查。依设置 issuer／JWKS 验证已签署的 logout JWT、aud、iat、必要的 backchannel event、sub 或 sid、不含 nonce，并以 jti 防止重播。只撤销相符的 OIDC 工作阶段；保留本机 admin／密码工作阶段。持久化重播防护记录。绝不保存或回传原始 logout_token。
- Identity 数据迁移必须保留既有账号哈希与工作阶段。优先添加数据表，不可假设 create_all 会修改既有数据表。容器重建／重新启动后，加密密钥与 DB volumes 都必须保留。

## 稽核与用户接口 {#audit-and-user-interface}

成功变更 Identity 时，在同一个 transaction 写入持久化身份审计事件。记录 SSO 成功／失败、设置变更／测试、布建／链接／解除链接、logout／backchannel logout、本机登录、邀请与管理权限／停用变更。绝不可包含密码、secret、authorization code／state／nonce、Cookie 或 Provider token。审计导出仅限 admin；Identity 服务路径为 `GET /api/auth/audit/export?limit=100`，浏览器／proxy 路径为 `GET /auth-api/audit/export?limit=100`。limit 范围为 1 至 10000。分页以 `before` 和 `before_id` 作为 `(created_at,id)` 复合游标；有下一页时，响应标头 `X-Next-Before` 与 `X-Next-Before-Id` 提供下一组值。

登录页显示已设置的企业登录按钮；SSO-only 政策会明显优先显示此按钮，并保留清楚标示的管理员密码复原入口。消耗／移除有界限的 auth_error query parameter，并显示易懂的繁体中文消息。不可捏造登录成功。Admin 账号／安全 UI 包含完整的 Enterprise SSO 设置页签、连接测试、手动 subject 链接／解除链接与身分稽核页签。默认／群组权限使用既有资源选择器，并清楚说明精确电子邮件网域与权限管理。SSO-only 账号隐藏密码／复原操作。保存或卸载后清除 client_secret 输入值。既有四种建置模式都必须通过，且表单／下拉列表须适合 390px viewport。

## SCIM 与验证强度扩充（2026-10-15） {#scim-and-mfa-extension-2026-10-15}

此扩充定义目前 SCIM 2.0 Users／Groups 范围，以及由外部 IdP 强制 MFA 的登录验证条件。SCIM 入口为 /api/scim/v2，使用部署管理员另行配置的 ORDIVANT_SCIM_TOKEN_FILE。支持 Users、Groups 与受限筛选；不支持 bulk。新增用户若 email 已属于现有 Ordivant 账号，必须返回冲突，不会依 email 自动认领或合并。管理员需先明确链接／迁移；群组只应用明确配置的产品与资源授权，不得授予 admin。停用用户或撤销授权会撤销现有 sessions。

OIDC required_acr 的值须符合配置值之一，required_amr 指定方式须全部出现在已验证的 ID token 中。启用任一 assurance 要求时，成员必须使用 SSO-only 政策；Ordivant 验证 IdP claims，不自行提供第二因素。客户租户互通性仍需逐一验收，fixture 或 API 存在不能替代该验收。

SMTP 邀请／恢复使用 Identity 持久 outbox；未配置邮件服务时不发送。管理员可查看寄送状态并重试符合条件的邮件。Identity 审计导出受权限保护、有记录数／时间范围限制且排除机密字段；只有明确应用保留期时才删除旧资料。整合状态见[项目计划验收清单](./project-plan.md#p0-p1-acceptance-ledger)。

## 验收 {#acceptance}

使用隔离的 QA PostgreSQL 数据库、产生的合成身分，以及固定版本的真实 Keycloak container；其中设置要求 PKCE S256 的 confidential OIDC client 与 groups mapper。不可初始化或修改用户主要人类账号／Provider 设置。验证 Work／Knowledge／Code 的实际 redirect／login／code exchange／签署 JWT／session、产品 scope、reload／logout／disable、群组权限降级、invited-only 与 JIT、明确链接、SSO-only 复原途径、secret 加密／CAS／无外泄、状态持久化／重启，以及伪造 state／nonce／audience／issuer／signature、backchannel logout／重播与本机账号回归。新增 SCIM 验收需覆盖既有 email 冲突、User／Group 授权、停用撤销、不得授予 admin 与不支持 bulk。Fixture 测试是安全性证据；Keycloak 集成是通信协定互通性证据，不代表已验证未设置的客户租户。文档须列出具体 Entra／Keycloak 设置、由 IdP 强制的 MFA、备份／密钥需求，以及仍未完成的原生 SAML／客户租户工作。

主要参考数据：[OIDC Core](https://openid.net/specs/openid-connect-core-1_0.html)、[PKCE](https://www.rfc-editor.org/rfc/rfc7636.html)、[OAuth security BCP](https://www.rfc-editor.org/rfc/rfc9700.html)、[Keycloak containers](https://www.keycloak.org/server/containers)。
