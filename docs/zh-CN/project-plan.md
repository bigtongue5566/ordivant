<span id="ordivant-專案實作計畫"></span>
<span id="ordivant-项目实作计划"></span>

# Ordivant 项目实作计划 {#ordivant-implementation-plan}

来源：用户的规划对话，并于 2026-10-06 用户调整范围后重新确认。产品为 **Ordivant Suite**，Work、Knowledge、Code 位于同一个 monorepo，并保有各自独立部署的界线。Code 可选择使用开源 Gitea；Work 可直接连接既有企业版控，不依赖 Code。技术组合：uv／Python、React、Pi Durable（仅 Work 使用）、PostgreSQL。

状态快照（2026-10-08）：本机 Suite 的原生帐号、组织／Agent 模型设置及企业 SSO 均已完成。本次版本交付 Work Run 控制台、不可变的 Agent／工作流程范本、可持续运行的间隔工作流程、受限的外部 MCP 工具，以及每次 Run 各自隔离的 Docker 沙箱。Identity／Work／Knowledge／Code 分别有 28／41／10／20 项测试通过；Runtime 有 25 项，沙箱有 3 项。实际验收包含 53 项完整容器检查、20 项经授权的 gpt-6.1-sol 检查、16 项收据／凭证检查、9 项终端清理检查、8 项 PostgreSQL 并发检查、67 项 Docker 隔离检查及 2 项当机复原检查，以及 65 项桌面／行动浏览器检查。开发模式 `5173` 和本机正式模式 `8088` 均已就绪，40 项环境保留／就绪检查通过，数据库与 Gitea 健康。已移除隔离的运行 QA 与较早的 SSO QA 容器，并保留具名 volumes。用户会自行创建第一位管理员；主环境帐号、SSO 及既有模型／Provider 设置均已保留。本次版本依据 `docs/execution-contracts.md`；企业身分仍依据 `docs/sso-contracts.md`。验收纪录及 `docs/validation.md` 收录证据与仍待客户环境确认的项目。

以下原始验收条件仍是 Work 模块的门槛。目前产品范围、端点契约及集成 Suite 的验收要求定义于 `docs/suite-contracts.md`；扩充产品范围时以该文件为准。

<span id="delivery-v01-suite-local-pilot"></span>

## 交付内容：v0.1 Suite 本机试行 {#delivery-v0-1-suite-local-pilot}

提供一个组织、两个团队、多个 Agent，并依项目范围授权。交付可运行的 Work、Knowledge 和 Code 模块，而非静态展示稿。SQLite 是有明确文档说明的快速入门模式；各产品的 SQLAlchemy 层也支持 PostgreSQL。产品不会读取彼此的数据库。每个 Work runtime 程序各自隔离 Pi 保存空间。共用 Identity 支持标准 OIDC，以及可选的 Keycloak SAML／LDAP／AD broker。真实 Keycloak OIDC 与签章 SAML 集成已验证；每位客户的身分租户、目录及既有企业版控凭证仍须分别设置并验收。

## 验收条件 {#acceptance-criteria}

1. 在连接的 React 工作区中创建及查看项目、结构化任务、相依关系、Agent 与证据。
2. 两个同时发出的 claim 尝试只能有一个成功。运行逾期后，即使出现新的 claim，旧运行也不能再更新进度或提交结果。
3. 相依任务尚未完成时不得 claim；系统拒绝循环相依；已接受的成果会解除后续任务的阻挡。
4. Agent A 向 B 求助；B 收到并回复，或运行委派任务；A 收到回复并继续工作；审查者 C 接受成果。
5. 重复的变更请求与事件传递不会创建重复任务、运行、消息或成果物。
6. REST 和 MCP 运行相同的身分／项目／角色政策。Agent 不得冒用其他身分；运行中的 Agent 不得核准自己的工作。
7. 后端重新启动后，稽核纪录与运行历程仍然存在。Pi Durable 持久化／续跑以确定性 fixture 测试；用户授权的测试 Provider 则分别验证已设置模型的即时工具运行、不含机密的收据及重启后持久性。
8. UI 显示错误／加载中／空白状态，在小屏幕可用，并使用真实 API 数据。用户能创建、查看、协作及审查。
9. 文档说明安装、启动、MCP 连接、凭证、数据备份及限制。交付内容包含锁定档、验收结果及更新后的任务清单。

