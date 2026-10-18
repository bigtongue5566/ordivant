# 人类用户验证修订（2026-10-06） {#human-authentication-revision-2026-10-06}

用户要求在 development 与 production 提供可实际使用的人类账号登录，且下拉列表能以鼠标操作。此要求取代试行版浏览器 local-session／token 接口。保留 Agent／MCP bearer 授权与所有既有产品数据。

企业身分修订通过同一个 Identity 服务添加 OIDC、账号布建、群组授权、生命周期撤销与稽核。`sso-contracts.md` 定义添加的路由与字段；以下原生账号／工作阶段契约仍然有效。


## 个人 API 与 MCP 存取权杖 {#personal-access-tokens}

- 真人在帐号设定建立 `ord_pat_` 个人权杖，资料库只存 SHA-256 杂凑；原始值仅在建立回应中显示一次。不得记录原始值到日志或稽核事件。
- `GET /api/auth/access-tokens` → `{tokens:[metadata]}`；`POST` 相同路径，本文 `{name,products:["work"|"knowledge"|"code"],expires_in_days:1..365}`（预设 30）→ `{token,access_token:metadata}`；`DELETE /api/auth/access-tokens/{id}` → 204。只可管理自己的权杖，须 Cookie session；变更还须精确 Origin 与 CSRF。每位使用者最多 50 个有效权杖，建立序列化以防并发超额。
- Metadata：`{id,name,prefix,products,created_at,expires_at,last_used_at,revoked_at}`，时间为 UTC ISO 字串，未使用／未撤销为 null；不包含杂凑或完整值。权杖建立及撤销写入 Identity 稽核。
- 内部 `POST /api/auth/access-tokens/introspect` 使用 service bearer，本文 `{access_token,product}` → `{user:User,token_id,expires_at}`。无效／撤销／到期／停用为 401；产品不符为 403。该端点免除浏览器 Origin，但不免除服务验证。所有回应 `Cache-Control: no-store`。
- 产品辨识个人权杖后，使用固定 Identity URL 与内部 secret introspect，逐次载入最新权限并同步相同的 human principal。无效 Authorization 不得退回 Cookie；网路或格式错误 fail closed 503。个人权杖不改变 claim、独立 review、范围或幂等规则，不授予 Agent 身分。
- 建立时仅允许使用者已获授权产品；后续权限变更立即套用。密码变更／帐号复原／停用撤销既有权杖；`logout-all` 只撤浏览器 session，外部权杖须另撤。权杖不能呼叫管理路由来自行扩权或签发新权杖。
- Work、Knowledge、Code 的 stdio MCP bridge 接受同一种 personal bearer，业务操作呼叫各自 REST API。`get_me` 可确认身分；建立资源工具接受 `request_id`，未提供时产生 UUID。介面依产品提供本机命令、环境变数和 API 根网址范例，值使用占位符。

## 责任范围 {#ownership}

- PM 负责这些契约、Compose／工具、下拉列表修正与最终验收。
- Identity worker 仅负责 `products/identity/backend/**`：独立的 Python／SQLAlchemy 身分服务、Dockerfile、测试与 lockfile。
- Bridge worker 负责 `backend/src/ordivant/{identity.py,api.py}`、`products/knowledge/backend/src/ordivant_knowledge/{identity.py,api.py}`、`products/code/backend/src/ordivant_code/{identity.py,main.py}`，以及各产品测试目录添加的身分 bridge 针对性测试。不得修改既有领域模型／安全性／服务或根目录工具。
- Frontend worker 负责 `frontend/src/App.tsx`、`frontend/src/api.ts`、`frontend/src/products/{knowledge/KnowledgeApp.tsx,code/CodeApp.tsx,shared/ProductLogin.tsx,shared/ProductShell.tsx,shared/productApi.ts}`，以及添加的 `frontend/src/auth/**`。不得修改 `main.tsx`、既有 CSS、套件清单或根目录文件；下拉列表 CSS 由 PM 负责。允许在 `auth/` 下添加 auth CSS。

## Identity 服务 {#identity-service}

使用独立的 8030 端口；PostgreSQL 可通过 `ORDIVANT_IDENTITY_DATABASE_URL_FILE` 或 URL 设置（测试／原生环境允许 SQLite）。Python 套件为 `ordivant_identity`。路由前缀为 `/api/auth`。Nginx／Vite 将 `/auth-api/*` 转送至 Identity 的 `/api/auth/*`。Identity 与产品数据不会直接读取彼此的数据库。

