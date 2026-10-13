# Ordivant 功能指南 {#product-features}

本指南结合日常场景，说明各项功能的入口、操作结果和现有限制。Work、Knowledge 和 Code 都支持真人与 Agent 在同一产品流程中协作；常规人工操作不需要 LLM。Work 管理任务、真人执行和 Agent Run；Knowledge 管理共同草稿、文档版本与决策；Code 管理连接到 Gitea 的仓库与 PR，并保存 Ordivant 讨论和审核记录。先查看[项目介绍](./overview.md)，再按以下场景操作。

## 真人与 Agent 协作 {#human-and-agent-collaboration}

### 场景 {#human-and-agent-collaboration-scenario}

团队希望先由同事处理任务、共同编写规范和审查 PR，再为适合自动化的工作加入 Agent。这些人工流程可以在配置模型之前使用。

### 操作入口 {#human-and-agent-collaboration-steps}

1. 在 Work 创建任务时，将其指派给已授权的真人同事或 Agent，也可留空让同事认领。真人 Worker、Manager 或 Admin 可认领未指派或指派给自己的待运行任务、回报进度、提交证据或交接。提交者不能审核自己的成果。参见[Work 指南](./guide/work.md)。
2. 在 Knowledge 打开最新版本的共同草稿。Writer 和 Manager 可以共同编辑；Reader 可以查看。只有服务器确认保存后才能发布为不可变版本。Agent 可通过 REST/MCP 编辑同一草稿。参见[Knowledge 指南](./guide/knowledge.md)。
3. 在 Code 的 PR 详情中讨论变更并提交 Ordivant 审核记录。每条审核都绑定当时的 PR head SHA；Git、合并和 Gitea 自身的核准仍由 Gitea 管理。参见[Code 指南](./guide/code.md)。

### 结果与限制 {#human-and-agent-collaboration-result}

人员使用自己的 Identity 账号，不需要创建 Agent 来代表真人，也不需要模型密钥。只有自主 Pi Agent Run 需要启用 Runtime 并配置 Provider/model。Code 的 repository、branch、commit 和 PR 写入需要 Gitea。Knowledge 断线时，尚未确认保存的修改只保存在当前浏览器标签页内存中，关闭或重新加载后可能丢失；发布冲突需要重新加载并检查最新草稿。Ordivant Code 审核不代表 Gitea approval、CI 结果或 Work 任务验收。

## 任务规格与依赖关系 {#work-task-design}

### 场景 {#work-task-design-scenario}

你要准备一份上线检查报告，其中必须先完成服务清单，后续检查才能开始。

### 操作入口 {#work-task-design-steps}

1. 在 Work 中选择有权限访问的 Project，打开“任务”，点击“添加任务”。
2. 填写任务名称、目标、输入资料、范围、限制条件和验收条件，每行填写一项验收条件。设置优先级，选择获授权的同事或 Agent 作为负责人，并设置独立审查者；也可以先不指派，让同事认领。
3. 在“相依任务”中选择必须先完成的任务并创建任务。打开任务后，可在“规格”页签查看字段和依赖状态；需要修改时点击“编辑规格”。

![Work 项目任务清单](/screenshots/work-zh-CN.png)

![任务详情与规格](/screenshots/task-zh-CN.png)

### 结果与限制 {#work-task-design-result}

依赖任务会显示在任务规格中，系统会拒绝循环依赖。前置任务经审查接受并完成后，后续任务才能开始。任务、Run／Execution、提交的证据和审查结果分别保留；修改规格不会删除已有历史。

## 请求协作与委派工作 {#work-help-and-delegation}

### 场景 {#work-help-scenario}

执行者需要另一位同事或 Agent 确认资料来源，或者要把“整理测试案例”拆分成可以单独审查的子任务。

### 操作入口 {#work-help-steps}

1. 在任务清单中打开 Task 详情，点击“请求协作”，选择获授权的同事或 Agent 作为接收者，写明问题或需要的信息后发送。讨论会保留在该 Task 的“协作”页签；接收者也可以在 Work 的“协作收件箱”查看。
2. 在任务讨论中回复。接收者或有权限的管理员可以将消息标记为已接收或已完成。问题、回复、决议和交接都会保留在项目及任务上下文中。
3. 如果工作可以独立交付，在 Task 详情中点击“委派子任务”，选择获授权的同事或 Agent 作为负责人，填写子任务名称、目标、范围、输入、限制和验收条件，然后委派。

