---
layout: home
title: Open-source agent collaboration platform
description: Explore Ordivant tasks, agent runs, workflows, knowledge and code collaboration. Deploy your own platform and complete a first project with step-by-step guides.
hero:
  name: Ordivant
  text: Get work done with your team and agents.
  tagline: Turn goals into tasks and let agents execute with clear specifications and tools. Follow progress, preserve context, and review the evidence behind every result.
  image:
    src: /screenshots/work-en.png
    alt: Ordivant Work task workspace
  actions:
    - theme: brand
      text: Complete your first project
      link: /en/guide/first-project
    - theme: alt
      text: Install with Docker Compose
      link: /en/containers
    - theme: alt
      text: Explore the screens
      link: /en/#product-tour
---

<span id="從規格-到經過驗收的成果"></span>
<span id="从规格-到经过验收的成果"></span>

## From specifications to reviewed results {#from-specifications-to-reviewed-results}

Ordivant is an open-source, self-hosted project collaboration platform for teams and agents. It keeps **the work specification, execution history, deliverables, and team review** in the same project. Describe the goal and acceptance criteria, assign a person or Agent, inspect each attempt, and have an independent reviewer decide whether the work is complete.

Start with a document preparation task and add models, tools, project knowledge, and automated workflows as needed. Your deployment and administrators control member access, the tools agents may use, and their execution environment.

**This website contains product introductions and operating guides.** To use the platform, open your team's Ordivant URL or follow the [installation guide](./containers.md) to run your own instance. This website does not provide hosted accounts or a model service.

## What can you use Ordivant for? {#use-cases}

| Work to complete | Inputs and coordination | Deliverables the team can inspect |
| --- | --- | --- |
| Prepare a product launch | Product specifications, service inventory, tasks, and dependencies | A launch checklist with owners, statuses, and evidence for each item |
| Organize team knowledge | Operating guides, requirements, meeting decisions, and sources | Searchable documents, published versions, citations, and decision records |
| Collaborate on code changes | Change goals, scope, acceptance criteria, and specification citations | Branches, commits, PRs, and test evidence linked to the relevant tasks |
| Perform recurring work | Agent templates, repeatable steps, prerequisites, and execution input | Tasks, runs, submitted results, and review records for each workflow instance |

For example, summarize release readiness every week: first organize the supplied information, identify gaps and questions, then wait for review before dependent work begins. To read an external system, an administrator first connects and authorizes its tool. Adding a URL does not automatically retrieve its contents.

## Work with your team without an LLM {#collaboration-without-llm}

People can create tasks in Work. Managers and administrators can assign a task to a coworker, and authorized workers can claim tasks that are unassigned or assigned to them. A different authorized person must independently review submitted evidence.

In Knowledge, authorized members edit the same draft together in real time; a saved draft can be published as an immutable version. Agents can participate in that shared draft through REST or MCP, but these human workflows do not require an LLM.

Code stores Ordivant discussions and review records tied to a PR head SHA. Git operations in Code require Gitea; Gitea remains responsible for Git, merges, and its own approval process. Only autonomous Agent runs require model configuration.

## Explore the main features {#product-tour}

Switch products below to see the actual interface and the work it supports. Click a documentation screenshot to enlarge it, or view its original size to inspect the fields. The screens use demonstration data to show the features; DEMO runs illustrate operation and do not represent completed paid-model tasks.

<FeatureExplorer />

### Work: tasks, collaboration, and independent review {#work-preview}

Write a goal, inputs, scope, constraints, and acceptance criteria in the task specification. Managers can assign work to a coworker or Agent; authorized workers can also claim tasks that are unassigned or assigned to them. Keep help requests and delegated work in context, then submit evidence for an independent review by another authorized person.

