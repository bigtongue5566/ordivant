# Shared REST/runtime contract (v0.1)

The user-selected Run console, automatic workflows, immutable Agent templates, external MCP connections and isolated execution workspaces are defined in [execution contracts](execution-contracts.md). Human and Agent claims, shared Knowledge drafts, and Code PR collaboration are described in [human and Agent collaboration contracts](collaboration-contracts.md). Agent leases, independent review, and secret-handling rules remain in effect.

UTF-8 JSON, UTC ISO-8601 timestamps, ids are strings. List endpoints return arrays. Resource endpoints return the object directly. Validation errors use FastAPI shape; domain errors: `{ "detail": { "code": "...", "message": "..." } }`. HTTP 401 unauthenticated, 403 forbidden, 404 unknown/inaccessible, 409 conflict, 422 invalid input. Mutating agent requests support `Idempotency-Key`. The same key + route + actor + same body replays the first response; changed body conflicts.

## Auth

- `GET /api/health` -> `{status:"ok", database:"sqlite"|"postgresql", mode:"development"|"production"}`.
- Human login uses the independent Identity service's HttpOnly cookie plus Origin/CSRF checks; see [authentication contracts](auth-contracts.md). Both configured modes disable `POST /api/auth/local-session`.
- REST/MCP agents use `Authorization: Bearer <token>`. `principal`: `{id,name,kind:"human"|"agent"|"runtime",role:"admin"|"manager"|"worker"|"reviewer",organization_id,project_ids:string[]}`. Browser users do not enter agent tokens.
- `GET /api/me` -> principal. POST `/api/agents` returns agent object plus `token` one time. Demo bootstrap credentials may be in ignored `.data/bootstrap.json`; do not log token contents.

## Types

`Project`: `{id,key,name,description,organization_id,team_id,budget_usd,created_at}`.

`Agent`: `{id,principal_id,name,role:"worker"|"reviewer",team_id,capabilities:string[],project_ids:string[],status:"available"|"busy"|"offline"|"disabled",runtime:"external"|"pi",model:string|null,model_config:ModelSelection|null,effective_model_config:ModelSelection|null,created_at}`. `principal_id` is read-only and maps message/audit actor ids to the agent's display name; task assignments use `id`. [Model contracts](model-contracts.md) define organization connections, encrypted credentials, defaults and Agent overrides.

Credential issuance is a documented idempotency exception: repeating an agent-creation request returns the same agent with a fresh one-time token, so raw bearer tokens never enter the response cache. Ordinary mutations replay their original response. Idempotency routes include actual resource ids, not path templates, and replay rechecks current project access.

`Task`: `{id,key,project_id,title,description,goal,inputs,scope,constraints,acceptance_criteria:string[],priority:"urgent"|"high"|"medium"|"low",status,assignee_id:string|null,assignee_principal_id:string|null,reviewer_id:string|null,reviewer_principal_id:string|null,parent_task_id:string|null,dependency_ids:string[],labels:string[],blocked_reason:string|null,progress:number,handoff:string|null,budget_usd:number,created_at,updated_at,assignee:{id,principal_id,name,kind:"human"|"agent"}|null,reviewer:{id,principal_id,name,kind:"human"|"agent"}|null}`. Each assignment is either a human or Agent. Agents use `assignee_id` / `reviewer_id`; people use `assignee_principal_id` / `reviewer_principal_id`. `inputs`, `scope`, and `constraints` are text strings.

`Execution`: `{id,task_id,agent_id:string|null,claimed_by_principal_id:string|null,submitted_by_principal_id:string|null,executor_id,executor_kind:"human"|"agent",executor_name,status:"running"|"submitted"|"accepted"|"rejected"|"expired"|"released",lease_expires_at:string|null,started_at,finished_at:string|null,progress:number,summary:string|null,cost_usd:number,cost_source:"self_reported"|"measured"}`. Human executions have no Agent lease. An Agent's fencing `lease_token` appears only in claim/renew responses, never in normal listings.

`Artifact`: `{id,task_id,execution_id,kind:"document"|"url"|"test_report"|"file"|"summary",title,uri:string|null,content:string|null,created_at}`.

`Message`: `{id,project_id,task_id:string|null,sender_id,recipient_id:string|null,kind:"question"|"reply"|"help_request"|"decision"|"handoff",body,reply_to_id:string|null,status:"delivered"|"accepted"|"completed",created_at}`.