### 结果与限制 {#work-help-result}

委派会创建一项关联到父任务的独立 Task，并保留自己的 Execution／Run、证据和审查历史。具备项目范围的 Manager／Admin，或当前实际负责父任务执行记录的真人或 Agent，可以委派子任务。子任务不会扩大任何人的项目权限；嵌套委派最多三层。协作消息是关联任务的工作记录，不是即时聊天服务。

## Run 与人工介入 {#runs-and-intervention}

### 场景 {#runs-intervention-scenario}

任务规格已经准备好，你想让 Pi 执行 Agent 实际执行任务，并在需要时由人员检查或控制 Run。

### 操作入口 {#runs-intervention-steps}

1. 打开 Task 详情。真人负责人直接选择“认领任务”；真人工作没有 Agent 租约，重新加载后可从执行历史继续。需要自主执行时才选择 Pi Agent 并派发，这会创建自动 Run。
2. 打开 Work 侧栏中的“Run 运行”，选择一个 Run，查看状态、回复、事件、工具结果、沙箱输出以及供应商回报的模型和用量。
3. 具备相应权限时，在 Run 详情请求“暂停”“恢复”或“停止”。失败或停止的 Run 可以通过“重跑”创建新的 Run，之前的 Run 仍保留在历史中。
4. 提交后回到 Task 详情的“运行与审核”，由另一位有权限的审查者检查摘要和证据，然后接受或退回。

![Run 执行控制台](/screenshots/run-zh-CN.png)

### 结果与限制 {#runs-intervention-result}

Run 显示已提交表示模型回合已经提交，并不代表任务已完成；还需经过独立审查并被接受。真人执行是与 Agent Run 分开的工作记录，不需要模型。暂停会等当前模型或工具操作结束后才生效。停止不会撤销外部服务已经完成的操作；结果不确定时，请先到上游服务核实再重跑。DEMO 不调用付费模型。无法确认的用量或美元金额会显示为未知。

## Agent 模板与工作流 {#agent-templates-and-workflows}

### Agent 模板：复用执行设置 {#agent-template-reuse}

在 Work 侧栏中打开“自动化”→“Agent 范本”。模板可以设置 Agent 角色、能力标签、指令、模型选项、可用工具连接、沙箱配置、最多模型回合数和运行超时。创建或编辑 Agent 时，在“Agent 范本版本”中选择要应用的精确版本，再按需调整 Agent 设置。修改模板需发布新版本；已有 Agent 和 Run 会保留原先使用的版本与设置。

模板便于复用同一套工作方式，但不会授予项目、模型 Provider 或工具的访问权限。Agent 仍须获准访问 Project；组织管理员设置 Provider，项目管理员设置工具连接。

### 工作流：安排多步骤交付 {#workflow-sequencing}

1. 打开“自动化”→“工作流程”，点击“添加流程”。添加步骤并填写名称、目标、优先级和验收条件，为每一步选择负责 Agent 或所需能力，以及审查者。
2. 在“相依步骤”中选择前置工作。互不依赖的步骤可以同时运行；系统会拒绝无效或循环依赖。
3. 点击“手动启动”，输入本次流程的“流程输入”并启动。每个步骤都会创建对应的 Task；没有合适 Agent 或前置结果尚未通过审查时，该步骤会等待。
4. 如需定期重复，在流程的“调度”中设置启用状态、启动间隔和最多启动次数。在“运行纪录”中查看各个流程实例。

每个流程实例固定使用启动时的流程版本。每一步仍需单独通过审查，后续步骤才会继续。前一个流程仍在运行时，排程不会重复启动；服务停机期间错过的时段不会补跑。取消流程会停止尚未完成的步骤，已接受的成果会保留。手动认领任务不等于派发 Run。

![工作流程编辑器与调度设置](/screenshots/workflow-zh-CN.png)

## 模型继承与 Agent 覆盖设置 {#model-inheritance-and-overrides}

### 场景 {#model-settings-scenario}

组织为大多数 Agent 设置一个默认模型，只为代码审查 Agent 指定另一个已核准的模型。

### 操作入口 {#model-settings-steps}

1. Work 组织管理员从侧栏打开“模型连接”，添加 Provider、HTTPS API 地址和 API key，登记该 Provider 支持的模型及选项，然后选择组织默认模型。
2. 在“Agent 名录”中新建或编辑 Agent。选择“沿用组织默认”，或者指定已配置的 Provider、模型、推理强度和输出上限。
3. 在 Agent 名录中确认实际生效的模型。已派发的工作会保留启动时的模型快照；修改从后续派发开始生效。

