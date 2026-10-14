# Enterprise identity revision (2026-10-07)

This contract records the 2026-10-07 OIDC enterprise-identity revision: configurable provider templates, scoped provisioning, group grants, lifecycle revocation, and identity audit in the shared Identity service. SAML and LDAP/AD providers use the optional Keycloak broker; the platform has no native SAML endpoint. SCIM was not supported at that time; the SCIM and assurance extension dated 2026-10-15 is defined below. Do not claim unconfigured vendor tenants have been tested.

## Ownership

- PM owns this contract, root Compose/tooling, integration and final acceptance.
- SSO backend worker owns `products/identity/backend/**`, including dependencies, locks and meaningful security tests.
- SSO frontend worker owns `frontend/src/auth/**`, including new SSO settings/audit components. The final permission alignment also assigns only new-scope creation visibility, handler guards and empty-state copy in `frontend/src/App.tsx`, `frontend/src/products/knowledge/KnowledgeApp.tsx` and `frontend/src/products/code/CodeApp.tsx`. Preserve other workers' changes; existing-scope business authorization remains unchanged.
- SSO QA worker owns `scripts/sso_acceptance.py`, `scripts/sso_fixture.py` and `tests/fixtures/sso/**` only. Build fixture realms/client import for both direct OIDC and an upstream Keycloak SAML realm federated into the broker realm. PM owns the Compose overlay that runs the real Keycloak fixture.
- All workers first read `docs/contracts.md`, `docs/project-plan.md`, `docs/auth-contracts.md` and this contract. Raise contract changes to PM before changing shared shapes.

## Configuration and API

One OIDC provider per Identity environment (one local organization). All new public routes are below `/api/auth`; browsers use `/auth-api`. Settings are durable, singleton, revision-fenced, admin-only and require Origin + CSRF for mutations. Client secrets are encrypted with a dedicated durable `/data/sso.key`, never returned, logged or included in validation errors/audit. Empty/omitted client_secret preserves it for the same issuer/client ID; changing either requires an explicit replacement. Never derive an admin role from IdP claims.

`GET /sso/settings` and `PUT /sso/settings` return:

```json
{
  "revision": 0,
  "enabled": false,
  "display_name": "企業帳號",
  "issuer_url": "",
  "client_id": "",
  "client_secret_configured": false,
  "redirect_uri": "http://127.0.0.1:5173/auth-api/oidc/callback",
  "scopes": ["openid", "profile", "email"],
  "allowed_email_domains": [],
  "email_claim": "email",
  "require_email_verified": true,
  "groups_claim": "groups",
  "provisioning": "invited_only",
  "default_permissions": {},
  "group_mappings": [],
  "login_policy": "password_and_sso"
}
```

PUT accepts these editable fields plus write-only `client_secret`; excludes derived `redirect_uri` and `client_secret_configured`. Existing revision is required even on first write (0), stale saves return 409. `group_mappings` entries are `{group:string,permissions:Permissions}` using existing per-product roles and exact resource IDs. Merge default and matching group permissions with deduplicated scope IDs. Work priority manager > reviewer > worker; Knowledge/Code manager > writer > reader. No wildcard resource grant, suite admin grant or actor from a claim.

`enabled=true` requires a valid issuer, client ID, stored secret, nonempty allowed_email_domains, and completed first-admin setup. `login_policy=sso_only` requires enabled SSO. Fixed public callback is derived from `ORDIVANT_SSO_PUBLIC_ORIGIN` or first exact `ORDIVANT_AUTH_ORIGINS` origin; it must be in the trusted origins. Request Host and query parameters never choose the callback origin.

`POST /sso/test` (admin + CSRF) uses saved settings, validates discovery/JWKS without starting login and returns `{status:"ok",issuer,authorization_endpoint,redirect_uri,supported_algs:string[]}`. Fail with safe genuine upstream/configuration errors; do not invent passing data.

`GET /status` retains setup_required and adds `sso:{enabled,display_name,login_policy,configured,public_origin}`. No secret or private discovery response. `public_origin` is the trusted canonical browser origin, so aliases cannot strand the browser binding cookie. Frontend SSO clicks from a different origin first navigate to the canonical product path with a one-time enterprise_login=1 flag; consume the flag and start only after status confirms enabled SSO. Backend start requires this canonical Origin and returns sso_origin_mismatch otherwise. `User` adds `credential_type:"local"|"sso"` and `permissions_source:"manual"|"sso"`; no schema break for the product introspection bridge. Session JSON adds `authentication:{method:"password"|"oidc",provider_name?:string}`. SSO-only users cannot change or recover a password or receive local recovery codes.

## Login flow

