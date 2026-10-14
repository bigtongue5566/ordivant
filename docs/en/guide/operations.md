<span id="維運與備份"></span>
<span id="运维与备份"></span>

# Operations and backups

This guide covers Docker Compose operations, backups, and Agent execution. Run Compose commands from the repository root. The default deployment name is `ordivant`, set by `compose.yaml`; no `.env` file is needed by default. To customize the name, create `.env` in the repository root, set `COMPOSE_PROJECT_NAME`, and keep it unchanged for that deployment. Service secrets are stored in `.data/container-secrets/` by default. If `ORDIVANT_SECRETS_DIR` is set, back up that actual path instead. When using the enterprise overlay, also back up `.data/enterprise-secrets/` or the path set in `ORDIVANT_ENTERPRISE_SECRETS_DIR`.

<span id="服務狀態與更新"></span>
<span id="服务状态与更新"></span>

## Service status and updates

```sh
docker compose ps
docker compose logs --tail 100
docker compose up -d --build --wait
docker compose down
```

The default site address is `http://127.0.0.1:8088`. These commands use the default deployment name, `ordivant`. Stopping services preserves volumes and secret files, but is not a backup. `docker compose down -v` deletes the volumes and their data.

The default web port is `8088`; Gitea uses `3002`. If a port is occupied, set `ORDIVANT_WEB_PORT` or `ORDIVANT_GITEA_PORT` in the repository-root `.env`. If the installation uses Runtime, Gitea, or another profile, include the same `--profile` options with every command. If Sandbox is enabled, also use the same Compose file set, `-f compose.yaml -f compose.sandbox.yaml`, for every command. Configure HTTPS, the public site origin, and secure cookies before allowing remote team access. See the [container deployment guide](../containers.md).

When using `compose.enterprise.yaml`, include the same `-f compose.yaml -f compose.enterprise.yaml` with every Compose command, including starts, stops, updates, and backup operations. This preserves the read-only Identity/Code mounts and consistent service configuration.

<span id="需要備份的資料"></span>
<span id="需要备份的数据"></span>

## Data to back up

For backups, use the Compose project label to find every volume for the environment. Preserve each product's database and data volume as a set. A typical full set includes:

| Area | Compose volumes / host files | Contents |
|---|---|---|
| Identity | `identity_postgres`, `identity_data` | People, sessions, SSO settings, and `sso.key` |
| Work | `work_postgres`, `work_data` | Work tasks, Agents, Runs, Runtime state, and `model-settings.key` |
| Knowledge | `knowledge_postgres`, `knowledge_data` | Spaces, document versions, decisions, and scope data |
| Code | `code_postgres`, `code_data` | Code scopes, repository bindings, PRs, and status receipts |
| Gitea (if enabled) | `gitea_data` | Actual Git data for repositories, branches, commits, and PRs |
| Keycloak broker (if enabled) | `identity_broker_postgres` | Broker realm and connection settings |
| Compose secrets and settings | `.data/container-secrets/` or `ORDIVANT_SECRETS_DIR`; with the enterprise overlay, also `.data/enterprise-secrets/` or `ORDIVANT_ENTERPRISE_SECRETS_DIR`; custom deployments also use `.env` | Database passwords/URLs, Runtime and internal service tokens, Gitea settings, Identity/Code enterprise configuration and token files, Compose project name, and port settings |

The actual volume list depends on the enabled products and profiles. Work's `model-settings.key` decrypts model and MCP tool-connection settings; Identity's `sso.key` decrypts enterprise IdP settings. Back up encryption keys with their corresponding databases and data volumes. Do not replace a key by itself, or existing ciphertext cannot be decrypted. Agent execution state is in the Work data volume. A sandbox workspace is temporary and is not a place to store results.

Use the Compose project label to find the actual volume names created for this environment:

```sh
docker volume ls --filter "label=com.docker.compose.project=ordivant"
```

If you customized `COMPOSE_PROJECT_NAME`, use its value from `.env` in the filter. Include every listed product, Identity, and enabled-profile volume in the backup. Use the command output as the authoritative list; do not guess from the example names.

<span id="一致性與還原"></span>
<span id="一致性与还原"></span>

## Consistency and restoration

1. Confirm that the backup target is the correct Compose project name. Stop the environment with `docker compose down` so files and PostgreSQL volumes are consistent; this does not delete data.
2. Use your organization's approved Docker volume snapshot or backup tool to back up every required volume under that project label. Also preserve the default `.data/container-secrets/` directory, or the actual path in `ORDIVANT_SECRETS_DIR`. If using the enterprise overlay, preserve `.data/enterprise-secrets/` or the path in `ORDIVANT_ENTERPRISE_SECRETS_DIR`, including Identity/Code configuration and token files. Encrypt and preserve a custom `.env` file as well.
3. Encrypt backups and the host secrets directory, restrict access, and test restoration regularly. Do not upload `.data`, bootstrap tokens, or Gitea/service credentials to public issues, chats, or Git.
4. To restore, first recover the Compose volumes under their original names and the original secrets, then start the original products, profiles, and Compose file set with the same deployment name. Do not mix encryption keys and databases from different environments.

For a single-product or partial-product deployment, back up every volume created by that mode along with the shared Identity volumes. Knowledge citations and Code PR provenance do not replace backups of the referenced product data; preserve the source product and actual Gitea data as well.

<span id="執行與排程"></span>
<span id="运行与调度"></span>

## Execution and scheduling

For a first installation, complete Compose initialization and service startup in the [container deployment guide](../containers.md). For a normal production installation, next create the first human administrator in the browser. The administrator can then set the provider, API key, and model on the model management page. The configured model is called only when work is actually dispatched. Without a valid model, Runs are marked DEMO.

For a brand-new trial that needs DEMO examples, seed after Compose initialization and service startup but before the first sign-in and before the first `bootstrap_runtime`. This is only for a fresh environment with no real data. Run only the command for the product you want to try, then create the first human administrator in the browser. Never run Seed on an existing deployment:

```sh
docker compose exec work-api python -m ordivant.seed
docker compose exec knowledge-api python -m ordivant_knowledge.seed
docker compose exec code-api python -m ordivant_code.seed
```

To enable the Agent Runtime, confirm that Work API is healthy, then run:

```sh
docker compose exec work-api python -m ordivant.bootstrap_runtime
docker compose --profile runtime up -d --build --wait runtime
```

`bootstrap_runtime` initializes only the Runtime machine identity. It creates no DEMO data, people, or projects, and can run against an existing production deployment. If a valid `runtime_token` already exists, rerunning the command does not rotate it. If you use Sandbox, start Runtime with the same Compose files and profiles used by the installation:

```sh
docker compose -f compose.yaml -f compose.sandbox.yaml --profile runtime --profile sandbox up -d --build --wait runtime
```

Interval workflows require the Work Runtime to keep running. Schedules missed while it is stopped are not all backfilled; an active workflow prevents the same schedule from overlapping. Each sandbox workspace is bounded and cleaned up when its Run ends, so it must not be used for persistent file storage. Save Runs, artifacts, and Knowledge documents through their respective products. See the [execution guide](../execution-usage.md) for execution controls, allowed tool hosts, and sandbox limits.
