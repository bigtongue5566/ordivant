<span id="企業登入與身分管理"></span>
<span id="企业登录与身分管理"></span>

# 企业登录与身分管理 {#enterprise-sign-in-and-identity-management}

Ordivant Work、Knowledge、Code 共用一个 Identity 服务。管理员可以接上企业既有的 OIDC 身分服务，并控制成员布建、产品／项目权限、登录政策及工作阶段。企业密码与 MFA 验证由身分服务处理，Ordivant 不接收企业密码。

<span id="管理員設定"></span>
<span id="管理员设置"></span>

## 管理员设置 {#administrator-setup}

1. 使用要设置的 Ordivant 管理员账号登录。不同部署分别保存账号及 SSO 设置，请确认使用正确的服务网址。
2. 打开「账号与安全性 → 企业 SSO」。选择身分服务模板，再填入组织专属 Issuer URL、Client ID、Client Secret。
3. 在身分服务创建 confidential OIDC Web application，允许 Authorization Code 和 PKCE S256。把 Ordivant 显示的 Callback URL 完整注册为 Redirect URI；不要使用通配符。
4. 设置允许的完整电子邮件网域、成员布建方式、预设权限及群组对应。先保存，再运行「测试连接」。这项测试检查 discovery/JWKS；真正登录仍需由身分服务授权。
5. 先用一位企业成员完成登录、产品访问及注销验收，再切换「仅企业 SSO」。本机管理员帐密入口保留作为复原途径。

Client Secret 留白会保留既有值；改变 Issuer 或 Client ID 必须明确填入新值。保存后界面清空 Secret，API 只回传是否已设置。公开设置网址以管理员设置的 canonical origin 为准；从 localhost／127.0.0.1 的其他别名开始登录时，界面先切到该网址。

<span id="常見身分服務"></span>
<span id="常见身分服务"></span>

## 常见身分服务 {#common-identity-providers}

| 身分服务 | Issuer／应用设置 | 注意事项 |
|---|---|---|
| Microsoft Entra ID | `https://login.microsoftonline.com/TENANT_ID/v2.0`；Web 平台、组织专属 tenant | 使用明确租户；依实际 token claims 选 email 或 preferred_username。Entra 未提供 email_verified 时，仅在确认租户与网域政策后关闭此验证。群组 claims 必须由管理员配置；group overage 不会被当成群组授权。 |
| Google Workspace | `https://accounts.google.com`；Web 应用 OAuth 客户端 | 限制允许网域；IdP 的 hd 提示不取代后端网域检查。Google 不预设提供产品所需 groups，请使用明确预设权限或手动授权。 |
| Okta | 组织自己的 OIDC authorization server issuer | 设置 groups claim 发到 ID token；名称须与权限对应完全一致。 |
| Auth0 | `https://YOUR_TENANT.REGION.auth0.com/` 或设置的 custom domain | OIDC ID token 的标准 claims；需要群组时由 Action 加入自订 claim，并在 Ordivant 填入相同 claim 名称。 |
| Keycloak | `https://IDP_HOST/realms/REALM` | confidential client、PKCE S256、将 groups mapper 加入 ID token；可代理 SAML 或 LDAP／AD。 |
| 其他 OIDC | 服务公开的精确 issuer | 必须提供 discovery、JWKS、Authorization Code、signed ID token，以及可用的身分 claims。 |

这些模板提供标准设置方式。实际企业 tenant 仍需使用该组织配置进行登录验收，不能以本机 Keycloak 验收推定所有 vendor tenant 均已通过。

