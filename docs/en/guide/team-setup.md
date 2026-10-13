# Team setup: people, roles, scopes, and sign-in {#team-setup}

This guide explains how an Identity administrator prepares a team to use Work, Knowledge, and Code. All three products can share one human sign-in, while each product still checks its own role and resource scope.

## Understand the first administrator and members {#admin-and-members}

Each environment has its own Identity service and account store. On first use, the first person creates the single initial administrator account. There is no default account or password. Save the one-time recovery codes securely.

An administrator can manage people and invitations. A regular member can use only the product roles and Projects, Spaces, or Code Projects explicitly granted to them. Work, Knowledge, and Code are not made available simply because the same account can sign in to all three.

## Invite a member and grant access {#invite-and-scope}

1. Sign in as an administrator and open **Accounts and security** beside your name.
2. Open **Users and invitations**, then choose **Invite user**. Enter the member's name and email. Keep the Suite role as **Member** unless the person must administer users and organization access; select **Administrator** only for that responsibility.
3. In the product permissions editor, select the needed product role and exact resource scope:

   | Product | Role | Resource scope |
   | --- | --- | --- |
   | Work | Manager, Worker, or Reviewer | One or more Work Projects |
   | Knowledge | Manager, Writer, or Reader | One or more Knowledge Spaces |
   | Code | Manager, Writer, or Reader | One or more Code Projects |

4. Choose **Create invitation**. The one-time code appears once, with its expiry. Reveal and copy it, then deliver it to the intended person through an approved secure channel. Ordivant does not send invitation email. Close the dialog only after you have safely delivered the code.
5. The invitee chooses **Accept invitation** on the sign-in page, enters the code, and sets a personal password. They should then see only the resources included in their grant.

Grant the smallest role and scope that lets each person do their work. If a project or Space does not appear, an administrator should edit that member's **Product roles and resources** grant. A role in one product does not authorize access in another.

## Keep independent review between people {#independent-review}

Plan for at least two people on work that requires review: one authorized person submits evidence and a different authorized Reviewer, Manager, or Admin reviews it. The service rejects self-review.

When creating or editing a Work task, a Manager can select an authorized human teammate or Agent under **Assignee**. **Assign reviewer** also accepts either a person or an Agent. If no assignee is selected, an eligible human Worker, Manager, or Administrator can claim the task directly. A person can claim only an unassigned task or one assigned to them, never a colleague's assignment. Managers can assign work to an invited, active teammate before that person first signs in to Work.

People use their own Work account to report progress, submit evidence, mark a task blocked, or hand it off. This does not require creating an Agent, enabling Agent Runtime, or configuring an LLM. After reloading, a person can resume their work from the task's execution history. **Handoff and release** ends the current execution, records the handoff, and clears the human assignee so another eligible teammate can claim it. A blocked or returned task keeps its current assignee. Agent automation continues to use Agent-specific leases and fencing tokens. See the [Work guide](work.md) and [first-project walkthrough](first-project.md#manual-route) for the complete flow.

## Separate people, Agents, and runtime identities {#separate-identities}

The browser account is a human Identity session. An Agent has its own role and explicit product resource scope. The Pi Durable runtime has a separate machine identity used to receive authorized work. None of these identities inherits the others' permissions: inviting a person does not grant an Agent Project access, and enabling Runtime does not grant it unrestricted business access.

Create an Agent while the intended Work Project is selected; the new Agent is granted that Project. Confirm the Agent appears in that Project's Agent directory. Agent creation can reveal its scoped token once; store it only in the intended runtime configuration if your deployment needs it. Do not paste it into a task, share it as a human login, or log it. Pi Durable handles its internal Agent handoff through the configured runtime.

## Disable or restore a member {#disable-restore}

Open **Accounts and security → Users and invitations**. Use the member's **Enabled** switch to disable access; the account's existing sessions are revoked. To restore access, turn the switch on again. The person must sign in again, and their product roles and resource scopes remain subject to the administrator's grant. The currently signed-in administrator cannot disable their own account from this page; another administrator must handle that change.

When access changes, also review any separately configured Agent, repository, provider, or external tool access that the person administered. Those identities and credentials are managed separately from the human account.

## Connect enterprise SSO {#connect-sso}

An Identity administrator opens **Accounts and security → Enterprise SSO** and configures the organization's OIDC provider. The page provides a callback URL to register with the identity provider. Enter the issuer, client ID, client secret, allowed domains, and membership provisioning policy, then save and test the connection. Configure explicit product roles and resource scopes for invited or provisioned members; a matching email domain by itself does not grant project access.

To connect an existing local account, use **Explicitly link an existing account** on the same page. Select the **Ordivant account** and enter the stable **Enterprise subject (sub claim)** supplied by the identity provider. At the first enterprise sign-in, the email must still match that local account. Matching email addresses alone never merge accounts. Review the link in the table; unlinking revokes the affected enterprise session.

Test a regular member's sign-in, resource access, and sign-out before enabling an SSO-only policy. Keep the administrator recovery route available. Existing local accounts are not merged with an enterprise identity just because their email addresses match; an administrator must explicitly link the enterprise subject. The client secret is stored encrypted and is not shown again in plaintext.

Direct OIDC supports providers such as Entra ID, Google Workspace, Okta, Auth0, Keycloak, and generic OIDC. SAML and LDAP/Active Directory can use the optional Keycloak broker. See [Enterprise sign-in and identity management](../enterprise-sso.md) for provider-specific setup.

## Troubleshoot access {#team-access-troubleshooting}

| Symptom | Check |
| --- | --- |
| Invitation cannot be accepted | Confirm the code was delivered correctly, is still within its 24-hour validity, and has not already been used. Create a new invitation if it expired or was consumed. |
| Sign-in works but a product is unavailable | Check that the account is active and has a role and resource scope for that product. |
| Product opens but a Project or Space is missing | Add that exact resource to the member's scope in **Product roles and resources**. |
| A reviewer cannot review a task | Confirm they have Reviewer, Manager, or Administrator scope for the Work Project, are not the submitter, and match the task's assigned human or Agent reviewer. |
| SSO sign-in succeeds but resources are empty | Review provisioning policy, group-to-role mapping, and explicit Project/Space scopes. Authentication alone grants no resource access. |

For the task flow after access is ready, see [First project](first-project.md). For the full role guide, see [Administration](administration.md).
