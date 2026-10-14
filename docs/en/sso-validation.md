<span id="企業-sso-驗收"></span>
<span id="企业-sso-验收"></span>

# Enterprise SSO Acceptance

Date: 2026-10-07 (Asia/Taipei). Scope: the local shared Ordivant Identity service, standard OIDC, and the optional Keycloak SAML identity broker. One Identity environment uses one organization identity service; Work, Knowledge, and Code retain separate databases and authorization boundaries.

This report records OIDC/SAML acceptance as of 2026-10-07 and does not cover SCIM or the SMTP outbox added later. Later Identity checks and remaining customer-tenant work are tracked in the [current P0/P1 ledger](project-plan.md#p0-p1-acceptance-ledger).

<span id="已通過的協定與安全驗收"></span>
<span id="已通过的协定与安全验收"></span>

## Protocol and security checks passed

| Check | Evidence | Result |
|---|---|---|
| Identity security and compatibility with existing accounts | `products/identity/backend/tests`, lock check, compileall | 28 tests passed, covering signatures, issuer/audience/nonce/state, PKCE, exact Google issuer aliases, invited/JIT provisioning, explicit subject linking, SSO-only policy, revocation/replay, trusted proxies, and existing-data migration |
| Work/Knowledge/Code business regressions | Existing product pytest suites | 31/10/20 tests passed |
| Real Keycloak OIDC and SAML | `.data/validation/sso-32eb71e9/report.json` | 136 checks passed; provider responses were not simulated |
| Encrypted storage, logs, and restart | `.data/validation/sso-84b63356/storage-report.json` | 27 checks passed; the QA Identity and Keycloak containers were restarted |
| Frontend types and independent builds | `npm run typecheck`, `build:suite` / `build:work` / `build:knowledge` / `build:code` | All exited 0, including the three product administrator creation flows and general-member empty states |
| Browser OIDC/SAML sign-in | `.data/validation/sso-browser/report.json` and screenshots in the same directory | Passed: enterprise sign-in, cross-product sessions, 390px mouse menus, immediate effect after settings save, SSO-only administrator recovery, hidden member password actions, and scope-limited creation in all three products |
| Main-environment upgrade and setup preservation | `.data/validation/sso-browser/main-environments.json` | All three product health checks and Identity status returned 200 in development on `5173` and local production mode on `8088`; the user still creates the first administrator |

The 136 HTTP checks cover a confidential client and PKCE S256, real authorization/code exchange, JIT and invited members, exact resource authorization in all three products, revocation of old sessions and `403` after group removal, explicit subject linking for an existing administrator, rejection of uninvited users, upstream SAML sign-in and signed assertions/responses, SSO-only rejection of member password sign-in while preserving administrator recovery, disabled members, signed back-channel logout actually sent by Keycloak, forged-state rejection, API/audit secret redaction, and platform-cookie and server-session logout.

Code permissions in Identity use public project IDs. The membership scope ID in Code `/me` is an internal identifier. Acceptance checks the public project permission in Identity and the Code collection together, and verifies that a single opaque scope ID remains consistent across authorized sign-ins. The HTTP suite does not access business databases directly or modify product APIs to expose internal IDs.

The 27 storage checks verify PostgreSQL persistence; that the encrypted Client Secret can be decrypted with the original key; that `sso.key` is 32 bytes with Linux permissions `0600`; that only hashes of state, browser binding, and nonce are stored; that the PKCE verifier is encrypted; that there are no provider-token or authorization-code fields; and that existing OIDC sessions and settings remain valid after restarting both containers. The checks also scan QA Identity, broker, and Web logs, output only pass/fail results, and do not save raw logs or credentials.

The browser used synthetic accounts to complete both direct OIDC sign-in and upstream SAML sign-in. SAML members entered Work, Knowledge, and Code with the same platform session. The account drawer identified enterprise sign-in and did not offer local password or recovery-code actions. After changing the enterprise sign-in button label, signing out without reloading the page caused the login screen to immediately show the new label and SSO-only policy. Administrator password recovery remained available; general members had no entry point for creating Projects or Spaces, while task and document entry points within their authorized scope remained. Gitea was not configured in the Code QA environment; the UI showed that state and disabled repository writes. This identity acceptance does not claim Git write acceptance.

<span id="可重現的隔離環境"></span>
<span id="可重现的隔离环境"></span>

## Reproducible isolated environment

```powershell
.\scripts\sso-containers.ps1 -Action up
uv --cache-dir .cache/uv run --project products/identity/backend --no-sync python scripts/sso_acceptance.py
uv --cache-dir .cache/uv run --project products/identity/backend --no-sync python scripts/sso_storage_acceptance.py
.\scripts\sso-containers.ps1 -Action down
```

The isolated environment uses the fixed project `ordivant-sso-qa`, app `127.0.0.1:8092`, Keycloak `127.0.0.1:8093`, separate PostgreSQL/volumes/service secrets, and two synthetic realms: `ordivant-qa` and `ordivant-qa-saml`. Test passwords and client credentials are public QA fixtures in the source, not user accounts. The first run initializes a synthetic administrator only in this QA environment; later runs reuse it. Docker must be accessible from the terminal.

The broker uses `quay.io/keycloak/keycloak:26.8.0`, pulled for this run at digest `sha256:b0f60d489d51c5d113390bdf5461d4c06e6051be026c05549f2e1e10ec352bcc`. The two realm files are mounted separately; the manifest is not passed to the realm importer. Existing realms are preserved during normal startup. To apply a changed synthetic fixture, use `-Action reimport`; it replaces only those two realms while this QA broker is stopped. Do not use this operation with a real enterprise realm.

Chromium sends the Secure flow cookie that Keycloak 26.8 sets over HTTP loopback; HTTPX does not by default. HTTP acceptance simulates that behavior only for the two fixed QA origins above. It still checks host, path, and expiry, and does not inject the IdP cookie into the app callback. `diagnostics` records this difference; `checks` contains only conditions that actually passed, and duplicate check names are combined with AND. The browser separately completes OIDC and SAML sign-in. Product cookie/TLS validation is not weakened for this test.

Between fixture correction and rerunning acceptance, the PM verified the fixed QA container project label before clearing the synthetic environment's SSO request counter. The 20 starts per 15 minutes limit in the main environment and products was not changed. Normal reruns must wait for the previous rate-limit window to expire; repeated full-suite requests must not be mistaken for a single ordinary sign-in failure.

The SAML fixture keeps `validateSignature` and `wantAssertionsSigned`, using `saml.assertion.signature` and `saml.server.signature` to enable upstream assertion/response signatures. Acceptance checks live client flags, AuthnRequest policy, metadata Entity ID/SSO endpoint, and that the metadata certificate matches the upstream public signing key. The broker loads its verification key from metadata; signature validation was not disabled to pass the test.

<span id="實際服務的配置邊界"></span>
<span id="实际服务的配置边界"></span>

## Configuration boundaries for real services

The UI includes configuration templates and provider-specific claim guidance for Entra ID, Google Workspace, Okta, Auth0, Keycloak, and generic OIDC. Protocol compatibility was tested with a real Keycloak instance. Each enterprise tenant still needs acceptance with its own issuer, client ID, secret, claims, and MFA policy. A signed fixture covers Google's issuer alias; it is not a connection to a user's Google Workspace.

The signed SAML round trip through the Keycloak broker passed. LDAP/AD uses Keycloak User Federation; operator configuration is documented, but no real directory was connected. As of this report, native SAML endpoints, SCIM 2.0, automated enterprise offboarding, backup/restore, load testing, and production monitoring remained separate work. Later SCIM/SMTP implementation checks are tracked in the [current acceptance ledger](project-plan.md#p0-p1-acceptance-ledger). Identity/Keycloak persistence across restart is not a full backup/restore test.

After acceptance, the synthetic account was signed out, the temporary viewport was reset, and the QA tab was closed; the user's existing `5173/work` tab was left open. The QA login policy was restored to `password_and_sso`, then `down` stopped the `ordivant-sso-qa` containers and network. Named volumes, service secrets, and local reports were retained for reproduction. No synthetic account, enterprise provider configuration, or QA realm was added to the main environment. Development and local production data remain separate. No external deployment, release, or push occurred. See [enterprise sign-in](enterprise-sso.md) and [container development and deployment](containers.md) for setup.