## 任务清单 {#task-ledger}

| ID | 负责者 | 交付项目 | 状态 |
|---|---|---|---|
| ORD-001 | PM | 架构、契约、范围及验收计划 | 已完成 |
| ORD-002 | luna-backend | Work 持久化、身分／RBAC、任务、租约、协作、证据、稽核及 MCP | 已完成；19 项单元测试，以及 REST／MCP／PostgreSQL 验收通过 |
| ORD-003 | luna-frontend | Work 操作工作区、任务看板／查看器、Agent、协作、证据与审查 | 已完成；类型检查／建置、浏览器创建项目／任务及 390px 规格编辑通过；协作／审查 API 通过 |
| ORD-004 | luna-runtime | Pi Durable adapter、持久派送、受限平台工具及复原 | 已完成；2 项单元测试及实际 Harness／outbox／重新启动验收通过 |
| ORD-005 | PM | 本机 runner、seed 流程、环境／文档、集成及浏览器／API 验收 | 已完成；原生与容器集成、正式模式完整流程，以及连接 Work／Knowledge／Code 的浏览器检查通过 |
| ORD-006 | luna-runtime | 独立 Knowledge 后端：不可变版本、搜索、决策、来源追溯、API／MCP | 已完成；5 项单元测试、集成版本／CAS 流程及仅 Knowledge 的容器验收通过 |
| ORD-007 | luna-backend | 独立 Code 后端：Gitea 保存库／分支／提交／PR／检查、签章 webhook、API／MCP | 已完成；15 项单元测试、真实 Gitea 集成及仅 Code 的正式模式验收通过 |
| ORD-008 | luna-frontend | Suite 导览，以及可独立建置的 Knowledge／Code 工作区 | 已完成；四种建置、真实产品浏览器流程、公开 Gitea 网址、来源追溯选取及 390px 表单检查通过 |
| ORD-009 | PM | 独立 API／MCP 启动，以及真实 Gitea 的 SQLite／PostgreSQL Suite 验收 | 已完成；两份 Suite 报告及独立 Work PostgreSQL 报告通过 |
| ORD-010 | PM | Compose 集成，以及前端、API 和 runtime 的开发／正式映像 | 已完成；六个应用程序映像（含 Identity）、开发／正式完整流程、Knowledge／Code 独立部署及持久化检查通过 |
| ORD-011 | luna-runtime | 容器 worker helper、runtime 启动／就绪集成及操作文档 | 已完成；两个 helper 均可启动；五项来源热重载条件与逐字节还原检查通过，包含 Windows bind mount 上的 TypeScript 轮询 |
| ORD-012 | luna-backend | 后端容器 QA：开发 proxy 验证、正式模式访问控制及 403 案例 | 开发 proxy 验证／直接 403，以及正式模式本机 403／范围读取通过 |
| ORD-013 | luna-reload-qa | 可重现的五来源开发热重载验收 | 已完成；所有 API worker PID、Pi 编译输出／server PID、Vite 来源／HMR 及还原后 SHA-256 检查通过 |
| ORD-014 | luna-production-qa / PM | 通过 Nginx 和内部 Pi runtime 验收正式模式完整流程 | 已完成；Suite／Git／MCP／Pi、本机 session 403、Work 在其他产品停止时运作，以及重启持久化检查通过 |
| ORD-015 | luna-code-standalone / luna-identity-bridge | 不含 Gitea 的仅 Code 部署，以及具范围限制的官方 MCP 检查 | 已完成；Code API／PostgreSQL／web 加上 Identity API／PostgreSQL、明确 Gitea 503、9 个 MCP 工具、范围及重新启动检查通过 |
| ORD-016 | luna-identity | 独立 Identity API／数据库：帐号、密码登录、邀请、复原、session 及管理控制 | 已完成；11 项安全测试、锁定档／wheel／建置检查，以及真实 HTTP 生命周期验收通过 |
| ORD-017 | luna-identity-bridge | 共用人员验证、独立产品主体、范围授权、CSRF／Origin 与 bearer 兼容性 | 已完成；每个产品 5 项 bridge 测试、55 项开发／正式验收，以及五服务独立部署通过 |
| ORD-018 | luna-login-ui / PM | 原生登录／设置、邀请／复原、帐号／session 管理、管理员权限及鼠标操作下拉列表 | 已完成；四个产品建置、实际鼠标操作产品／状态／优先级／范围选取，以及 390px 帐号／注销检查通过 |
| ORD-019 | PM | Identity Compose／原生工具、契约／文档、隔离验证验收及业务回归 | 已完成；开发／正式环境就绪，每种模式 55 项 HTTP 检查，正式 REST／MCP／Git／Pi 回归、用户首次管理员页面及 QA 清理均已验证 |
| ORD-020 | luna-model-backend | 组织模型连接、加密凭证、Agent 继承／覆写、具 fencing 的范围限制 runtime 交接 | 已完成；Work 31 项测试，revision／RBAC／错误屏蔽／密钥保留／null snapshot 检查，以及隔离 cookie HTTP 验收通过 |
| ORD-021 | luna-model-runtime | Pi Responses Provider 设置、实际模型／用量／工具收据、两次租约 heartbeat 及凭证复原 | 已完成；使用实际 Pi adapter 的 5 项测试、真实 gpt-6.1-sol 平台工具运行、用量明细及完成收据重新启动通过 |
| ORD-022 | luna-model-ui | 管理员模型设置，以及 Agent 创建／编辑时的模型选取 | 已完成；四种建置、实际鼠标操作设置保存／创建／编辑／重载，以及 390px 弹出层／持久化检查通过 |
| ORD-023 | PM | 模型契约／操作导入、容器集成、即时端点／工具／审查验收及文档 | 已完成；开发／即时及正式 DEMO 回归、密钥／暂时 token 纪录检查和隔离 QA 清理通过；详见 model-validation.md |
| ORD-024 | luna-sso-backend | 企业 OIDC、加密设置、范围限制的布建／群组授权、生命周期撤销及稽核 | 已完成；28 项安全测试、锁定档／编译检查及真实协定／生命周期验收通过 |
| ORD-025 | luna-sso-ui | 共用企业登录、Provider 范本、政策／链接及稽核管理 | 已完成；六个 Provider 范本、TypeScript／四种建置、实际桌面／390px 鼠标检查、立即更新状态、仅 SSO 模式复原及仅管理员可创建范围通过 |
| ORD-026 | luna-sso-qa / PM | 真实 Keycloak OIDC 与 SAML broker、隔离 PostgreSQL／浏览器验收、容器集成及操作文档 | 已完成；136 项真实 HTTP 检查、27 项保存／日志／重新启动检查、OIDC／SAML 浏览器验收、主环境就绪及隔离 QA 清理通过；详见 sso-validation.md |
| ORD-027 | luna-run-backend | 授权的 Run 查看／控制、不可变 Agent／工作流程范本、持久调度器及项目工具／设置档设置 | 已完成；41 项业务／安全测试及 8 项实际 PostgreSQL 并发检查；REST／MCP 共用业务授权 |
| ORD-028 | luna-run-runtime | 实际 Pi 事件／控制闸门、受限外部 MCP 工具及隔离 Docker 运行器 | 已完成；25 项 Runtime 与 3 项沙箱测试、真实模型／工具收据、67 项实际运行器检查、2 项当机复原检查，以及终端同步前清理回归检查通过 |
| ORD-029 | luna-run-ui | Run 查看器／控制、版本化自动化编辑器及工具／沙箱管理 | 已完成；TypeScript／四种产品建置及 65 项实际桌面／行动鼠标检查通过，包含 server 回复遗失后重试，以及实际收据／stdout／exit 0／7 |
| ORD-030 | PM | 共用契约、沙箱 Compose／helper，以及本机 API／容器／鼠标验收 | 已完成；完整容器 53 项、即时 20 项、凭证 16 项、最后清理 9 项及主环境保留／就绪 40 项检查通过；两个本机环境均已更新，并移除本项目拥有的 QA；详见 execution-validation.md |