`AuditEvent`: `{id,project_id:string|null,actor_id,action,entity_type,entity_id,data:object,created_at}`. Secrets/fencing tokens must never occur in audit data.

`TaskContext`: `{task,executions:Execution[],artifacts:Artifact[],messages:Message[],events:AuditEvent[],dependencies:Task[]}`.

## REST

- `GET/POST /api/projects`; create `{key,name,description?,team_id?,budget_usd?}`.
- `GET /api/projects/{id}`; `GET /api/projects/{id}/context` -> `{project,tasks,agents,decisions}`.
- `GET /api/projects/{id}/participants` -> people and Agents authorized for project assignment.
- `GET /api/projects/{id}/vcs/pulls/{provider}/{number}?repository=owner/repo` -> `{provider,repository,number,title,state,web_url,head_sha,head,base,checks,checks_available,source:"provider_api"}`. Work reads configured existing GitHub/GitLab/Gitea directly; Code is not required. First enforce project scope, then server-side repository allowlist. No upstream credentials returned. Missing configuration is 503; unavailable checks are explicit, never a passing result. This read cannot accept a task or merge a PR.
- `GET /api/tasks?project_id=&status=&q=&ready_only=true`; `POST /api/tasks` takes all editable task fields above; defaults ready/medium. Actor scope enforced.
- `GET /api/tasks/{id}`; `PATCH /api/tasks/{id}` editable spec/dependencies/assignment/budget fields; lifecycle states only via guarded operations, except manager cancellation or backlog->ready. Agents cannot patch executing fields without lease.
- `GET /api/tasks/{id}/context`; `GET /api/tasks/{id}/executions`.
- `POST /api/tasks/{id}/claim` body `{lease_seconds?:300,agent_id?:string}`. A person uses an authenticated cookie with no `agent_id` and can claim a ready task that is unassigned or assigned to them. Only a manager/administrator may explicitly include an authorized `agent_id` to claim on its behalf; an Agent is otherwise identified by its bearer token. Human executions have null Agent and lease fields and can resume after reload. Runtime identities must never impersonate an arbitrary user.
- `POST /api/tasks/{id}/renew` renews an Agent lease only; body `{execution_id,lease_token,lease_seconds?:300}`.
- `POST /api/tasks/{id}/progress` body `{execution_id,lease_token?,progress,summary?,cost_usd?}` -> task. Agents send the current fencing token; for a person, Python verifies the authenticated actor still owns the execution and has project access.
- `POST /api/tasks/{id}/block` body `{execution_id,lease_token?,reason,handoff?}` -> task; closes execution and releases the lease. A person does not send a lease token.
- `POST /api/tasks/{id}/release` body `{execution_id,lease_token?,handoff}` -> task ready, execution released. A person can hand off and release work. Manager can `POST /api/tasks/{id}/unblock` `{}`.
- `POST /api/tasks/{id}/submit` body `{execution_id,lease_token?,summary,artifacts:[{kind,title,uri?,content?}],cost_usd?:0}` -> TaskContext. Requires at least one evidence artifact. Sets in_review; a person does not send a lease token.
- `POST /api/tasks/{id}/review` body `{decision:"accept"|"reject",comment}` -> TaskContext. Reviewer/manager/admin only; cannot be submitting actor, obey designated reviewer if set, rejecting sets ready and preserves history/evidence.
- `POST /api/tasks/{id}/delegate` body `{agent_id,title,goal,description?,inputs?,scope?,constraints?,acceptance_criteria:string[],priority?,budget_usd?:0}` -> child Task; actor must be scoped manager or active owner of parent; child assigned to agent; delegation cannot grant access. Limit nesting depth to 3.
- `GET/POST /api/agents`; create `{name,role,team_id?,capabilities,project_ids,runtime?,model?,model_config?}`. `PATCH /api/agents/{id}` admin/manager may disable, edit capability/model. An explicit null `model_config` clears an override and restores inheritance.
- `GET /api/messages?project_id=&task_id=&inbox=true` inbox recipient is current actor; manager can inspect authorized project thread. `POST /api/messages` body `{project_id,task_id?,recipient_id?,kind,body,reply_to_id?}` -> Message. Recipient and sender must share authorized project. Reply validated in same task/project and auto completes parent question.
- `POST /api/messages/{id}/ack` body `{status:"accepted"|"completed"}` recipient only (manager can act with audit).
- `GET /api/events?project_id=&task_id=` -> newest-first audit array, max 200.
- `GET /api/overview?project_id=` -> `{counts:{total,ready,in_progress,blocked,in_review,done},agents:{total,available,busy},cost_usd,budget_usd,activity:AuditEvent[]}`.