### 结果与限制 {#model-settings-result}

Provider key 会加密保存，重新打开设置时不会再次显示明文。外部 Runtime Agent 的模型名称仅用于标识，Work 不会替它调用模型。如果没有配置模型，Pi Run 会使用明确标注的 DEMO 模式。即时 Provider 调用失败会显示失败，不会伪装成 DEMO 成功。Token 用量和供应商回报的模型不是账单；模型输出上限也不是美元费用硬上限。费率和实际费用请在 Provider 账户中核实。设置步骤见[模型连接指南](./model-usage.md)。

## Knowledge 文档版本与搜索 {#knowledge-versioning-and-search}

### 场景 {#knowledge-versioning-scenario}

团队正在修改上线规格，但仍需要让旧任务指向当时采用的版本。

### 操作入口 {#knowledge-versioning-steps}

1. 打开 Knowledge，选择有权限访问的 Space，再进入“文档库”。点击“添加文档”，填写标题、摘要、正文、标签和可追溯来源。
2. 要修改文档时，打开最新版本的共同草稿并选择编辑。Writer／Manager 与 Agent 可以同时更新正文，修改会自动合并；切换预览检查 Markdown。
3. 等待草稿显示已连接和已保存，再点击“发布新版本”，填写变更摘要并确认。发布会创建不可变版本；Reader 只能查看。如果出现版本冲突，重新加载草稿并检查合并结果，等到已保存后再发布。
4. 在文档阅读器中切换版本，查看版本 URI、创建时间、SHA-256 和变更摘要。通过搜索框查找标题或正文，也可以按标签筛选。

![Knowledge 文档与版本历史](/screenshots/knowledge-zh-CN.png)

### 结果与限制 {#knowledge-versioning-result}

每次发布都会创建不可变版本，旧版本与引用都会保留。未确认的离线修改只保存在当前浏览器标签页内存中，不应假设关闭页面后仍会保留。搜索比对已保存的标题、正文和标签，是文字搜索；产品不提供向量搜索或 RAG。

## Knowledge 决策与精确引用 {#knowledge-decisions-and-citations}

在 Knowledge 中选择 Space，进入“决策纪录”并点击“添加决策”。填写标题和决策内容，可选关联文档及来源引用。这里适合记录为何采用某方案及其依据；日后决策改变时新建记录，以保留原有上下文。

引用规格时，从文档的指定版本复制完整 URI，并添加到 Work Task 的输入或证据中，或添加到 Code PR 的来源中。之后文档更新时，该 URI 仍指向原版本。引用记录来源，但不会授予读取 Knowledge Space 的权限；读者仍须单独获授权。

版本 URI 格式如下：

~~~text
ordivant://knowledge/spaces/{space_id}/documents/{document_id}/versions/{version}
~~~

## Code 分支与 Pull Request {#code-pull-requests}

### 场景 {#code-pull-requests-scenario}

工程团队要在 Gitea 中准备一项配置变更，将 Work 任务和 Knowledge 来源附到 PR，并按团队现有流程进行审查。

### 操作入口 {#code-pull-requests-steps}

1. 打开 Code，选择有权限访问的 Code Project 和 repository。有写入权限的成员可以创建私有 repository。
2. 在 repository 详情中创建 branch。点击“提交文件”，添加或更新 UTF-8 文件并填写 commit message。
3. 点击“创建 PR”，选择来源 branch 和目标 branch，填写标题与描述，再添加 Work、Knowledge 或外部来源引用。
4. 在 PR 详情检查 head SHA、来源、状态和 check 收据。在 Ordivant 讨论与审核面板中留言、要求修改或记录核准。点击“在 Gitea 打开”，按组织流程完成正式审查和合并。

![Code repository 与 Pull Request](/screenshots/code-zh-CN.png)

### 结果与限制 {#code-pull-requests-result}

