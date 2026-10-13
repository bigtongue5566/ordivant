<span id="v0-1-0-公開版本"></span>
<span id="v0-1-0-公开版本"></span>
<span id="public-release-v0-1-0"></span>

# Ordivant v0.2.0 release {#public-release-v0-2-0}

Release date: 2026-10-14. License: [MIT](../../LICENSE). Source code and downloads: [GitHub Releases](https://github.com/ordivant-ai/ordivant/releases).

## What's included {#included-in-this-release}
<span id="本版內容"></span>
<span id="本版内容"></span>

- **Work**: Managers can assign tasks to authorized coworkers or Agents. Coworkers can claim eligible work, report progress, hand it off, and submit results for an independent review by another authorized person. Human execution remains in Work history and can be resumed after reloading.
- **Knowledge**: Multiple people can edit the same Markdown draft together in real time. Agents can update that draft through REST/MCP. After a disconnect, reconnect to merge unconfirmed edits; offline changes remain only in the current browser tab's memory. Wait until the draft is connected and saved before leaving or publishing. Publication creates an immutable version and preserves history.
- **Code**: People and Agents can discuss PRs, comment, and submit review records in Ordivant. Each record is tied to the PR head SHA, and old reviews are marked expired when the head changes. Gitea handles Git writes and merges; Ordivant records do not create Gitea approvals or represent upstream CI results.
- Routine human work in Work, Knowledge, and Code needs no LLM. Only autonomous Agent Runs require model settings. Code Git operations still require Gitea.
- Documentation is available in Traditional Chinese, Simplified Chinese, and English, including the feature guide, team setup, and full first-project tutorial.

## Upgrade and limitations {#upgrade-and-limitations}
<span id="升級與限制"></span>
<span id="升级与限制"></span>

Before upgrading from v0.1.0, stop the services and back up the Compose project's databases, all persistent data volumes, service secrets, and any custom `.env` file as described in the [operations guide](./guide/operations.md). Keep encryption keys with their corresponding databases and volumes. Secrets are stored in `.data/container-secrets/` by default; if `ORDIVANT_SECRETS_DIR` is set, back up that location instead.

Update the existing repository to v0.2.0. Keep the original Compose project name, `.env`, secrets directory, Compose file combination, and profiles. From the repository root, start the updated services:

```sh
docker compose up -d --build --wait
docker compose ps
```

If the deployment uses custom profiles or multiple Compose files, include the same options. Once services are healthy, sign in and check the workspace. Do not run `docker compose down -v` or manually remove data volumes; upgrades must preserve existing data. When Knowledge disconnects, unconfirmed edits remain only in the current tab's memory. Wait for Saved before leaving or reloading.

This release does not provide vector search, built-in CI, SCIM, hard dollar budgets, or distributed execution. Knowledge search is text-based. Ordivant Code PR reviews are not Gitea approvals or CI results. Validate your own identity provider, Git service, model provider, and HTTPS settings before enterprise use.

See the [changelog](https://github.com/ordivant-ai/ordivant/blob/main/CHANGELOG.md) for release history and the [operations guide](./guide/operations.md) for backup and restore instructions.
