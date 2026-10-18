# Human authentication revision (2026-10-06)

The user requires usable human account login in development and production and working mouse-operated dropdowns. This supersedes the pilot browser local-session/token UI. Keep agent/MCP bearer authorization and all existing product data.

The enterprise identity revision adds OIDC, provisioning, group grants, lifecycle revocation and audit through the same Identity service. `sso-contracts.md` defines the additive routes and fields; the native account/session contracts below remain in force.

## Personal API and MCP access tokens {#personal-access-tokens}

- Humans create `ord_pat_` personal tokens in account settings. Store only a SHA-256 hash; return the raw value once on creation and never log it or include it in audit events.
- `GET /api/auth/access-tokens` returns `{tokens:[metadata]}`. `POST` to the same path accepts `{name,products:["work"|"knowledge"|"code"],expires_in_days:1..365}` (default 30) and returns `{token,access_token:metadata}`. `DELETE /api/auth/access-tokens/{id}` returns 204. Management is owner-only and requires a Cookie session; mutations also require an exact allowed Origin and CSRF. Serialize creation to enforce a limit of 50 active tokens per user under concurrency.
- Metadata is `{id,name,prefix,products,created_at,expires_at,last_used_at,revoked_at}` with UTC ISO timestamps and null for unused/unrevoked values. It excludes the hash and complete credential. Creation and revocation produce Identity audit events.
- Internal `POST /api/auth/access-tokens/introspect` requires service bearer authentication and `{access_token,product}`; it returns `{user:User,token_id,expires_at}`. Invalid/revoked/expired tokens or inactive accounts return 401; an incorrect product returns 403. This route bypasses browser Origin checks only. All responses use `Cache-Control: no-store`.
- Product bridges introspect personal tokens using the fixed Identity URL and service secret, load current permissions on every request, and map to the same human principal. Invalid Authorization never falls back to Cookie authentication; network or malformed responses fail closed with 503. Tokens preserve claim, independent review, scope, and idempotency rules, and grant no Agent identity.
- Creation allows only products currently granted to the user. Permission changes apply to subsequent requests. Password change, account recovery, and deactivation revoke existing tokens. `logout-all` affects browser sessions only; external tokens are revoked separately. Tokens cannot use management routes to expand access or issue more tokens.
- Work, Knowledge, and Code stdio MCP bridges accept personal bearer tokens and delegate business operations to their respective REST APIs. `get_me` confirms the principal. Resource creation tools accept `request_id` and generate a UUID when omitted. The interface provides product-specific local commands, environment variables, and API root examples with credential placeholders.

## Ownership

- PM owns these contracts, Compose/tooling, dropdown fixes and final acceptance.
- Identity worker owns `products/identity/backend/**` only: independent Python/SQLAlchemy identity service, Dockerfile, tests and lockfile.
- Bridge worker owns `backend/src/ordivant/{identity.py,api.py}` and `products/knowledge/backend/src/ordivant_knowledge/{identity.py,api.py}` and `products/code/backend/src/ordivant_code/{identity.py,main.py}`, plus new targeted identity bridge tests in each product's tests directory. Do not edit existing domain models/security/service or root tooling.
- Frontend worker owns `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/products/{knowledge/KnowledgeApp.tsx,code/CodeApp.tsx,shared/ProductLogin.tsx,shared/ProductShell.tsx,shared/productApi.ts}`, and new `frontend/src/auth/**`. Do not edit main.tsx, existing CSS, manifests or root files; PM owns dropdown CSS. New auth CSS under auth/ is allowed.

## Identity service

Independent port 8030, PostgreSQL via `ORDIVANT_IDENTITY_DATABASE_URL_FILE` or URL (SQLite allowed for tests/native). Python package `ordivant_identity`. `/api/auth` is its route prefix. Nginx/Vite route `/auth-api/*` to identity `/api/auth/*`. Identity and product data do not directly read each other's databases.

Environment: `ORDIVANT_IDENTITY_DATA_DIR=/data`; `ORDIVANT_IDENTITY_SERVICE_TOKEN_FILE` (internal introspection secret); `ORDIVANT_AUTH_COOKIE_NAME` (unique per Compose project); `ORDIVANT_AUTH_ORIGINS` comma-separated exact trusted browser origins; `ORDIVANT_AUTH_COOKIE_SECURE` true for HTTPS deployments, false for loopback HTTP. Identity binds 0.0.0.0 in containers. Outside tests, reject incomplete unsafe configuration rather than silently opening access.

Identity uses Argon2id password hashes, unique normalized email, durable throttling, random hashed session handles, idle and absolute expiry, HttpOnly/SameSite=Lax/Path=/ cookies (Secure configurable for local HTTP). Never expose password/hash/session handle in JSON/logs. All auth responses use Cache-Control: no-store. Browser mutations require an allowed exact Origin; authenticated mutations additionally require `X-CSRF-Token`. Derive CSRF with HMAC(service secret, raw session handle), return it in session JSON, compare constant-time. Introspection requires `Authorization: Bearer <service secret>`; it is never a public browser credential.

