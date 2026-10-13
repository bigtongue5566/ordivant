# Human and Agent collaboration contracts {#human-agent-contracts}

This extension uses shared Identity, product resource scopes, and Python authorization. An LLM must never be a prerequisite for ordinary tasks, documents, or Code operations.

## Work

- Existing `assignee_id` and `reviewer_id` remain Agent IDs. New `assignee_principal_id` and `reviewer_principal_id` identify human Principals. Each assignment selects either a person or an Agent. Responses include `assignee` and `reviewer` as `{id,principal_id,name,kind:"human"|"agent"}` or null.
- `GET /api/projects/{id}/participants` returns active, authorized humans and Agents as an array of `{id,principal_id,name,kind,role}`. A human id is the local principal ID; an Agent id is the Agent ID. The protected Identity directory includes registered coworkers before their first Work login, so assignment does not depend on visiting Work first.
- Humans call existing `POST /tasks/{id}/claim` under their own account without `agent_id`. Workers, managers, and administrators may claim a ready task that is unassigned or assigned to them. They cannot claim for another human or claim a task they are designated to review. The explicit manager proxy path with `agent_id` remains available for Agents.
- Human Execution fields `agent_id`, `lease_token`, and `lease_expires_at` are null. `claimed_by_principal_id` identifies the actual person. Human work persists without an Agent expiry lease. Agents retain lease expiry and fencing. Execution responses include `executor_id`, `executor_kind`, `executor_name`, `claimed_by_principal_id`, and `submitted_by_principal_id`.
- Humans use existing progress, submit, release, and block actions with optional `lease_token`. Python verifies current execution ownership and project authorization on every action. Reloading resumes a running human execution from `context.executions`.
- Submission and independent review remain separate. Neither people nor Agents can review their own submission. Managers can assign scoped human workers/managers or worker Agents, and human reviewers/managers as reviewers. Other actors cannot claim an assigned task.
- Releasing human work stores its handoff, closes the old execution, clears its human assignee, and returns the task to ready so a coworker can claim it. Blocking and rejection retain the assignee.
- Task messages, help, delegation, and recipients support authorized humans and Agents without granting additional project or product access. Automatic Pi dispatch accepts Agent assignments and cannot override human work.

## Knowledge

- The CRDT is compatible with Yjs, using pycrdt in Python and root `Y.Text("body")` for document content. Drafts and immutable published versions are separate durable records in PostgreSQL or SQLite. Updates are acknowledged after persistence.
- `GET /api/documents/{id}/draft` returns `{document_id,base_version,revision,published_revision,title,body,update}`. `update` is a standard base64 Yjs v1 update. Readers can read; writers and managers can edit.
- `POST /api/documents/{id}/draft/updates` accepts `{update}` and uses existing Idempotency-Key, Bearer, and Cookie CSRF checks. Python merges the CRDT update and returns the same draft structure. Agents read and edit the shared draft through REST or MCP; they cannot overwrite another editor's unpublished draft through a legacy version operation.
- `POST /api/documents/{id}/draft/publish` accepts `{expected_revision,change_summary,title?,source_refs?}`. Authorized writers and managers atomically publish the revision as a new immutable version, preserving CRDT IDs and advancing base_version/published_revision. The response is the existing DocumentVersion format. Concurrent updates return 409 without discarding content. Conflicts between legacy version operations and shared drafts are explicit.
- `WS /api/documents/{id}/collaborate` uses the same scope authorization. Browsers use the HttpOnly Cookie with first message `{type:"authenticate",csrf_token}`. Every connection checks Origin and periodically revalidates the session and scope. Credentials never appear in URLs. No document data or presence is sent before authentication.
- Server messages are `{type:"sync",draft,participants:[{id,name,kind}]}`, `{type:"ack",request_id,draft}`, `{type:"presence",participants}`, or `{type:"error",code,message,request_id?}`. Client updates are `{type:"update",update,request_id}`. Database polling distributes committed CRDT state across processes and restarts. Reconnection merges unconfirmed local updates. The interface distinguishes unsaved data and lost access; it must not falsely report a save.
- Update size, document size, frequency, and connection count are bounded. Readers cannot update. Presence identities come from the server rather than client claims. Editing and publication audits identify human or Agent actors.

## Code and acceptance {#code-acceptance}

Gitea remains authoritative for Git, PRs, and merging. Ordivant separately stores shared human/Agent discussions and review receipts. These are not Gitea approvals, CI results, or Work acceptance. The server verifies actors rather than accepting an identity from request bodies.

- `GET /api/repositories/{repository_id}/pulls/{number}/collaboration` returns `{pull_request_id,head_sha,proposer,comments,reviews}`. Authors and proposers use `{id,name,kind}`. An unknown proposer is null unless verified creation records identify them; the upstream service account is never assumed to be the actor.
- `POST .../comments` accepts `{body}`. `POST .../reviews` accepts `{decision:"approve"|"request_changes"|"comment",comment,expected_head_sha}`. Existing Idempotency-Key, scope, and writer/manager/admin requirements apply; readers can only read.
- Reviews fetch the current Gitea head and return 409 when it differs from expected_head_sha. Proposers cannot approve or request changes on their own PR; closed PRs accept comment reviews only. Historical receipts retain head_sha, and GET computes is_current against the live head. Code changes make older reviews outdated without deleting history.
- REST and MCP share service methods. Local discussion/review records, audit events, and idempotency receipts commit in one transaction. A Gitea API failure never produces fabricated success.

Acceptance covers two-person assignment, claims, evidence, and independent review without an LLM; concurrent edits by two people and an Agent; reconnection and restart persistence; scope, reader, and logout rejection; Gitea-backed PR collaboration; all three interface languages; and containers. No real user passwords or paid model runs are used.