环境变量：`ORDIVANT_IDENTITY_DATA_DIR=/data`；`ORDIVANT_IDENTITY_SERVICE_TOKEN_FILE`（内部 introspection 机密）；`ORDIVANT_AUTH_COOKIE_NAME`（每个 Compose 项目各自唯一）；`ORDIVANT_AUTH_ORIGINS`（以逗号分隔、必须精确符合的受信任浏览器 origin）；`ORDIVANT_AUTH_COOKIE_SECURE`（HTTPS 部署设为 true，loopback HTTP 设为 false）。Identity 在容器内绑定 `0.0.0.0`。测试环境以外，若设置不完整且不安全，必须拒绝启动或请求，不可默默开放访问。

Identity 使用 Argon2id 密码哈希、范式后唯一的电子邮件、持久化节流、随机且哈希后保存的工作阶段代码，以及闲置与绝对到期时间；Cookie 属性为 HttpOnly／SameSite=Lax／Path=/（本机 HTTP 可设置 Secure）。JSON／log 绝不可暴露密码、哈希或工作阶段代码。所有 auth 回应使用 Cache-Control: no-store。浏览器变更操作必须有允许的精确 Origin；已验证的变更操作还必须带有 `X-CSRF-Token`。以 HMAC(service secret, raw session handle) 计算 CSRF token，在 session JSON 回传，并以常数时间比较。Introspection 必须使用 `Authorization: Bearer <service secret>`；此凭证绝不是浏览器可用的公开凭证。

- `GET /api/auth/status` -> `{setup_required:boolean}`。
- `POST /api/auth/setup` `{name,email,password}` 仅能以原子 singleton row／DB constraint 创建一次第一位 admin，在全新且未 Seed 的系统也能使用。不提供人类账号默认密码。-> session JSON + Cookie + 一次性 recovery codes。并行竞争失败者回传 409。
- `POST /api/auth/login` `{email,password}` -> session JSON + Cookie。凭证无效、未知、停用或锁定时均回传一般化错误；达到门槛后节流并回传 429。每次登录都使用新的 session handle，避免 session fixation。
- `GET /api/auth/me` -> session JSON 或 401。
- `POST /api/auth/logout` `{}` 撤销目前工作阶段并使 Cookie 到期。
- `POST /api/auth/logout-all` `{}` 撤销用户所有工作阶段并使 Cookie 到期。
- `POST /api/auth/change-password` `{current_password,new_password}` 验证目前密码、更新哈希、撤销所有旧工作阶段，并签发新工作阶段与一次性 recovery codes。
- `POST /api/auth/recover` `{email,recovery_code,new_password}` 以原子操作消耗一次性哈希 recovery code，变更密码／撤销工作阶段，并回传新工作阶段与 recovery codes。失败消息一般化并实施节流；这是真正的脱机复原，不会假装已寄出 email／SMTP。
- `GET /api/auth/sessions` -> `{sessions:[{id,created_at,last_seen_at,expires_at,current:boolean}]}`。
- `DELETE /api/auth/sessions/{id}` 只能操作自己的工作阶段；撤销该工作阶段，若为目前工作阶段则清除 Cookie。
- `GET /api/auth/users` 仅限 admin -> `{users:[User]}`。
- `POST /api/auth/invitations` 仅限 admin，本文 `{email,name,role:"admin"|"member",permissions:Permissions}` -> `{invitation_code,expires_at}`，创建一次性邀请。数据库只保存邀请哈希，原始代码只在签发回应中出现。
- `POST /api/auth/accept-invitation` `{invitation_code,password}` 仅能成功一次地使用有效、未到期邀请 -> 新工作阶段 + recovery codes。
- `PATCH /api/auth/users/{id}` 仅限 admin，本文 `{active?,name?,permissions?}`。不可停用最后一位 admin，也不可让管理者锁住自己；停用或变更权限时撤销受影响的工作阶段。
- `POST /api/auth/introspect` 使用内部 secret + `{session_token}` -> `{user:User,csrf_token,session_id,expires_at}` 或 401。绝不回传 session_token。

Session JSON：`{user:User,csrf_token:string,expires_at:string,recovery_codes?:string[]}`。
User：`{id,email,name,role:"admin"|"member",active:boolean,permissions:Permissions}`。
Permissions：`{work?:{role:"manager"|"worker"|"reviewer",scope_ids:string[]},knowledge?:{role:"manager"|"writer"|"reader",scope_ids:string[]},code?:{role:"manager"|"writer"|"reader",scope_ids:string[]}}`。Admin 可访问同一个本机组织中的所有资源；member 不会自动取得任何授权。添加账号须通过邀请，不开放不受限制的公开注册。

使用共用领域错误格式 `{detail:{code,message}}`。具意义的安全性测试须涵盖 setup 竞争、未以明文保存、无效登录／节流、到期、logout／revoke／密码变更／复原、重复使用邀请，以及最后一位 admin 的保护。