Code 的 repository、branch、commit 和 PR 由部署端配置的 Gitea 保存；尚未配置 Gitea 时无法执行写入操作。真人和 Agent 都可在 Ordivant 中讨论和审核；每条审核绑定 PR head SHA，head 更新后旧审核会过期。Ordivant 记录不会成为 Gitea approval，也不代表 CI 或 Work Task 验收。使用“回报状态”记录的状态会标记为 Agent 回报，并不证明 CI 真正执行过测试。已验证签名的 Gitea webhook 会显示不同的来源标签；仍需打开上游 check 记录确认实际运行内容。如果只需查看现有 GitHub、GitLab 或 Gitea PR 状态，可使用已配置的 Work 只读集成，无须部署 Code。

## 权限、成员与企业 SSO {#permissions-and-sso}

### 场景 {#permissions-and-sso-scenario}

管理员希望成员使用企业身份登录，并限制每个人只访问获分配的项目、知识空间和代码项目。

### 操作入口 {#permissions-and-sso-steps}

1. 打开“账号与安全性”→“企业 SSO”。选择 OIDC Provider 模板，填写组织的 Issuer、Client ID、Client Secret、允许的域名，以及仅限受邀或首次登录自动创建（JIT）的账号政策。
2. 如需基于群组授权，在身份服务中设置 groups claim 和明确的群组→产品／资源范围映射。保存后点击“测试连接”，再以普通成员身份登录并检查实际权限。
3. 如需强制使用企业登录，先确认管理员恢复入口可用，再启用 SSO-only。管理员还可在“用户与邀请”中调整产品角色和资源范围、撤销 session，并在“身份审计”中查阅管理记录。

### 结果与限制 {#permissions-and-sso-result}

组织管理员授予产品角色和资源范围。各产品的角色分别生效：Work 使用 Manager、Worker、Reviewer；Knowledge 使用 Manager、Writer、Reader；Code 使用 Manager、Writer、Reader。SSO 只建立平台 session，不会自动授予 Project、Space、Agent、Runtime 或 Gitea 权限。管理员须另行向受邀成员提供邀请码；平台不会发送邮件。

平台使用 OIDC 连接身份服务；SAML 或 LDAP／Active Directory 可通过选配的 Keycloak broker 接入。产品未提供原生 SAML 端点或 SCIM 帐号同步。请依照[企业登录指南](./enterprise-sso.md)检查实际身份服务租户和策略。

## 外部工具与隔离沙箱 {#tools-and-sandbox}

### 场景 {#tools-and-sandbox-scenario}

你要让某个 Agent 查询内部 MCP 服务，并在独立工作区运行分析命令，同时避免工作区读取主机文件。

### 配置外部 MCP 工具 {#external-mcp-tool-setup}

1. 部署管理员先允许 MCP 主机。Work 项目管理员打开“工具与沙箱”，使用 HTTPS URL 和 Bearer token 点击“添加连接”，选择可用工具并点击“测试 tools/list”。
2. 在 Agent 模板或“Agent 名录”的执行设置中，只选择该 Agent 需要的项目连接，然后派发 Run。
3. 在 Run 详情的事件中查看实际观察到的工具调用和结果。

Token 会加密保存，之后不会再次显示。当前连接使用 Bearer token，尚不支持交互式 MCP OAuth。默认会阻止任意外部主机；私有 HTTP 或内网目标需要部署管理员明确配置。外部工具可能修改上游数据；结果不确定时不会自动重试，停止 Run 也不能撤销已经完成的操作。

### 配置沙箱 {#sandbox-setup}

在“工具与沙箱”为项目创建沙箱配置，设置命令时间、内存、CPU、进程数、输出量和工作区大小，再将配置应用到 Agent。派发 Run 后，命令会在该 Run 专属的临时工作区中执行。

沙箱不联网，也不能访问主机目录；不能在线下载依赖或任意 clone repository，只能使用环境中已有的命令和依赖。Run 结束、停止或超时后工作区会清理；需要保留的文件和测试输出须先提交为成果。Docker 沙箱与主机共用 kernel，不等同于 VM／microVM 级隔离。

![工具连接与沙箱设置](/screenshots/tools-zh-CN.png)

## 更多用户指南 {#next-steps}

- [创建第一个项目](./guide/first-project.md)和[设置团队](./guide/team-setup.md)
- [Work 任务、运行与审查](./guide/work.md)以及[Run、工作流、工具和沙箱操作](./execution-usage.md)
- [模型连接与 Agent 设置](./model-usage.md)
- [Knowledge 文档与引用](./guide/knowledge.md)和[Code PR](./guide/code.md)
- [管理员与成员设置](./guide/administration.md)和[企业 SSO 配置](./enterprise-sso.md)
