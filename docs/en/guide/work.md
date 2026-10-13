# Ordivant Work

Work organizes projects, tasks, Agent execution, messages, result evidence, and independent review. A Task is business work; a Run or Execution is one actual attempt. Execution completion does not automatically complete the Task: an authorized reviewer other than the submitter must accept the result.

![Work task list: follow demonstration tasks by status](/screenshots/work-en.png)

<span id="建立專案與任務"></span>
<span id="创建项目与任务"></span>

## Create projects and tasks

1. An Identity administrator creates a Project in Work and grants members access to it. Members see only their authorized scope.
2. In the Project's “Tasks” view, create a Task and enter its goal, description, inputs, scope, constraints, acceptance criteria, and priority.
3. In **Assignee**, choose a human teammate or Agent authorized for this Project, or leave it unassigned for an eligible person to claim. In **Assign reviewer**, choose another authorized person or Agent. Add prerequisite Tasks as dependencies when needed. Cycles are rejected. A dependent Task can start only after its prerequisites pass independent review.
4. Save and search the task list or filter it by status. Editing the task specification does not replace saved execution or review history.

Human assignees must be invited, active, and granted a Work role and this Project scope by an Identity administrator. An administrator can assign work to an invited teammate before they have signed in to Work. See [Team setup](team-setup.md) for roles and scopes.

<span id="執行並提交證據"></span>
<span id="运行并提交证据"></span>

## Execute and submit evidence

Human work needs no LLM or Agent. A Worker, Manager, or Admin with access to this Project can claim a ready task that is unassigned or assigned to them. Select **Claim task** directly; do not select an Agent. A person cannot claim work assigned to someone else. Human execution has no Agent lease and can be resumed from the task's execution history after reloading the page.

Use **Report progress** to record updates and evidence while working. If the task must wait for information, select **Mark blocked**. A blocked or returned task keeps its current assignee. To pass work to a colleague, choose **Handoff and release** and add a handoff note. This closes the current execution, records the handoff, clears the human assignee, and returns the task to **Ready** so another eligible teammate can claim it. A Manager or Admin can also reassign a task before execution starts.

When done, submit a summary and one or more results, such as text, an Artifact URI, or a file/test-result reference. Submission moves the Task into review and preserves its execution, evidence, and handoff history. Explain how the evidence meets the acceptance criteria; submission does not mean the Task was accepted. A different authorized person reviews it and accepts or returns it. Submitters cannot review their own results.

Dispatching an Agent is a separate path: the Agent execution service must be enabled, and only autonomous Pi Runs need a model connection. Agent executions retain their own lease and fencing token. See [Runs and automation](../execution-usage.md) for dispatching.

<span id="協作與引用"></span>
<span id="协作与引用"></span>

## Collaboration and citations

Use messages in the Task context to ask another member or Agent a question, reply, hand off work, or record a decision. A Project Manager or Admin, or the human or Agent responsible for a parent Task, can select **Delegate child task** to assign work to a colleague or Agent with execution rights in that Project. Delegation does not grant access to other Projects.

When work depends on a Knowledge document, put its **exact-version citation URI** in Task inputs or submitted evidence, retaining the version number. A citation records the source but does not authorize readers in the Knowledge Space; members who need the original document must be granted access separately. See the [Knowledge guide](knowledge.md) for the citation format and workflow.

Work can also read pull-request and check states from configured existing GitHub, GitLab, or Gitea providers. This is scoped read access and evidence inspection; it does not merge pull requests or replace independent review. See the [Code guide](code.md) for repositories and pull requests managed through Gitea in Code.

<span id="run-控制"></span>

## Run controls

Use “Run execution” to view each attempt's status, events, and usage. Administrators and project managers can pause, resume, stop, or retry. Pause takes effect before the next tool operation and keeps the task assigned. After stopping, that attempt cannot update the task. Retry creates a new Run. Stopping does not undo completed external operations; check their results before retrying.

See the [execution guide](../execution-usage.md) for Run states, waiting and stop semantics, sandbox configuration, and tools. External side effects from tools are not automatically replayed on retry; verify uncertain outcomes with the upstream service first.

<span id="權限概覽"></span>
<span id="权限概览"></span>

## Permissions overview

- **Manager:** manages tasks and execution schedules in authorized Projects.
- **Worker:** claims unassigned work or work assigned to them, submits results, and can hand work off.
- **Reviewer:** reviews submissions and cannot accept their own. Managers and Administrators can also review within their authorized scope.

Organization administrators create Projects, invite members, and grant product roles. Work access is based on Project scope and manager, worker, or reviewer identity; there is no separate Work Reader role. A human sign-in session does not become an Agent or Runtime credential.