## 产品 Bridge {#product-bridge}

若请求带有 Authorization header，现有 bearer 验证仍具权威性；即使提供的 token 无效，也不得改用 Cookie。若没有 Authorization header，只读取 `ORDIVANT_AUTH_COOKIE_NAME` 指定的 Cookie，并使用 `ORDIVANT_IDENTITY_URL=http://identity-api:8030` 与 service secret file 运行 introspection（httpx 设置逾时、不跟随重新导向／trust_env，不接受用户端提供的 URL）。Identity 无法连接时必须 fail closed。

已验证浏览器的变更操作，须强制检查设置的精确 Origin 与 introspection 回传的 `X-CSRF-Token`，并以常数时间比较。GET／HEAD 为唯读。已签署的 Gitea webhook 与 bearer 操作维持既有政策。

使用新的本机 `IdentityBinding` table（subject 唯一）将身分 subject 对应至明确的本机 principal。只在一个已设置／本机组织内对应。Admin 对应为人类 manager（Work 允许 admin），并具有该组织明确的本机成员资格；member 使用产品权限角色，且只能使用属于该组织、已存在的 scope ID。每次验证请求同步目前角色／成员资格，但不修改 Agent principal。业务变更前安全地 flush／commit 对应结果；处理首次请求的竞争情况。Principal.active 跟随 introspection 的身分激活状态。若 Identity 用户没有产品权限，回传明确易懂的 403，不可自动授权。不可导入其他产品的 ORM。

`ORDIVANT_IDENTITY_ORG_ID` 可选择现有本机组织。未设置时，若只存在一个组织就使用该组织；若数据库为空就创建具确定 ID 的本机 Identity 组织；若有多个组织且无法判定则拒绝。绝不从调用端 scope ID 决定组织。保存 `IdentityBinding.identity_admin`；身分绑定的 member manager 只能操作指派给自己的 scope，且仅 Identity admin 可创建新 project／space。

保留 local-session endpoint 供旧的明确测试工具使用；产品设置 Identity 后，该 endpoint 必须拒绝绕过登录。Frontend 不会显示此 endpoint。

## 浏览器 {#browser}

Permission `scope_ids` 指各产品公开的资源识别码：Work project ID、Knowledge space ID、Code project ID。Code 会将公开 project ID 对应到自己的内部 Scope 成员资格；UI 不需要知道私有 ORM scope 识别码。

Work／Knowledge／Code 共用 Identity Cookie 登录。首次加载时检查 `/auth-api/status` 与 `/auth-api/me`；全新安装显示 admin 设置页，否则显示 email／password 登录。邀请与复原必须是真正可操作的表单。一般登录 UI 不提供人类 bearer-token 字段或 local-session 按钮。

凭证只保留在密码输入字段的 state 中，完成或卸载时清除；不可写入浏览器保存空间。Fetch 使用 `credentials=same-origin`。已验证的写入请求加上来自 Identity me／login 的内存 CSRF token。未授权请求会清除 UI 身分并显示登录画面；工作阶段到期时提供易懂消息。切换产品或重新加载页面后会恢复 Cookie 工作阶段。注销先调用服务器 logout，再清除 UI 状态。

提供账号设置：变更密码、一次性 recovery-code 显示、工作阶段清单／撤销／全部注销，以及 admin 邀请／停用用户／指派访问权。将 codes 视为凭证：不可记录到 console，截屏须屏蔽或隐藏其值。呈现真实的服务不可用／权限错误。保留既有业务接口与独立建置模式。

## 容器验收 {#container-acceptance}

每个选定产品都可搭配自己的数据库及共用 Identity 服务／数据库部署；不得引入 Work／Knowledge／Code 彼此的服务依赖。Development 与 production 使用分开的 Identity 数据及 Cookie 名称。保留既有业务 volume。使用自有隔离 QA Identity 数据测试人类账号流程；绝不可用测试密码初始化用户的第一个 admin。让实际安装环境保持可用，供用户在应用程序中创建自己的 admin。

## 项目授权的冲突检查 {#permission-snapshots}

管理员 `PATCH /api/auth/users/{id}` 可在更新 `permissions` 时附上可选的 `expected_permissions:Permissions`。服务锁定目标用户后比较完整旧权限；不符返回 409 `permissions_changed`，不写入权限、不撤销会话。明确传入 null 或未同时提供新 permissions 返回 422；省略则保持旧客户端兼容行为。项目设置界面使用此快照，仅增减指定 Work scope 并保留其他产品及项目授权。角色仍以产品为单位，SCIM 防护、SSO 手动接管及变更后撤销登录政策保持不变。
