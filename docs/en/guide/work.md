# Ordivant Work

Work organizes projects, tasks, Agent execution, messages, result evidence, and independent review. A Task is business work; a Run or Execution is one actual attempt. Execution completion does not automatically complete the Task: an authorized reviewer other than the submitter must accept the result.

The URL preserves the active page and selected project or Space across all three modules, including Work planning, automation, and tool subtabs. Refreshing returns to that location; you can also bookmark the URL. Open tasks, Knowledge documents, and Code pull requests can be restored from their URLs. Access is checked again after login; deleted or inaccessible projects, Spaces, and repositories fall back to accessible items. Unsaved form content is not automatically saved.

![Work task list: follow demonstration tasks by status](/screenshots/work-en.png)

## Using the sidebar {#sidebar-navigation}

Work groups navigation into **Project work** (overview, tasks, planning, and collaboration inbox), **Agents & execution** (Agent directory, Runs, and automation), and **Administration** (tools and sandbox, audit; administrators also see model connections). Selecting a page preserves the current project.

All three modules keep a compact account row at the bottom of the sidebar. A status dot beside the avatar shows the service connection state; hover over it for details. Select the account row to open a floating panel with notifications, search, settings, language selection, and sign-out, without reducing navigation space. Click outside or press Escape to close it. On small screens, use the grouped **Go to** selector.

## Retire Agents {#retiring-agents}

Project managers and administrators can select **Delete Agent permanently** or **Archive Agent** in the Agent directory. Both require confirmation. If an Agent belongs to multiple projects, the operator must have access to all of them.

- **Permanent deletion** applies only to unused Agents without task, execution, collaboration, or configuration references. It removes the Agent, dedicated principal, credentials, project memberships, and model/execution settings. It cannot be undone; audit records remain.
- **Archiving** retains the Agent name and existing tasks, results, executions, and audit history, while revoking credentials and hiding the Agent from the default directory, assignment choices, and Agent counts. Select **Show archived Agents** to see them. Archived Agents cannot be re-enabled, edited, or assigned new work.
- **Unfinished work** must be handled first: stop Runs, hand off, reassign, complete, or cancel unfinished tasks, and disable or reassign automatic rules and schedules that still use the Agent. This also applies to tasks that have not started and designated reviewers.

These operations do not require an LLM. Disabling pauses an Agent's use while leaving it visible in the directory. The same control then displays **Re-enable** so managers can restore availability and assignment eligibility while retaining settings and history. An Agent's execution must finish before its status can change. Archive Agents that are no longer needed but have history to retain; archived Agents cannot be re-enabled.

## Built-in Agent templates {#built-in-agent-templates}

In a project's **Agent directory → Add Agent**, start with **Agent template version**. Six built-in roles are available:

| Template | Purpose |
|---|---|
| PM · Project Manager | Goals, scope, task breakdown, dependencies, risks, and handoffs |
| PG · Programmer | Implementation, fixes, code, and test evidence |
| SA · Systems Analyst | Business processes, requirements, access rules, and traceable acceptance criteria |
| SD · Systems Designer | Architecture, APIs, data models, tradeoffs, and migration plans |
| QA · Quality Assurance | Test plans, actual verification, reproducible defects, and coverage gaps |
| Reviewer · Independent Review | Check deliverables and evidence, giving reasons to accept or return work |

Applying a template fills a suggested name, platform role, capability tags, and instructions. It selects platform execution and inherits organization model settings. Edit the fields before creation; manually entered names are preserved.

**Execution method** determines who starts the Agent. Most users should choose **Run on the platform (recommended)**: the platform uses the configured model to execute tasks and track progress. An administrator must first enable the execution service. If you already have your own Agent program, choose **Run with an external program**. That program claims tasks and reports progress and results through the API or MCP; the platform does not start it, and the program manages its own model and connection settings. The execution method cannot be changed after creation.

Reviewer uses the reviewer platform role; the other jobs use worker. Job titles grant no additional administrator permissions. The Agent belongs to the current project; managers select tools and Sandbox separately. Server-side authorization and independent-review separation still apply.

Use **Automation → Agent template versions** to view built-ins, apply a version, or publish a custom version. Built-in text supports all three interface languages; entered drafts and custom templates stay verbatim. Templates are immutable versions stored per organization. Existing Agents and Runs retain their applied settings. REST and the `list_agent_templates` MCP tool expose these versions too.

<span id="建立專案與任務"></span>
<span id="创建项目与任务"></span>

## Create projects and tasks

1. An Identity administrator creates a Project in Work and grants members access to it. Members see only their authorized scope.
2. In the Project's “Tasks” view, create a Task and enter its goal, description, inputs, scope, constraints, acceptance criteria, and priority.
3. In **Assignee**, choose a human teammate or Agent authorized for this Project, or leave it unassigned for an eligible person to claim. In **Assign reviewer**, choose another authorized person or Agent. Add prerequisite Tasks as dependencies when needed. Cycles are rejected. A dependent Task can start only after its prerequisites pass independent review.
4. Save and search the task list or filter it by status. Editing the task specification does not replace saved execution or review history.

