<span id="路線圖與功能邊界"></span>
<span id="路线图与功能边界"></span>

# Roadmap and feature boundaries {#roadmap-and-feature-boundaries}

This page explains what is available today and what is not supported yet. It does not promise delivery dates. Use [GitHub Issues](https://github.com/ordivant-ai/ordivant/issues) to suggest needs, discuss them, or follow progress; a request does not guarantee development.

## New in v0.3.0 {#unreleased-development}

v0.3.0 adds Work planning, Knowledge document organization, and cross-product attachments, mentions, subscriptions, notifications, and search. It also adds SCIM, SMTP, OIDC login policies, and audit administration. See the [feature tour](./features.md) for operating steps and the [upgrade guide](./release.md) before updating an existing installation. Enterprise integrations require administrator configuration; validate your own IdP/directory and external Git services in your actual environment.

<span id="v0-1-已交付"></span>

## Available today {#delivered-in-v0-1}

- **Work**: Create projects and tasks, assign colleagues or agents, or let colleagues claim work. People can update progress, submit results, hand off work, and set task ordering. Agent workflows can be started manually or scheduled at minute intervals.
- **Knowledge**: Edit a shared document draft in real time with colleagues and let agents contribute through API / MCP. Publish immutable document versions, search text, record decisions, and cite exact sources.
- **Code (optional)**: Collaborate on code with Gitea and let colleagues and agents discuss and review pull requests. Reviews indicate whether their commit is outdated. Work can also show merge-request information from a configured Git service.
- **Sign-in and permissions**: Use regular accounts or enterprise OIDC single sign-on. SAML and LDAP / Active Directory can be connected through the optional Keycloak integration.
- **External tools**: Administrators can configure MCP tools that use an access token.
- **Execution isolation**: Docker work environments deny network access by default, but share the host kernel and are not equivalent to virtual machines.
- **Review**: A different authorized person must independently review submitted results before a task is complete.

Regular sign-in, manual tasks, shared document editing, and code collaboration do not require an LLM. A model service is needed only for automatic agent execution; Gitea still manages formal Git approval rules and merging. Offline edits remain only in the current tab, so wait for the editor to show "Saved" before leaving.

<span id="優先候選"></span>
<span id="优先候选"></span>

## Current limits and possible directions {#candidates-for-future-work}

| Area | Available now | Not supported yet |
| --- | --- | --- |
| Work execution | One execution service handles work. | Distributing work across multiple execution services or scaling them automatically. |
| Approval before actions | A different person can review submitted results. | A pre-approval flow that covers all actions taken through external tools. |
| Model usage and cost | Set per-response output, run-turn, and time limits; view usage records. | Reliable price calculation across all providers or a hard organization-wide spending limit. |
| Notifications and code checks | In-platform collaboration notifications, SMTP invitation/recovery mail, and upstream Git checks and Actions evidence. | Email/chat notifications for all collaboration events; running CI on behalf of upstream services. |
| Account management | OIDC groups, account disabling, SCIM 2.0 Users/Groups, and login policies. | Validate each customer IdP/directory lifecycle integration; SCIM bulk and automatic account claims by email are unsupported. |
| External tool sign-in | Connect MCP tools using an access token. | Interactive tool sign-in or Agent-to-Agent (A2A) connections. |
| Knowledge import | Save and search text documents. | Automatic document parsing, image text recognition, semantic indexing, or batch source synchronization. |
| Sandbox isolation | Docker execution denies network access by default and shares the host kernel. | Virtual-machine-level isolation or execution distributed across multiple services. |
