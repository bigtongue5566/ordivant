<span id="企業-sso-驗收"></span>
<span id="企业-sso-验收"></span>

# 企业 SSO 验收 {#enterprise-sso-acceptance}

日期：2026-10-07（Asia/Taipei）。范围是本机 Ordivant 共用 Identity、标准 OIDC 与可选 Keycloak SAML 身分代理。一个 Identity 环境使用一组组织身分服务；Work、Knowledge、Code 各自保有数据库与授权边界。

本报告记录截至 2026-10-07 的 OIDC／SAML 验收，不包含之后加入的 SCIM 与 SMTP outbox。后续 Identity 检查及待验客户租户范围见[现行 P0/P1 清单](project-plan.md#p0-p1-acceptance-ledger)。

<span id="已通過的協定與安全驗收"></span>
<span id="已通过的协定与安全验收"></span>

## 已通过的协定与安全验收 {#protocol-and-security-checks-passed}

| 验收 | 证据 | 结果 |
|---|---|---|
| Identity 安全与既有账号兼容性 | `products/identity/backend/tests`、lock 检查、`compileall` | 28 项测试通过；包含签章、issuer/audience/nonce/state、PKCE、Google 精确 issuer alias、受邀/JIT、明确 subject link、SSO-only、撤销/replay、可信 proxy 与既有数据迁移 |
| Work／Knowledge／Code 业务回归 | 各产品既有 pytest | 31／10／20 项测试通过 |
| 真实 Keycloak OIDC 与 SAML | `.data/validation/sso-32eb71e9/report.json` | 136 项检查通过；不是模拟 provider 回应 |
| 加密保存、日志与重启 | `.data/validation/sso-84b63356/storage-report.json` | 27 项检查通过；实际重启 QA Identity 与 Keycloak 容器 |
| 前端类型与独立建置 | `npm run typecheck`、`build:suite`／`build:work`／`build:knowledge`／`build:code` | 全部以 exit 0 结束；包含三产品管理员创建入口与一般成员空状态修订 |
| 实际浏览器 OIDC／SAML 登录 | `.data/validation/sso-browser/report.json`、同目录截屏 | 通过；企业登录、跨产品工作阶段、390px 鼠标菜单、设置保存后立即生效、SSO-only 管理员复原、企业成员密码操作隐藏及三产品 scope 创建权限 |
| 主环境升级与保留初始化 | `.data/validation/sso-browser/main-environments.json` | 开发 `5173` 与本机正式模式 `8088` 的三个产品 health 及 Identity status 都为 200；仍由用户创建第一位管理员 |

136 项 HTTP 验收包含 confidential client 与 PKCE S256、真实 authorization/code exchange、JIT 和受邀成员、三产品精确资源授权、群组移除后的旧 session 撤销与 403、既有管理员的明确 subject 链接、未受邀成员拒绝、SAML 上游登录与 signed assertion/response、SSO-only 拒绝一般成员密码登录且保留管理员复原、禁用成员、Keycloak 真正发送的 signed backchannel logout、伪造 state 拒绝、API/audit 密钥遮罩，以及平台 cookie 和服务器 session 注销。

Identity 中的 Code 权限使用公开 project ID。Code `/me` 的 membership Scope ID 是内部识别码；验收同时精确检查 Identity 的公开 project 权限与 Code collection，并确认单一 opaque Scope ID 在不同授权登录间一致。HTTP suite 不直接读取业务数据库，也不修改产品 API 来暴露内部 ID。

27 项保存验收确认 PostgreSQL 持久化、Client Secret 密文可由原密钥解密、`sso.key` 为 32 bytes 且 Linux 权限 `0600`、state/browser binding/nonce 仅保存 hash、PKCE verifier 加密、没有 provider token 或 authorization code 字段，以及既有 OIDC session 和设置在两个容器重启后仍有效。它也扫描 QA Identity、broker、web 日志，只输出通过与否，不保存原始日志或 credential。

浏览器使用合成账号，实际完成直接 OIDC 与上游 SAML 登录。SAML 成员沿用同一平台 session 进入 Work、Knowledge、Code；账号抽屉标示企业登录且不提供本机密码／复原码操作。更新企业登录按钮名称后，没有重新加载页面便注销，登录画面立即使用新名称及 SSO-only 政策。管理员密码复原仍可登录；一般成员没有创建 Project／Space 的入口，而授权 scope 内的任务／文档入口保留。Code 的 QA 环境没有 Gitea，界面明确显示未设置并禁用 repository 写入，不把这个认证验收当作 Git 写入验收。

<span id="可重現的隔離環境"></span>
<span id="可重现的隔离环境"></span>

## 可重现的隔离环境 {#reproducible-isolated-environment}

```powershell
.\scripts\sso-containers.ps1 -Action up
uv --cache-dir .cache/uv run --project products/identity/backend --no-sync python scripts/sso_acceptance.py
uv --cache-dir .cache/uv run --project products/identity/backend --no-sync python scripts/sso_storage_acceptance.py
.\scripts\sso-containers.ps1 -Action down
```

使用固定 project `ordivant-sso-qa`、app `127.0.0.1:8092`、Keycloak `127.0.0.1:8093`、独立 PostgreSQL/volumes/service secrets，以及 `ordivant-qa` 与 `ordivant-qa-saml` 两个合成 realm。测试密码和 client credentials 是程序中的公开 QA fixture，不是用户账号。第一次运行只在这个 QA 工作区初始化合成管理员；后续运行沿用它。Docker 必须可由运行终端机访问。

Broker 使用 `quay.io/keycloak/keycloak:26.8.0`，本次拉取 digest `sha256:b0f60d489d51c5d113390bdf5461d4c06e6051be026c05549f2e1e10ec352bcc`。两个 realm 文件单独挂载，manifest 不交给 realm importer。已存在的 realm 会被正常 startup 保留；要套用修改过的合成 fixture，使用 `-Action reimport`，它只在这个 QA broker 停止时替换上述两个 realm。该操作不适用于真实企业 realm。

Keycloak 26.8 在 HTTP loopback 发送的 Secure flow cookie，Chromium 可以发送，HTTPX 预设不会。HTTP acceptance 只针对上述两个固定 QA origin 模拟此行为，仍检查 host、path、expiry，且不把 IdP Cookie 注入 app callback。`diagnostics` 记录此差异；`checks` 仅包含真正通过的条件，同名条件采 AND 累积。实际浏览器另行完成 OIDC 与 SAML 登录。产品的 cookie/TLS 验证没有为此放宽。

在 fixture 修正与重跑之间，PM 曾核对固定 QA container project label 后清除合成环境的 SSO request counter；主环境与产品的 20 starts／15 minutes 限流没有变更。一般重跑需等前一限流窗口到期，不能将反复跑完整 suite 的累计次数误认为单一正常登录失败。

SAML fixture 保持 `validateSignature`、`wantAssertionsSigned`，使用 `saml.assertion.signature` 与 `saml.server.signature` 激活上游 assertion/response 签章。Acceptance 核对 live client flags、AuthnRequest policy、metadata Entity ID/SSO endpoint，并确认 metadata 凭证对应上游公开 signing key。Broker 从 metadata 加载验证密钥，没有关闭验证来通过测试。

<span id="實際服務的配置邊界"></span>
<span id="实际服务的配置边界"></span>

## 实际服务的配置边界 {#configuration-boundaries-for-real-services}

Entra ID、Google Workspace、Okta、Auth0、Keycloak 与通用 OIDC 已提供界面模板及 provider-specific claim 提示。协定兼容性由真实 Keycloak 验证，特定企业 tenant 仍须使用该组织的 Issuer、Client ID、Secret、claims 与 MFA 政策完成验收。Google issuer alias 另有实际签章 fixture；不是已连到用户的 Google Workspace。

SAML 使用 Keycloak broker 的实际签章 round trip 已通过。LDAP／AD 透过 Keycloak User Federation 串接，已提供运维设置，尚未连接真实目录。以本报告日期为准，原生 SAML endpoint、SCIM 2.0、企业离职同步、备份还原、负载测试与正式运维监控仍是独立工作；后续 SCIM／SMTP 实作检查见现行[验收清单](project-plan.md#p0-p1-acceptance-ledger)。Identity/Keycloak restart persistence 不等同完整 backup restore。

验收后已注销合成账号、重设暂时 viewport 并关闭 QA 分页；用户原有 `5173/work` 分页保留。QA 登录政策恢复 `password_and_sso` 后，使用 `down` 停止 `ordivant-sso-qa` 容器／网络，保留具名 volumes、service secrets 与本地报告供重现。主环境没有加入合成账号、企业 provider 设置或 QA realm。开发与本机正式模式数据各自独立；此次没有远程部署、发布或 push。设置流程见 [企业登录](enterprise-sso.md)，容器流程见 [容器开发与部署](containers.md)。
