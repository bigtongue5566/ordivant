# Ordivant Feature Guide {#product-features}

This guide explains where to find each feature, what it produces, and the limits to keep in mind. Work, Knowledge, and Code support people and Agents collaborating in the same product workflows; routine human work does not need an LLM. Work manages tasks, human execution, and Agent Runs; Knowledge manages shared drafts, document versions, and decisions; Code manages repositories and PRs connected to Gitea and keeps Ordivant discussion and review records. Start with the [project overview](./overview.md), then follow the scenarios below.

This guide describes v0.4.0. If an entry is missing from your screen, ask your administrator to check the installed version, product permissions, and required integrations.

## Human and Agent collaboration {#human-and-agent-collaboration}

### Scenario {#human-and-agent-collaboration-scenario}

A team wants coworkers to handle tasks, co-edit a specification, and review a PR before adding Agents to suitable automated work. These human workflows can be used before configuring a model.

### Where to go and what to do {#human-and-agent-collaboration-steps}

1. In Work, assign a task to an authorized teammate or Agent, or leave it unassigned for a teammate to claim. A human Worker, Manager, or Administrator can claim a ready task that is unassigned or assigned to them, report progress, submit evidence, or hand it off. Submitters cannot review their own results. See the [Work guide](./guide/work.md).
2. In Knowledge, open the latest version's shared draft. Writers and Managers can edit together; Readers can view it. Publish an immutable version only after the server confirms it is saved. Agents can work on the same draft through REST/MCP. See the [Knowledge guide](./guide/knowledge.md).
3. In Code, discuss a PR and submit an Ordivant review record. Each review is bound to that PR head SHA; Gitea remains responsible for Git, merges, and its own approvals. See the [Code guide](./guide/code.md).

### Result and limits {#human-and-agent-collaboration-result}

People use their Identity accounts; there is no need to create an Agent to represent a person or provide a model key. Only an autonomous Pi Agent Run requires an enabled Runtime and a configured provider/model. Code repository, branch, commit, and PR writes require Gitea. During a Knowledge disconnect, unconfirmed changes remain only in the current browser tab's memory and may be lost if it is closed or reloaded. A publication conflict requires reloading and checking the latest draft. Ordivant Code reviews are not Gitea approvals, CI results, or Work task acceptance.

## Task specifications and dependencies {#work-task-design}

### Scenario {#work-task-design-scenario}

You are preparing a launch checklist. The service inventory must be complete before the follow-up checks can start.

### Where to go and what to do {#work-task-design-steps}

1. In Work, select a Project you can access, open Tasks, and select Add task.
2. Enter the title, goal, inputs, scope, constraints, and acceptance criteria, with one criterion per line. Set the priority, choose an authorized coworker or Agent as the assignee, and select an independent reviewer. You can also leave it unassigned for a coworker to claim.
3. Under Dependencies, select the tasks that must finish first and create the task. Open the task to review its fields and dependency status in the Specification tab. Select Edit specification to make a change.

![Work project task list](/screenshots/work-en.png)

![Task details and specification](/screenshots/task-en.png)

### Result and limits {#work-task-design-result}

Dependencies remain visible in the task specification, and circular dependencies are rejected. A dependent task cannot start until its prerequisites are accepted and complete. A task, its runs or executions, submitted evidence, and review decisions remain separate records; editing the specification does not erase their history.

## Asking for help and delegating work {#work-help-and-delegation}

### Scenario {#work-help-scenario}

An assignee needs another coworker or Agent to confirm a data source, or wants to split off a test-case deliverable that can be reviewed on its own.

### Where to go and what to do {#work-help-steps}

1. Open the task details from the task list and select Request collaboration. Choose an authorized coworker or Agent as the recipient, describe the question or requested information, and send it. The thread stays in the task's Collaboration tab, and the recipient can also find it in Work's Collaboration inbox.
2. Reply in the task thread. The recipient or an authorized manager can mark a message accepted or completed. Questions, replies, decisions, and handoffs remain in the project and task context.
3. To create a separately tracked deliverable, select Delegate subtask in task details. Choose an authorized coworker or Agent as the assignee, enter the subtask's title, goal, scope, inputs, constraints, and acceptance criteria, then delegate it.

### Result and limits {#work-help-result}

Delegation creates a separate task linked to its parent, with its own execution or Run, evidence, and review history. A project-scoped Manager or Administrator, or the current human or Agent owner of the parent execution, may delegate. Delegation does not expand anyone's project access, and nested delegation is limited to three levels. Collaboration messages are task-linked work records, not an instant chat service.

## Runs and human intervention {#runs-and-intervention}

### Scenario {#runs-intervention-scenario}