## 架构决策 {#architecture-decisions}

- FastAPI service 是业务状态的唯一真实来源。SQLAlchemy 支持 SQLite 本机快速入门，也支持 PostgreSQL 试行部署。
- 公开 REST 前缀为 `/api`。MCP 通过 stdio 另行提供（用户端 HTTP bridge 使用 Agent 凭证）；未来可加入可串流的 HTTP，而不重复实作业务逻辑。
- 人员验证在两种模式都使用独立 Identity service：密码登录、邀请、复原及服务器管理的 cookie session。Agent REST／MCP 使用各自签发、以哈希保存的不透明 token。Identity 设置完成后，两种模式都会停用旧的本机 session 端点；详见 `auth-contracts.md`。
- 每个组织环境可设置一个企业 OIDC Provider，使用 Authorization Code + PKCE、精确的 subject 链接、邀请／JIT 成员资格，以及明确的资源／群组授权。SSO 不会根据 Provider claim 指派管理员角色。SAML 和 LDAP／AD 使用可选的 Keycloak broker；详见 `sso-contracts.md`。
- 所有 Agent 变更都从验证信息记录操作者身分，绝不采用未受信任请求本文中的身分字段。所有对象都会依允许的项目与组织范围过滤。
- 租约包含 execution id 及不可猜测的 fencing token。每次运行中的变更都会验证两者的拥有权及租约是否过期。
- 工作流程状态：`backlog`、`ready`、`in_progress`、`blocked`、`in_review`、`done`、`cancelled`。
- 一般情况下，只有通过审查才能转为 done。指派任务不会授予项目访问权。
- Outbox 事件会与业务状态一起原子化持久保存，并由 runtime worker 领取。Runtime request id 等于 outbox id；回呼具幂等性。
- 每个 Pi SQLite 保存空间只由一个 runtime 拥有。已设置模型／Provider 的身分会明确呈现；具确定性的 demo 模式则分开处理并清楚标示。

