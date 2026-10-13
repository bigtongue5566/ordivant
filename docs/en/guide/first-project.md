# First project: from launch checklist to accepted result {#first-project}

This walkthrough takes a team from first sign-in through coworker assignment, human claiming, Knowledge co-editing, and independent review. The example project is **Product launch readiness** (`LAUNCH`), with a task named **Organize the product launch checklist**. Human workflows in all three products need no LLM and do not require an Agent to stand in for a person. Model connections and automatic Agent Runs are optional.

## Before you begin {#before-you-begin}

Open the platform URL supplied by your administrator. If you are installing Ordivant yourself, finish the [installation guide](../containers.md) and open the local or organization URL. Regular human work in Work, Knowledge, and Code needs no model key. An autonomous Pi Durable Run needs an administrator to enable the runtime and configure a provider and model. Code's Git repositories and PRs require an administrator-configured Gitea service.

![Ordivant sign-in screen](/screenshots/login-en.png)

## Sign in as an administrator or invited member {#sign-in}

On a new environment, the first person opens the workspace and chooses **Create administrator account**. Enter a name, email, and password of at least 12 characters, confirm it, and submit. Save the one-time recovery codes in a secure place. There is no default account or password.

If an administrator invited you, choose **Accept invitation** on the sign-in screen, enter the one-time code they gave you, and set your own password. The invitation code expires after 24 hours and is usable once. An SSO user signs in through the enterprise button instead. Sign-in alone does not grant access to every product or project; see [Team setup](team-setup.md).

## Create the launch project {#create-project}

1. Select **Work** in the product switcher. In the project selector, choose **Create project**. Only an Identity administrator can create a Work project.
2. Enter these values:

   | Field | Example |
   | --- | --- |
   | Project key | `LAUNCH` |
   | Project name | `Product launch readiness` |
   | Description | `Plan, track, and review the work required before the product launch.` |
   | Team ID | Leave blank unless your administrator gave you the actual team ID. |
   | Budget limit (USD) | Leave blank unless your organization uses a project budget. |

3. Submit **Create project**. The project selector and page heading should show `LAUNCH` and `Product launch readiness`.

If you are a regular member and cannot create the project, ask an administrator to create it and grant your Work role and Project scope. Selecting Work does not grant access by itself.

## Add an optional versioned Knowledge specification {#knowledge-specification}

Knowledge is optional. Use it when the launch requirements should have an owner, version history, and traceable sources.

1. Switch to **Knowledge**. An Identity administrator selects **Add space** and creates a space with key `LAUNCH`, name `Product launch readiness`, and a short description. The administrator then grants the appropriate people a Knowledge role and that Space scope.
2. Select the `LAUNCH` Space and choose **Add document**. For example, use title `Launch readiness specification`, summary `Requirements and evidence for the first launch review`, and tags such as `launch` and `readiness`.
3. Enter the actual specification in **Body (Markdown)**. Include the decisions, owners, dates, and known source material. Add source references with their label and URI where appropriate, then choose **Create document**. The reader should show version `v1`, its body, and its source references.
4. After creating the document, open the latest version's **Shared draft** and choose **Edit**. Writers and Managers can edit the body together and switch to **Preview** to inspect formatting. The online list shows signed-in members editing together. Agents can also contribute to the same draft through REST or MCP. When the draft shows **Connected** and **Saved**, select **Publish new version**, enter a change summary, and confirm. This creates an immutable version; published content cannot be changed.

Readers can view the shared draft and version history but cannot edit. If the connection drops, changes not confirmed by the server remain only in the current browser tab's memory; do not close or reload that tab. If publication reports a version conflict, reload the shared draft, inspect the latest merged content, make edits, wait for **Saved**, then publish. A source URI is a citation; entering it does not fetch page contents. See the [Knowledge guide](knowledge.md) for details.

## Optional: configure a model connection for Agent Runs {#configure-model}

Skip this step for the manual route. Only an Identity administrator can edit organization model connections. Ask your provider or deployment administrator for the supported HTTPS API base URL and exact model ID. Enter your own provider-issued key directly in the form; never copy a key from a guide, put it in a task, or send it to an Agent.

1. In **Work**, open **Model connections**.
2. Choose **Add provider** and enter a unique Provider ID, a display name, the provider's **HTTPS API base URL**, and your own value in **API Key**. For example, the URL may look like `https://api.example.com/v1`; that example domain is a placeholder, not a working provider.
3. Add model metadata using the provider's exact Model ID and display name. Enter its context window, maximum output tokens, and supported reasoning strengths as supplied by the provider. Enable the provider.
4. Turn on the organization default and select the Provider and Model. Save the settings. The model selector should then be available when creating a Pi Agent. A saved key is not shown again in plaintext; enter a new key only when replacing it.