The task specification is ready. You want a Pi execution agent to perform it, and a person to inspect or control the run when needed.

### Where to go and what to do {#runs-intervention-steps}

1. Open the task details. A human assignee selects **Claim task** directly; human work has no Agent lease and can be resumed from its execution history after reloading. To run work autonomously, select a Pi Agent and dispatch it; this creates an automatic Run.
2. Open Run execution in the Work sidebar and select a run to inspect its status, answer, events, tool results, sandbox output, and provider-reported model and usage.
3. With the required permissions, request Pause, Resume, or Stop in the run details. A failed or stopped run can be retried to create a new Run; the prior run remains in the history.
4. After submission, return to Execution and review in the task details. A different authorized reviewer checks the summary and evidence, then accepts or returns the work.

![Run execution console](/screenshots/run-en.png)

### Result and limits {#runs-intervention-result}

A Run marked submitted means the model turn was submitted; it does not complete the task. A separate authorized review must accept it. Human execution is a separate work record and does not need a model. Pause takes effect after the current model or tool operation finishes. Stop cannot undo an operation already completed by an external service. Check the upstream service before retrying when the result is uncertain. DEMO does not call a paid model. Missing or unverified usage and dollar amounts are shown as unknown.

## Agent templates and workflows {#agent-templates-and-workflows}

### Agent templates: reuse execution settings {#agent-template-reuse}

Open Automation > Agent template in the Work sidebar. A template can define an agent role, capability labels, instructions, model options, tool connections, a sandbox profile, maximum model turns, and a run timeout. When creating or editing an agent, choose an exact template version under Agent template version, then adjust the agent settings if needed. To change a template, publish a new version; existing agents and runs retain the version and settings they already use.

Templates make it easier to reuse a working setup. They do not grant access to projects, model providers, or tools. The agent still needs project access, the organization administrator configures providers, and a project manager configures tool connections.

### Workflows: sequence a multi-step deliverable {#workflow-sequencing}

1. Open Automation > Workflow and select Add workflow. Add steps with a title, goal, priority, and acceptance criteria, choose an agent or required capabilities, and select a reviewer for each step.
2. Set prerequisite steps under Step dependencies. Independent steps can run in parallel; invalid or circular dependencies are rejected.
3. Select Start manually, enter this instance's workflow input, and start it. Each step creates a task. A step waits if no eligible agent is available or a prerequisite result has not passed review.
4. For recurring work, open Schedule and set whether it is enabled, its interval, and its maximum number of starts. Review workflow instances under Run history.

Each workflow instance uses the version that was active when it started. Every step still needs its own accepted review before dependent steps can proceed. A schedule will not start a second instance while the previous one is running, and missed intervals are not replayed after downtime. Canceling a workflow stops unfinished steps and preserves accepted results. Manually claiming a task does not dispatch a Run.

![Workflow editor and schedule settings](/screenshots/workflow-en.png)

## Model inheritance and agent overrides {#model-inheritance-and-overrides}

### Scenario {#model-settings-scenario}

The organization uses one default model for most agents and assigns a different approved model to a code-review agent.

### Where to go and what to do {#model-settings-steps}

1. A Work organization administrator opens Model connections, adds a provider with its HTTPS API URL and API key, registers supported models and options, and selects the organization default.
2. In the Agent directory, create or edit an agent. Choose Use organization default, or select a configured provider, model, reasoning effort, and output limit.
3. Confirm the effective model in the Agent directory. Dispatched work keeps the model snapshot it started with; changes apply to later dispatches.

### Result and limits {#model-settings-result}

Provider keys are encrypted and are not shown again in plain text. For an external-runtime agent, the model name is informational; Work does not call that model for the agent. If no model is configured, Pi Runs use clearly labeled DEMO mode. A failed live provider call is reported as a failure and is not presented as a successful demo. Token counts and the provider-reported model are not a bill. Model output limits are not a hard dollar spending cap; check rates and actual charges with the provider. See the [model connection guide](./model-usage.md) for setup details.

## Knowledge document versions and search {#knowledge-versioning-and-search}

### Scenario {#knowledge-versioning-scenario}

Your team is revising a launch specification but needs old tasks to keep pointing to the version they used.

### Where to go and what to do {#knowledge-versioning-steps}

1. Open Knowledge, select a Space you can access, and open Documents. Select Add document, then enter the title, summary, body, tags, and traceable sources.
2. To revise it, open the latest version's shared draft and select Edit. Writers/Managers and Agents can update the body together; changes merge. Switch to Preview to inspect Markdown.
3. Wait for the draft to show Connected and Saved, then select Publish new version, enter a change summary, and confirm. Publication creates an immutable version; Readers can view it but not edit. If a version conflict appears, reload the draft, inspect the merged content, and wait for Saved before publishing.
4. In the document reader, select a version to inspect its URI, creation time, SHA-256, and change summary. Search by title or body, or filter by tag.

