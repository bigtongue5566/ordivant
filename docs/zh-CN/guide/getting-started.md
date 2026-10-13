<span id="開始使用-ordivant"></span>
<span id="开始使用-ordivant"></span>

# 开始使用 Ordivant {#getting-started-with-ordivant}

这是快速认识平台的入门页。第一次建立自己的工作区，请跟着[第一个项目完整教程](first-project.md)创建项目与任务，再由真人认领、提交成果并完成独立审核；这条流程不需要先创建 Agent。管理员邀请成员时，请搭配[建立团队](team-setup.md)。

以“整理产品上线清单”为例，带你从登录、创建任务到审查成果。使用团队提供的 Ordivant 网址；若是自己部署，请先完成安装，再打开你的平台网址。

<span id="準備環境"></span>
<span id="准备环境"></span>
<span id="prepare-the-environment"></span>

## 登录与界面语言 {#sign-in-and-language}

若是全新安装，请依首次画面创建初始管理员并保存复原码；之后使用自己的账号登录。若加入现有团队，在登录页选择「接受邀请」，输入邀请码并设置自己的密码。如果组织使用单点登录，请选择登录页显示的组织身份服务。Ordivant 没有默认人员账号或密码；如果没有邀请或无法登录，请联系管理员。其他登录方式见[账号与登录](../human-login.md)。

登录后可使用「界面语言」选择「繁體中文」、「简体中文」或「English」。切换语言会更改平台界面文字，不会自动翻译成员创建的任务、文档或留言。

![登录页：受邀成员可登录或接受邀请](/screenshots/login-zh-CN.png)

## 选择工作区与项目 {#choose-workspace-and-project}

在产品导航中选择 **Work**，再从「选择项目」列表打开管理员授予你访问权限的项目。我们将用整理产品上线清单作为任务示例。若你是初始管理员，按「创建项目」，填入项目代码与名称；例如 LAUNCH、产品上线准备。一般成员若没有可选项目，请联系管理员授予访问权限。登录平台不会自动获得所有项目的访问权限。

<span id="複製並啟動"></span>
<span id="拷贝并启动"></span>
<span id="clone-and-start"></span>
<span id="create-task-and-review"></span>

## 创建第一个任务 {#create-first-task}

在任务页选择「新增任务」，将「整理产品上线清单」填入任务名称。目标可写为“整理产品正式上线前需要完成的准备事项”，再按需补充输入资料、工作范围和限制条件。

在「验收条件」中逐行写下可核对的标准，例如“列出所有上线前准备事项”、“每项标明负责人和当前状态”、“附上可追溯的来源或证据”。填写后选择「创建任务」保存。任务可以先保持未指派，让有项目权限的 worker 认领；manager 或 admin 也可以指派给同事或 Agent。字段说明见[Work 任务与审核指南](work.md)。

<span id="seed-與-runtime"></span>
<span id="seed-与-runtime"></span>
<span id="seed-and-runtime"></span>
<span id="create-project-and-agent"></span>

![任务详细资料：查看目标与验收条件，选择 Pi Agent 派发](/screenshots/task-zh-CN.png)

## 由真人或 Agent 执行 {#select-agent-and-run}

**真人执行：** 使用自己的账号打开任务，直接选择「认领任务」即可认领未指派或指派给自己的工作。你不必选择 Agent、创建 Run 或设置模型；重新载入页面后可以继续进行中的工作。真人执行没有 Agent 租约，也不能认领指派给其他同事的任务。Manager 或 admin 可以把任务指派给同事；只有明确代表 Agent 执行时，才选择已获准访问此项目的 Agent 代为认领。

**Agent 自动执行：** 由 manager 或 admin 在任务详情选择已获准访问此项目的 Pi Agent，再按「派发给 Agent」。这会创建 Run；打开侧栏的「Run 运行」即可查看进度、事件与成果。Agent 自动执行需要管理员启用 Runtime 并设置有效模型连接。

尚未设置模型时，仍可由真人认领、完成工作、提交成果并审核。Run 若标记为 **DEMO**，表示它不是付费模型调用。管理员可参阅[运行与自动化指南](../execution-usage.md)了解 Agent 执行设置。

<span id="檢查與停止"></span>
<span id="检查与停止"></span>
<span id="check-and-stop"></span>

![Run 控制台：查看 DEMO 运行的事件与提交结果](/screenshots/run-zh-CN.png)

## 提交成果并完成审核 {#submit-and-review}

以上线清单为例，执行者完成整理后提交摘要以及清单、来源链接等证据。任务会进入待审核状态；另一位 Reviewer 对照验收条件检查证据后，可以接受成果或退回修改。执行者不能接受自己的提交。Run 显示完成不代表任务已完成，只有经过独立审核并接受后，任务才会标记为完成。详细操作见[Work 任务与审核指南](work.md)。

<span id="self-host"></span>

## 功能简介 {#product-overview}

- **Work**：把任务指派给同事或 Agent，也可以由真人认领；提交证据后由另一位获授权的人独立审核。
- **Knowledge**：多人实时共同编辑草稿，再发布不可变版本；Agent 可通过 REST 或 MCP 参与同一份草稿。
- **Code**：在 Ordivant 留存绑定 PR head SHA 的讨论与审查；Git 操作及合并由 Gitea 负责。

<span id="接下來"></span>
<span id="接下来"></span>

## 后续步骤 {#next-steps}

- [Work：任务与审核](work.md)
- [Knowledge：文档、版本与引用](knowledge.md)
- [Code：仓库与 Pull Request](code.md)
- [管理员、角色与 SSO](administration.md)
- [账号与登录](../human-login.md)

- [第一个项目完整教程](first-project.md)
- [建立团队与邀请成员](team-setup.md)
- [功能导览](../features.md)