- `POST /oidc/start` with `{return_to:"/work"|"/knowledge"|"/code"}` requires trusted Origin, returns `{authorization_url}`, sets a distinct HttpOnly/SameSite=Lax/Secure-as-configured browser binding cookie. Requires enabled SSO and completed setup. Rate limit starts/callbacks. Use Authorization Code + PKCE S256 + random state + nonce.
- Persist only hashed state and browser binding, nonce hash, encrypted short-lived PKCE verifier, fixed return path, configuration revision and expiry (five minutes). State is consumed with an atomic conditional write exactly once. Reject absent/wrong binding, expiry and changed provider config. This must work with PostgreSQL and survive process restart.
- `GET /oidc/callback` verifies binding/state, exchanges code server-side, validates a signed ID token against discovery JWKS, then creates the existing suite HttpOnly session. No provider tokens in browser storage, API JSON, URL redirect, database or logs. Clear binding cookie on success and failure.
- Callback redirects 303 to the trusted public origin and stored product path. Failures use only bounded `auth_error` codes, never raw provider errors/codes/tokens. A valid state with provider denial is consumed; invalid state cannot cause an external redirect. API/server access logs must not record callback query strings.
- Explicit allowlist RS256/ES256 only; validate signature, exact issuer, audience, azp when required, expiry, nbf/iat, nonce, nonempty stable sub and normalized valid email. Require email_verified=true by default. Tenant-specific Entra deployments may explicitly opt out after choosing an exact tenant issuer and allowed domains; do not silently infer email ownership or link existing users by email.
- Discovery issuer must exactly match configured issuer. Validate all URLs; reject credentials, fragments, invalid ports, link-local/metadata/unspecified targets, unexpected endpoint hosts and redirects. HTTPS outside the explicitly trusted local test/private HTTP hosts; strict timeouts and bounded responses; no trust_env.
- Google OIDC discovery legitimately uses oauth2.googleapis.com and www.googleapis.com for backchannel endpoints; include these exact HTTPS-only vendor hosts in the built-in endpoint host allowlist. Other different hosts require the explicit operator allowlist. Provider templates are configuration aids, not simulated provider integrations.
- Google documents exactly two signed ID token issuer spellings: https://accounts.google.com and accounts.google.com. Only when configured canonical issuer is https://accounts.google.com, accept those exact aliases, keep canonical issuer for identity binding, and normalize the legacy verified-email string "true". Other issuers and verified-email strings remain strict. Cover this with signed-token fixtures; no general issuer-prefix matching.
- `ORDIVANT_SSO_HTTP_HOSTS` comma-separated trusted HTTP hostnames (loopback is allowed locally); `ORDIVANT_SSO_ALLOWED_ENDPOINT_HOSTS` explicitly allows discovery endpoints on hosts different from issuer. `ORDIVANT_SSO_BACKCHANNEL_OVERRIDES` JSON maps an exact public issuer prefix to a trusted internal issuer prefix, for container-network routing only. Still validate the public discovery issuer/endpoints/token issuer, then rewrite only matching prefixes for backchannel HTTP. Production has no default overrides.
- Reverse-proxy rate limiting uses `ORDIVANT_AUTH_TRUSTED_PROXY_HOSTS` (explicit hostnames/IPs). Only if the socket peer matches a resolved trusted proxy may one valid X-Real-IP affect the throttle identity. Compose trusts only web; Nginx overwrites X-Real-IP with remote_addr. Ignore supplied forwarding headers from direct/untrusted clients. No blanket trust of all source IPs.

## Provisioning and lifecycle

- Keep issuer+sub as stable identity with a unique database constraint. First admin is always explicitly created locally. Existing local accounts are never automatically merged with an IdP email; return account_link_required.
- `invited_only`: a verified, allowed email may consume a live member invitation atomically and create an SSO-only member with its explicit permissions. No invitation code is needed because the IdP attests the email. Admin invitations cannot auto-create SSO administrators. Unknown/uninvited identities are denied.
- `jit`: a verified allowed identity may create an SSO-only member with default/matching-group permissions; without grants the account has no product access. Such accounts synchronize managed permissions on every subsequent SSO login; revoke prior sessions when permissions shrink/change. Missing groups remove prior group grants. New sign-ins never reactivate disabled users.
- Existing manual grants remain manual. Administrative permission edits switch an SSO-managed member to manual permissions rather than secretly overwriting the edit on the next login. `POST /sso/links` admin + CSRF `{user_id,subject,managed_permissions?:false}` explicitly links an existing user to the current issuer; initial login must match the linked user's email. `GET /sso/links` admin returns `{links:[{id,user_id,issuer,subject,managed_permissions}]}`. `DELETE /sso/links/{id}` admin + CSRF unlinks/revokes the affected user's SSO sessions. One link per issuer/subject and no silent reassignment.
- `sso_only` rejects non-admin password login, recovery and password invitation acceptance, and revokes existing non-admin password sessions. Local admin password login stays available as an explicit recovery path. Disabling/changing provider identity revokes affected OIDC sessions; disabled users/permission changes reuse current immediate revocation mechanisms across all three products.
- `POST /oidc/backchannel-logout` accepts form logout_token, exempt only from browser Origin/CSRF. Validate signed logout JWT against the configured issuer/JWKS, aud, iat, required backchannel event, sub or sid, no nonce, and replay-fenced jti. Revoke only matching OIDC sessions; preserve local admin/password sessions. Persist replay guard. Never persist or echo raw logout_token.
- Identity data migration must preserve existing account hashes and sessions. Prefer additive tables instead of assuming create_all alters existing tables. Encryption keys and DB volumes survive container rebuild/restart.