![Model connection settings](/screenshots/models-en.png)

If the provider or model is not configured, a dispatched Run may be labeled **DEMO**. DEMO uses a deterministic demonstration response, makes no paid model call, and does not produce a real launch deliverable. Do not treat its output or reported cost as a completed task. See [Model connections](../model-usage.md) and [Run and automation usage](../execution-usage.md).

## Optional: create a Pi Durable Agent in this project {#create-agent}

Complete this section only if you want an autonomous Agent to perform tasks. Human teammates can be assigned or claim work directly; no Agent is needed. An Identity administrator or Work Manager can manage Agents. First make sure `LAUNCH` is the selected Work project; the create form grants the new Agent access to the currently selected project. There is no Project field in this Agent form.

1. Open **Agent directory** and choose **Add agent**.
2. Enter name `Launch checklist worker`; set **Agent role** to **Worker** and **Runtime** to **Pi Durable**. Leave **Agent template version** empty unless your team has already published a suitable immutable template.
3. Add useful **Capability tags**, for example `launch-readiness`, `research`, and `documentation`. Leave **Team ID** empty unless the administrator supplied the real ID.
4. Under **Model settings**, inherit the organization default or choose a configured override. Confirm the effective model is the expected provider and model. Choose **Create agent**.

The Agent should appear in this project's directory with an available status. Confirm you are still in `LAUNCH` before creating another Agent for a different project. Agent identities and runtime identities are separate from human sign-in; a project grant to a person does not grant the same access to an Agent. The platform hands the scoped Agent credential to its runtime for an authorized Run.

![Pi Durable Worker Agent settings](/screenshots/agent-en.png)

## Create the task from a concrete specification {#create-task}

Open **Tasks** and choose **Add task**. This is a self-contained synthetic exercise; it needs no API, external system, or company data. Copy the eight lines in **Synthetic practice data** into **Inputs**.

### Synthetic practice data {#practice-background}

```text
SYNTHETIC EXERCISE ONLY: the following is fictional practice data; no API or external source is needed.
Product: Northstar practice release; launch date: unconfirmed.
Product: release scope and owner were not supplied; confirm both; owner is unassigned.
Login: current sign-in setup and validation evidence were not supplied; status is unknown.
Backup: backup owner, latest backup record, and restore evidence were not supplied; status is unknown.
Docs: a draft release note is requested; its owner and current document link are unassigned.
Support: support owner, coverage hours, and escalation contact were not supplied; status is unknown.
Analytics: success metrics, event mapping, and dashboard evidence were not supplied; status is unknown.
```

The practice data deliberately leaves information unknown. Do not invent dates, owners, approvals, or test results.

| Task field | Copyable example |
| --- | --- |
| Task name | `Organize the product launch checklist` |
| Description | `Prepare a reviewable checklist for the planned product launch.` |
| Goal | `Identify launch-readiness work, owners, status, and evidence so a reviewer can decide what remains before release.` |
| Inputs | Copy the eight-line block under **Synthetic practice data**. |
| Scope | `Using the supplied practice-background inputs, write one checklist line for each domain: Product, Login, Backup, Docs, Support, and Analytics. Each line must include the item, owner, status, and next action.` |
| Constraints | `Do not invent owners, dates, approvals, or completion status. Do not change the release plan or external systems. Do not include credentials or personal data.` |
| Acceptance criteria, one per line | `Checklist has a row for each of Product, Login, Backup, Docs, Support, and Analytics.`<br>`Every item has an owner or is explicitly marked unassigned.`<br>`Every status is supported by a source, or marked unknown.`<br>`Each open item has a next action.`<br>`The submitted result includes the checklist and links or quoted evidence needed for review.` |
| Priority | `Medium` |
| Assignee | Choose a human teammate authorized for this Project, or leave unassigned for an eligible teammate to claim. Choose `Launch checklist worker` only for an automatic Run. |
| Assign reviewer | Choose another authorized person or Agent. Leave blank when any eligible person may review. |
| Dependencies | Leave blank unless another task must be accepted first. |

Choose **Create task**. An unassigned task should appear in the task list with **Ready** status. Open it and check the goal and criteria. A human assignee can select **Claim task** directly; if assigned to a teammate, that person signs in and works on their own task. The task drawer has separate **Specification**, **Execution and review**, **Collaboration**, and **Events** views.