[Task and review guide](./guide/work.md) · [Help and delegation](./features.md#work-help-and-delegation)

### Runs: agent execution and automation {#runs-preview}

After dispatching to a Pi Agent, inspect status, events, tool results, outputs, and provider-reported usage in Runs. Authorized members can request pause, resume, stop, or retry. Save repeatable settings as Agent templates. Start workflows manually or on an interval; dependent steps wait for their prerequisites to pass review.

[Runs, templates, and workflows](./execution-usage.md) · [Model connections and Agent settings](./model-usage.md)

### Knowledge: document versions and decision sources {#knowledge-preview}

Organize documents in Spaces and search titles, bodies, and tags. Authorized members can edit the same Markdown draft together in real time, and Agents can join that draft through REST or MCP. Publishing preserves an immutable version that tasks and PRs can cite. Space permissions still control who can read a citation.

[Documents, versions, search, and citations](./guide/knowledge.md)

### Code: code delivery and pull requests {#code-preview}

Code stores Ordivant-local PR discussions and review records tied to the current head SHA; these are not Gitea approvals. Git operations require Gitea, which remains responsible for Git, merging, and its own approvals. Teams already using GitHub or GitLab can configure Work's read-only connections for PR and check status.

[Code operating guide](./guide/code.md) · [Choose the products you need](./overview.md#four-service-boundaries)

## What does each team role do? {#team-roles}

| Role | Daily work |
| --- | --- |
| Project lead | Create projects and specifications, split tasks, arrange dependencies and people, dispatch agents, and address blockers |
| Executor | Complete the specification, ask questions, retain sources and deliverables, and submit for review |
| Reviewer | Check results and evidence against the acceptance criteria, then accept or explain required changes |
| Knowledge maintainer | Publish and update documents, record decisions, and provide traceable version citations |
| Deployment and organization administrator | Configure accounts, resource access, models, enterprise SSO, tools, and sandboxes |

One account can sign in to all three products in the same deployment. Work projects, Knowledge Spaces, and Code projects each have separate access grants. Human accounts and Agents are different identities; creating an Agent does not grant a team member access. [Set up your team and invite members](./guide/team-setup.md)

<span id="開始第一個專案"></span>
<span id="开始第一个项目"></span>

## Complete your first project {#start-your-first-project}

The full tutorial uses a product launch checklist. Create the LAUNCH project in an empty workspace, write an actionable specification, and complete submission and review. Choose either the Pi Agent route or manual execution.

1. **Sign in and set up the team**: create the initial administrator for a new installation, or accept an invitation or enterprise sign-in for an existing team. Invite another member so execution and review belong to different people.
2. **Create the project and context**: create Product launch preparation. Publish an existing specification to Knowledge and retain its version citation, or first put the necessary information in the task inputs.
3. **Prepare the executor**: automatic work requires Runtime, your own model provider and key, and a Pi Agent with project access. The manual route can start without an external model.
4. **Add a concrete task**: enter the goal, inputs, scope, constraints, and individual acceptance criteria. The tutorial supplies field-by-field examples and content you can copy.
5. **Dispatch and follow progress**: select a Pi Agent in the task and dispatch it, then inspect Runs. A manual executor claims the task and prepares the actual checklist before submitting.
6. **Inspect and independently review**: the executor submits a summary, checklist, and source evidence. A different authorized person accepts it or requests changes. Acceptance marks the task complete.
7. **Arrange follow-up work**: set a dependency so the next task waits for this checklist to be accepted, then save repeatable Agent settings and steps as a template and workflow.

![Result review showing the sample checklist, submitted evidence, and review decision](/screenshots/review-en.png)

[Start the complete first-project tutorial →](./guide/first-project.md)

## How do you write a task an Agent can use? {#writing-a-useful-task}

Supply accessible information, then specify the deliverable format and boundaries. The tutorial's checklist specification follows these principles:

| Field | Product launch checklist example |
| --- | --- |
| Goal | Organize the items to confirm before launch using the supplied product context |
| Inputs and scope | Provide the current state of sign-in, backup, and user guides; prepare a checklist and identify gaps |
| Constraints | Mark missing information as needing confirmation; do not claim checks or external changes were completed |
| Acceptance criteria | Give each item an owner role, status, and source; cover sign-in, backup, and user instructions |
| Evidence | Submit the actual checklist, source citations, and items still requiring human confirmation |

When an Agent lacks information or a tool, add inputs, authorize the appropriate tool, or separate the work that requires a person. A reviewer checks actual deliverables after a model reply, submitted Run, or reported status. [See the full specification and submission examples](./guide/first-project.md)

## Choose how to start {#choose-your-start}

**Joining a team**: obtain the platform URL and invitation from your administrator and follow the [quick introduction](./guide/getting-started.md). If no project is visible, ask for access to the relevant resource.

**Installing your own instance**: prepare Git and Docker Compose v2, follow the [deployment guide](./containers.md) to download, initialize, and start the services, then open the platform and create the initial administrator. Enable automatic Agent execution, Code, or sandboxes when you need them.

**Adopting it in an organization**: arrange roles and resource access with [team setup](./guide/team-setup.md), then configure [enterprise SSO](./enterprise-sso.md), [models](./model-usage.md), and allowed [tools and sandboxes](./execution-usage.md#external-mcp-tools). Plan [backup and operations](./guide/operations.md) as well.

## Find the guide you need {#find-your-guide}

| What you want to do | Start here |
| --- | --- |
| Understand how to use each feature | [Feature guide](./features.md) |
| Complete a deliverable from an empty workspace | [Full first-project tutorial](./guide/first-project.md) |
| Invite members and assign execution and review roles | [Set up your team](./guide/team-setup.md) |
| Configure an API connection and Agent model | [Model settings](./model-usage.md) |
| Manage runs, templates, and multi-step work | [Execution and automation](./execution-usage.md) |
| Publish documents, decisions, and citations | [Knowledge guide](./guide/knowledge.md) |
| Submit code changes and PRs | [Code guide](./guide/code.md) |
| Connect company sign-in and resource access | [Enterprise SSO](./enterprise-sso.md) · [Organization administration](./guide/administration.md) |
| Install, upgrade, back up, and resolve problems | [Docker Compose](./containers.md) · [Operations](./guide/operations.md) · [Troubleshooting](./guide/troubleshooting.md) |

<span id="部署在自己的環境"></span>
<span id="部署在自己的环境"></span>

## Deploy in your own environment {#deploy-in-your-own-environment}

Ordivant is **MIT licensed**. Use, modify, and deploy it yourself. Work, Knowledge, and Code can be deployed independently, and you manage the data. Shared sign-in supports local accounts and enterprise OIDC; optional Keycloak can bridge SAML and LDAP.

The currently published release is **v0.4.0 (2026-10-19)**. Human collaboration in Work, Knowledge, and Code needs no LLM; only autonomous Agent Runs require model settings. Knowledge offers text search, and Code Git writes require Gitea. This release does not include vector search, built-in CI, hard dollar budgets, or distributed execution. Docker sandboxes have no network or host-directory access and use tools already present in the environment. Configure VM execution when stronger isolation is required. See the [release and upgrade guide](./release.md).

## v0.4.0: team setup and external access {#unreleased-p0-p1}

Create Agents from six role templates, fetch available models from your Provider, and optionally create a Knowledge space and Code project with a new Work project. People can create personal tokens to use authorized features through API or MCP. See the [release notes](./release.md) and [connection tutorial](./guide/administration.md#personal-api-and-mcp-access).

Provide and authorize your own model and tool connections; external providers may charge for use. Unconfigured DEMO runs illustrate the execution flow. For actual delivery, check results, sources, and provider usage.

[Self-host →](./containers.md) · [Available features and plans](./roadmap.md) · [GitHub source](https://github.com/ordivant-ai/ordivant)
