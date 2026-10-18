<span id="帳號與登入"></span>
<span id="账号与登录"></span>

# 账号与登录 {#accounts-and-sign-in}

Work、Knowledge、Code 共用这一套环境的账号。首次启动时打开工作区，会显示「创建管理员账号」：输入姓名、电子邮件与至少 12 个字符的密码，再次确认后送出。系统只允许创建一位初始管理员，没有预设账号或密码。请直接在网页输入，不要把密码传给 agent。

创建完成会登录并提供十组一次性复原码。码预设隐藏，只在这次创建或修改密码后提供，请自行保存到安全的位置。每次改密码或复原后，先前的复原码都会失效。

之后使用「电子邮件」与「密码」登录。刷新页面、切换三个产品会维持登录；注销会立即撤销服务器上的工作阶段。闲置超过 30 分钟或登录超过 12 小时，需要重新登录。

<span id="帳號與安全性"></span>
<span id="账号与安全性"></span>

## 账号与安全性 {#accounts-and-security}

侧栏底部的账号菜单提供“账号设置”，只管理自己的账号、安全性与 API／MCP。管理员另有侧栏“组织管理”入口，管理用户与邀请、企业 SSO、企业治理与身份审计。两者使用独立界面；桌面版使用左侧导航，小屏幕改用菜单。刷新会保留所在设置页。你可以：

- 查看账号信息、修改密码；修改成功后其他登录设备立即失效。
- 查看自己的工作阶段、撤销其他登录，或注销全部工作阶段。
- 管理员可邀请成员、禁用账号、修改成员的产品角色与项目／知识空间访问范围。

邀请码由管理员创建，24 小时有效，仅能使用一次；管理员自行将邀请码提供给成员。平台不会假装已寄出邮件。成员在登录页选「接受邀请」，粘贴邀请码并自行设置密码，即可使用授予的权限。

成员只可访问明确授予的 Work 项目、Knowledge 空间与 Code 项目。创建新的项目／知识空间由管理员负责。变更权限或禁用账号会撤销其既有工作阶段，需要重新登录。

忘记密码时选「使用复原码」，输入电子邮件、一组未使用的复原码与新密码。平台会撤销所有旧登录、消耗该码并提供新复原码；没有复原码就无法透过这条流程重设。

<span id="環境與部署"></span>
<span id="环境与部署"></span>

## 环境与部署 {#environments-and-deployment}

使用管理员提供的部署网址打开 Ordivant。每个独立部署各自保存账号与业务数据；若使用多个部署，需在每个环境分别创建初始管理员。`-Seed` 只加入明确标示的业务示范数据，不会创建人的密码账号。

Docker helper 自动创建 Identity API、独立 PostgreSQL 与内部服务凭证。产品只透过内部验证服务查找登录状态，不读 Identity 数据库。浏览器工作阶段使用 HttpOnly／SameSite cookie，写入操作检查 Origin 与 CSRF；agent REST／MCP 使用原有受限 bearer token。

对外部署需要 HTTPS、`ORDIVANT_AUTH_COOKIE_SECURE=true` 和明确的 `ORDIVANT_AUTH_ORIGINS`。只有 literal localhost／127.0.0.1／::1 的 HTTP Origin 可使用本地例外；设置不完整或服务脱机时拒绝登录与人员业务授权。若产品数据库有多个组织，Compose／launcher 分别设置 `ORDIVANT_WORK_IDENTITY_ORG_ID`、`ORDIVANT_KNOWLEDGE_IDENTITY_ORG_ID`、`ORDIVANT_CODE_IDENTITY_ORG_ID`，它们传入各产品自己的 `ORDIVANT_IDENTITY_ORG_ID`；不得把不同组织的项目混在同一个登录范围。

Identity volumes、业务 volumes 与部署所配置的服务机密储存位置必须一起保留及备份。停止容器不会删除数据；企业设置还需要 Identity data volume 中的 `sso.key` 才能解密还原。

<span id="企業-sso"></span>
<span id="企业-sso"></span>

## 企业 SSO {#enterprise-sso}

管理员在「组织管理 → 企业 SSO」设置企业 OIDC 服务。支持 Entra ID、Google Workspace、Okta、Auth0、Keycloak 与通用 OIDC；SAML、LDAP／AD 可经可选 Keycloak broker 接入。设置流程、群组授权及容器操作见 [企业登录与身分管理](enterprise-sso.md)。

激活后，登录页出现企业登录按钮，密码与 MFA 在企业身分服务完成。成员首次登录必须符合允许网域及受邀／JIT 政策，并取得明确产品范围权限。三模块共用同一个平台工作阶段，登录成功不代表能访问全部项目。SSO 账号不使用本机密码复原。

切换「仅企业 SSO」会撤销一般成员的密码工作阶段；本机管理员入口保留作为复原途径。既有本机账号不会只因 email 相同而自动合并，须由管理员明确链接企业 subject。
