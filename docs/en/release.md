<span id="v0-1-0-公開版本"></span>
<span id="v0-1-0-公开版本"></span>
<span id="public-release-v0-1-0"></span>
<span id="public-release-v0-2-0"></span>
<span id="public-release-v0-3-0"></span>

# Ordivant v0.4.0 release {#public-release-v0-4-0}

Released: 2026-10-19. License: [MIT](../../LICENSE). Source and downloads: [GitHub Releases](https://github.com/ordivant-ai/ordivant/releases/tag/v0.4.0).

## Included in this release {#included-in-this-release}
<span id="本版內容"></span>
<span id="本版内容"></span>

- **Personal API and MCP access**: Create a product-scoped, expiring token under Account and security → API and MCP, copy connection examples for your environment, and revoke it at any time. Tokens act as the human owner using current roles and resource scopes; they grant no Agent identity or additional permissions. See the [connection guide](./guide/administration.md#personal-api-and-mcp-access).
- **Six built-in Agent templates**: PM, PG, SA, SD, QA, and Reviewer. Creating an Agent fills editable names, capabilities, and instructions. Templates are immutable versions per organization and do not overwrite existing Agents. See the [Work guide](./guide/work.md#built-in-agent-templates).
- **Companion products during project creation**: After creating a Work project, optionally create its Knowledge space and Code project. Retry failed products individually without duplicating successful results; authorization remains separate for each product.
- **Discover Provider models**: Fetch, search, and select models from an OpenAI-compatible `/models` endpoint. Context, output limits, and reasoning efforts are populated only when explicitly supplied by the upstream service; otherwise enter them manually. Discovery does not run model inference. See [Model settings](./model-usage.md).
- **Clearer execution settings**: Execution method, Run by the platform, and Run by an external program explain how an Agent operates. Fixes prevent incomplete model selections from crashing the screen and keep long model lists from stretching the navigation rail.
- **Open-source contribution guidance**: Updated AGENTS and contribution conventions describe repository paths, contracts, tests, and PR expectations for different developers and coding agents.
- New controls and operating guides support Traditional Chinese, Simplified Chinese, and English. Existing human tasks, shared document editing, and Code collaboration still need no LLM.

The full personal token is shown once. Each user may have up to 50 active tokens, expiring in 1 to 365 days. Password changes, account recovery, and account deactivation revoke existing tokens. Sign out of all devices revokes browser sessions only; revoke external-tool tokens separately. MCP currently uses a local stdio bridge requiring uv and the source checkout, not a remote Streamable HTTP MCP service. Connection examples use placeholders; configure the token securely in your own client.

## Upgrade and limitations {#upgrade-and-limitations}
<span id="升級與限制"></span>
<span id="升级与限制"></span>

Before upgrading from v0.3.0 or earlier, follow the [operations guide](./guide/operations.md) to stop services and back up the Compose project's databases, all persistent volumes, service secrets, and custom `.env`. Keep encryption keys with the matching databases and volumes. Secrets default to `.data/container-secrets/`; back up the location selected by `ORDIVANT_SECRETS_DIR` if customized. Also back up `ORDIVANT_ENTERPRISE_SECRETS_DIR` if enterprise secret mounts are enabled.

Update the existing repository to v0.4.0 while preserving the original Compose project name, `.env`, secrets directory, Compose file combination, and profiles. Services apply database schema updates at startup. From the repository root, run:

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
