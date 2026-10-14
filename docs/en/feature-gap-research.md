<span id="ordivant-功能缺口研究"></span>

# Ordivant Feature-Gap Research

Updated: 2026-10-08 (Asia/Taipei). The PM and three luna workers reviewed the code, contracts, and acceptance records on 2026-10-07, using official protocol and product documentation as references. The user selected **F03 Run console, F04 workflows and Agent templates, and F05 tool connections and sandboxes**; implementation and local integration acceptance are complete. This page distinguishes the first-release capabilities from work that remains.

This page's gap list and F11 SCIM candidate are a historical snapshot from 2026-10-08. SCIM implementation was added on 2026-10-15; current customer-tenant acceptance status is in the [project plan](project-plan.md#p0-p1-acceptance-ledger).

See [execution features](execution-usage.md) and [acceptance](execution-validation.md) for this release's behavior and evidence. The next priority candidates are **pre-execution approvals, total-token and cost governance, notifications, and real CI integration**. Enterprise document import, existing VCS integration, SCIM, and other requirements remain on the roadmap.

Priorities assume a private deployment used by one enterprise team. If one service is to host multiple customers, tenant isolation and per-tenant Identity/IdP configuration must move earlier.

<span id="現有能力與判讀方式"></span>
<span id="现有能力与判读方式"></span>

## Existing capabilities and status definitions

"Partial" means the related foundation exists and the candidate fills a gap. "Not implemented" means there is no complete corresponding service/API/UI. "Not verified" means configuration or operating instructions exist, but there is no end-to-end delivery evidence for that capability.

Existing capabilities include shared Identity, native accounts and OIDC, a Keycloak SAML broker, invitations/JIT, project/Space authorization, group synchronization at sign-in, and session revocation; Work task/execution separation, dependencies, atomic claims, lease fencing, delegation, help requests, messages, idempotency, outbox, and independent result acceptance; immutable Knowledge versions, text search, and precise citations; and real Gitea repository/branch/commit/PR/status operations in Code. This release does not rebuild those capabilities.

<span id="優先候選"></span>
<span id="优先候选"></span>

## Priority candidates

P0 covers core operational capabilities for the next iteration; P1 covers enterprise onboarding and day-to-day use; P2 covers expansion driven by usage, integrations, or procurement requirements. These are PM priorities and do not include effort estimates.