## 接口设计 {#interface-design}

视觉方向：平静、精准的操作工作区，采用温暖中性色表面、石墨色导览、紫罗兰色操作，以及精简易读的任务信息。
内容规划：以项目／任务工作区为主、导览为辅；任务查看器呈现结构化规格、运行、协作及审查证据。
交互方向：快速切换查看、抽屉／对话框采用克制的进场效果，并清楚呈现 hover／focus 状态；尊重减少动态效果的偏好。

## 扩充 Suite 验收门槛 {#expanded-suite-gates}

- Knowledge 发布不可变的精确版本规格与决策；文本检索回传可追溯的引用。
- Code 调用真实 Gitea API 管理 repository／branch／commit／PR／status，并验证有签章且去重后的 webhook。
- 每项产品都有各自具范围限制的身分、数据库、REST API 及 MCP 入口。
- 前端各产品模式可分别建置／部署；即使另两项产品停止运作，Work 仍可使用。
- 完整来源追溯链：Knowledge v1 -> Work task/delegation -> Code PR/evidence -> Work review -> Knowledge v2。

## 公开版本交付（2026-10-08） {#public-release-handoff-2026-10-08}

公开 repository 为 `ordivant-ai/ordivant`，采用 MIT 授权。VitePress 文档网站包含安装、产品指南、维运、疑难排解及 API 契约。公开 CI 会检查五个 Python 项目、Runtime、四种前端模式及合成 REST／MCP 集成；Pages 会建置网站并验证本机链接。付费服务验收须由操作人员明确设置并在隔离 QA 环境运行；不会缺省提供私人 Provider，也不会自动查找主环境凭证。

版本来源从 Git index 导出到干净目录，并以新的 Compose project 启动。全部 12 项服务均进入健康状态；真实 Knowledge／Work／Gitea／MCP／Pi DEMO、独立审查、产品隔离及重新启动后持久性均通过。Gitleaks 扫描来源导出内容，未侦测到机密。过往被忽略的 QA 报告不会随版本发布。下列企业验收门槛刻意保留为未完成项目，但不影响已声明的 v0.1 范围。

