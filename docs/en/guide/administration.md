<span id="管理員、角色與企業登入"></span>
<span id="管理员、角色与企业登录"></span>

# Administrators, roles, and enterprise sign-in

Browser sign-in is provided by the shared Identity service. Work, Knowledge, and Code each enforce their own product roles and resource scopes. Successful SSO sign-in creates a human platform session; it does not issue an Agent token, Runtime identity, or Gitea credential to the user.

<span id="初始管理員與成員"></span>
<span id="初始管理员与成员"></span>

## First administrator and members

Each Compose project or environment has its own Identity data. Create the first administrator for that environment when you first open the web application; there is no default human account. Administrators can invite members, disable accounts, revoke sessions, and grant product roles plus explicit Work Project, Knowledge Space, and Code Project scopes.

When SMTP is configured, Identity queues and sends invitation and local-account recovery email. Otherwise it does not attempt to send mail, so an administrator must securely provide the one-time invitation code another way. Mail links expire and can be used only once; local accounts can still use their recovery codes. Members can see only explicitly authorized resources. Administrators create new Projects and Spaces.

<span id="產品角色"></span>
<span id="产品角色"></span>

## Product roles

| Product | Role | Main permissions |
|---|---|---|
| Work | Manager | Manages work and execution schedules in authorized Projects |
| Work | Worker | Runs authorized tasks and submits results |
| Work | Reviewer | Independently reviews results; cannot accept their own submission |
| Knowledge | Manager | Manages documents and decisions in authorized Spaces; only Identity administrators create Spaces |
| Knowledge | Writer | Creates documents, publishes versions, and records decisions |
| Knowledge | Reader | Searches and reads authorized Spaces |
| Code | Manager | Manages authorized Code Projects |
| Code | Writer | Creates repositories and changes in authorized Projects |
| Code | Reader | Inspects Projects, repositories, pull requests, and status receipts |

The organization's Identity `admin` manages people and grants; product roles are a separate authorization layer. A person may have different roles or scopes in each product. Agents use separate scoped identities; access to one product does not imply access to another.

<span id="設定企業-oidc"></span>
<span id="设置企业-oidc"></span>

## Configure enterprise OIDC

1. Sign in to the environment as an administrator and open “Accounts and security → Enterprise SSO.”
2. Create a confidential OIDC web application in your enterprise IdP and enable Authorization Code with PKCE S256.
3. Register the complete Callback URL shown by Ordivant as a Redirect URI. Do not use wildcards.
4. Enter the organization's Issuer, Client ID, Client Secret, allowed domains, and membership provisioning policy. To use groups, configure the IdP groups claim and explicit product/scope mappings.
5. Save, test the connection, then test a regular member's sign-in, product access, and sign-out. Confirm the administrator recovery path still works before considering SSO-only mode.

Members use invitations or an explicitly configured JIT policy; matching an email domain alone does not grant organization-wide access. The Client Secret is encrypted at rest, and forms never refill its plaintext. Direct OIDC is a sign-in protocol. Organizations with only SAML or LDAP/Active Directory can use the optional Keycloak broker. When required_acr or required_amr is enabled, member sign-in must use SSO-only policy. Identity checks assurance claims in the verified IdP token; the platform does not provide an MFA factor itself. See [enterprise sign-in](../enterprise-sso.md) for details.

## SCIM, MFA, mail, and audit governance {#enterprise-provisioning-mfa-mail-audit}

Administrators can open **Account and security → Enterprise governance** from the top-right account menu to check SCIM and mail status, configure group grants and audit retention, export Identity audit records, and inspect or retry retryable mail. The screen displays the SCIM endpoint. A deployment administrator must separately provide ORDIVANT_SCIM_TOKEN_FILE and configure that dedicated bearer credential in the enterprise provisioning service. SCIM supports Users and Groups; SCIM bulk operations are not supported.

Before saving a group grant, add the exact group name supplied by the IdP and use the permission editor to select explicit product roles and resource IDs. SCIM groups cannot grant organization-admin rights, and wildcard resource scopes are rejected. A regular SCIM User PATCH that attempts to change SCIM-managed product permissions returns HTTP 409; it cannot manually switch permission ownership. Change the IdP group membership or its mapping here, then let SCIM synchronize the grant. When explicitly linking an OIDC account, use `managed_permissions=false` so SCIM remains the owner of group-derived permissions. If SCIM tries to create a user whose email already belongs to an Ordivant account, provisioning returns a conflict; it does not automatically claim, merge, or change that account. Resolve it through an explicit administrator-managed account-linking or migration process first. Disabling a SCIM user or changing group grants revokes the user's existing Identity sessions.

Docker Compose deployments may opt into the read-only `compose.enterprise.yaml` overlay, which mounts separate secret directories for Identity and Code. Put the SCIM token and SMTP password file in Identity's mount; put Code's deployment configuration and its token files in Code's mount. See the [container guide](../containers.md#enterprise-secret-mounts) and [Code deployment evidence setup](code.md#upstream-governance-and-deployment-evidence). Do not put secret values in `.env`.

MFA is performed by the enterprise IdP. Under **Account and security → Enterprise SSO**, set the required authentication assurance acr values and authentication methods amr (for example, mfa), then require SSO-only sign-in for members. The acr claim must match one of the configured values; amr must include every configured method. Confirm that the IdP issues these claims in its verified sign-in token, then test both member sign-in and the administrator recovery path.

Before invitation and account-recovery mail can be sent, a deployment administrator must configure SMTP host, port, sender, TLS, and, when needed, the username and password file (ORDIVANT_SMTP_HOST, ORDIVANT_SMTP_PORT, ORDIVANT_SMTP_SENDER, ORDIVANT_SMTP_STARTTLS, ORDIVANT_SMTP_USERNAME, and ORDIVANT_SMTP_PASSWORD_FILE). Production requires STARTTLS. Identity does not send mail when required settings are absent. Check the mail queue under **Enterprise governance**; pending or failed messages can be retried, while expired messages cannot. Resource-follow and collaboration-center notices appear in Ordivant and are not sent through this SMTP channel.

Audit export is an administrator-only JSONL file containing only fields permitted for Identity audit export. It is not a combined export of Work, Knowledge, and Code events. The UI paginates automatically but caps an export at 100,000 records or 50 MiB; if either limit is exceeded, it refuses to produce a partial file. Use the Identity admin API for larger exports: `GET /auth-api/audit/export` accepts `limit=1..10000`. Continue with the paired `before` and `before_id` cursor values from response headers `X-Next-Before` and `X-Next-Before-Id`. Export records you need to retain before setting a retention period from 30 to 3,650 days and explicitly applying it; applying retention deletes Identity audit rows older than the period.

<span id="agent-與模型連線"></span>
<span id="agent-与模型连接"></span>

## Agents and model connections

Organization administrators configure providers, API URLs, keys, and models, then choose an organization default. When creating or editing an Agent, inherit that default or select another configured model. Saved keys and tool access tokens are never refilled in plaintext; enter a new value to replace one. See [model settings](../model-usage.md) and the [Run and tools guide](../execution-usage.md).

Before production use, review TLS, trusted origins, allowed membership provisioning policies, Project/Space scopes, and recovery-code storage. SSO does not replace server-side authorization in each product.
