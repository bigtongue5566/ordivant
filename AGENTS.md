# Guide for coding agents

This file applies to contributions throughout this repository. It describes project conventions for any coding agent or developer; no particular agent, delegation model, operating system, or hosted service is required.

Ordivant is a self-hosted collaboration platform for people and Agents. Human task management, document editing, and code collaboration work without an LLM. Autonomous Agent Runs require a model connection and the execution service.

## Start here

- Read [CONTRIBUTING.md](CONTRIBUTING.md) for environment setup, test commands, and the PR process.
- Use [the development reference](docs/en/reference.md) and the contracts relevant to your change: [Work](docs/en/contracts.md), [Identity](docs/en/auth-contracts.md), [execution](docs/en/execution-contracts.md), [models](docs/en/model-contracts.md), or [collaboration](docs/en/collaboration-contracts.md).
- Check the working tree before editing. Preserve existing changes and avoid unrelated refactors. When several contributors work together, coordinate overlapping edits.
- Keep public contracts, corresponding REST/MCP operations, and user documentation consistent. Explain compatibility or migration changes in the PR.

## Repository map

| Path | Responsibility |
| --- | --- |
| `backend/` | Work projects, tasks, planning, authorization, REST API, and MCP bridge |
| `products/identity/backend/` | Human accounts, sessions, personal access tokens, SSO, and provisioning |
| `products/knowledge/backend/` | Spaces, documents, shared drafts, immutable versions, and citations |
| `products/code/backend/` | Code projects, Gitea integration, PR collaboration, and upstream evidence |
| `runtime/` | Node.js/Pi Durable execution, dispatch, transcripts, and execution recovery |
| `sandbox/` | Restricted command/file execution environments |
| `frontend/` | React/TypeScript/Ant Design interfaces and Suite/Work/Knowledge/Code builds |
| `docs/` | Translated user guides and maintainer reference documents |
| `scripts/`, `tests/`, `.github/workflows/` | Tooling, integration acceptance, and CI |

Python services use Python 3.12 and `uv` (CI pins 0.12.20), each with its own `pyproject.toml`, `uv.lock`, and environment. JavaScript projects use Node.js 24 and npm with committed lockfiles. Install from the existing lockfiles; update dependencies only when the change requires it. Use a repository-local `.cache/` if the default cache is inaccessible.

## Business and authorization rules

- Enforce authorization in the Python service. REST and MCP must reach the same business checks; frontend controls are not an authorization boundary.
- Preserve organization, product, Project, and Space boundaries. Personal access tokens act as their human owner with current permissions and allowed products; they do not confer Agent or administrator privileges.
- A task and an execution are distinct records. Completion requires submitted evidence and acceptance by an authorized reviewer who is independent of the submitter.
- Claims use atomic conditional writes, and Agent leases use fencing tokens. Check task dependencies and reject cycles.
- Mutating Agent operations accept idempotency keys. Commit business state and outbox records in the same transaction. Recheck current authorization when replaying results.
- Pi owns execution transcripts, not business task state. Only one process may own each Pi storage file.
- Knowledge publishes immutable versions from saved shared drafts. Preserve version checks, draft reconciliation, and exact-version citations.
- Gitea owns upstream Git operations and approvals. Ordivant discussion, review, or Agent-reported status must not masquerade as upstream approval or verified CI/deployment evidence.
- Report unavailable APIs and integrations honestly. Do not fabricate fallback data or present DEMO execution or self-reported cost as a verified paid model run.

## Interface and documentation

- Support Traditional Chinese (default), Simplified Chinese, and English through `frontend/src/i18n`. Maintain English (`catalogs/*.en.ts`) and Simplified Chinese (`catalogs/*.zh-CN.json`) translations by hand for every Traditional Chinese source key. Translate meaning and regional terminology; do not generate translations with character conversion. Run `npm run i18n:check --prefix frontend` to check coverage, placeholders, and consistency without rewriting catalogs.
- Keep API identifiers, credentials, code, and user-authored content unchanged when translating. Prefer language users understand over implementation names in ordinary UI controls.
- Maintain corresponding `docs/`, `docs/en/`, and `docs/zh-CN/` pages with matching section IDs. See [the translation guide](docs/en/i18n.md).
- The website publishes only topics in `docs/.vitepress/public-pages.json`. Maintainer contracts, research, and validation records stay in the repository and must not enter website navigation, search, or sitemap. This publication boundary does not make repository files private.

## Validation

Run affected service tests in their own Python environments and the checks relevant to the change. [CONTRIBUTING.md](CONTRIBUTING.md) lists the complete commands; `.github/workflows/` defines the CI gates.

- Python: `uv sync --project <service> --frozen --extra dev`, then `uv run --directory <service> --frozen --no-sync pytest`. Sandbox uses `--group dev` and the test invocation documented in CONTRIBUTING.
- Runtime: `npm ci --prefix runtime` and `npm test --prefix runtime`.
- Frontend: run type checking, translation/Markdown checks, affected interaction tests, and the relevant product builds. CI builds all four product modes.
- Documentation: `npm ci --prefix docs`, `npm run build --prefix docs`, `uv run --project backend --no-sync python scripts/check_docs.py`, and `node scripts/build_docs_redirects.mjs`.
- Before committing: review the staged changes and run `git diff --cached --check`.

Choose tests that exercise meaningful risks: concurrent claims, expiry, cross-project access, dependency cycles, idempotency, independent review, token revocation, stale versions, restart recovery, and collaboration round trips. Describe commands, outcomes, and any untested scope in the PR. Do not claim that mocked or synthetic checks verified a customer's IdP, live CI, or a paid model.

## Credentials, data, and publication

- Never commit credentials, session cookies, private user data, `.env`, `.data/`, `.venv/`, `node_modules/`, or generated build/test output. Committed `.env.example` and `.env.compose.example` contain placeholders only.
- Use synthetic fixtures and isolated test directories, ports, and Compose project names. Do not overwrite a contributor's running installation or initialize/reset existing data to run tests.
- Do not use real provider credentials, call paid models, or contact private integrations without explicit authorization. Let users authenticate through a secure interactive flow; do not request or record passwords in chat, source files, or logs.
- Do not push, merge, publish a release, or deploy unless explicitly authorized. Respect branch protection and required checks; never bypass them to finish a task.
- Follow [SECURITY.md](SECURITY.md) for private vulnerability reports. Keep exploitable details and sensitive logs out of public issues and PRs.
