# Self-host Ordivant {#container-workflow}

<span id="development"></span>

Install Ordivant on your own computer or server with Docker Compose. These commands work on Linux, macOS, and Windows with Docker Desktop. PowerShell 7, host Python, and host Node.js are not required. Members joining an existing team can go straight to [getting started](guide/getting-started.md).

## Before installation {#deployment-prerequisites}

Install Git, Docker Engine or Docker Desktop, and Docker Compose v2. Use Linux containers in Docker Desktop. Check that `docker compose version` works. The first build needs internet access to download images and dependencies.

The default deployment name is `ordivant`, with a web address of `http://127.0.0.1:8088`. To use another name or port, create `.env` in the repository root; `.env.compose.example` is a template. Choose the deployment name and secrets directory before first installation, and keep using the same settings.

## Install and start {#production-targets}

Choose the features you need today. You can enable automatic execution and code services after the basic installation:

| Work you want to do | Services needed | What to do after installation |
| --- | --- | --- |
| Coordinate manual tasks, submit results, and review | Basic installation below | Set up your team and first project |
| Let agents execute using a model | Basic installation plus Runtime | Configure your own model connection and Pi Agent |
| Preserve specifications, document versions, and decisions | Knowledge is included in the basic installation | Create a Space, publish documents, and cite versions |
| Create code branches, commits, and PRs | Basic installation plus Gitea | Create a Code project and repository |
| Let an Agent execute restricted commands | Runtime plus sandbox service | Create a sandbox profile and assign it to an Agent |

Run these commands in order in your terminal:

```sh
git clone https://github.com/ordivant-ai/ordivant.git
cd ordivant
docker compose -f compose.init.yaml run --rm init
docker compose up -d --build --wait
```

The first Compose job prepares service settings without creating human accounts or sample tasks. The second command builds and starts Work, Knowledge, Code, and shared login. The first build takes some time; `--wait` waits for healthy services.

Open `http://127.0.0.1:8088/work`, create the initial administrator, and save the recovery codes. There is no default human password. The three products share login within this deployment, while their projects and permissions remain separate. Code repository operations also need the Gitea setup below.

### Confirm you can start using the platform {#verify-installation}

Run `docker compose ps` and confirm the services are running and healthy. The browser should show sign-in or initial administrator setup. If installation fails or the page does not open, inspect `docker compose logs --tail 100 web identity-api work-api`. Check that Docker is running, port 8088 is available, and you are using the same deployment settings. See [troubleshooting](guide/troubleshooting.md) for other cases.

![Sign-in entry for a new installation, with administrator setup and team invitations](/screenshots/login-en.png)

### Complete your first deliverable after installation {#after-installation}

1. Sign in as the initial administrator and create a Work project, such as `LAUNCH` / Product launch preparation.
2. Invite another member and grant the appropriate project role. A submitter cannot review their own result.
3. Choose execution: manual claims and submissions can start without an external model; automatic execution requires the Runtime and model setup below.
4. Create a task with a goal, inputs, and acceptance criteria. Submit the actual deliverable and its sources, then have a different authorized member review it.

The [full first-project tutorial](guide/first-project.md) supplies field examples, Agent creation, manual and automatic routes, and review steps. [Team setup](guide/team-setup.md) explains invitations and resource grants across all three products.

### Enable automatic Agent execution {#enable-agent-execution}

To let Pi agents execute tasks, also run:

```sh
docker compose exec work-api python -m ordivant.bootstrap_runtime
docker compose --profile runtime up -d --build --wait runtime
```

Initialization creates only the execution service's machine identity: no DEMO project, Agent, or human account. Repeating it preserves valid configuration. It also works on an installation with existing work data. In Work, configure a provider and model under **Model connections**, then create a Pi worker in **Agent directory**. Select the Agent in a task's details and choose **Dispatch to agent**. See [model settings](model-usage.md) and [getting started](guide/getting-started.md).

An unconfigured Run is labeled DEMO and does not call a paid model. Skip the execution service if you only need manual tracking, submissions, and review. Add `COMPOSE_PROFILES=runtime` to `.env` to include it on subsequent ordinary starts.

## Install only the products you need {#individual-products}

For a new deployment, select the product in `.env`, run initialization, and use the corresponding start command. Use a separate deployment name and secrets directory to keep it isolated from another installation. Concurrent installations also need different `ORDIVANT_WEB_PORT` values.

| Product | Product settings in `.env` | Start command |
| --- | --- | --- |
| Work | `ORDIVANT_PRODUCT_MODE=work`, `ORDIVANT_WEB_API_UPSTREAM=http://work-api:8000` | `docker compose up -d --build --wait work-api web` |
| Knowledge | `ORDIVANT_PRODUCT_MODE=knowledge`, `ORDIVANT_WEB_API_UPSTREAM=http://knowledge-api:8010` | `docker compose up -d --build --wait knowledge-api web` |
| Code | `ORDIVANT_PRODUCT_MODE=code`, `ORDIVANT_WEB_API_UPSTREAM=http://code-api:8020` | `docker compose up -d --build --wait code-api web` |

Required login and database services start alongside the selected product. Work and Knowledge do not need Code or Gitea. Code needs Gitea for repository changes.

## Enable optional features {#optional-services}

### Code and Gitea {#enable-gitea}

Run in the same deployment:

```sh
docker compose --profile gitea up -d --wait gitea
docker compose -f compose.yaml -f compose.gitea-init.yaml --profile gitea run --build --rm gitea-init
docker compose up -d --no-deps --force-recreate --wait code-api
```