## Audit and user interface

Append durable identity audit events in the same transaction as successful identity mutations. Record SSO success/failure, settings changes/test, provisioning/link/unlink, logout/backchannel logout, local login, invitation and administrative permissions/disable changes. Never include passwords, secrets, authorization code/state/nonce, cookies or provider tokens. Audit export is admin-only. The Identity service route is `GET /api/auth/audit/export?limit=100`; the browser/proxy route is `GET /auth-api/audit/export?limit=100`. Limit ranges from 1 to 10,000. Paginate with `before` and `before_id` as the composite `(created_at,id)` cursor. When another page exists, `X-Next-Before` and `X-Next-Before-Id` response headers provide the next pair.

Login presents the configured enterprise button; SSO-only policy visibly prioritizes it and retains an explicit administrator password recovery entry. Consume/remove bounded auth_error query parameters with useful Traditional Chinese messages. No fake login success. Admin account/security UI includes a complete Enterprise SSO settings tab, connection test, manual subject linking/unlinking and identity audit tab. Use the existing resource selectors for default/group permissions, clearly explain exact email domains and permission management. Hide password/recovery actions for SSO-only accounts. Clear client_secret input after save/unmount. Existing four build modes must pass and forms/dropdowns fit a 390px viewport.

## SCIM and authentication-assurance extension (2026-10-15) {#scim-and-mfa-extension-2026-10-15}

This extension defines the current SCIM 2.0 Users/Groups scope and the claims used to enforce MFA performed by an external IdP. SCIM is served at /api/scim/v2 using the dedicated deployment credential in ORDIVANT_SCIM_TOKEN_FILE. Users, Groups, and limited filtering are supported; bulk is not. Creating a provisioned user whose email already belongs to an Ordivant account returns a conflict. Never claim or merge an account automatically by email. An administrator must handle explicit linking or migration first. Groups apply only the product and resource grants configured by an administrator and cannot grant admin. Deactivation and grant changes revoke existing sessions.

OIDC required_acr must match one configured value and required_amr must include all configured methods in the verified ID token. When either assurance requirement is enabled, members must use SSO-only policy. Ordivant validates IdP claims and does not provide the second factor itself. Customer-tenant interoperability remains to be accepted individually; a fixture or the presence of an API is not that acceptance.

SMTP invitation and recovery use the durable Identity outbox and send nothing when mail is unconfigured. Administrators can inspect delivery status and retry eligible messages. Identity audit export is permission-protected, bounded by record/time limits, and excludes secret fields; retention deletes older data only when explicitly applied. See the [project-plan acceptance ledger](./project-plan.md#p0-p1-acceptance-ledger) for integration status.

## Acceptance

Use isolated QA PostgreSQL databases, generated synthetic identities and a real pinned Keycloak container with a confidential OIDC client requiring PKCE S256 and a groups mapper. Do not initialize or modify the user's main human account/provider settings. Verify actual redirect/login/code exchange/signed JWT/session across Work/Knowledge/Code, product scopes, reload/logout/disable, group downgrade, invited-only vs JIT, explicit linking, SSO-only recovery path, encrypted secret/CAS/no leak, persisted state/restart, forged state/nonce/audience/issuer/signature, backchannel logout/replay, and local account regression. Add SCIM checks for existing-email conflicts, User/Group grants, deactivation revocation, no admin grants, and unsupported bulk. Fixture tests are security evidence; Keycloak integration is protocol interoperability evidence, not verification of an unconfigured customer tenant. Document concrete Entra and Keycloak configuration, MFA enforced by IdP, backup/key requirements, and the remaining native SAML and customer-tenant gates.

Primary references: [OIDC Core](https://openid.net/specs/openid-connect-core-1_0.html), [PKCE](https://www.rfc-editor.org/rfc/rfc7636.html), [OAuth security BCP](https://www.rfc-editor.org/rfc/rfc9700.html), [Keycloak containers](https://www.keycloak.org/server/containers).
