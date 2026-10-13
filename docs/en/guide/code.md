# Ordivant Code

Use Ordivant Code to manage repository branches, file changes, commits, and pull requests, and to keep version-bound discussion and review records in Ordivant. Gitea remains responsible for Git history, merges, and its own approvals. Human Code collaboration does not need an LLM; Git features require a deployed Gitea service.

![Code pull request for changes in a real demonstration repository](/screenshots/code-en.png)

<span id="啟用-gitea"></span>
<span id="激活-gitea"></span>

## Enable Gitea {#enable-gitea}

Gitea is optional. If it is not enabled, Code cannot create or update repositories, branches, commits, pull requests, or statuses. For a Docker Compose installation, ask your deployment administrator to enable the Gitea service in Compose. Ordivant PR discussions and reviews are a Code feature and do not replace Gitea. See the [container deployment guide](../containers.md) for deployment options.

<span id="repository-到-pr"></span>

## From repository to pull request {#from-repository-to-pull-request}

1. Select a Code project you are authorized to use. A **Manager** can create and manage projects; contact an administrator if you cannot find the project you need.
2. A **Writer** can create a private repository in the project or select an existing repository.
3. Choose a source branch and create a working branch. Add or update files on that branch, then enter a clear commit message and commit the changes.
4. Open a PR by choosing the head and base branches and entering a title and description. Attach a Work, Knowledge, or external reference so reviewers can understand the context.
5. Inspect the changes, references, and Gitea status in the PR details. Under **Discussion and review records**, add a comment or submit an Ordivant review such as a comment, request for changes, or approval. Each record identifies its author as a person or Agent.
6. Follow your organization's Gitea process for formal review and merge. Creating a PR or submitting an Ordivant review does not approve a Work task or create a Gitea approval.

Code project roles determine what you can do: **Manager** manages the project, **Writer** creates repositories, branches, commits, and PRs in authorized projects, and **Reader** views project data. A source reference describes a work relationship; it does not grant access to Work, Knowledge, or another system.

<span id="pr-狀態與證據"></span>
<span id="pr-状态与证据"></span>

## PR status and evidence {#pr-status-and-evidence}

**Report status** can mark a commit as pending, success, failure, or error. A status labeled `agent_reported` means an Agent reported the result; it does not mean a test actually ran. `gitea_webhook` means the status came from a Gitea webhook. To confirm what ran and its result, open the corresponding check in Gitea.

PR status helps track work, but it does not replace actual testing, Gitea review, or the merge process.

Each Ordivant review is bound to the PR **head SHA** at the time it is submitted. If the PR head changes, the earlier review remains in the history but is marked **Expired**. Reload the review records, inspect the current head, and submit a new record. Ordivant discussion and review records are not Gitea approvals, CI results, or Work task acceptance.

People and Agents can both participate according to their Code project permissions. Viewing and writing these records does not require an Agent or model; Git repository and PR operations still require an available Gitea service. See [Team setup](team-setup.md) for human roles and Project scopes.