## 尚待完成的企业验收门槛 {#remaining-enterprise-gates}

候选功能、目前实作界线与建议优先级记录在[功能缺口研究](feature-gap-research.md)。该研究不会将候选功能标示为已实作，也不会将其加入已完成的任务清单。

- SCIM 2.0 Users／Groups、SMTP outbox、OIDC acr／amr 验证及 Identity 审计导出／保留已加入当前代码，但客户 IdP／目录布建及企业租户生命周期整合验收仍待完成。原生 SAML 端点与 Keycloak SAML broker 是不同实作。
- 更多正式环境 Provider／模型组合、已确认的费率／发票集成，以及硬性成本上限。用户授权的测试 Provider／gpt-6.1-sol 合成即时运行及 token 收据记录在 `model-validation.md`；这不代表一般帐单控制已完成。
- 既有 GitHub／GitLab／Jira 的正式同步凭证、MCP gateway、外部 A2A、对象保存及备份还原演练。
- 可扩展的派送所有权／分片、负载测试及营运监控。

不能只因为存在接口或占位组件，就将这些门槛标记为已完成。

## P0/P1 验收清单 {#p0-p1-acceptance-ledger}

此清单补充 2026-10-15 P0/P1 契约的交付边界。本地整合与验收已完成；客户 IdP／SCIM 租户及 GitHub／GitLab 部署 provider／CI 结果未测试。此清单不代表功能已发布到 v0.2.0 或可用于其他部署。

2026-10-15 本地验收快照（尚未推送或发布）：backend／Runtime 共 220 项测试通过（Work 82、Identity 38、Knowledge 32、Code 40、Sandbox 3、Runtime 25）；tool guards 20 项通过、1 项略过。Work 真实 PostgreSQL API 53 项及浏览器 51 项、Code 真实 Gitea API 65 项及浏览器 34 项、Knowledge 真实 PostgreSQL authoring 4 组及浏览器 336 项、Enterprise STARTTLS SMTP／SCIM 30 项及浏览器 10 项（含审计 API 游标分页）通过。整合与产品 smoke、四个产品 build、i18n 1,750 项／3 语系／7 项行为检查通过。四个 API 服务重新启动后健康；4 个数据库共 103 张表、4,836 条数据的逐表 row count 与完整数据 hash 均一致，没有异动或非预期表格；既有协作 context API 读回 7/7 通过。

| ID | 范围 | 状态 |
|---|---|---|
| P0-1 | Work 规划字段、同一 Project 的 Epic 防循环、Sprint／里程碑／字段／阶段设置与 rank 排序 | 本地验收通过：真实 PostgreSQL API 53 项及浏览器 51 项；数据库重启持久性通过 |
| P0-2 | 资源附件、提及、订阅、通知、协作中心、授权范围内跨产品搜索及 SMTP 邀请／恢复 outbox | 本地验收通过：tool guards 20 项通过、1 项略过；整合／产品 smoke、Work／Knowledge UI 与协作 context 读回 7/7 通过 |
| P0-3 | Knowledge 页面树与封存、引用锚定留言／回复／解决、Space 范本、Markdown 工具、版本差异与还原 | 本地验收通过：真实 PostgreSQL authoring 4 组、浏览器 336 项及数据库重启持久性通过 |
| P1-1 | 项目提报表单、自定义字段、阶段与同步事件规则 | 本地验收通过：Work 真实 PostgreSQL API 53 项、浏览器 51 项及数据库重启持久性通过 |
| P1-2 | 授权范围内搜索、个人保存的查找、带作者身份的工时、观察报表与安全原子 CSV | 本地验收通过：Work 真实 PostgreSQL API 53 项、浏览器 51 项及数据库重启持久性通过 |
| P1-3 | 上游 Git checks／actions／pipelines／部署证据、绑定 head SHA 的 inline review 与真实 branch protection | 本地真实 Gitea API 65 项与浏览器 34 项通过；未测试 GitHub／GitLab 部署 provider 成功结果或外部 CI |
| P1-4 | SCIM Users／Groups、外部 IdP ACR／AMR MFA 政策、邮件及受控审计保留／导出 | 本地验收通过：STARTTLS SMTP／SCIM 30 项与浏览器 10 项，含审计 API 游标分页；未测试客户 IdP／SCIM 租户 |