## Outbox/runtime

POST `/api/tasks/{id}/dispatch` body `{agent_id}` manager/admin or active parent owner -> `{id,project_id,task_id,agent_id,type:"run_task",payload:object,status:"pending",created_at}`. Agent must be pi runtime, authorized for project, task ready, dependencies done. Unique outstanding dispatch per task.

Runtime credential is distinct from agent credentials. `POST /api/runtime/outbox/claim` `{worker_id,limit?:5}` -> outbox array (fields also include `delivery_token`, `attempts`; exclusive timed ownership). `POST /api/runtime/outbox/{id}/ack` `{worker_id,delivery_token,status:"delivered"|"failed",error?:string}`. Delivery tokens fence stale acknowledgements. Claim only runtime/admin, ack only owner. A runtime scopes all outbound platform tools using per-agent credentials, NOT runtime privileges.

Runtime local HTTP API on 8090: `GET /health` -> engine/mode and availability; `POST /runs` body `{request_id,task_id,agent_id,prompt,model?}` -> `{request_id,conversation_id,submission_id,status}`; `GET /runs/{request_id}` -> persisted status/answer; `POST /runs/{request_id}/resume`; `POST /runs/{request_id}/abort`. Bind loopback, require configurable `ORDIVANT_RUNTIME_TOKEN` outside development.

Runtime dispatcher polls Python outbox and uses id=event id as Pi requestId. A fenced, uncached server handoff provides the assigned Agent credential and the configured Provider key in memory. It supports newly created Agents, renews both delivery and execution leases and revokes the delivery credential on acknowledgement. Configured dispatches use live Responses calls; unconfigured dispatches use the documented demo fallback. No model failure fallback is permitted. `demo` uses a deterministic provider with the actual Pi Harness/storage. Selection snapshots, receipt and secret handling are defined in [model contracts](model-contracts.md).

## MCP

Official Python SDK FastMCP stdio process: `uv run --project backend python -m ordivant.mcp_server`; env `ORDIVANT_API_URL=http://127.0.0.1:8000`, `ORDIVANT_API_TOKEN=<scoped agent token>`. Thin async httpx bridge to REST ensures shared authorization/idempotency/lease checks. Tools: `get_project_context`, `create_task`, `update_task`, `find_ready_tasks`, `claim_task`, `renew_lease`, `report_progress`, `get_task_context`, `block_task`, `release_task`, `submit_result`, `review_result`, `find_agents`, `request_help`, `send_message`, `read_inbox`, `delegate_task`. Expose context resources and task/review prompts. Mutation tools accept an optional `request_id`, passed as Idempotency-Key. No caller-controlled actor identity.

Also expose `get_vcs_pull_request(project_id,provider,repository,number)`. Work-only `ORDIVANT_VCS_CONFIG` points at ignored JSON: `{ "projects": { "WORK_PROJECT_ID": { "github": { "api_url": "https://api.github.com", "token": "OPTIONAL_PROVIDER_TOKEN", "repositories": ["owner/repository"] } } } }`. GitLab uses its `/api/v4` API base, Gitea `/api/v1`. Private enterprise instances use a configured HTTPS base and least-privilege read token. HTTP defaults to loopback only; operators can explicitly list trusted private service hosts in `ORDIVANT_VCS_HTTP_HOSTS`. Compose permits exactly `gitea` for the isolated local container network. Request bodies cannot provide an API URL or alter this policy. Configuration is per project and exact repository; possession of a global service token never grants all Work actors access to every repository.

## Local seed

Explicit `uv run --project backend python -m ordivant.seed` creates one demonstration org, engineering+operations teams, manager human, worker agents `planner`, `builder`, `analyst`, and reviewer `reviewer`; scoped second project proves isolation. Main project key ORD. Seed includes a small realistic project with tasks spanning ready/in_progress/blocked/in_review/done, dependency, messages and evidence. Repeat seeding is idempotent. `.data/bootstrap.json` -> `{manager_token,runtime_token,agents:{planner:{id,token},builder:{id,token},analyst:{id,token},reviewer:{id,token}},project_id,isolated_project_id}`; .data path anchored to repository root. These are generated development credentials, never shipped tracked or printed.
