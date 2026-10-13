# Ordivant Work

Work 用来整理项目、任务、Agent 运行、消息、成果证据与独立审核。Task 是业务工作；Run/Execution 是一次实际运行。运行完成不会自动把 Task 标成完成，必须由有权限且非提交者的审核者接受成果。

![Work 任务清单：以任务状态追踪示范项目](/screenshots/work-zh-CN.png)

<span id="建立專案與任務"></span>
<span id="创建项目与任务"></span>

## 创建项目与任务 {#create-projects-and-tasks}

1. 由 Identity 管理员在 Work 创建 Project，并把成员授权到这个 Project。成员只会看到自己获授权的范围。
2. 在 Project 的「任务」创建 Task，填写目标、描述、输入数据、运行范围、限制、验收条件和优先级。
3. 在「负责者」中选择管理员已授权此 Project 的真人同事或 Agent，也可以先留空，让符合条件的成员认领；在「指定审核者」中选择另一位获授权的真人或 Agent。需要先完成的 Task 可加为 dependency。系统拒绝循环依赖；前置任务要完成独立审核后，后续任务才可开始。
4. 保存后在任务清单搜索或依状态查看工作。修改任务规格不会取代已保存的运行与审核历程。

可指派的真人必须已受邀、处于启用状态，并具有 Work 角色和此 Project scope。即使受邀成员尚未登录 Work，管理员也可以先指派任务。角色和范围由 Identity 管理员设置，详见[团队设置](team-setup.md)。

<span id="執行並提交證據"></span>
<span id="运行并提交证据"></span>

## 运行并提交证据 {#execute-and-submit-evidence}

真人工作不需要 LLM 或 Agent。具有此 Project scope 的 Worker、Manager 或 Admin 可以认领未指派给其他人的「待运行」任务；如果任务已指派给自己，也可以认领。直接选择「认领任务」，不必选择 Agent。不能代替另一位同事认领。真人执行没有 Agent 租约，任务执行记录可在重新加载页面后恢复。

工作期间可用「回报执行进度」记录进展和证据；需要等待外部资料时选择「标记任务受阻」。受阻或成果被退回时，原负责人仍保留。要交给其他人时，选择「交接并发布」并填写交接内容：当前执行会结束，交接记录会保留，真人负责人会清空，任务返回「待运行」，其他符合条件的同事即可认领。Manager/Admin 也可以在执行开始前重新指派负责人。

完成后提交摘要和一项或多项成果，例如文字、Artifact URI 或文件／测试结果引用。提交会把 Task 移入待审核，并保留执行、证据和交接历史。说明成果如何符合验收条件；提交不代表任务已被接受。由另一位有权限且不是提交者的人审核，并选择接受或退回。提交者不能审核自己的成果。

派发 Agent 是另一条路径：管理员须先启用 Agent 执行服务，只有自主 Pi Run 需要模型连接。Agent 执行仍使用自己的租约和 fencing token，与真人工作分开。派发操作详见[Run 与自动化](../execution-usage.md)。

<span id="協作與引用"></span>
<span id="协作与引用"></span>

## 协作与引用 {#collaboration-and-citations}

在 Task 脉络使用消息向其他成员或 Agent 提问、回复、交接工作或记录决议。Project 的 Manager／Admin，或父任务的真人、Agent 负责人，可以选择「委派子任务」把工作交给具备此 Project 执行权限的同事或 Agent；委派不会自动授予受托人其他 Project 的访问权。

若工作依赖 Knowledge 文档，将该文档的**特定版本引用 URI** 放入 Task 输入或提交证据，并保留版本号。引用只是来源纪录，不会替读者授权 Knowledge Space；需要阅读原文的成员必须另外获授权。Knowledge 引用格式与操作见[Knowledge 指南](knowledge.md)。

Work 也能读取已设置的既有 GitHub、GitLab 或 Gitea PR/check 状态。这是项目范围内的读取与证据查看；它不会合并 PR，也不会代替独立审核。Code 中由 Gitea 管理的 repository 与 PR 操作见[Code 指南](code.md)。

<span id="run-控制"></span>

## Run 控制 {#run-controls}

在「Run 执行」查看每次执行的状态、事件与用量。管理员或项目管理者可暂停、继续、停止或重试。暂停会在下一个工具操作前生效，并保留任务；停止后，本次执行不能再更新任务。重试会创建新的 Run。已完成的外部操作不会因停止而撤销，重试前请先核对结果。

控制台的 Run 状态、等待与停止语意、沙箱和工具设置详见[运行使用指南](../execution-usage.md)。工具外部副作用不会因重试而自动重播；不确定的操作结果应先到上游服务核对。

<span id="權限概覽"></span>
<span id="权限概览"></span>

## 权限概览 {#permissions-overview}

- **Manager**：管理已授权 Project 的任务与运行安排。
- **Worker**：认领未指派或指派给自己的工作、提交成果，并可交接释放任务。
- **Reviewer**：审查提交的成果；不能批准自己的提交。Manager 和 Admin 也可在获授权范围内审查。

组织管理员负责创建 Project、邀请成员及分配产品角色。Work 访问以 Project scope 与 manager、worker、reviewer 身分为准；没有独立的 Work Reader role。人类登录工作阶段不会变成 Agent/runtime 凭证。
