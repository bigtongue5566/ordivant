<span id="v0-1-0-公開版本"></span>
<span id="v0-1-0-公开版本"></span>
<span id="public-release-v0-1-0"></span>
<span id="public-release-v0-2-0"></span>

# Ordivant v0.3.0 release {#public-release-v0-3-0}

Released: 2026-10-15. License: [MIT](../../LICENSE). Source and downloads: [GitHub Releases](https://github.com/ordivant-ai/ordivant/releases/tag/v0.3.0).

## Included in this release {#included-in-this-release}
<span id="本版內容"></span>
<span id="本版内容"></span>

- **Work team planning**: Board and backlog ordering, Epics, work types, Sprints, milestones, dates, custom fields and stages; authenticated task intake, event rules, private saved queries, work logs, weekly capacity, observed reports, and CSV import/export. People can claim or receive work, hand it off, and submit results for independent review by another authorized person. See the [Work guide](./guide/work.md).
- **Collaboration across products**: Work, Knowledge, and Code resources support attachments, mentions, subscriptions, and notifications. The notification center and cross-product text search show only content currently authorized for the user.
- **Knowledge document collaboration**: Page hierarchies, archiving, PRD/meeting/ADR/SOP templates, comment replies and resolution, Markdown tools and preview, version differences, and controlled restoration. People and Agents can still edit the same shared draft and publish immutable versions. See the [Knowledge guide](./guide/knowledge.md).
- **Code review and evidence**: Inline PR discussions bind to a head SHA, file, and line, and become stale after a head change. Manage and read back Gitea branch protection, inspect upstream approvals, checks, and Actions for the current commit, and read same-SHA deployments when GitHub/GitLab sources are configured. Ordivant does not run upstream CI or deployments. See the [Code guide](./guide/code.md).
- **Enterprise identity and governance**: SCIM 2.0 Users/Groups, OIDC ACR/AMR login policies, SMTP invitations and account recovery, and Identity audit export and retention administration. See [Administration](./guide/administration.md) and [Enterprise SSO](./enterprise-sso.md).
- **Works without an LLM**: Human tasks, shared editing, attachments, search, and Code collaboration need no model. Only autonomous Agent Runs require a model connection. The interface and operating guides support Traditional Chinese, Simplified Chinese, and English.

## Upgrade and limitations {#upgrade-and-limitations}
<span id="升級與限制"></span>
<span id="升级与限制"></span>

Before upgrading from v0.2.0 or earlier, follow the [operations guide](./guide/operations.md) to stop services and back up the Compose project's databases, all persistent volumes, service secrets, and custom `.env`. Keep encryption keys with the matching databases and volumes. Secrets default to `.data/container-secrets/`; back up the location selected by `ORDIVANT_SECRETS_DIR` if customized. Also back up `ORDIVANT_ENTERPRISE_SECRETS_DIR` if enterprise secret mounts are enabled.

Update the existing repository to v0.3.0 while preserving the original Compose project name, `.env`, secrets directory, Compose file combination, and profiles. Services apply database schema updates at startup. From the repository root, run:

```sh
docker compose up -d --build --wait
docker compose ps
```

If the installation uses profiles or multiple Compose files, keep those options on every start, rebuild, and upgrade. After services become healthy, sign in and check existing projects, documents, PRs, and permissions. Do not run `docker compose down -v` or delete volumes. To roll back, restore the pre-upgrade databases, volumes, secrets, and application version together.

Knowledge shared editing uses Markdown. Unconfirmed offline edits exist only in the current browser tab's memory; wait for "Saved" before leaving or reloading. Git writes and merging require Gitea. Ordivant PR reviews do not create Gitea approvals.

This release does not include vector search, a built-in CI runner, a hard organization-wide spending limit, or distributed execution. SCIM does not support bulk or claim existing accounts by email. MFA policy relies on verified IdP claims. SMTP sends invitation and recovery mail; other collaboration notifications are viewed inside the platform. Verify your own IdP/SCIM directory, Git service, SMTP, models, and HTTPS before production use. Real CI and successful deployment results from GitHub/GitLab providers require validation in the actual environment.

## Optional enterprise integrations {#enterprise-setup}

Administrators configure SCIM, SMTP, and GitHub/GitLab deployment sources through the [container guide](./containers.md#enterprise-secret-mounts). `compose.enterprise.yaml` mounts separate Identity and Code secret directories as read-only. Keep this overlay when starting or upgrading an installation that uses it, for example:

```sh
docker compose -f compose.yaml -f compose.enterprise.yaml up -d --build --wait
docker compose -f compose.yaml -f compose.enterprise.yaml ps
```

Retain any additional Gitea, Runtime, or other configuration files as well. Regular accounts and human collaboration remain available without enterprise integrations.

See the [Changelog](https://github.com/ordivant-ai/ordivant/blob/main/CHANGELOG.md) for the complete version history and [Operations](./guide/operations.md) for backup and restoration.