验收前置条件已通过：REST 与 MCP 使用同一服务授权；管理写入与资源读取重新检查当前权限；覆盖循环、跨 Space／Project 权限、并发唯一性、幂等、过期或 stale 版本、未发布共同草稿以及升级时原有数据保留。QA 已明确验证没有已配置的 LLM provider 时 provider 列表为空；真人认领、提交证据、独立审核及共同 Markdown 编辑可正常运作。四个 API 服务重启后健康；4 个数据库共 103 张表、4,836 条数据的逐表 row count 与完整数据 hash 完全一致，没有异动或非预期表格；协作 context API 读回 7/7 通过。这批没有运行付费 LLM，也未验证客户 IdP／SCIM 租户或 GitHub／GitLab 部署 provider／CI 成功结果。不得以 Agent 自报值冒充已验证支出或 CI。

企业验收还需证明：未配置 SMTP 时不寄信，测试邮件只投递至合成 sink；SCIM 不依 email 认领既有账号，一般 user PATCH 不可更改权限，明确 SSO 链接使用 `managed_permissions=false` 以保留 SCIM 群组权限来源，停用会撤销 session，群组不能授予 admin；MFA 只接受符合政策的已验证 IdP acr／amr；审计导出有界且不含机密。Git checks、review 和部署结果必须对应真实上游 URL／SHA／来源，head 改变后 inline comment 明确标记过期。以上状态仅代表本地整合验收，不代表已发布到 v0.2.0 或通过客户专属 IdP／SCIM 租户及 GitHub／GitLab 部署 provider／CI 验收。

## 国际化交付（2026-10-08） {#internationalization-delivery-2026-10-08}

应用程序与公开文档目前支持繁体中文（`zh-TW`）、简体中文（`zh-CN`）及英文（`en`）。共用导览会在各产品和分页之间保留浏览器的语言偏好。应用程序文本、Ant Design 组件、日期、数字及 API 错误呈现会依选定语言更新；用户撰写的内容及 API 识别码保持原样。切换语言时，已打开的表单会保留草稿，并重新验证既有错误。

验收结果：1,247 则语系目录消息通过完整性／插值／来源文本检查及 7 项语系行为检查；四种前端目标皆完成建置；Identity、Work、Knowledge、Code 及行动版面共完成 121 项隔离浏览器检查；文档完成 46 项浏览器检查；产生 109 个 HTML 页面（每种语言 36 篇文章，另有 404 页），检查 5,030 个本机参照，链接错误为 0。浏览器报告保留于忽略的 `.data/validation/`。这些接口检查不需调用付费模型。维护方式及可重复运行的命令见[语言与翻译](i18n.md)。

## 国际化修正与组织迁移（2026-10-09） {#internationalization-correction-2026-10-09}

第一轮文档验收只覆盖导航与部分文章，未拦截容器、契约及验收记录中的英文正文。修正版已完整翻译三语对应文章，并将每份文档的段落与表格加入构建前检查。三语采用相同的章节标识符，保留旧书签，切换语言时仍会停在对应章节。

修正版通过 108 份文档来源检查、8 项漏翻回归检查，以及 388 项实际文档浏览器检查。平台补齐共用品牌、离线状态与 Agent 运行环境文案；1,250 则目录消息、四种前端构建与 127 项隔离浏览器检查均通过。这次验收没有调用付费模型。

源代码已迁移至 `ordivant-ai/ordivant`。文档站仓库为 `ordivant-ai/ordivant-ai.github.io`，使用 GitHub Pages 原生工作流读取公开来源的精确 revision，构建并发布至 <https://ordivant-ai.github.io/>。发布方式与来源版本核查见[语言与翻译](i18n.md)。