![Task specification and execution controls](/screenshots/task-en.png)

### Add a prerequisite when work depends on another task {#task-dependencies}

Create the prerequisite task first, such as `Confirm launch date and release scope`, and state what evidence will prove it is accepted. Edit the checklist task and select that task in **Dependencies** (the prompt says these tasks must be completed first). Until the prerequisite is accepted, the dependent task cannot be claimed or dispatched. Accepting the prerequisite releases eligible dependent tasks to **Ready**. Do not create circular dependencies.

## Optional: dispatch an Agent and inspect its Run {#dispatch-and-run}

Skip this section for the human workflow. An authorized Work Manager or Administrator opens the ready task, chooses `Launch checklist worker` in **Select a Pi runtime agent**, and selects **Dispatch to agent**. This creates an automatic Run and requires a configured Provider and model. **Claim task** is the human path and does not start an automatic Run.

Open **Run execution** and select the new Run. Review its status, progress, events, response, tools, and any reported model or usage receipt. A real provider call should identify the configured model in the Run record. If the Run says DEMO, stop treating its response as launch evidence and use the manual route or configure the provider first.

Run completion and task acceptance are separate. Continue only when the task has a submitted result and at least one evidence artifact, and its task status is **In review**. If the Run ended without submitting evidence, it is not ready for review; the worker must submit a summary and evidence through the task's execution flow.

![Run details and recorded events](/screenshots/run-en.png)

## Submit and independently review evidence {#submit-review}

The submitter provides a concise completion summary and at least one evidence item, such as a document, file, URL, or test report. The task enters **In review**. Open the task's **Execution and review** view and compare each acceptance criterion with the submitted artifacts and sources.

An authorized Reviewer, Manager, or Administrator who did not submit the result chooses **Accept** or **Return**, enters a review comment, and confirms. Accepting changes the task to **Completed** and can release dependent tasks. Returning it preserves the submission, history, and current assignee. The submitter cannot review their own result. A human or Agent can be assigned as the reviewer.

![Independent review of task evidence](/screenshots/review-en.png)

### Human collaboration without an LLM {#manual-route}

People use their own accounts; do not create or select an Agent, enable Runtime, or configure a model for this workflow. Invite a second member in Identity and grant them the Work Worker or Manager role and the `LAUNCH` Project scope. See [Team setup](team-setup.md) for invitation and scope steps.

Assign the task to that teammate or leave it unassigned so they can claim it. A person can claim only a ready task that is unassigned or assigned to them. Human work does not expire; after reloading, resume it from the task's execution history.

1. The second invited member opens the task in the `LAUNCH` Project and selects **Claim task**. They can report progress, or use **Collaboration** to record questions, handoffs, and decisions.
2. In the task execution controls, choose **Submit result**. Enter a completion summary, set **Evidence type** to **Document**, enter an evidence title, and paste the six-line checklist below into **Evidence content**. Submit at least one artifact; the task should move to **In review**.
3. A different authorized Reviewer, Manager, or Administrator opens **Execution and review**, checks the evidence against each criterion, and chooses **Accept** or **Return** with a written review comment. The reviewer must not be the submitter.

To give the task to another person, the current assignee selects **Handoff and release** and records completed work, open items, and next steps. The task returns to **Ready** and clears the human assignee so another eligible teammate can claim it. A blocked or returned task keeps its current assignee.

Copyable evidence content (one Markdown checklist line per area):

```markdown
- [ ] Product: confirm release scope and owner; owner unassigned, status unknown; next action is to confirm scope and owner.
- [ ] Login: sign-in setup and validation evidence not supplied; owner unassigned, status unknown; next action is to obtain the approved setup and evidence.
- [ ] Backup: owner, latest backup record, and restore evidence not supplied; owner unassigned, status unknown; next action is to obtain backup and restore records.
- [ ] Docs: draft release notes are needed; owner unassigned, status unknown; next action is to assign a documentation owner and provide a draft.
- [ ] Support: owner, coverage hours, and escalation path not supplied; owner unassigned, status unknown; next action is to confirm support arrangements.
- [ ] Analytics: success metrics, event mapping, and dashboard evidence not supplied; owner unassigned, status unknown; next action is to confirm metrics and evidence.
```

Example submission fields: summary `Prepared a checklist for all six launch-readiness areas from the synthetic practice data. Unknown statuses and unassigned owners are preserved, with a next action for each. No external system was accessed and no test or approval is claimed.`; evidence title `Northstar synthetic launch checklist`. After independently checking the evidence, the reviewer may write: `All six areas are present; unknown statuses and unassigned owners are preserved, and each item has a next action. This is a synthetic exercise and does not claim that tests passed.`

