<span id="帳號與登入"></span>
<span id="账号与登录"></span>

# Accounts and sign-in

Work, Knowledge, and Code share accounts within the same environment. On first startup, open the workspace and select “Create administrator account.” Enter your name, email, and a password of at least 12 characters, then confirm. The system permits only one initial administrator; there is no default account or password. Enter the password directly in the web page. Do not send it to an Agent.

After creation, you are signed in and shown ten one-time recovery codes. They are hidden by default and shown only after account creation or a password change. Store them somewhere secure. Every password change or recovery invalidates all previous recovery codes.

Afterward, sign in with “Email” and “Password.” Your session persists when you reload the page or switch between the three products. Signing out immediately revokes the server-side session. You must sign in again after 30 minutes of inactivity or 12 hours from sign-in.

<span id="帳號與安全性"></span>
<span id="账号与安全性"></span>

## Accounts and security

The account menu at the bottom of the sidebar opens **Account settings** for your own profile, security, and API/MCP access. Administrators have a separate **Organization administration** entry in the sidebar for users and invitations, enterprise SSO, governance, and identity audit. These are separate screens, with left navigation on desktop and a selector on small screens. Refreshing preserves the selected settings page. You can:

- View account information and change your password. Other signed-in devices are invalidated as soon as the change succeeds.
- View your sessions, revoke other sign-ins, or sign out all sessions.

Under **Organization administration**, administrators can invite members, disable accounts, and change product roles and access scopes for Projects and Knowledge Spaces.

An administrator creates an invitation code that expires after 24 hours and can be used once. The administrator gives the code to the member; the platform does not pretend to send an email. The member selects “Accept invitation” on the sign-in page, enters the code, and sets a password to activate the granted access.

Members can access only the Work Projects, Knowledge Spaces, and Code Projects explicitly granted to them. Administrators create new Projects and Knowledge Spaces. Changing permissions or disabling an account revokes its existing sessions, requiring the member to sign in again.

If you forget your password, select “Use a recovery code” and enter your email, one unused recovery code, and a new password. The platform revokes all previous sign-ins, consumes that code, and provides new recovery codes. Without a recovery code, this recovery flow cannot reset the password.

<span id="環境與部署"></span>
<span id="环境与部署"></span>

## Environments and deployment

Open Ordivant at the deployment URL provided by your administrator. Each deployment stores accounts and business data separately; create an initial administrator in each environment you use. `-Seed` adds only clearly labeled business demo data; it does not create a human password account.

The Docker helper creates the Identity API, a separate PostgreSQL database, and internal service credentials. Products check sign-in state through the internal Identity service; they do not read the Identity database. Browser sessions use HttpOnly/SameSite cookies, and write operations check Origin and CSRF. Agent REST/MCP continues to use scoped Bearer tokens.

External deployments require HTTPS, `ORDIVANT_AUTH_COOKIE_SECURE=true`, and an explicit `ORDIVANT_AUTH_ORIGINS`. The local exception permits HTTP only for literal localhost, `127.0.0.1`, or `::1` origins. Sign-in and human business authorization are denied if configuration is incomplete or Identity is offline. If a product database has multiple organizations, configure `ORDIVANT_WORK_IDENTITY_ORG_ID`, `ORDIVANT_KNOWLEDGE_IDENTITY_ORG_ID`, and `ORDIVANT_CODE_IDENTITY_ORG_ID` in Compose/the launcher; each is passed to that product's own `ORDIVANT_IDENTITY_ORG_ID`. Do not mix projects from different organizations into one sign-in scope.

Preserve and back up Identity volumes, business volumes, and the service-secret storage configured for the deployment together. Stopping containers does not delete data. Enterprise settings also require `sso.key` from the Identity data volume for decryption during restoration.

<span id="企業-sso"></span>
<span id="企业-sso"></span>

## Enterprise SSO

An administrator configures enterprise OIDC under “Organization administration → Enterprise SSO.” Supported providers include Entra ID, Google Workspace, Okta, Auth0, Keycloak, and generic OIDC. SAML and LDAP/AD can connect through the optional Keycloak broker. See [Enterprise sign-in and identity management](enterprise-sso.md) for setup, group authorization, and container operations.

After it is enabled, the sign-in page shows an enterprise sign-in button. Password and MFA checks happen at the enterprise identity service. On first sign-in, members must meet the allowed-domain and invitation/JIT policies and receive explicit product scopes. The three modules share one platform session; successful sign-in does not grant access to every Project. SSO accounts do not use local password recovery.

Enabling “Enterprise SSO only” revokes password sessions for regular members; the local administrator entry point remains as a recovery path. Existing local accounts are not automatically merged just because their email addresses match. An administrator must explicitly link the enterprise subject.