| ID | Priority | Candidate | Available today | Gap and common use |
|---|---|---|---|---|
| F01 | P0 | Pre-execution approvals and tool policies | Task-result review and role/resource authorization | Create a durable approval request before sensitive operations and resume according to policy after approval, rejection, or expiry. Deployment, PR merges, external messages, and data changes can each have separate rules. See [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) for durable pause and resume patterns. |
| F02 | P0 | Execution and cost limits | Per-request output-token ceiling, actual token receipts, per-Run turn/global time limits, and sandbox resource limits | Total-token/concurrency quotas, pre-request budget reservation, versioned pricing, and atomic settlement remain to be built. USD/cache rates and invoice reconciliation require separate configuration. See [LiteLLM virtual keys](https://docs.litellm.ai/docs/proxy/virtual_keys) for per-key/team budgets and rate limits. |
| F03 | This release | Run console | Project Run list/detail, durable events/errors/model usage, queued stop, tool-boundary pause/resume, source-linked retry, restart/submission idempotency, and independent review | Future additions could include continuing a run with arbitrary human input, dead-letter handling, and cross-Run statistics. Active external calls may finish; Run `done` still does not mean the task passed independent acceptance. |
| F04 | This release | Automated collaboration and reusable workflows | Immutable DAG versions, manual/minute-interval triggers, Agent selection by capability, automatic dispatch, review dependencies and cancellation; Agent templates can be applied during creation/editing | Conditional branches, webhook/Cron triggers, cross-system events, and open-ended collaboration wakeups remain to be built. Existing workflows do not fabricate CI or independent-review results. |
| F05 | This release | Agent tool connections and isolated workspaces | Project-scoped MCP Streamable HTTP/Bearer, `tools/list` and allowlists, encrypted keys; per-Run networkless Docker workspace, file/command tools, resource limits, and cleanup | Interactive OAuth, host stdio launchers, authorized repository checkout, controlled networking/package installation, and VM executors remain to be built. The fixed job image includes Python/Node/Git. |
| F06 | P1 | Notifications, mentions, due dates, and SLAs | Collaboration messages with specified recipients and an inbox | Notifications for pending review, blocked or failed work, and overdue items; notification center/live updates, Email/Teams/Slack, subscriptions, and deduplication. Due dates/SLAs are prerequisites for overdue alerts and escalation. Teams can be connected through [Workflows webhooks/Adaptive Cards](https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-incoming-webhook?tabs=dotnet). |
| F07 | P1 | Document and task-attachment import | Markdown bodies and versions; URI/text references on results | Upload PDF/Word/files, extract text and use OCR where needed, preserve source/hash/version/import state, and manage attachment storage, size, access, and deletion lifecycle. Existing `kind=file` does not provide binary upload service. |
| F08 | P1; import first, then improve retrieval | Permission-aware semantic search/RAG/cross-product search | Knowledge text search, Space permissions, snippet/version citations; the backend can search multiple authorized Spaces | Semantic/hybrid retrieval, cited natural-language answers, and unified search across tasks, documents, and PRs. Retrieval, caches, and responses must honor current authorization and exact versions. See [Microsoft document-permission search](https://learn.microsoft.com/en-us/azure/search/search-document-level-access-overview) for source ACL and query-time filtering patterns. |
| F09 | P1 | Existing enterprise VCS and Jira integration | Work can read GitHub/GitLab/Gitea PRs/checks; Code can write to Gitea | Authorized GitHub/GitLab connections, repository bindings, branch/commit/PR writes, webhooks, and Jira issue synchronization. Select Bitbucket/Azure DevOps based on initial customers. Work should continue integrating directly with existing forges rather than requiring Code. |
| F10 | P1; before production software delivery | Real CI/test evidence integration | Code can report status and validate/deduplicate Gitea webhooks; Work can read provider checks | Trigger/view/retry/cancel pipelines, obtain test reports/logs/artifacts, bind results to commit SHA/execution, and submit them for independent review. Start with an enterprise's existing runner if useful; the [GitLab pipelines API](https://docs.gitlab.com/api/pipelines/) provides pipeline and test-report interfaces. |
| F11 | P1; advance when directory sync is mandatory | SCIM and automated joiner/mover/leaver sync | Invitations/JIT, group sync at sign-in, administrator disable, and back-channel logout | SCIM 2.0 Users/Groups, group/permission changes, platform-session revocation after `active=false`, and idempotent events with retries/reconciliation. This is the directory lifecycle channel; [Entra provisioning](https://learn.microsoft.com/en-us/entra/identity/app-provisioning/how-provisioning-works) describes create/update/disable synchronization. |
| F12 | P1 | General Agent-token lifecycle | Work stores token hashes and can disable Agents; runtime delivery tokens expire and are revoked after completion | Add `expires_at`, individual revocation, rotation/grace periods, last-use tracking, least-privilege scopes, and an administration UI for general Agent tokens. Long-running automation should not need a replacement Agent just to rotate a credential. |
| F13 | Partially included in this release | Agent configuration versions, role instructions, and multi-protocol models | Immutable Agent templates; role/capabilities/instructions/model/tools/sandbox/limits, dispatch snapshots, and per-Agent overrides | Native Anthropic/Gemini adapters, a standalone skill registry, and configuration-quality evaluation remain to be built. Multiple `base_url`/model metadata values using `openai-responses` do not mean other vendors' native protocols have been verified. |
| F14 | P1/P2, based on document collaboration frequency | Document comments, review, and publication approval | Immutable Knowledge versions, decisions, and source references | Inline comments, assigned reviewers, draft/submission/approval/rejection and publish-after-approval, with version and review evidence for collaborative standards, SOPs, or policy documents. |
| F15 | P2; advance when Agents run continuously | Agent quality evaluation and observability | Execution/audit records, Pi persistence, and model-usage receipts | Redacted tool/model traces, latency/success/cost metrics, datasets and fixed scoring rules to compare prompt/model/Agent versions, and regression cases derived from real failures. See [LangSmith datasets/evaluation](https://docs.langchain.com/langsmith/evaluation) and [OpenTelemetry traces](https://opentelemetry.io/docs/concepts/signals/traces/). |
| F16 | P2; advance MCP when cloud Agents must connect | Remote MCP gateway and A2A | Local stdio MCP bridges for each product and a restricted bearer REST bridge | Streamable HTTP MCP, remote token/scope management, and a tool catalog; later, connect independent Agents through A2A Agent Cards and task lifecycle. See [MCP authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) and the [A2A specification](https://a2a-protocol.org/latest/specification/). |
| F17 | P2; P0 for multi-customer SaaS | Team management and full multi-tenancy | Organization/team fields and project authorization; one organization/IdP per Identity environment | Department/team management and authorization; multi-organization membership, tenant switching, per-tenant IdP/model/quotas/audit, and cross-tenant isolation acceptance. Multi-tenancy can come later when enterprises run separate deployments. |

<span id="本輪第一版與後續候選"></span>
<span id="本轮第一版与后续候选"></span>

## This release and later candidates

<span id="f03-執行控制台"></span>
<span id="f03-运行控制台"></span>

### F03: Run console

This release provides a Run list and detail view, model/token/tool events and errors, stop, and pause/resume/retry subject to explicit eligibility rules. Python validates the current user's project permissions for every operation; the browser never holds a runtime service token. See [execution-contracts.md](execution-contracts.md) for the exact contract.

Acceptance covers stopping a pending run, pause/resume, expired-lease/project rejection, restart, and retry after a lost response. A retry creates a new execution linked to its source; resuming the same run preserves its idempotency boundary. Full dead-letter handling and operator workflows remain future work.

<span id="f01-可持久化的執行前審批"></span>
<span id="f01-可持久化的运行前审批"></span>

### F01: Durable pre-execution approvals

The first version should define an ApprovalRequest, approver, reason, tool/resource/parameter summary and hash, and expiry. Approval authorizes only the corresponding action; changed inputs require a new decision. Policy belongs in Python and is shared by REST/MCP; Pi only pauses and resumes execution.

Acceptance must cover no side effect before approval; rejection of unauthorized or self-approval; expiry/cancellation; input changes after approval; replay and restart; and exactly-once execution of the approved side effect. Existing result review keeps its own business rules. See the official [LangGraph interrupts documentation](https://docs.langchain.com/oss/python/langgraph/interrupts) for durable interrupt behavior.

<span id="f02-先有可執行的上限-再有金額治理"></span>
<span id="f02-先有可运行的上限-再有金额治理"></span>

### F02: Enforce limits before cost governance

The first version can enforce total token, turn, tool-call, execution-time, and concurrency limits, and show why a limit was reached. A USD hard budget also requires known versioned prices, pre-request reservation, settlement/release after completion, and atomic control when several executions compete for the remaining budget.

Acceptance must cover no new model request when the budget is insufficient; concurrency that cannot exceed the reservable amount; explicit handling of unknown usage/prices; settlement after failure or cancellation; cache rates; and deduplication of repeated receipts. An upstream provider may still bill a request that was already sent; an abort cannot promise a refund. Reconciling provider invoices/actual bills is a separate deliverable.

<span id="企業採購或正式維運時的附加項"></span>
<span id="企业采购或正式运维时的附加项"></span>

## Additional enterprise procurement and operations candidates

| Candidate | Current state | Trigger and minimum deliverable |
|---|---|---|
| Local administrator MFA/passkeys | Enterprise MFA can be delegated to the IdP; local accounts have no TOTP/WebAuthn | If administrator recovery accounts also need a second factor, deliver enrollment, verification, recovery policy, and security audit. |
| Audit integration, SIEM, and tamper resistance | Identity has restricted JSONL export with a composite cursor and explicitly applied retention; SIEM delivery and signature/hash-chain/WORM tamper protection are not available | When organizations need to correlate Identity and product events centrally, add bounded, retryable SIEM/event export. Add signatures, hash chains, or WORM storage and verification if tamper resistance is required. |
| Vault/KMS/Secret Manager | Client secrets/model keys are encrypted locally; Compose secrets are mounted from files | Add an external secret backend, key rotation, and recovery when key management must be centralized or shared across nodes. |
| Automated backup, restore exercises, monitoring, and HA | Health checks, named volumes, restart persistence, and manual backup instructions exist; full restore/HA is unverified | Define RPO/RTO before production; verify that databases, keys, Pi, and Git/attachments restore consistently; add alerts/metrics, then address worker partitioning/HA if required. Pi storage must retain a single owner. |

<span id="分期與依賴"></span>
<span id="分期与依赖"></span>

## Phases and dependencies

1. **Execution foundation in this release:** F03/F04/F05 and F13 configuration templates reuse the existing Identity, Work service, outbox, and Pi. Evidence is collected in `execution-validation.md`.
2. **Deepen the first enterprise workflows:** F01 approvals, F02 cost/quotas, basic notifications, existing forges and CI (F09/F10), or document import and retrieval (F07/F08). Start with one confirmed Git/document source, accept it end to end, then add vendors.
3. **Ongoing enterprise onboarding:** F11/F12, identity and token lifecycle, quality evaluation, SIEM/backup operations, then teams/multi-tenancy, remote MCP/A2A, MFA, or Vault as needed.

Document import and source permissions should precede broad RAG indexing. Approvals, scopes, and execution isolation must cover shell/deployment/merge tools. CI results must bind to the actual commit/execution. Cross-product search and tool connections integrate through APIs/events, while each product retains its business authorization and database. These are design premises for future implementation; they do not change current contracts.

<span id="程式碼證據"></span>
<span id="代码证据"></span>

## Code evidence

| Finding | Source |
|---|---|
| Result review and cancellation/manual operations | [Work service](../../backend/src/ordivant/service.py):542, 828, 865; [Work UI](../../frontend/src/App.tsx):1144, 1336; [runtime server](../../runtime/src/server.ts):95 |
| Instructions templates and automatic dispatch | [Agent schemas](../../backend/src/ordivant/schemas.py):145; [Work service](../../backend/src/ordivant/service.py):1111, 1159; [dispatcher](../../runtime/src/dispatcher.ts):25, 169 |
| Existing bounded retries and tool registration | [Work service](../../backend/src/ordivant/service.py):1226; [dispatcher](../../runtime/src/dispatcher.ts):285; [engine](../../runtime/src/engine.ts):455; [platform tools](../../runtime/src/platform-tools.ts):160; [runtime Dockerfile](../../runtime/Dockerfile):28 |
| Cost budgets and fixed model protocol | [Work service](../../backend/src/ordivant/service.py):1346; [engine](../../runtime/src/engine.ts):423; [configured provider](../../runtime/src/configured-provider.ts):42 |
| No runtime human-wait status; receipt cost unknown | `RunStatus`/`RunReceipt` in [runtime types](../../runtime/src/types.ts); [model contracts](model-contracts.md) |
| Budget and self-reported cost UI | [App.tsx](../../frontend/src/App.tsx):1149, 1214; [frontend types](../../frontend/src/types.ts):106 |
| Notifications/mentions/due dates and attachments | [App.tsx](../../frontend/src/App.tsx):427, 951, 1216; [Work schemas](../../backend/src/ordivant/schemas.py):91, 185; [contracts](contracts.md):20 |
| Knowledge import/search/direct publication | [Knowledge schemas](../../products/knowledge/backend/src/ordivant_knowledge/schemas.py):25; [Knowledge API](../../products/knowledge/backend/src/ordivant_knowledge/api.py):227, 382; [Knowledge UI](../../frontend/src/products/knowledge/KnowledgeApp.tsx):144, 469, 528 |
| Gitea in Code; read-only multi-forge access in Work | [Code main](../../products/code/backend/src/ordivant_code/main.py):177; [Work VCS](../../backend/src/ordivant/vcs.py):15, 50; [Work API](../../backend/src/ordivant/api.py):405 |
| Current CI status/webhook scope | [Code service](../../products/code/backend/src/ordivant_code/service.py):714; [Code UI](../../frontend/src/products/code/CodeApp.tsx):523, 538; [suite-contracts](suite-contracts.md):63 |
| Single-organization Identity/IdP | [SSO contracts](sso-contracts.md):15; [auth contracts](auth-contracts.md):50; [organization model](../../backend/src/ordivant/models.py):11 |
| SCIM/MFA/current disable and revocation | [SSO contracts](sso-contracts.md):64; [enterprise sign-in](enterprise-sso.md):78, 80; later enterprise gates in [project plan](project-plan.md) |
| Agent-token lifecycle | [Token model](../../backend/src/ordivant/models.py):37; [security](../../backend/src/ordivant/security.py):31; [contracts](contracts.md):18, 58 |
| Audit scope and key management | [SSO contracts](sso-contracts.md):15, 73; [SSO API](../../products/identity/backend/src/ordivant_identity/sso.py):1266; [Identity models](../../products/identity/backend/src/ordivant_identity/models.py):143; [Compose secrets](../../compose.yaml):209 |
| Verified and unverified production operations | [SSO validation](sso-validation.md):48; [validation ledger](validation.md); later enterprise gates in [project plan](project-plan.md) |

Line numbers and earlier scope in the table reflect the 2026-10-07 review and may shift as code changes. For current F03/F04/F05/F13 evidence, use `execution-contracts.md` and `execution-validation.md`. Official documentation is used to assess candidates; it is not evidence that Ordivant already implements them.
