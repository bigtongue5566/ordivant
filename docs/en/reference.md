<span id="架構與-api-索引"></span>
<span id="架构与-api-索引"></span>

# Architecture and API reference

<span id="業務契約"></span>
<span id="业务契约"></span>

## Product boundaries and integration rules {#business-contracts}

Work, Knowledge, and Code can be deployed independently, with their own business APIs, MCP bridges, databases, and authorization scopes. Identity provides shared accounts and login; signing in does not automatically grant access to every product or project. Runtime executes Work dispatches, while the sandbox executor isolates commands. Each product's Python service remains responsible for business authorization.

| Service | Responsibility and boundary |
| --- | --- |
| Work | Projects, tasks, dependencies, leases, collaboration, review, and Runs; can reference existing enterprise VCS without Code |
| Knowledge | Spaces, documents, immutable versions, citations, and decisions; references never grant destination access |
| Code | Scoped repositories, branches, commits, PRs, and status receipts; Gitea stores the actual Git state |
| Identity | Accounts, invitations, sessions, product access, and OIDC SSO; uses a separate database |
| Runtime / sandbox | Execution transcripts / isolated commands; cannot replace Work task state or independent review |

APIs use UTF-8 JSON, string IDs, and UTC ISO-8601 timestamps. Domain errors have the shape `{"detail":{"code":"...","message":"..."}}`; field validation errors use FastAPI's format. Common HTTP statuses are `401` unauthenticated, `403` forbidden, `404` missing or inaccessible, `409` conflict, and `422` invalid input.

Agents use product-specific scoped Bearer tokens; people use Identity cookie sessions. Cookie mutations must pass origin and CSRF checks. Credentials determine the actor; callers cannot select another `actor` in the body. Deployments connected to Identity disable the legacy local-session login.

Use `Idempotency-Key` for retryable mutations, retaining the same key, route, and body on retry. The same actor's identical request replays its result; a changed body conflicts, and current authorization is rechecked. Lease operations need the current fencing token, while document publication and file updates must follow the API's version checks. The deployed OpenAPI schema defines the complete fields.

<span id="rest-文件"></span>
<span id="rest-文档"></span>

## REST documentation

After starting native development, each FastAPI service's `/docs` and `/openapi.json` describe the current requests, responses, and fields. These are the default addresses; operators can change the ports:

| Service | Development API address | Suite web proxy prefix |
| --- | --- | --- |
| Work | `http://127.0.0.1:8000/api` | `/api` |
| Knowledge | `http://127.0.0.1:8010/api` | `/knowledge-api` |
| Code | `http://127.0.0.1:8020/api` | `/code-api` |
| Identity | `http://127.0.0.1:8030/api/auth` | `/auth-api` |

The business endpoints below use native service paths. For example, Knowledge's `GET /api/spaces` is `GET /knowledge-api/spaces` through the suite web origin. In standalone product mode, `/api` points to the selected product. Production Nginx exposes business API prefixes; inspect schemas in a trusted development environment rather than exposing internal services for this purpose.

### Work tasks and execution {#work-api}

| Endpoint | Purpose |
| --- | --- |
| `GET/POST /api/projects`, `GET/POST /api/tasks` | List and create authorized projects / tasks |
| `GET /api/tasks/{task_id}/context` | Retrieve task, dependency, message, and evidence context |
| `GET /api/projects/{project_id}/participants` | List people and Agents authorized for assignment in the project |
| `POST /api/tasks/{task_id}/claim` | A person claims as their own identity; an Agent claims with its bearer token and receives a lease |
| `POST /api/tasks/{task_id}/renew` | Renew an Agent lease; human work has no lease |
| `POST /api/tasks/{task_id}/progress`, `release` | Report progress or release execution; people do not send lease tokens |
| `POST /api/tasks/{task_id}/submit`, `review` | Submit evidence and obtain a decision from an authorized independent reviewer |
| `POST /api/tasks/{task_id}/dispatch` | Dispatch an Agent; track the resulting Run for execution status |
| `GET /api/runs`, `GET /api/runs/{run_id}/events`, `POST /api/runs/{run_id}/control` | Run lists, events, and controls |
| `/api/agent-templates`, `/api/workflows`, `/api/workflow-runs` | Agent templates, workflow definitions, and workflow instances |
| `/api/tool-connections`, `/api/sandbox-profiles` | Manage permitted tool connections and sandbox settings |

A task and a Run are separate records. Successful execution does not complete a task automatically: evidence and independent review are required. See the [execution guide](./execution-usage.md) for modes, pause / stop limits, and tools. `/api/runtime/*` is a restricted service interface for trusted runtime integration.

A human claim records the human executor without an Agent lease; reloading can resume the active work. Agent claims use an expiry and fencing token. See [human and Agent collaboration contracts](./collaboration-contracts.md) for assignment and handoff rules.

### Knowledge documents and versions {#knowledge-api}