![Knowledge document and version history](/screenshots/knowledge-en.png)

### Result and limits {#knowledge-versioning-result}

Each publication creates an immutable version and preserves prior versions and citations. Unconfirmed offline changes remain only in the current browser tab's memory; do not assume they survive closing the page. Search matches stored titles, bodies, and tags. It is text search; vector search and RAG are not provided.

## Knowledge decisions and exact citations {#knowledge-decisions-and-citations}

In Knowledge, select a Space, open Decisions, and select Add decision. Enter the title and decision, then optionally associate a document and source references. Use this to record why a choice was made and what supported it. When the decision changes, add a new record to preserve the earlier context.

To cite a specification, copy the full URI from its exact document version and add it to a Work task's inputs or evidence, or to a Code pull request's sources. The URI stays pointed at that version after later edits. A citation records provenance; it does not grant permission to read the Knowledge Space. Readers still need access.

The version URI has this format:

~~~text
ordivant://knowledge/spaces/{space_id}/documents/{document_id}/versions/{version}
~~~

## Code branches and pull requests {#code-pull-requests}

### Scenario {#code-pull-requests-scenario}

An engineering team wants to prepare a configuration change in Gitea, link its Work task and Knowledge source, and send the pull request through the team's existing review process.

### Where to go and what to do {#code-pull-requests-steps}

1. Open Code and select an authorized Code Project and repository. A member with write access can create a private repository.
2. In the repository details, create a branch. Use Commit file to add or update a UTF-8 file and provide a commit message.
3. Select Create pull request, choose the head and base branches, enter a title and description, and add Work, Knowledge, or external source references.
4. In the pull request details, inspect the head SHA, sources, state, and check receipts. Use Ordivant's discussion and review panel to comment, request changes, or record an approval. Select Open in Gitea to follow the formal review and merge process.

![Code repository and pull request](/screenshots/code-en.png)

### Result and limits {#code-pull-requests-result}

Code repositories, branches, commits, and PRs are stored by the configured Gitea service. Write operations are unavailable until Gitea is configured. PR details also read Gitea branch rules, approvals, status checks, and Actions for the current head SHA; when a GitHub or GitLab deployment source is configured for that repository, they also show deployment records for the same SHA. Code reads this evidence; it does not start CI or create deployments. Without provider configuration, the page clearly reports that evidence as unavailable. People and Agents can discuss and review in Ordivant; each review is bound to the PR head SHA and becomes expired when the head changes. An Ordivant record does not create a Gitea approval or represent CI or Work task acceptance. A status entered with Report status is labeled agent-reported; it does not prove that CI ran tests. A signature-verified Gitea webhook has a distinct source label, and the upstream check record is still needed to confirm what ran. If you only need to inspect existing GitHub, GitLab, or Gitea PR status, Work can use its configured read-only integration without deploying Code.

## Permissions, members, and enterprise SSO {#permissions-and-sso}

### Scenario {#permissions-and-sso-scenario}

An administrator wants people to sign in with the company identity provider while limiting each person to their assigned projects, knowledge spaces, and code projects.

### Where to go and what to do {#permissions-and-sso-steps}

1. Open Account and security > Enterprise SSO. Choose an OIDC provider template, enter the organization's Issuer, Client ID, Client Secret, allowed domains, and invited-only or just-in-time (JIT) account provisioning policy.
2. For group-based access, configure the identity provider's groups claim and explicit group-to-product/resource mappings. Save, select Test connection, then sign in as a regular member and verify their access.
3. Before requiring enterprise sign-in, confirm the administrator recovery path, then enable SSO-only. In Users and invitations, an administrator can change product roles and resource scopes and revoke sessions. Identity audit shows administrative records.

### Result and limits {#permissions-and-sso-result}

An organization administrator grants product roles and resource scopes. Roles are separate for each product: Work has Manager, Worker, and Reviewer; Knowledge has Manager, Writer, and Reader; Code has Manager, Writer, and Reader. SSO creates a platform session; it does not automatically grant access to a Project, Space, agent, runtime, or Gitea. Invited members use a one-time invitation created by an administrator. Identity sends the invitation email when SMTP is configured; otherwise, no email is sent and the administrator must securely deliver the code.

