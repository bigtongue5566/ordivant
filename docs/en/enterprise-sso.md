<span id="企業登入與身分管理"></span>
<span id="企业登录与身分管理"></span>

# Enterprise sign-in and identity management

Ordivant Work, Knowledge, and Code share one Identity service. Administrators can connect an existing enterprise OIDC identity service and control member provisioning, product and Project permissions, sign-in policy, and sessions. Enterprise passwords and MFA are handled by the identity service; Ordivant does not receive enterprise passwords.

<span id="管理員設定"></span>
<span id="管理员设置"></span>

## Administrator setup

1. Sign in as an administrator of the Ordivant deployment you want to configure. Deployments have separate accounts and SSO settings, so confirm that you are using the correct service URL.
2. Open “Accounts and security → Enterprise SSO.” Choose an identity provider template, then enter the organization-specific Issuer URL, Client ID, and Client Secret.
3. Create a confidential OIDC web application in the identity service with Authorization Code and PKCE S256 enabled. Register the complete Callback URL shown by Ordivant as a Redirect URI; do not use wildcards.
4. Configure allowed full email domains, member provisioning, default permissions, and group mappings. Save, then run “Test connection.” This checks discovery and JWKS; actual sign-in still requires authorization by the identity service.
5. Validate sign-in, product access, and sign-out with one enterprise member before enabling “Enterprise SSO only.” The local administrator credentials remain available as a recovery path.

Leaving Client Secret blank preserves the existing value; changing the Issuer or Client ID requires you to enter a new value explicitly. After saving, the interface clears the Secret and the API returns only whether one is configured. The configured canonical origin is the public source of truth. If sign-in starts from another localhost or `127.0.0.1` alias, the interface first redirects to that origin.

<span id="常見身分服務"></span>
<span id="常见身分服务"></span>

## Common identity providers

| Identity provider | Issuer / application settings | Notes |
|---|---|---|
| Microsoft Entra ID | `https://login.microsoftonline.com/TENANT_ID/v2.0`; Web platform, organization-specific tenant | Use an explicit tenant. Choose `email` or `preferred_username` based on actual token claims. If Entra does not provide `email_verified`, disable that check only after confirming tenant and domain policy. Administrators must configure group claims; group overage is not treated as group authorization. |
| Google Workspace | `https://accounts.google.com`; Web application OAuth client | Restrict allowed domains; the IdP's `hd` hint does not replace backend domain checks. Google does not provide the groups needed by the product by default; configure explicit default permissions or assign access manually. |
| Okta | The organization's own OIDC authorization-server issuer | Configure a groups claim in the ID token. Group names must exactly match the permission mapping. |
| Auth0 | `https://YOUR_TENANT.REGION.auth0.com/` or a configured custom domain | Uses standard OIDC ID-token claims. To use groups, add a custom claim with an Action and enter the same claim name in Ordivant. |
| Keycloak | `https://IDP_HOST/realms/REALM` | Use a confidential client, PKCE S256, and a groups mapper in the ID token. Keycloak can broker SAML or LDAP/AD. |
| Other OIDC providers | The exact issuer exposed by the service | Must provide discovery, JWKS, Authorization Code, a signed ID token, and usable identity claims. |

These templates provide standard setup patterns. A real enterprise tenant still needs sign-in validation with that organization's configuration; passing a local Keycloak test does not mean every vendor tenant has passed.