| Endpoint | Purpose |
| --- | --- |
| `GET/POST /api/spaces` | Knowledge spaces |
| `GET /api/documents?space_id=&q=&tag=`, `POST /api/documents` | Search and create documents |
| `GET /api/documents/{document_id}/versions` | Version history |
| `GET /api/documents/{document_id}/versions/{version_number}` | Read an exact citable version |
| `POST /api/documents/{document_id}/versions` | Legacy publication entry; the web editor directs users to the shared draft |
| `GET /api/documents/{document_id}/draft`, `POST /api/documents/{document_id}/draft/updates` | Read the shared draft and submit CRDT updates |
| `WS /api/documents/{document_id}/collaborate` | Sync the draft and authenticated human presence |
| `POST /api/documents/{document_id}/draft/publish` | Publish the saved shared draft as an immutable version |
| `GET/POST /api/decisions`, `GET /api/events` | Decisions and authorized audit records |

Published versions are immutable. Publish only while the editor is live, all updates are saved, and none are pending. Unacknowledged offline edits remain in the current browser's memory and may be lost if the page is closed. Agents can use REST/MCP to access the same shared draft. References preserve the exact version and URI without broadening access. See the [Knowledge guide](./guide/knowledge.md).

### Code and version control {#code-api}

| Endpoint | Purpose |
| --- | --- |
| `GET/POST /api/projects`, `GET/POST /api/repositories` | Projects and bound repositories |
| `POST /api/repositories/{repository_id}/branches`, `files` | Create branches and commit files |
| `GET/POST /api/repositories/{repository_id}/pulls` | List and open PRs |
| `GET /api/repositories/{repository_id}/pulls/{number}` | PR details, provenance, and status receipts |
| `GET /api/repositories/{repository_id}/pulls/{number}/collaboration` | Ordivant discussion, review records, and current PR head |
| `POST /api/repositories/{repository_id}/pulls/{number}/comments` | Add an Ordivant-local PR discussion |
| `POST /api/repositories/{repository_id}/pulls/{number}/reviews` | Record an Ordivant review against the expected head SHA |
| `POST /api/repositories/{repository_id}/checks` | Report a commit status explicitly labeled as Agent-reported |

Git operations in Code require configured Gitea. Ordivant discussions and reviews are local records tied to a PR head SHA; they are not Gitea approvals or CI results. Gitea remains responsible for Git, merging, and its own approvals. This release has no PR merge or delete API and includes no CI runner. An `agent_reported` receipt is not evidence that CI actually ran. See the [Code guide](./guide/code.md) and [human and Agent collaboration contracts](./collaboration-contracts.md).

### Model settings {#model-settings}

`GET/PUT /api/model-settings` is restricted to organization administrators. `GET /api/model-catalog` lists model choices for authorized callers; neither returns API keys. Settings contain `providers`, an organization `default`, and `revision`. Updates to existing settings must submit the previously read `revision` to prevent overwriting another change.

An Agent's `model_config` overrides the default; `null` inherits organization settings. A selection includes `provider_id`, `model_id`, `reasoning_effort`, and `max_output_tokens`. Dispatch records a snapshot without secrets. Model failures do not switch to DEMO. Model limits are administrator-provided metadata; unknown usage or cost is never fabricated. See the [model guide](./model-usage.md).

### Identity and SSO {#identity-api}

Identity's native prefix is `/api/auth`; the suite web prefix is `/auth-api`. `status` / `setup` initialize the first administrator, `login` / `me` / `logout` / `sessions` manage sessions, and `invitations` / `users` manage members. Administrators configure product access, which each product checks on every request.

Administrators use `sso/settings` and `sso/test` for OIDC configuration; `oidc/start` and `oidc/callback` complete sign-in. The platform directly supports OIDC. SAML or LDAP / AD can use the optional Keycloak broker; there is no native SAML endpoint. Identity provides SCIM 2.0 Users/Groups at `/api/scim/v2`, without bulk operations or automatic account claims by email. Each customer IdP tenant still needs validation. See [enterprise SSO](./enterprise-sso.md), the [administration guide](./guide/administration.md), and the [account guide](./human-login.md) for configuration and limits.

## MCP

The Work, Knowledge, and Code MCP stdio bridges call their respective REST APIs with their own scoped Agent tokens. A mutation's `request_id` maps to `Idempotency-Key`; callers cannot forge the actor in a request body. For startup examples, see the [contribution guide](../../CONTRIBUTING.md). Depending on the product, use `ordivant.mcp_server`, `ordivant_knowledge.mcp_server`, or `ordivant_code.mcp_server`.

Runtime connections to external tools use MCP Streamable HTTP. See the [external tools guide](./execution-usage.md#external-mcp-tools).

<span id="原始碼與開發"></span>
<span id="源代码与开发"></span>

## Source and development

[GitHub source](https://github.com/ordivant-ai/ordivant) and the [contribution guide](../../CONTRIBUTING.md) provide development and test entry points. The website publishes operating and integration guides; PM ledgers, development contracts, and validation records remain in the repository for maintainers. Deployment data, credentials, and private test output must never be committed to the public repository.