After creating a Work project, you can choose to create a Knowledge space and a Code project with the same name and description. Select either, both, or skip. Knowledge keeps the Work key; Code uses lowercase and replaces underscores with hyphens. Each product enforces its own access rules. Unavailable services, conflicting keys, and permission errors are shown separately. Retrying skips completed items, and the Work project remains available. This step creates a Code project; repositories can be created later in Code.

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

## Planning workspace {#planning-workspace}

In the Work sidebar, open **Planning workspace** and select a Project. Use **Board** to review task lifecycle columns and **Backlog order** to adjust project priority. Search and filters narrow the list by status, work type, Sprint, milestone, assignee, and overdue state. Enter a name and choose **Save query** to load your own saved filters later.

Managers can choose **Planning** on a task row to edit its work type (task, story, bug, or epic), Epic link, start and due dates, Sprint, milestone, estimate points, planning stage, and project custom fields. Moving an item up or down in Backlog changes its order only. A stage must match the task's current status. Board status controls allow backlog, ready, and cancelled transitions; execution, blocked, review, and completion remain governed by the existing execution and review flows.

Members with management permission can create Sprints, milestones, custom fields, planning stages, event rules, and task intake forms under **Planning settings**. A Project can have only one active Sprint at a time; closing a Sprint does not complete its tasks. After a task uses a custom field, its key and type cannot be changed. Rules run synchronously when a task is created or updated and can apply a label, assign an owner, or move a backlog task to ready. They do not dispatch Agent Runs, claim tasks, or complete reviews.

**Task intake** lets a signed-in Project member select an active form and submit a title, description, and its configured fields. Submission creates a backlog task for authorized members to triage, order, and assign. This is not an anonymous public form.

Choose **Worklogs** on a task row to record minutes, start time, and a summary under the signed-in person's identity. Managers can review worklogs, cycle time, and member capacity under **Worklogs and reports**, and import or export CSV. Managers must explicitly set weekly capacity in minutes for each Project participant (person or Agent); utilization remains blank until set, with no system estimate. Cycle time starts at a task's first execution and ends when an independent review accepts it, including rework and review wait; it is not effort spent. CSV import validates the whole batch before writing, so invalid input does not create partial rows; export protects spreadsheet formulas. Reports show recorded observations rather than forecasts of future effort or cost, and Agent-reported cost is not verified spend.

## Attachments, following, and the collaboration center {#resource-collaboration-center}

In a Task's **Attachments and collaboration** panel, upload or download an attachment while you retain access, follow updates, or post a comment that mentions an eligible teammate or Agent. Each file is limited to 10 MiB; the list shows its filename, size, and SHA-256 digest. Comment and attachment notices appear in the shared collaboration center. Following a resource does not send email.

Use the bell at the top right to open **Notification center**, review notices, and mark them read. The search button searches content across Work, Knowledge, and Code services available to your account. Results include only resources you can currently access. If a service is unavailable, its error is shown separately instead of treating missing results as a successful search. Search needs no LLM. Resource links recheck access when opened; revoked permissions do not expose previously available content.

## Select a project and manage its settings {#project-settings}

**Current project** at the top of the sidebar shows the selected project. Choose a project before using its tasks, planning workspace, Agents, runs, automation, or project administration. The breadcrumb also shows its key, name, and current section. The URL retains the selected project and section when you refresh.

Open **Project administration → Project settings**:

- **General**: project managers can edit the name, description, and tracking budget; other members can view them. The project key is immutable and the budget does not enforce a model spending limit. If another editor saves first, reload the settings before editing again.
- **Members and access**: system administrators can grant or remove access to this Work project while preserving other project and product grants. Changes revoke the affected member's current sign-in sessions, so they must sign in again. A member without a Work role joins as a Worker; an existing role is retained. Change SCIM-managed grants through provisioning groups. Manually editing SSO permissions stops enterprise group permission synchronization for that account.
- **Related workspaces**: administrators can create a corresponding Knowledge Space and Code project. The modules manage separate resources and permissions; matching names do not establish a link or shared access.

Work access scopes are project-specific, while the role applies across the product: a member has the same Work role in every granted project. Independent roles per project and a read-only Work role are not supported. Change roles in **Organization administration → Users and invitations**. Manage Agents in the selected project's **Agent directory**.

Personal passwords, sign-in sessions, and personal API tokens belong in **Account settings** in the bottom-left account menu. Enterprise SSO, organization members, and model connections belong in **Organization administration**. Project administration and human collaboration work without an LLM.