Official setup references: [Entra OIDC](https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc), [Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect), [Okta OIDC](https://developer.okta.com/docs/guides/implement-grant-type/authcode/main/), [Auth0 Regular Web Apps](https://auth0.com/docs/get-started/authentication-and-authorization-flow/authorization-code-flow), and the [Keycloak administration guide](https://www.keycloak.org/docs/latest/server_admin/index.html).

<span id="成員與權限"></span>
<span id="成员与权限"></span>

## Members and permissions

- **Invitation only:** An administrator first creates a member invitation. After the enterprise email is verified and matches an allowed domain, the member can accept the invitation through SSO and receives the product and resource permissions specified in it. Enterprise sign-in does not create administrators automatically.
- **JIT provisioning:** The first sign-in creates a regular member with explicit default and group permissions. Members without configured permissions cannot access product data; sharing a domain does not grant organization-wide visibility.
- **Group synchronization:** JIT-managed members have their groups synchronized at every sign-in. Removing a group removes the related grants and revokes existing sessions. Members can still access only authorized products and resources.
- **Existing account linking:** Matching email addresses do not merge accounts automatically. An administrator must explicitly map an existing user to an IdP subject, which is verified at sign-in. Unlinking revokes the enterprise sign-in session.
- **Manual permissions:** When an administrator explicitly changes a member's permissions, those permissions become manually managed so the next sign-in does not silently overwrite them. To resume group management, set the management mode again through the identity link.

Successful sign-in creates a platform session only; it does not grant credentials for Agents or version-control services. Agent REST/MCP continues to use separate project-scoped identities.

<span id="saml、ldap-與-active-directory"></span>
<span id="saml、ldap-与-active-directory"></span>

## SAML, LDAP, and Active Directory

Ordivant uses OIDC as its integration protocol. Enterprises with only SAML or LDAP/AD can use the optional Keycloak identity broker: configure a SAML Identity Provider or LDAP User Federation in Keycloak, then connect its exposed OIDC realm to Ordivant. Work, Knowledge, and Code do not each need to store LDAP passwords or implement different sign-in protocols.

For SAML, add a SAML Identity Provider in Keycloak and import the upstream metadata. Register the broker's Entity ID and ACS/Redirect URI with the upstream provider. Keep assertion signature validation enabled, configure email and name mappers, and decide whether to enable Trust Email according to the enterprise email-verification policy. Configure a separate broker mapper for groups so the final OIDC ID token's groups claim contains the complete group names mapped in Ordivant. SAML groups do not automatically become platform permissions.

For LDAP/AD, add an LDAP provider under Keycloak User Federation. Enter the directory address, Users DN, search filters, and username/email attributes provided by the enterprise. Configure group mappers and use LDAPS or StartTLS with a trusted CA. Enterprise administrators enter directory bind credentials and member passwords directly in the identity service. Validate the directory connection and synchronization for one member before creating an OIDC client for Ordivant. Ordivant still applies allowed domains, invitation/JIT policy, and explicit resource grants.

For SAML or LDAP/AD, complete [container initialization](containers.md) first. Add these settings to the same repository root's `.env`, then start optional Keycloak and its separate database. Retain any other Compose files already used by the installation:

```dotenv
ORDIVANT_BROKER_PUBLIC_URL=http://127.0.0.1:8093
ORDIVANT_SSO_HTTP_HOSTS=identity-broker
ORDIVANT_SSO_BACKCHANNEL_OVERRIDES={"http://127.0.0.1:8093":"http://identity-broker:8080"}
```

```sh
docker compose -f compose.yaml -f compose.identity-broker.yaml --profile identity-broker up -d --wait identity-broker identity-api
```

By default, the broker binds only to `127.0.0.1:8093`. The caller can set `ORDIVANT_BROKER_PORT` and `ORDIVANT_BROKER_PUBLIC_URL`; deployments across machines should use a fixed HTTPS URL and a trusted reverse proxy. Other OIDC providers can be configured directly without enabling the broker container.

The broker does not create a default human administrator. These commands use `ordivant`; use the same project name and secret directory as the broker deployment. The administrator enters the password directly at the interactive prompt in tmux. On Windows, open a WSL session first and ensure Docker Desktop has WSL integration enabled:

```sh
wsl -- tmux new-session -A -s ordivant-idp-admin
```

On Linux, use `tmux new-session -A -s ordivant-idp-admin`. Change to the repository directory in the tmux terminal, then run the one-time bootstrap:

```sh
docker compose -f compose.yaml -f compose.identity-broker.yaml --profile identity-broker stop identity-broker
docker compose -f compose.yaml -f compose.identity-broker.yaml --profile identity-broker run --rm identity-broker bootstrap-admin user --username temp-admin
docker compose -f compose.yaml -f compose.identity-broker.yaml --profile identity-broker up -d identity-broker
```

Do not put the password in chat, commands, environment variables, or files. Sign in to the broker as the temporary administrator, create the permanent administrator, then remove the temporary account. See [Keycloak's official bootstrap and recovery guide](https://www.keycloak.org/server/bootstrap-admin-recovery).

<span id="工作階段、安全與稽核"></span>
<span id="工作阶段、安全与审核"></span>

## Sessions, security, and audit

The platform uses HttpOnly, SameSite, and Origin/CSRF protections. OIDC uses one-time state, browser binding, nonce, PKCE S256, and signature/issuer/audience validation. Client Secrets are encrypted at rest; authorization codes, ID tokens, and access tokens are not written to business databases, API responses, or sign-in logs.

Disabling an account, changing permissions, unlinking an enterprise identity, or disabling/replacing an identity provider revokes the related sessions. SSO-only mode revokes regular members' password sessions. If the IdP supports OIDC Back-Channel Logout, configure its URL as `https://APP_HOST/auth-api/oidc/backchannel-logout`. Only logout notifications that pass signature and replay checks can revoke the matching enterprise sign-in.

Signing out of Ordivant revokes the session shared by its three modules; the IdP manages sessions in other enterprise applications. Configure enterprise MFA, Conditional Access, password policies, and offboarding in the IdP. If the platform's SSO policy sets required_acr or required_amr, Identity validates claims in the signed IdP token: acr must match one required value, and amr must include every required method. These claims are checks; the IdP performs the actual MFA factor. If the IdP does not send back-channel logout, administrators must also disable the member in Ordivant; disabling an IdP account alone does not immediately invalidate an existing platform session.

The “Identity audit” records sign-ins, provisioning, settings and permission changes, linking/unlinking, and sign-outs. Administrators can view it or export Identity records under **Account and security → Enterprise governance**. This export does not include Work, Knowledge, or Code product events and contains no passwords, cookies, Client Secrets, or provider tokens.

<span id="維運與備份"></span>
<span id="运维与备份"></span>

## Operations and backups

Preserve Identity PostgreSQL, `identity_data` (including `sso.key`), and Compose service secrets. When using the broker, also preserve `identity_broker_postgres`. Back up databases with their encryption keys; a database alone cannot restore an encrypted Client Secret.

For production HTTPS, set `ORDIVANT_AUTH_COOKIE_SECURE=true`, `ORDIVANT_AUTH_ORIGINS`, and `ORDIVANT_SSO_PUBLIC_ORIGIN` explicitly. If the token or JWKS endpoint found through provider discovery uses a different host, use `ORDIVANT_SSO_ALLOWED_ENDPOINT_HOSTS` to list additional trusted hosts. The exact Google HTTPS token/JWKS hosts are supported. A private HTTP broker requires explicit `ORDIVANT_SSO_HTTP_HOSTS`; the `.env` settings above route broker backchannel connections to its internal address, and external providers do not need this exception.

For a private enterprise CA, mount its PEM trust bundle into the Identity container and set `ORDIVANT_SSO_CA_BUNDLE` to the file path; TLS certificate verification remains enabled. Compose trusts the designated `web` proxy, whose Nginx instance overwrites `X-Real-IP` so sign-in rate limits use the actual source. A custom reverse proxy must be listed by exact host/IP in `ORDIVANT_AUTH_TRUSTED_PROXY_HOSTS` and must overwrite this header; forged headers sent directly to the Identity API are ignored.

Ordivant uses OIDC as its identity integration protocol; SAML and LDAP/AD are federated through the optional Keycloak broker, and the platform has no native SAML endpoint. Identity provides SCIM 2.0 Users/Groups provisioning, but does not support bulk operations or automatically link an existing account by email. Customer-specific IdP tenants and LDAP/AD directories have not been individually verified. Before production use, follow the [administration guide](./guide/administration.md) to configure the dedicated SCIM credential, explicit group resource grants, mail, audit, and MFA performed by the IdP, then validate each organization's claims, domain restrictions, and resource authorization.
