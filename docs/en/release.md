<span id="v0-1-0-公開版本"></span>
<span id="v0-1-0-公开版本"></span>
<span id="public-release-v0-1-0"></span>
<span id="public-release-v0-2-0"></span>
<span id="public-release-v0-3-0"></span>
<span id="public-release-v0-4-0"></span>

# Ordivant v0.5.0 release {#public-release-v0-5-0}

Released: 2026-10-19. License: [MIT](../../LICENSE). Source and downloads: [GitHub Releases](https://github.com/ordivant-ai/ordivant/releases/tag/v0.5.0).

## Included in this release {#included-in-this-release}
<span id="本版內容"></span>
<span id="本版内容"></span>

- **Project settings and scoped navigation**: the sidebar identifies the current project or space, with a breadcrumb for the current location. Work Project settings manages names, descriptions, tracking budgets, and member access. Conflicting edits require reloading instead of overwriting another editor. See the [Work guide](./guide/work.md#project-settings).
- **Separate personal and organization settings**: Account settings holds personal profile, security, and API/MCP access. Organization administration holds users, enterprise SSO, governance, and identity audit for administrators only.
- **Agent lifecycle**: re-enable disabled Agents, archive them while retaining history, or permanently delete unused Agents. The service blocks retirement while unfinished work or enabled automation references remain. Archiving revokes credentials and cannot be reversed.
- **Keep your place after refresh**: all three modules retain page and resource selections in the URL. Account actions use a compact menu, and settings use readable section navigation with support for small screens.
- **Authored translations in three languages**: removed OpenCC.js and automatic character conversion, manually reviewed Simplified Chinese, and added coverage and interpolation checks that never rewrite catalogs.

Work access can be granted per project, but each member has one Work role across all granted projects. Independent roles per project and a read-only Work role are not supported. Only system administrators can change human member access. Knowledge spaces and Code projects retain separate permissions; matching names do not share access.

The full personal token is shown once. Each user may have up to 50 active tokens, expiring in 1 to 365 days. Password changes, account recovery, and account deactivation revoke existing tokens. Sign out of all devices revokes browser sessions only; revoke external-tool tokens separately. MCP currently uses a local stdio bridge requiring uv and the source checkout, not a remote Streamable HTTP MCP service. Connection examples use placeholders; configure the token securely in your own client.

## Upgrade and limitations {#upgrade-and-limitations}
<span id="升級與限制"></span>
<span id="升级与限制"></span>

Before upgrading from v0.4.0 or earlier, follow the [operations guide](./guide/operations.md) to stop services and back up the Compose project's databases, all persistent volumes, service secrets, and custom `.env`. Keep encryption keys with the matching databases and volumes. Secrets default to `.data/container-secrets/`; back up the location selected by `ORDIVANT_SECRETS_DIR` if customized. Also back up `ORDIVANT_ENTERPRISE_SECRETS_DIR` if enterprise secret mounts are enabled.

Update the existing repository to v0.5.0 while preserving the original Compose project name, `.env`, secrets directory, Compose file combination, and profiles. Services apply database schema updates at startup. From the repository root, run:

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