The initialization job configures Code's service connection without creating a default human login password. Return to Code to create projects, repositories, and PRs. Gitea's default address is `http://127.0.0.1:3002`. Keep `gitea` in `.env`'s `COMPOSE_PROFILES`, for example `runtime,gitea`, to include it on subsequent starts.

### Execution sandbox {#enable-sandbox}

Initialize the execution service first, then build the sandbox job image and start it:

```sh
docker compose -f compose.yaml -f compose.sandbox.yaml --profile sandbox build sandbox-job-image
docker compose -f compose.yaml -f compose.sandbox.yaml --profile runtime --profile sandbox up -d --build --wait runtime
```

If Gitea is enabled, add `--profile gitea` to the second command. Save the enabled configuration in `.env` so subsequent operations can use ordinary Compose commands:

```dotenv
COMPOSE_PATH_SEPARATOR=,
COMPOSE_FILE=compose.yaml,compose.sandbox.yaml
COMPOSE_PROFILES=runtime,gitea,sandbox
```

Remove `gitea` if it is not enabled. Sandboxes have no network access or host data mounts. Submit files you need to preserve before a Run ends. [Sandbox operations](execution-usage.md#sandboxes)

### Enterprise login and external tools {#enterprise-and-tools}

Connect your company's OIDC provider directly without an extra container. SAML and LDAP can use optional Keycloak; follow the [enterprise SSO guide](enterprise-sso.md#saml-ldap-and-active-directory). Add custom Compose files to the existing `COMPOSE_FILE` list without replacing an enabled sandbox configuration.

For external MCP tools, add exact hostnames to `.env`'s `ORDIVANT_TOOL_ALLOWED_HOSTS`, then restart Work and the execution service. Do not put model keys or human passwords in `.env`; enter model keys in the administration interface. [Tool connections](execution-usage.md#external-mcp-tools)

### Enterprise secret files and deployment providers {#enterprise-secret-mounts}

Enterprise integrations can use the optional read-only Compose overlay. By default, create `.data/enterprise-secrets/identity/` and `.data/enterprise-secrets/code/` in the repository root. If using another location, set `ORDIVANT_ENTERPRISE_SECRETS_DIR` in `.env` first. Put the SCIM token and SMTP password file in `identity/`; put Code's `deployment-providers.json` and its `token_file` files in `code/`. The directories are mounted read-only at `/run/ordivant-enterprise` in their respective Identity and Code containers, so neither service can read the other's files.

`.env.compose.example` lists the path settings. Common paths are `ORDIVANT_SCIM_TOKEN_FILE=/run/ordivant-enterprise/scim-token`, `ORDIVANT_SMTP_PASSWORD_FILE=/run/ordivant-enterprise/smtp-credential`, and `ORDIVANT_CODE_DEPLOYMENT_CONFIG_FILE=/run/ordivant-enterprise/deployment-providers.json`. These settings point to files inside the containers; store credential values only in server-side files, never in `.env`.

After preparing the files and `.env` paths, build and start with the same Compose overlay:

```sh
docker compose -f compose.yaml -f compose.enterprise.yaml up -d --build
```

Include both `-f` files in later starts, updates, and rebuilds to preserve the read-only mounts.

## Status, stopping, and backups {#actions-and-data}

Use the same repository directory, `.env`, and Compose configuration as installation:

```sh
docker compose -f compose.yaml -f compose.enterprise.yaml ps
docker compose -f compose.yaml -f compose.enterprise.yaml logs --tail 100 work-api identity-api
docker compose -f compose.yaml -f compose.enterprise.yaml down
docker compose -f compose.yaml -f compose.enterprise.yaml up -d --wait
```

Use the commands above only when the enterprise overlay is enabled; regular deployments should follow the [basic container operations](guide/operations.md). With the overlay, include the same `-f compose.yaml -f compose.enterprise.yaml` on every start, stop, update, and rebuild. `down` preserves volumes. Do not add `-v`, which deletes data. Back up product databases, data volumes, `.data/container-secrets/` (or its configured path), and `.data/enterprise-secrets/` (or the path in `ORDIVANT_ENTERPRISE_SECRETS_DIR`). Preserve the Identity and Code configuration and token files in the enterprise secrets directory together with model and SSO encryption keys. [Backup and restore](guide/operations.md)

Only in a fresh trial installation with no real accounts or business data, you may add DEMO examples before initializing execution or signing in for the first time:

```sh
docker compose exec work-api python -m ordivant.seed
docker compose exec knowledge-api python -m ordivant_knowledge.seed
docker compose exec code-api python -m ordivant_code.seed
```

Examples create sample projects and agents, without human passwords or model connections. A normal production installation does not need these commands; do not add examples to an existing installation.

## Provide team access through HTTPS {#https-access}

The web service binds to local `127.0.0.1:8088` by default. For remote team access, configure an HTTPS reverse proxy on the server to forward to this local address, then use your actual public address in `.env`:

```dotenv
ORDIVANT_AUTH_ORIGINS=https://ordivant.example.com
ORDIVANT_AUTH_COOKIE_SECURE=true
ORDIVANT_SSO_PUBLIC_ORIGIN=https://ordivant.example.com
```

Run `docker compose up -d --wait` to apply the settings. A proxy in another container must join the same Compose network and forward to `web:80`; host loopback is not that container's loopback. For enterprise login, also verify the identity provider's Callback URL. [Enterprise login settings](enterprise-sso.md)