This workflow records the human account that submits the evidence; it creates no Pi Run or paid model call. Never enter a person's password or an API key in a task.

## Reuse an Agent template or workflow {#templates-workflows}

For repeat work, open **Automation** in the selected `LAUNCH` project.

- Under **Agent templates**, an authorized Manager or Admin can choose **Add template** and define a key, display name, description, Agent role, capabilities, optional model, tools, sandbox profile, instructions, and run limits. Choose **Create v1**. Later edits publish a new version; existing versions and already-created Runs keep their snapshot. Applying a template from the Agent directory copies its configuration to a new Agent. A template does not grant project, model, or tool access by itself.
- Under **Workflows**, choose **Add workflow**, define steps with a unique step key, name, goal, description, dependencies, a Pi Agent or required capabilities, acceptance criteria, and an optional independent reviewer, then choose **Create v1**. The editor checks that each step has an Agent or candidate capability. To launch an instance, choose **Start manually**, enter this launch's data under **Workflow inputs**, and confirm **Start workflow**. The workflow creates task instances; each step still requires its own evidence and independent review. You can inspect earlier instances under **Run history**.

Use a template when you want to reuse an Agent's operating instructions. Use a workflow when you want a repeatable sequence of dependent tasks and reviews. See [Run and automation usage](../execution-usage.md).

## Optional: attach a Code pull request {#optional-code-pr}

Use this only when your deployment has configured Code and its Gitea service, or when your organization has already connected a supported repository to Work. In **Code**, select or create a Code project, create a private repository if needed, create a branch and commit, then open a pull request. The repository and PR should be visible in the Code project. A new Code project and repository setup require an Administrator and a configured Gitea connection.

In the Code project, choose **Add project** and enter project key `LAUNCH`, name `Product launch readiness`, and a description. Choose **Add private repository** and enter repository name `launch-readiness` and a description; the default creates a private repository with a `main` branch and README. Choose **Create branch** and create `feature/launch-checklist` from `main`. Choose **Commit file**; in the **Submit UTF-8 file** form, enter **Target branch**, **Repository path** `docs/launch-readiness.md`, **File content (UTF-8)** with the six-line checklist above, and **Commit message** `docs: add launch readiness checklist`. Leave **Expected SHA** blank for a new file, then choose **Create commit**. Choose **Create pull request**; set **Source branch (Head)** to `feature/launch-checklist`, **Target branch (Base)** to `main`, title to `Add launch readiness checklist`, and describe the change. The PR should appear on the Code page. The `head` and `base` values must name branches that exist.

Return to the Work task and submit the pull request URL as a **URL** evidence artifact, with a title such as `Launch readiness checklist PR`. The reviewer can open the PR and compare its contents and checks with the task's acceptance criteria. A PR link is evidence to inspect; it does not itself accept the Work task. See the [Code guide](code.md).

## Finish and troubleshoot {#finish-and-troubleshoot}

The task is finished only when its result has evidence and an independent reviewer accepts it. The task should show **Completed**; dependent tasks may then become **Ready**. The project task list and overview reflect the accepted state.

| What you see | What to check |
| --- | --- |
| No project in the selector | Ask an Admin to create the Work project and grant your Work role and Project scope. |
| Cannot create a Project, Space, or model connection | Project and Space creation and organization model settings require an Identity Admin. |
| No Agent can be selected | Confirm an available Worker Agent was created while `LAUNCH` was selected and that its runtime is enabled for the project. |
| Run is labeled DEMO | No usable provider/model is configured for the Pi Agent, or the Pi runtime is not using a configured model. DEMO is not a real deliverable. |
| Task is blocked or dispatch is refused | Inspect **Dependencies** and accept every prerequisite first. |
| Run ended but the task is not in review | Check the task execution view for a submitted summary and evidence artifact. A completed Run alone is not a submission. |
| Review is refused | The reviewer must have an authorized Work role and Project scope, must not be the submitter, and must match the Agent in **Assign reviewer** unless the reviewer is an Administrator. |
| Knowledge link appears but its contents are missing | A source URI is a citation only. Add the authorized contents to the document body or use an approved retrieval integration. |
| Code cannot create a repository or PR | Ask the deployment administrator whether Gitea is configured and Code is available in this deployment. |

For access and team administration, continue to [Team setup](team-setup.md). For field definitions, see the [Work guide](work.md).