官方设置参考：[Entra OIDC](https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc)、[Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect)、[Okta OIDC](https://developer.okta.com/docs/guides/implement-grant-type/authcode/main/)、[Auth0 Regular Web Apps](https://auth0.com/docs/get-started/authentication-and-authorization-flow/authorization-code-flow)、[Keycloak 管理指南](https://www.keycloak.org/docs/latest/server_admin/index.html)。

<span id="成員與權限"></span>
<span id="成员与权限"></span>

## 成员与权限 {#members-and-permissions}

- **仅受邀成员**：先由管理员创建 member 邀请。企业身分的电子邮件通过验证并符合允许网域后，可以直接使用 SSO 接受邀请，沿用邀请中指定的产品与资源权限。企业登录不会自动创建管理员。
- **JIT 自动布建**：首次登录创建一般成员，套用明确的预设与群组权限。没有设置权限的成员无法访问产品数据；同网域不代表全组织可见。
- **群组同步**：JIT 管理的成员每次登录同步群组。移除群组会移除相应授权并撤销旧工作阶段；成员仍只能访问获授权的产品与资源。
- **既有账号链接**：电子邮件相同不会自动合并账号。管理员必须明确指定现有用户与 IdP subject，并在登录时验证对应。解除链接会撤销企业登录工作阶段。
- **手动权限**：管理员明确修改成员权限后改为手动管理，避免下一次登录悄悄覆盖设置。要恢复群组管理，透过身分链接重新指定管理方式。

登录成功只创建平台工作阶段，不直接授予 agent 或版控服务的 credential。Agent REST／MCP 仍使用项目受限的独立身分。

<span id="saml、ldap-與-active-directory"></span>
<span id="saml、ldap-与-active-directory"></span>

## SAML、LDAP 与 Active Directory {#saml-ldap-and-active-directory}

Ordivant 采 OIDC 接入协定。SAML-only 或 LDAP／AD 企业系统可以使用可选 Keycloak 身分代理：在 Keycloak 创建 SAML Identity Provider 或 LDAP User Federation，将它对外提供的 OIDC realm 接到 Ordivant。Work／Knowledge／Code 不必各自保存 LDAP 密码或实作不同登录协定。

SAML 串接时，在 Keycloak 添加 SAML Identity Provider，导入上游 metadata，向上游登记该 broker 显示的 Entity ID 与 ACS／Redirect URI。保持 assertion 签章验证，配置电子邮件与姓名 mapper，再依企业的电子邮件验证政策决定是否激活 Trust Email。群组需要另外配置 broker mapper，让最终 OIDC ID token 的 groups claim 包含 Ordivant 对应的完整群组名称；SAML 的群组不会自动变成平台权限。

LDAP／AD 串接时，在 Keycloak 的 User Federation 添加 LDAP provider，填入企业提供的目录地址、Users DN、搜索条件与 username／email attribute，配置群组 mapper，并使用 LDAPS 或 StartTLS 与可信 CA。目录 Bind Credential 与人员密码由企业管理员直接在身分服务输入。先验证目录连接与单一成员同步，再创建 OIDC client 接到 Ordivant；平台端仍套用允许网域、受邀／JIT 与明确资源授权。

如需 SAML 或 LDAP／AD，先完成[容器部署](containers.md)的初始化。在同一仓库根目录的 `.env` 加入以下设置，再启动可选的 Keycloak 与独立数据库；若已使用其他 Compose 配置文件，请一并保留：

```dotenv
ORDIVANT_BROKER_PUBLIC_URL=http://127.0.0.1:8093
ORDIVANT_SSO_HTTP_HOSTS=identity-broker
ORDIVANT_SSO_BACKCHANNEL_OVERRIDES={"http://127.0.0.1:8093":"http://identity-broker:8080"}
```

```sh
docker compose -f compose.yaml -f compose.identity-broker.yaml --profile identity-broker up -d --wait identity-broker identity-api
```

broker 预设只绑定 `127.0.0.1:8093`。可由调用端指定 `ORDIVANT_BROKER_PORT` 及 `ORDIVANT_BROKER_PUBLIC_URL`；跨电脑的企业部署使用固定 HTTPS 网址与可信反向代理。其他 OIDC 身分服务可直接设置，不需要激活 broker 容器。

broker 不会建立默认的人员管理员。以下命令以 `ordivant` 为例；请使用启动 broker 时相同的项目名称与机密文件夹。密码由管理员直接在 tmux 的交互提示中输入。Windows 可先打开 WSL 会话，并确认 Docker Desktop 已启用 WSL 集成：

```sh
wsl -- tmux new-session -A -s ordivant-idp-admin
```

Linux 可使用 `tmux new-session -A -s ordivant-idp-admin`。在 tmux 终端中切换至仓库目录，再执行一次性初始化：

```sh
docker compose -f compose.yaml -f compose.identity-broker.yaml --profile identity-broker stop identity-broker
docker compose -f compose.yaml -f compose.identity-broker.yaml --profile identity-broker run --rm identity-broker bootstrap-admin user --username temp-admin
docker compose -f compose.yaml -f compose.identity-broker.yaml --profile identity-broker up -d identity-broker
```

请勿将密码放入聊天、命令、环境变量或文件。以临时管理员登录 broker 后创建正式管理员，再移除临时管理员。[Keycloak 官方初始化与复原说明](https://www.keycloak.org/server/bootstrap-admin-recovery)

<span id="工作階段、安全與稽核"></span>
<span id="工作阶段、安全与审核"></span>

## 工作阶段、安全与审核 {#sessions-security-and-audit}

平台保留 HttpOnly、SameSite 与 Origin／CSRF 保护。OIDC 使用单次 state、browser binding、nonce、PKCE S256 与签章／issuer／audience 验证。Client Secret 加密存放；authorization code、ID token、access token 不进入业务数据库、API 回应或登录日志。

禁用账号、变更权限、解除企业身分或禁用／更换身分服务会撤销相关工作阶段。激活 SSO-only 时撤销一般成员的密码工作阶段。若 IdP 支持 OIDC Back-Channel Logout，可将 URL 设为 `https://APP_HOST/auth-api/oidc/backchannel-logout`；只有通过签章与重放检查的注销通知才能撤销对应企业登录。

Ordivant 注销会撤销三个模块共用的工作阶段；企业其他应用的工作阶段由 IdP 管理。企业 MFA、Conditional Access、密码规则与人员离职流程需在 IdP 设置。如果平台 SSO 政策配置了 required_acr 或 required_amr，Identity 会验证已签署 IdP 权杖中的 claims：acr 必须符合其中一个要求值，amr 必须包含全部指定方式。这些 claim 是验证条件，实际 MFA 因素由 IdP 执行。若 IdP 不发送 backchannel logout，管理员应在平台同步禁用成员，而不能把 IdP 禁用误认为现有平台 session 立即失效。

「身分审核」记录登录、布建、设置与权限变更、链接／解除链接及注销事件。管理员可查看或在「账号与安全性」→「企业治理」导出 Identity 记录。此导出不包含 Work、Knowledge 或 Code 产品事件，也不含密码、cookie、client secret 或 provider token。

<span id="維運與備份"></span>
<span id="运维与备份"></span>

## 运维与备份 {#operations-and-backups}

保留 Identity PostgreSQL、`identity_data`（包含 `sso.key`）、Compose service secrets。使用 broker 时还要保留 `identity_broker_postgres`。数据库与加密密钥须一起备份；只有数据库无法还原已加密的 client secret。

正式 HTTPS 环境设置 `ORDIVANT_AUTH_COOKIE_SECURE=true`、明确 `ORDIVANT_AUTH_ORIGINS` 和 `ORDIVANT_SSO_PUBLIC_ORIGIN`。若 provider discovery 的 token/JWKS endpoint 使用不同 host，使用 `ORDIVANT_SSO_ALLOWED_ENDPOINT_HOSTS` 指定额外可信 host。Google 的精确 HTTPS token/JWKS hosts 已受支持。私有 HTTP broker 需明确 `ORDIVANT_SSO_HTTP_HOSTS`；上述 `.env` 设置将 broker 的回程连接转向其内部网址，外部 provider 不需此例外。

私有企业 CA 可将 PEM trust bundle 挂载到 Identity 容器，再设置 `ORDIVANT_SSO_CA_BUNDLE` 为该文件路径；TLS 凭证验证持续激活。Compose 信任指定的 `web` proxy，由 Nginx 覆写 `X-Real-IP`，依实际来源进行登录限流。自订反向代理需在 `ORDIVANT_AUTH_TRUSTED_PROXY_HOSTS` 列出精确 proxy host／IP，并由它覆写此 header；直接连到 Identity API 的伪造 header 不会被采用。

Ordivant 使用 OIDC 作为身分整合协定；SAML 与 LDAP／AD 透过选配的 Keycloak broker 联邦，平台没有原生 SAML 端点。Identity 提供 SCIM 2.0 Users／Groups 布建，但不支持 bulk 操作，也不会按 email 自动链接既有账号。各客户的 IdP tenant 与 LDAP／AD 目录尚未逐一验证。上线前请依[管理指南](./guide/administration.md)设置 SCIM 专用凭证、明确的群组资源授权、邮件、审计与由 IdP 执行的 MFA，并逐一核对各组织的 claims、网域限制及资源授权政策。