- `GET /api/auth/status` -> `{setup_required:boolean}`.
- `POST /api/auth/setup` `{name,email,password}` creates the first admin exactly once (atomic singleton row/DB constraint), also works on a fresh non-seeded system. No default human password. -> session JSON + cookie + one-time recovery codes. Race losers 409.
- `POST /api/auth/login` `{email,password}` -> session JSON + cookie. Invalid/unknown/disabled/locked credentials have generic errors; rate limit and return 429 after threshold. New handle on every login, no session fixation.
- `GET /api/auth/me` -> session JSON or 401.
- `POST /api/auth/logout` `{}` revokes current session and expires cookie.
- `POST /api/auth/logout-all` `{}` revokes all user's sessions and expires cookie.
- `POST /api/auth/change-password` `{current_password,new_password}` verifies current password, updates hash, revokes all old sessions, issues a new session and one-time recovery codes.
- `POST /api/auth/recover` `{email,recovery_code,new_password}` consumes a one-time hashed recovery code atomically, changes password/revokes sessions and returns new session/recovery codes. Generic failure, throttle; this is actual offline recovery, no pretend email/SMTP delivery.
- `GET /api/auth/sessions` -> `{sessions:[{id,created_at,last_seen_at,expires_at,current:boolean}]}`.
- `DELETE /api/auth/sessions/{id}` only own session; revoke, clear cookie if current.
- `GET /api/auth/users` admin only -> `{users:[User]}`.
- `POST /api/auth/invitations` admin only `{email,name,role:"admin"|"member",permissions:Permissions}` -> `{invitation_code,expires_at}` one-time invitation. Keep invitation hash at rest, raw code only in issuance response.
- `POST /api/auth/accept-invitation` `{invitation_code,password}` consumes valid unexpired invitation exactly once -> new session + recovery codes.
- `PATCH /api/auth/users/{id}` admin only `{active?,name?,permissions?}`. Cannot disable the last admin or self-lock; revoke affected sessions when disabling or changing permissions.
- `POST /api/auth/introspect` internal secret + `{session_token}` -> `{user:User,csrf_token,session_id,expires_at}` or 401. Never returns session_token.

Session JSON: `{user:User,csrf_token:string,expires_at:string,recovery_codes?:string[]}`.
User: `{id,email,name,role:"admin"|"member",active:boolean,permissions:Permissions}`.
Permissions: `{work?:{role:"manager"|"worker"|"reviewer",scope_ids:string[]},knowledge?:{role:"manager"|"writer"|"reader",scope_ids:string[]},code?:{role:"manager"|"writer"|"reader",scope_ids:string[]}}`. Admin can access all resources in the one local organization; member has no implicit grants. Invitations are the route to additional accounts, not public unrestricted registration.

Use shared domain error shape `{detail:{code,message}}`. Meaningful security tests cover setup race, no plaintext storage, invalid login/throttle, expiry, logout/revoke/password change/recovery, invitation reuse and last-admin protection.

## Product bridge

With Authorization header, existing bearer auth remains authoritative; an invalid supplied token must not fall back to a cookie. Without it, read only the cookie named by `ORDIVANT_AUTH_COOKIE_NAME`, introspect using `ORDIVANT_IDENTITY_URL=http://identity-api:8030` and service secret file (httpx timeout, no redirects/trust_env, no client-provided URL). Fail closed on identity outage.

For authenticated browser mutations enforce configured exact Origin and constant-time `X-CSRF-Token` from introspection. GET/HEAD are read-only. Signed Gitea webhook and bearer operations retain their existing policies.

Map identity subject to an explicit local principal via a new local `IdentityBinding` table (subject unique). Map only within one configured/local organization. Admin maps to human manager (Work admin allowed) and explicit local memberships in this org; members use the product permission role and only existing scope IDs belonging to this org. Synchronize current roles/membership on each authenticated request without touching agent principals. Flush/commit mapping safely before business mutation; handle racing first requests. Principal.active follows introspected active identity. If identity user lacks product permission, return 403 with a useful message, no auto-grant. No product ORM imports from peers.

`ORDIVANT_IDENTITY_ORG_ID` optionally selects an existing local organization. Without it, use the sole existing organization or create a deterministic local identity organization when the database is empty; reject ambiguous multi-organization data. Never choose an organization from caller scope IDs. Persist `IdentityBinding.identity_admin`; identity-bound member managers may operate only assigned scopes, and creation of new projects/spaces is reserved to identity admins.

Local-session endpoint is retained for old explicit test harnesses but must refuse to bypass login after Identity has been configured for the product. Frontend never renders it.

## Browser

Permission `scope_ids` refer to each product's public resource identifiers: Work project IDs, Knowledge space IDs, and Code project IDs. Code resolves public project IDs to its own internal Scope memberships; UI never needs private ORM scope identifiers.

Common login across Work/Knowledge/Code through identity cookie. Initial render checks `/auth-api/status` and `/auth-api/me`; fresh installation shows admin setup, otherwise email/password login. Invitation and recovery flows are real forms. No human bearer-token field or local-session button in ordinary login UI.

Keep credentials only in password input state, clear on completion/unmount; no browser storage. Fetch uses credentials=same-origin. Authenticated writes add in-memory CSRF token from identity me/login. Unauthorized requests clear UI identity and show login, expired sessions have readable copy. Product switching and page reload recover cookie session. Sign-out calls server logout before clearing UI.

Provide account settings for password change, recovery-code display (once), session list/revoke/logout-all and admin invitation/user disable/access assignment. Treat codes as credentials: no console logging, screenshot masks/hides values. Surface genuine unavailable/permission errors. Preserve existing business surfaces and independent build modes.

## Container acceptance

Each selected product can deploy with its own database plus the shared identity service/database; no Work/Knowledge/Code peer dependency introduced. Development and production have separate identity data and cookie names. Preserve existing business volumes. Test human account flows against owned isolated QA identity data; never initialize the user's first admin with a test password. Leave real installed environments ready for the user to create their own admin in the app.
