<span id="ordivant-功能缺口研究"></span>

# Ordivant 功能缺口研究 {#ordivant-feature-gap-research}

更新：2026-10-08（Asia/Taipei）。原研究于 2026-10-07 由 PM 与三位 luna-worker 盘点程序、契约及验收纪录，参考官方协定与产品文档。用户已选定 **F03 Run 控制台、F04 自动流程／Agent 模板、F05 工具连接／沙箱**，已完成实作与本机集成验收；本页同步区分第一版能力与仍待开发的范围。

本页的功能缺口和 F11 SCIM 候选是 2026-10-08 的历史快照。2026-10-15 已加入 SCIM 实作；当前客户租户验收状态见[项目计划](project-plan.md#p0-p1-acceptance-ledger)。

本轮功能说明与证据见 [运行功能](execution-usage.md)／[验收](execution-validation.md)。接续优先候选是 **运行前审批、总 token／金额治理、通知与真实 CI 集成**；企业文档导入、既有版控、SCIM 等需求仍保留。

排序先假设「一家企业私有部署，团队共同使用」。如果改为同一套服务承载多家客户，租户隔离与每个租户的 Identity／IdP 设置必须提前。

<span id="現有能力與判讀方式"></span>
<span id="现有能力与判读方式"></span>

## 现有能力与判读方式 {#existing-capabilities-and-status-definitions}

「部分」表示相关基础已存在，候选是补足缺少的范围。「未实作」指候选能力未见对应的完整 service／API／UI。「尚未验证」表示已有设置或运维说明，但没有该项端到端交付证据。

已存在的功能包括：共用 Identity、原生账号与 OIDC、Keycloak SAML broker、邀请／JIT、项目／Space 授权、登录时群组同步、工作阶段撤销；Work 的任务／运行分离、依赖、原子 claim、lease fencing、委派、求助、消息、幂等、outbox 与独立成果验收；Knowledge 的不可变版本、文字搜索与精确引用；Code 的真实 Gitea repo／branch／commit／PR／status 操作。这些不是本轮要重做的功能。

<span id="優先候選"></span>
<span id="优先候选"></span>

## 优先候选 {#priority-candidates}

P0 是下一轮内核操作能力；P1 是企业日常使用与导入功能；P2 是依使用量、集成对象或采购要求扩展。排序是 PM 判断，尚未提供工期估算。

| ID | 优先 | 候选 | 目前已有 | 缺少的能力与常见用途 |
|---|---|---|---|---|
| F01 | P0 | 运行前审批与工具政策 | 任务成果 review、角色／资源授权 | 运行敏感操作前产生持久审批请求；核准／拒绝／逾时后按政策恢复。部署、合并 PR、对外发送、数据变更可以各有规则。持久暂停与批准后恢复可参考 [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)。 |
| F02 | P0 | 运行与成本上限 | 单次 output token ceiling、实际 token receipt；添加每 Run turn／总时间上限及沙箱资源限制 | 总 token／并发配额、请求前预留金额、版本化定价与原子结算仍待开发。USD／cache 费率与帐单对帐需另外配置。按 key／team 设 budget 与 rate limit 可参考 [LiteLLM virtual keys](https://docs.litellm.ai/docs/proxy/virtual_keys)。 |
| F03 | 本轮 | Run 运行控制台 | 项目 Run 列表／详细页、持久事件／错误／模型用量、queued stop、工具边界 pause／resume、具来源链接的 retry、重启／提交幂等与独立 review | 后续可加入任意人工输入续谈、死信处理与跨 Run 统计。正在进行的外部调用可先结束；Run done 仍不等于 task 独立验收完成。 |
| F04 | 本轮 | 自动协作与可重用工作流程 | 不可变 DAG 版本、手动／分钟间隔触发、能力选 Agent、自动派工、review 依赖与取消；Agent 模板可套用创建／编辑 | 条件分支、webhook／Cron 触发、跨系统事件与自由协作唤醒仍待开发。现有流程不自动假造 CI 或独立 review 结果。 |
| F05 | 本轮 | Agent 工具连接与隔离工作区 | 项目 MCP Streamable HTTP／Bearer、tools/list 与 allowlist、加密密钥；每 Run 无网络 Docker workspace、文件／命令工具、资源限制与清理 | 交互式 OAuth、host stdio launcher、授权 repo checkout、可控网络／套件安装及 VM 运行器仍待开发。固定 job image 内含 Python／Node／Git。 |
| F06 | P1 | 通知、mentions、到期与 SLA | 指定 recipient 的协作消息与收件匣 | 待审、阻塞、失败、逾期通知；通知中心／实时更新、Email／Teams／Slack、订阅与去重。创建 due date／SLA 才能做逾期与升级处理；Teams 可透过 [Workflows webhook／Adaptive Card](https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-incoming-webhook?tabs=dotnet) 接入。 |
| F07 | P1 | 文档与任务附件导入 | Markdown body、版本；成果的 URI／文字 reference | 上传 PDF／Word／文件、抽取文字与必要的 OCR，保存来源／hash／版本及导入状态；对附件保存、大小、访问与删除生命周期做管理。现有 `kind=file` 不包含二进位上传服务。 |
| F08 | P1；先导入再强化检索 | 权限感知的语意搜索／RAG／跨产品搜索 | Knowledge 文字搜索、Space 权限、snippet／版本引用；后端可搜索多个授权 Space | 语意／混合检索、自然语言问答与引用；统一查找任务、文档与 PR。检索、cache 与回复都须维持当前授权与精确版本。来源 ACL 与 query-time filtering 的设计可参考 [Microsoft 文档权限搜索](https://learn.microsoft.com/en-us/azure/search/search-document-level-access-overview)。 |
| F09 | P1 | 企业既有版控与 Jira 集成 | Work 可唯读查找 GitHub／GitLab／Gitea PR／checks；Code 可写入 Gitea | GitHub／GitLab 的授权连接、repo binding、branch／commit／PR 写入、webhook 与 Jira issue 同步；Bitbucket／Azure DevOps 按第一批客户选用。Work 保持能直接集成既有 forge，不把 Code 变成必要依赖。 |
| F10 | P1；正式程序交付前需要 | 真实 CI／测试证据集成 | Code 可回报 status、验证／去重 Gitea webhook；Work 可读 provider checks | 触发／查看／重试／取消 pipeline，取得测试报告、log／artifact，将结果绑定 commit SHA／execution 并供独立 reviewer 验收。可以先接企业现有 runner；[GitLab pipelines API](https://docs.gitlab.com/api/pipelines/) 已提供 pipeline 与 test report 接口。 |
| F11 | P1；人员目录强制同步时提前 | SCIM 与自动入离职／调职同步 | 邀请／JIT、登录时群组同步、管理员禁用、backchannel logout | SCIM 2.0 Users／Groups、群组与权限变更、active=false 后撤销平台 session；事件幂等、重试与对帐。这是目录生命周期通道；[Entra provisioning](https://learn.microsoft.com/en-us/entra/identity/app-provisioning/how-provisioning-works) 说明创建／维护／禁用同步。 |
| F12 | P1 | 一般 Agent 权杖生命周期 | Work token hash、Agent 禁用；runtime delivery token 有期限且完成后撤销 | 一般 Agent token 的 expires_at、单把撤销、轮替／过渡期、最后使用、最小 scope 与管理界面。避免长期自动化只靠重新创建 Agent 来更换凭证。 |
| F13 | 部分纳入本轮 | Agent 配置版本、角色指令与多协定模型 | 不可变 Agent 模板；角色／能力／指令／模型／工具／沙箱／限制、派工快照与个别覆写 | 原生 Anthropic／Gemini 等 adapter、独立 skill registry 与配置品质评估仍待开发。现有多个 base_url／model metadata 都走 `openai-responses`，不代表已验收其他供应商的原生协定。 |
| F14 | P1／P2，依文档协作频率 | 文档留言、送审与发布核准 | Knowledge 不可变版本、Decision 与来源 reference | 行内留言、指定 reviewer、草稿／送审／核准／退回与批准后发布；保存版本及审查证据，供多人维护正式规格、SOP 或制度文档。 |
| F15 | P2；持续跑 Agent 时提前 | Agent 品质评估与可观测性 | 运行／审核纪录、Pi 持久化、模型用量 receipt | 脱敏工具／模型 trace、延迟／成功率／成本指针；数据集与固定评分规则，比较 prompt／model／Agent 版本，将真实失败转成回归案例。可参考 [LangSmith datasets／evaluation](https://docs.langchain.com/langsmith/evaluation) 与 [OpenTelemetry traces](https://opentelemetry.io/docs/concepts/signals/traces/)。 |
| F16 | P2；需要云端 Agent 接入时提前 MCP | 远程 MCP gateway 与 A2A | 各产品本机 stdio MCP、受限 bearer REST bridge | Streamable HTTP MCP、远程 token/scope 管理与工具目录；之后以 A2A Agent Card／Task lifecycle 接入独立 Agent。设计参照 [MCP authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) 与 [A2A specification](https://a2a-protocol.org/latest/specification/)。 |
| F17 | P2；多客户 SaaS 时为 P0 | 团队管理与完整多租户 | 组织／团队字段、项目授权；Identity 环境绑定单一组织／IdP | 部门与团队管理、团队授权；多组织 membership、租户切换、各自的 IdP／模型／配额／audit、跨租户隔离验收。企业各自独立部署时可较晚做多租户。 |

<span id="本輪第一版與後續候選"></span>
<span id="本轮第一版与后续候选"></span>

## 本轮第一版与后续候选 {#this-release-and-later-candidates}

<span id="f03-執行控制台"></span>
<span id="f03-运行控制台"></span>

### F03：运行控制台 {#f03-run-console}

本轮提供运行列表、详细页、模型／token／工具事件与错误、停止，以及有明确资格条件的暂停／恢复／重跑。所有操作由 Python 验证当前用户与项目权限；浏览器不持有 runtime 服务 token。精确契约见 [execution-contracts.md](execution-contracts.md)。

本轮验收涵盖 pending 停止、实际暂停／恢复、过期 lease／项目拒绝、重启与回应遗失重试。新的一次重做有新 execution 与来源链接；同一次 resume 保留幂等界线。完整死信与操作人员处理界面仍为后续项。

<span id="f01-可持久化的執行前審批"></span>
<span id="f01-可持久化的运行前审批"></span>

### F01：可持久化的运行前审批 {#f01-durable-pre-execution-approvals}

第一版定义 ApprovalRequest、批准者、原因、工具／资源／参数摘要及 hash、有效期限。核准只授权对应动作，内容改变后需重新判定。政策位于 Python，共用 REST／MCP；Pi 只负责运行暂停／恢复。

验收要涵盖：未批准时无副作用、越权／自批拒绝、逾时／取消、核准后参数遭修改、重放与重启、批准后相同副作用只运行一次。现有成果 review 保持自己的业务规则。持久 interrupt 的相关行为可参考 [LangGraph 官方文档](https://docs.langchain.com/oss/python/langgraph/interrupts)。

<span id="f02-先有可執行的上限-再有金額治理"></span>
<span id="f02-先有可运行的上限-再有金额治理"></span>

### F02：先有可运行的上限，再有金额治理 {#f02-enforce-limits-before-cost-governance}

第一版可先落实总 token／turn／工具调用／运行时间与并发配额，并显示达限原因。要宣称 USD hard budget，还需要已知且版本化的定价、请求前预留、完成后结算／释放，以及多个 execution 同时抢用剩余预算的原子控制。

验收要涵盖：预算不足时不发新模型请求、并发不能共同超用可预留额度、未知 usage／价格的显式政策、失败与取消后结算、cache 费率、重复 receipt 的去重。已发送请求的费用可能仍会由上游结算；不能承诺事后 abort 会退费。供应商的发票／实际帐单对帐属另一个交付项目。

<span id="企業採購或正式維運時的附加項"></span>
<span id="企业采购或正式运维时的附加项"></span>

## 企业采购或正式运维时的附加项 {#additional-enterprise-procurement-and-operations-candidates}

| 候选 | 现况 | 建议启动条件与最小交付 |
|---|---|---|
| 本机管理员 MFA／Passkey | 企业 MFA 可交给 IdP；本机账号没有 TOTP／WebAuthn | 若管理员复原账号也必须第二因素，提供 enrollment／验证／复原政策及安全审计。 |
| 审计整合、SIEM 与防篡改 | Identity 已有受限 JSONL 导出、复合游标分页及明确应用的保留期；尚无 SIEM 推送、签名／hash chain 或 WORM 防篡改存储 | 当组织需要集中关联 Identity 与产品事件时，先提供有界、可重试的 SIEM／事件导出整合；如需防篡改，再加入签名／hash chain／WORM 存储与验证。 |
| Vault／KMS／Secret Manager | 客户端密钥／模型密钥已在本地加密；Compose 机密通过挂载文件提供 | 当密钥管理要集中或跨节点时，增加外部机密后端、凭证轮替与复原流程。 |
| 自动备份、还原演练、监控与 HA | 有 health、具名 volumes、重启持久化及手动备份说明；完整 restore／HA 未验收 | 正式运行前制定 RPO／RTO，验证数据库、key、Pi 与 Git／附件一致还原；加入告警／metrics，需求升高后再处理 worker partition／HA。Pi storage 维持单一拥有者。 |

<span id="分期與依賴"></span>
<span id="分期与依赖"></span>

## 分期与依赖 {#phases-and-dependencies}

1. **本轮运行基础**：F03／F04／F05 与 F13 配置模板，共用既有 Identity、Work 服务、outbox 与 Pi。完成证据集中于 `execution-validation.md`。
2. **第一批企业流程深化**：F01 审批、F02 金额／配额、基本通知、自有代码托管平台与 CI（F09／F10），或知识导入与检索（F07／F08）。先支持一个确定的 Git／文档来源并端到端验收，再扩充供应商。
3. **持续企业导入**：F11／F12、人员与 token 生命周期、品质评估、SIEM／备份运维，再依需求加入团队／多租户、远程 MCP／A2A、MFA／Vault。

文件导入与来源权限要先于大量 RAG 索引；审批、scope 与运行隔离要纳入 shell／部署／merge 类工具；CI 结果需绑定实际 commit／execution。跨产品搜索与工具连接透过 API／事件集成，每个产品维持自己的业务授权及数据库。这些是具体实作的设计前提，尚未改写现有契约。

<span id="程式碼證據"></span>
<span id="代码证据"></span>

## 代码证据 {#code-evidence}

| 盘点 | 来源 |
|---|---|
| 成果 review 与取消／人工操作 | [Work 服务](../../backend/src/ordivant/service.py):542、828、865；[Work UI](../../frontend/src/App.tsx):1144、1336；[runtime 服务器](../../runtime/src/server.ts):95 |
| 指令模板与自动派发 | [Agent 结构定义](../../backend/src/ordivant/schemas.py):145；[Work 服务](../../backend/src/ordivant/service.py):1111、1159；[派送器](../../runtime/src/dispatcher.ts):25、169 |
| 既有有限重试与工具注册 | [Work 服务](../../backend/src/ordivant/service.py):1226；[派送器](../../runtime/src/dispatcher.ts):285；[执行引擎](../../runtime/src/engine.ts):455；[平台工具](../../runtime/src/platform-tools.ts):160；[runtime `Dockerfile`](../../runtime/Dockerfile):28 |
| 金额预算与固定模型协定 | [Work 服务](../../backend/src/ordivant/service.py):1346；[执行引擎](../../runtime/src/engine.ts):423；[已配置的 Provider](../../runtime/src/configured-provider.ts):42 |
| 尚未有 runtime 人工等待状态；receipt 金额未知 | [runtime 类型](../../runtime/src/types.ts) 的 `RunStatus`／`RunReceipt`；[模型契约](model-contracts.md) |
| 预算与自陈成本 UI | [`App.tsx`](../../frontend/src/App.tsx):1149、1214；[前端类型](../../frontend/src/types.ts):106 |
| 通知／mentions／due date 与附件 | [`App.tsx`](../../frontend/src/App.tsx):427、951、1216；[Work 结构定义](../../backend/src/ordivant/schemas.py):91、185；[契约](contracts.md):20 |
| Knowledge 导入／搜索／直接发布 | [Knowledge 结构定义](../../products/knowledge/backend/src/ordivant_knowledge/schemas.py):25；[Knowledge API](../../products/knowledge/backend/src/ordivant_knowledge/api.py):227、382；[Knowledge UI](../../frontend/src/products/knowledge/KnowledgeApp.tsx):144、469、528 |
| Code Gitea；Work 多 forge 唯读 | [Code 主程序](../../products/code/backend/src/ordivant_code/main.py):177；[Work 版控](../../backend/src/ordivant/vcs.py):15、50；[Work API](../../backend/src/ordivant/api.py):405 |
| CI status／webhook 的目前范围 | [Code 服务](../../products/code/backend/src/ordivant_code/service.py):714；[Code UI](../../frontend/src/products/code/CodeApp.tsx):523、538；[Suite 契约](suite-contracts.md):63 |
| 单组织 Identity／IdP | [SSO 契约](sso-contracts.md):15；[Auth 契约](auth-contracts.md):50；[组织模型](../../backend/src/ordivant/models.py):11 |
| SCIM／MFA／现有禁用与撤销 | [SSO 契约](sso-contracts.md):64；[企业登录](enterprise-sso.md):78、80；[项目计划](project-plan.md) 的后续企业验收门槛 |
| Agent token 生命周期 | [Token 模型](../../backend/src/ordivant/models.py):37；[安全性](../../backend/src/ordivant/security.py):31；[契约](contracts.md):18、58 |
| Audit 范围与密钥管理 | [SSO 契约](sso-contracts.md):15、73；[SSO API](../../products/identity/backend/src/ordivant_identity/sso.py):1266；[Identity 模型](../../products/identity/backend/src/ordivant_identity/models.py):143；[Compose 机密](../../compose.yaml):209 |
| 已验收与尚未验收的正式运维 | [SSO 验收](sso-validation.md):48；[验收清单](validation.md)；[项目计划](project-plan.md) 的后续企业验收门槛 |

上表行号与旧范围是 2026-10-07 的盘点位置，实作后可能位移；F03／F04／F05／F13 的目前证据以 execution-contracts.md 与 execution-validation.md 为准。官方数据只用来评估候选功能，不能作为 Ordivant 已具备该功能的证据。
