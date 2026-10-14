# 验收纪录 {#validation-record}

日期：2026-10-08（Asia/Taipei）。状态：本机 Suite 已包含原生账号、组织／Agent 模型设置，以及可选用 Keycloak SAML／LDAP／AD broker 的企业 OIDC。最新 Work 版本交付 Run 控制与收据、版本化 Agent 与工作流程范本、持久化间隔调度、外部 MCP 连接，以及每次运行各自隔离的 Docker sandbox。实际模型／工具运行、独立审查、容器重新启动、并行处理、工作区清理，以及桌面／行动版浏览器检查均已通过。两个既有本机环境均已更新，并保留其账号／SSO／模型／项目数据。下方较早的试点、模型与 SSO 验收门槛仍属历史证据；目前的运行契约与结果见 `docs/execution-contracts.md` 和 `docs/execution-validation.md`。在本报告日期之后，Identity SMTP／SCIM 实作通过 11 项隔离检查；客户专属 IdP／目录和正式营运验收仍待完成，见[现行 P0/P1 清单](project-plan.md#p0-p1-acceptance-ledger)。

## 必要验收门槛 {#required-gates}

| 验收门槛 | 证据 | 状态 |
|---|---|---|
| 可重现的相依套件 | backend/uv.lock、frontend/package-lock.json、runtime/package-lock.json | 已通过／已安装 |
| Work 业务与授权风险 | Work 单元测试 | 已通过：41 项测试，涵盖 Identity bridge、模型设置、Run 控制／同步、不可变范本、工作流程调度与工具／设置档范围 |
| Knowledge 业务与授权风险 | Knowledge 单元测试 | 已通过：10 项测试，包含 Identity bridge 涵盖范围 |
| Code 业务与授权风险 | Code 单元测试 | 已通过：20 项测试，包含 Identity bridge 涵盖范围 |
| 人类账号安全性与生命周期 | Identity 单元测试、lock 检查与 Docker 建置 | 已通过：28 项测试；涵盖本机账号生命周期、签章 OIDC claims、PKCE／state／nonce、subject 链接、布建、政策／撤销、backchannel 重播、trusted proxy 与增量迁移 |
| Pi Durable adapter 与复原单元检查 | Runtime 单元测试 | 已通过：25 项测试，包含已设置的 Responses／cache、实际 SDK 工具事件、lease 串行化、控制闸门、完全相同本文的重试、即时运行复原，以及延迟／失败的终端清理 |
| 前端 TypeScript 与产品建置 | `npm run typecheck`；`npm run build`、`npm run build:work`、`npm run build:knowledge`、`npm run build:code` | 已通过，包含 Knowledge／Code 可重试的 health 检查 |
| 独立 API／MCP 进程启动 | Work、Knowledge 与 Code 黑箱启动检查 | 已通过 |
| REST 协作与并行认领 | SQLite Work 验收 | 已通过：并行认领中恰有一项成功；求助、委派、审查者分离、幂等性与范围检查均通过 |
| 官方 MCP SDK 探索与选定往返调用 | Work MCP 验收；`.data/validation/20261008-021346-6e1664/report.json` | 已通过：最新官方 SDK 探索列出 29 个工具，并实际往返验证协作／认领／范围／相依性／审查，以及 Pi DEMO 派送。较早的试点列出 18 个工具；两者都不表示每个已注册工具都曾被调用 |
| 限定范围的 outbox -> Pi -> 证据 -> 审查者流程 | 实际 Pi Durable Harness、outbox 与重新启动复原 | 已通过 |
| PostgreSQL Work 业务数据库 | `.data/validation/20261006-023924-a991c9/report.json` | 已通过 |
| 使用真实 Gitea 的完整 SQLite Suite | `.data/validation/suite-20261006-023713-2dc030/report.json` | 已通过；完整 provenance 流程、实际 PR、签章 webhook 重播、重新启动后持久性，以及停止 peers 时的 Work 均通过 |
| 使用真实 Gitea 的完整 PostgreSQL Suite | `.data/validation/suite-20261006-023940-7a147c/report.json` | 已通过；完整 provenance 流程、实际 PR、签章 webhook 重播、重新启动后持久性，以及停止 peers 时的 Work 均通过 |
| 前端／后端／runtime 开发与 production 映像 | PM 容器映像建置 | 已通过：共六个应用程序映像，包含独立 Identity；既有第三方数据库／Gitea／broker 映像仍分别固定版本 |
| 开发容器端对端、dev proxy 验证与直接 403 | `.data/validation/containers-ordivant-dev-85eff4cd-20261006-025843-d04d7a/report.json` | 已通过：PostgreSQL、Suite／MCP／Pi、停止 peers 时的 Work、重新启动后持久性与 dev proxy 检查 |
| Production 初始基本门槛 | `.data/validation/containers-ordivant-prod-85eff4cd-20261006-025955-5d0de6/report.json` | 已通过：8088 Web、API prefixes、PostgreSQL、production local 403、范围读取与重新启动后持久性；完整 production 验收记录如下 |
| 通过 Nginx 的 Production 完整流程 | `.data/validation/containers-ordivant-prod-85eff4cd-20261006-220058-bd14cd/report.json` | 已通过：实际 Suite／Git／MCP 流程、内部 Pi Durable 派送、全部 local-session 403 检查、停止 peers 时的 Work、API 重新启动与流程／seed 持久性 |
| 仅 Knowledge 的容器验收 | `.data/validation/standalone-knowledge-ordivant-knowledge-qa-20261006-031232-1c2cc5/report.json` | 已通过：仅有 Knowledge API、PostgreSQL 与 Web；创建／重播／精确 SHA／搜索／reader 403、容器内官方 MCP 的 8 个工具与指定版本读取、重新启动及最后 readiness |
| 未设置 Gitea 的 Code-only 容器验收 | `.data/validation/standalone-code-ordivant-code-qa-20261006-220447-410767/report.json` | 已通过：仅有 Code API、PostgreSQL 与 Web；独立 bundle、范围／reader 403、项目持久性、明确的 Git 写入 503、官方 MCP 的 9 个工具及 repository／event 读取；13 个条件全部通过 |
| Dev／prod helper 启动 | PM Compose helper 检查 | 已通过：两种 helper 变体都成功完成 `up` |
| 五个来源文件的开发热重新加载 | `.data/validation/hot-reload-acceptance-20261006T135822Z-26cbb8.json` | 已通过：三个 API worker PID 改变、Pi 原代码成功编译且 server 子进程 PID 从 458 变为 732、Vite 回传标记／HMR、所有 health 均为 200，五个来源文件都已还原至原始 SHA-256 |
| 产品部署独立性 | 上方 PM Compose 验收；下方 authentication 版本 | 已通过：Work 可在 peers 停止时运作；每个独立产品都有自己的 API／数据库／Web，以及独立 Identity API／数据库 |
| 浏览器：Work 创建项目与完整结构化任务 | 已连接的应用程序 | 已通过 |
| 浏览器：Knowledge 创建 v1、发布 v2、保留 v1 SHA／历史记录并创建决策 | 已连接的应用程序 | 已通过实际 API 验证 |
| 浏览器：Code 真实 repository／branch／commit／PR／status 与公开 URL | `.data/validation/browser/code-provenance-390.jpg`；`browser/report.json` | 已通过：实际私有 repository 与 UTF-8 commit、PR、位于 127.0.0.1:3002 的 Gitea URL、精确 Knowledge 版本 provenance，以及清楚标记为 agent_reported 的状态 |
| 浏览器：390px 窗口 | `.data/validation/browser/report.json` 及 Work／Knowledge／Code 截屏 | 已通过：文档没有水平溢出；Work 规格编辑已保存，Knowledge 搜索／历史／表单及 Code branch／PR／provenance 表单均可操作 |
| 开发模式原生登录 HTTP 验收 | `.data/validation/auth-ad6c32a4/report.json` | 已通过：55 项检查；三个 Cookie principal、明确成员范围、重新启动后持久性与 Identity 中断时采取 fail-closed |
| Production 原生登录 HTTP 验收 | `.data/validation/auth-1b5fc8b5/report.json` | 已通过：通过 Nginx 完成 55 项检查；邀请／复原仅可使用一次、密码变更、工作阶段撤销、权限变更、节流、CSRF／Origin 与停用账号 |
| 激活 Identity 后的 Production 业务回归 | `.data/validation/containers-ordivant-prod-85eff4cd-20261006-233819-4246ee/report.json` | 已通过：Suite／Git／MCP／Pi、拒绝所有旧版 local-session endpoints、停止 peers 时的 Work 与重新启动后持久性 |
| 激活 Identity 的 Knowledge-only 部署 | `.data/validation/standalone-knowledge-ordivant-knowledge-qa-20261006-234154-96dbda/report.json` | 已通过：五个服务、24 项检查、首次人类用户设置就绪、范围限定的 bearer／MCP 与重新启动后持久性 |
| 激活 Identity 的 Code-only 部署 | `.data/validation/standalone-code-ordivant-code-qa-20261006-234312-7e2f48/report.json` | 已通过：五个服务、首次人类用户设置就绪、范围限定的 bearer／MCP、未设置时明确拒绝 Git 写入并回传 503，以及重新启动后持久性 |
| 浏览器：原生验证与实际鼠标下拉列表操作 | `.data/validation/auth-browser/report.json` 及截屏 | 已通过：三种产品选择器、Work 状态／紧急任务持久性、Drawer／Modal 上方的权限弹出菜单、390px 弹出菜单边界、行动版账号控制项与刷新后仍有效的注销 |
| 组织模型设置／范围限定的 Agent 覆写 | `.data/validation/model-settings-76ed3fd4/report.json` | 已通过：仅使用管理员 Cookie、Origin／CSRF、revision、保留密钥／错误屏蔽、catalog、继承与设为 null 清除；未调用 provider |
| 模型设置与 Agent 表单的鼠标操作 | `.data/validation/model-browser/report.json` 及截屏 | 已通过：桌面／行动版设置保存、添加覆写、编辑继承、重新加载、Modal 弹出菜单指针命中，以及 390px 无溢出 |
| 即时 gpt-6.1-sol endpoint 与工具往返调用 | `.data/validation/live-probe-388b5ccd/report.json` | 已通过：models 探索、实际 Responses 完成事件，以及由合成模型发起的 function-call 往返调用 |
| 即时 Work／Pi／工具／证据／审查及重新启动 | `.data/validation/live-work-08fdbdb1/report.json` | 已通过：27 项条件、新的范围限定 Agent／项目派送、get_task_context／report_progress、回传的模型、包含 token／cache 的收据、拒绝自行审查、独立测试审查者与持久化的已完成提交 |
| Provider 与派送凭证记录检查 | `.data/validation/live-work-08fdbdb1/record-checks.json` | 已通过：密钥已加密、确认后撤销、Pi 或幂等记录中没有密钥／派送 token，近期服务记录也没有 provider key |
| 更新后的 production runtime fallback 回归 | `.data/validation/model-production-runtime.json` | 已通过：未设置 provider 时，使用实际 Pi 运行明确标记的 DEMO，并完成证据与独立审查；provider 连接仍未设置 |
| 真实企业 OIDC 与 SAML broker | `.data/validation/sso-32eb71e9/report.json` | 已通过：136 项检查；实际签章 provider 流程、精确产品范围、JIT／邀请／链接、群组撤销、SSO-only、停用成员、签章 backchannel 注销与敏感信息屏蔽 |
| 企业加密保存、记录与重新启动 | `.data/validation/sso-84b63356/storage-report.json` | 已通过：27 项检查；PostgreSQL／加密／哈希流程状态、私有持久化密钥、不保存 provider token／code、实际重新启动 Identity／Keycloak 与不含秘密的记录 |
| 企业登录／设置与鼠标操作 | `.data/validation/sso-browser/report.json` 及截屏 | 已通过：OIDC／SAML 与共用工作阶段、六种范本、连接测试、保存后立即更新状态、390px 下拉列表命中／边界、由 IdP 管理的密码接口、SSO-only 管理员复原，以及仅管理员可创建 Project／Space |
| 更新后主环境的开发／本机 production 就绪状态 | `.data/validation/sso-browser/main-environments.json` | 已通过：两个 origin、三个 health prefixes 与 Identity 状态均回传 200；主环境仍需完成初始设置，且未设置 SSO |
| Run 控制、范本与完整工作流程运行 | `.data/validation/execution-e8f561d8/report.json`；`execution-postgres.json` | 已通过：53 项完整容器检查及 8 项实际 PostgreSQL 并行检查，包含停止／重试／历史、经审查的相依项目、实际间隔调度、取消与启动时权限授予 |
| 实际即时 MCP／模型／sandbox 运行 | `.data/validation/execution-55faa750/live-report.json` | 已通过：使用已授权的 gpt-6.1-sol 连接完成 20 项检查，包含协作式暂停／继续、实际 MCP sum=42、真实 Python stdout／exit 0 与 7、独立审查及重新启动后的收据 |
| Runtime 记录与终端清理 | `.data/validation/execution-55faa750/record-checks.json`；`execution-cleanup.json` | 已通过：16 项凭证／记录检查及 9 项实际清理检查；密钥已加密、暂时 token 已撤销、取得真实 Pi 结果、没有剩余自有工作，且 terminal sync 前已完成清理 |
| Docker sandbox 隔离／复原 | `.data/validation/sandbox-integration.json`；`sandbox-crash-recovery.json` | 已通过：67 项实际隔离／资源／路径／逾时检查，以及 executor 收到 SIGKILL 并重新启动后的 2 项自有工作清理检查；Docker 仍是共用内核的隔离边界 |
| 运行功能的桌面／行动版浏览器操作 | `.data/validation/execution-browser/report.json`；`execution-run-browser/report.json`；`execution-live-browser/report.json` | 已通过：45 + 10 + 10 项检查；实际鼠标下拉列表／表单操作、已提交请求失去回复后的复原、历史／控制操作，以及桌面与 390px 行动版上实际收据／stdout／结束代码 |
| 最新主环境本机数据保留／就绪检查 | `.data/validation/execution-local-before.json`；`execution-local-after.json` | 已通过：5173／8088 上的 40 项检查；账号数／初始设置／SSO／模型／provider／项目快照未变，API／产品回传 200，runtime／sandbox／产品容器皆健康 |

Suite 验收流程涵盖：Knowledge 不可变 v1 与精确引用 -> Work 任务 A／B 及独立审查者 C -> 真实私有 Gitea repository、branch、commit 与 PR -> 六案例 fixture pytest -> 签章 webhook 重播 -> Knowledge v2 -> CAS 结果 `[201, 409]` -> 重新启动后持久性 -> 停止 Knowledge 与 Code peers，让 Work 直接读取 Gitea PR／checks 并结束任务。开发与 production 容器都通过此流程。Production MCP bridge 通过 Nginx 保留各产品 API prefix；Pi 验收在 Work 容器内对内部 runtime 服务运行，没有公开其连接端口。已连接的浏览器检查另外确认 Work 项目／任务创建与规格编辑、Knowledge v1／v2／历史记录／决策／搜索，以及 Code repository／branch／commit／PR／status 与精确版本来源选取。浏览器状态收据是 Agent 手动回报，不是外部 CI 运行结果。

Windows bind mount 需要以 polling 方式运作 TypeScript runtime watcher；`compose.dev.yaml` 同时设置 watch-file 与 watch-directory polling。验收 harness 会观察编译输出与变更后的 server 子进程 PID。Vite health probe 接受 HTML（`Accept: */*`），接着检查 source／HMR，并还原所有原始 source 字节。

账号验收使用专用 `ordivant-auth-qa` 项目、loopback 连接端口 `8092`、合成 fixture 与独立 volume。检查涵盖首次成员并行绑定、通用验证失败消息、目前密码检查、一次性复原、账号停用及最后一位管理员保护。代理程序未初始化主环境的开发与 production Identity 数据库；用户会在网页自行创建第一位管理员。重现方式记载于[账号验收](auth-validation.md)。

本纪录不包含任何凭证值。产生的测试数据与完整诊断信息保留在 git 忽略的 `.data/validation/` 目录。详细报告留在本机；此摘要省略凭证与含秘密的值。

验收后，通过 helper 的 `down` 动作停止暂时使用的 `ordivant-knowledge-qa`、`ordivant-code-qa` 与 `ordivant-auth-qa` 容器／network；其具名 volume 与本机 secrets 仍保留。开发 Suite 与本机 production-target Suite 维持运行。最后检查时，其 API、数据库、Web 与 Gitea 容器均健康；开发 runtime 也通过 HTTP health endpoint 确认正常。用户的两个 Identity instance 仍回报 `setup_required: true`；Work 显示原生的首次管理员设置表单。

企业身分版本使用独立的 `ordivant-sso-qa` 项目（连接端口 `8092/8093`），以及含公开合成 fixture 的两个真实 Keycloak realm。它不会在用户的主环境安装任何人类账号或企业 provider。浏览器操作使用已授权的合成 QA 账号；临时 viewport／tab 已清理，并保留用户原本的 tab。QA 容器／network 已停止，具名 volume 则保留。通用 OIDC 互通性与签章 SAML broker 往返流程已验证；客户自己的 Entra／Google／Okta／Auth0 tenant 与真实 LDAP／AD 目录，仍须各自设置并验收。详见 [SSO 验收](sso-validation.md)与[企业设置](enterprise-sso.md)。

模型版本验证了用户明确授权的 HTTPS endpoint、要求／回传的 `gpt-6.1-sol`、实际由 Pi 模型调用的 Work 工具、证据与独立测试审查。最后一次运行回报输入 17,157 tokens（其中 10,496 为缓存）、输出 97、合计 17,254；金额仍未知。Provider 发票／底层路由、硬性预算限制、客户专属企业 IdP tenant、已设置的企业 GitHub／GitLab 即时凭证、外部 CI、备份还原、负载测试及 production 可观测性均未验证。较早的 Pi 测试仍明确标示为 demo。测试模型连接只在开发环境设置。详见[模型验收](model-validation.md)与[模型使用方式](model-usage.md)。未运行远程部署、发布或 push。

运行功能版本的另一场已授权即时运行回报输入 40,000 tokens（其中 16,128 为缓存）、输出 744、合计 40,744；美元成本仍未知。MCP 测试 endpoint 与 sandbox 内容均为合成数据，但其实际调用、输出与结束状态已验证；DEMO 检查仍分开标示。暂停功能会在工具边界协作运行，工作流程以分钟为间隔调度，外部工具使用 Bearer 验证的 Streamable HTTP，工作容器则无网络。核准政策、硬性金额配额、交互式 MCP OAuth、任意 repository／network checkout，以及 VM 隔离仍属后续工作。验收后已移除自有的 `ordivant-execution-qa` 容器／network，并保留具名 volume 与报告；主开发／本机 production 数据库、Gitea 与服务仍健康。详见[运行功能使用方式](execution-usage.md)与[运行功能验收](execution-validation.md)。

## P0/P1 本地验收快照（2026-10-15） {#p0-p1-local-acceptance-2026-10-15}

以下结果来自尚未推送或发布的本地工作树；前面的记录保留各自日期的历史验收结果。

| 范围 | 结果 |
|---|---|
| Backend／Runtime 测试 | 220 项通过：Work 82、Identity 38、Knowledge 32、Code 40、Sandbox 3、Runtime 25 |
| 工具权限防护检查 | 20 项通过、1 项略过 |
| Work／Knowledge | Work 真实 PostgreSQL API 53 项及浏览器 51 项通过；Knowledge 真实 PostgreSQL authoring 4 组及浏览器 336 项通过。四个 API 服务重启后健康；4 个数据库共 103 张表、4,836 条数据的逐表 row count 与完整数据 hash 前后均一致；协作 context API 读回 7/7 通过 |
| Code | 真实 Gitea API 65 项及浏览器 34 项通过；未验证 GitHub／GitLab deployment provider 或 CI 成功结果 |
| 企业身份 | 真实 STARTTLS SMTP／SCIM 30 项及浏览器 10 项通过，包含审计 API 游标分页；客户 IdP／SCIM 租户仍待验收 |
| 整合与 i18n | 整合／产品 smoke、四个产品 build 通过；1,750 项消息、3 种语言与 7 项语系行为检查通过 |

QA 确认未设置 LLM provider 时 provider 列表为空；真人认领、提交证据、独立审核与共同 Markdown 编辑可在没有 LLM 时运行。本批没有运行付费 LLM，也没有验证客户 IdP／SCIM 租户或 GitHub／GitLab deployment provider／CI 成功结果。