OIDC is the sign-in protocol. SAML or LDAP / Active Directory can connect through the optional Keycloak broker; there is no native SAML endpoint. Identity provides SCIM 2.0 Users/Groups, without bulk operations or automatic account claims by email. Each customer IdP and directory still needs validation. See the [enterprise sign-in guide](./enterprise-sso.md) and [administration guide](./guide/administration.md) for tenant setup and limits.

## External tools and isolated sandboxes {#tools-and-sandbox}

### Scenario {#tools-and-sandbox-scenario}

You want one agent to query an internal MCP service and run analysis commands in an isolated workspace without reading host files.

### Configure an external MCP tool {#external-mcp-tool-setup}

1. A deployment administrator first allows the MCP host. A Work project manager opens Tools and sandbox, selects Add connection, enters its HTTPS URL and bearer token, selects the available tools, and selects Test tools/list.
2. In the agent template or the Agent directory's execution settings, select only the project connections this agent needs, then dispatch a Run.
3. Inspect the observed tool calls and results in the Run details.

Tokens are encrypted and are not displayed again. Connections currently use bearer tokens; interactive MCP OAuth is not available. Arbitrary external hosts are blocked by default, and private HTTP or internal network targets require explicit deployment configuration. External tools can change upstream data. If an operation's result is uncertain, it is not automatically repeated; stopping a Run cannot undo a completed action.

### Configure a sandbox {#sandbox-setup}

In Tools and sandbox, create a project sandbox profile and set limits such as command time, memory, CPU, process count, output size, and workspace size. Apply the profile to an agent. Commands then run in a temporary workspace dedicated to that Run.

The sandbox has no network access or host-directory access. It cannot download dependencies or clone arbitrary repositories; only tools and packages already in the environment are available. The workspace is removed when the Run ends, stops, or times out, so submit files and test output as artifacts before then. A Docker sandbox shares the host kernel and is not equivalent to VM or microVM isolation.

![Tool connections and sandbox settings](/screenshots/tools-en.png)

## Work planning and intake {#work-planning-and-intake}

Open **Planning workspace** in the Work sidebar to organize tasks, stories, bugs, and epics on a board or in Backlog order, filter by Sprint, milestone, assignee, or due date, and save your own queries. Managers can configure custom fields, stages, event rules, and intake forms. Signed-in Project members submit requests through a form, creating backlog tasks for triage. Worklogs and reports show recorded observations; CSV import validates a whole batch before writing, and export protects spreadsheet formulas. Planning does not replace execution and review or dispatch Agents. See the [Work guide](./guide/work.md) for the full workflow and limits.

## Knowledge page trees and comments {#knowledge-page-tree-and-comments}

When creating a document, choose a PRD, meeting, ADR, or SOP template, or select a parent in the same Space. Archived pages are hidden from the default search list. Writers and Managers can add comments tied to a published-version quote, reply and resolve a thread, compare versions, or restore old content as a new version. The shared draft keeps Markdown as its single canonical content; toolbar actions insert formatting, links, image URLs, or tables and update a live preview. This is not a full WYSIWYG editor. See the [Knowledge guide](./guide/knowledge.md).

## Attachments, follow notices, and cross-product search {#shared-attachments-notifications-search}

Work Tasks, Knowledge documents, and Code pull requests have a collaboration panel for authorized attachments, following updates, comments, and mentioning eligible members. The shared collaboration center shows notices and lets people mark them read; its search spans Work, Knowledge, and Code resources currently available to the account. Service failures are listed clearly. Attachments have a per-file size limit. Notices stay in the platform and are not sent through SMTP; full-text search needs no LLM.

## Enterprise provisioning, MFA, and audit {#enterprise-provisioning-mfa-audit}

Administrators use **Account and security → Enterprise governance** to configure explicit SCIM group grants to product resources, inspect the mail queue, set audit retention, and export Identity records as JSONL. SCIM requires a dedicated credential configured by the deployment administrator. It never claims or merges an existing account just because its email matches, and provisioning groups cannot grant admin. When MFA is required, Identity enforces OIDC acr/amr claims from the verified external IdP token; the IdP supplies the actual second factor. If SMTP is not configured, invitation and recovery mail are not sent. See the [administration guide](./guide/administration.md) and [enterprise sign-in guide](./enterprise-sso.md).

## More user guides {#next-steps}

- [Create your first project](./guide/first-project.md) and [set up a team](./guide/team-setup.md)
- [Work tasks, runs, and reviews](./guide/work.md) and [Run, workflow, tool, and sandbox operations](./execution-usage.md)
- [Model connections and agent settings](./model-usage.md)
- [Knowledge documents and citations](./guide/knowledge.md) and [Code pull requests](./guide/code.md)
- [Administrator and member setup](./guide/administration.md) and [enterprise SSO configuration](./enterprise-sso.md)
