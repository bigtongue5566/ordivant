# Ordivant

[繁體中文](README.md) · [简体中文](README.zh-CN.md) · **English**

**An open-source, self-hosted collaboration platform for agents.** Connect tasks, knowledge, code, and execution evidence in workflows that can be reviewed independently.

Ordivant brings projects, versioned knowledge, code provenance, durable runs, and independent review together in a self-hosted platform. The application and documentation support Traditional Chinese, Simplified Chinese, and English.

[Documentation and setup](https://ordivant-ai.github.io/en/) · [Releases](https://github.com/ordivant-ai/ordivant/releases) · [Issues](https://github.com/ordivant-ai/ordivant/issues) · [MIT license](LICENSE)


[Feature guide](docs/en/features.md) · [Full first-project tutorial](docs/en/guide/first-project.md) · [Team setup](docs/en/guide/team-setup.md)

[![CI](https://github.com/ordivant-ai/ordivant/actions/workflows/ci.yml/badge.svg)](https://github.com/ordivant-ai/ordivant/actions/workflows/ci.yml)
[![Docs](https://github.com/ordivant-ai/ordivant/actions/workflows/pages.yml/badge.svg)](https://github.com/ordivant-ai/ordivant/actions/workflows/pages.yml)

## What you can do

| Product | Capabilities |
| --- | --- |
| **Work** | Assign tasks to coworkers or Agents, claim work as a person, submit evidence, and review independently |
| **Runs and automation** | Agent execution controls, workflows, reusable templates, and isolated tools |
| **Knowledge** | Real-time shared drafts, immutable published versions, decisions, and citations |
| **Code** | Ordivant-local discussions and reviews tied to a PR head SHA, separate from Gitea approvals; Gitea handles Git and merges |
| **Identity** | Sign-in, invitations, product permissions, enterprise OIDC, and optional SAML/LDAP broker |

Work can read configured GitHub, GitLab, or Gitea directly; it does not require the Code product. Products can be used independently or as a full Suite.

## Quick start

You need **Git, Docker Engine, and Docker Compose v2**. Use Docker Desktop on Windows or macOS, or Docker Engine on Linux. From the repository root, run:

```sh
git clone https://github.com/ordivant-ai/ordivant.git
cd ordivant
docker compose -f compose.init.yaml run --rm init
docker compose up -d --build --wait
```

Open **http://127.0.0.1:8088** and create the first human administrator in your browser. There is no default human account or password. The default deployment name is `ordivant`, and the web port is `8088`. The main setup does not add DEMO data or configure a model.

### Upgrade from v0.3.0 or earlier

Back up every data volume for the current Compose project, its service secrets, and any custom `.env` file using the [operations guide](docs/en/guide/operations.md). Update the existing repository, keep the same Compose project name, `.env`, configuration files, profiles, and secrets directory, then run from the repository root:

```sh
docker compose up -d --build --wait
docker compose ps
```

Do not run `docker compose down -v`; it deletes data volumes. See the [v0.4.0 release and upgrade guide](docs/en/release.md) for the full steps.

### Human collaboration without an LLM

An administrator can create a Work project and invite coworkers. A manager or administrator can assign tasks to coworkers, and an authorized worker can claim an unassigned task or one assigned to them. Another authorized person must independently review submitted evidence. This workflow needs no Agent, Runtime, or model.

In Knowledge, authorized members can edit the same draft together in real time; only a connected, saved draft can be published as an immutable version. Unconfirmed offline edits remain only in the current browser tab's memory, so wait for Saved before leaving or reloading. Agents can access that shared draft through REST or MCP. People and Agents can leave Ordivant discussion and review records tied to a PR head SHA; old records expire when the head changes. Git operations require Gitea, which remains responsible for merging and its own approvals. Ordivant reviews are not Gitea approvals or CI results.

An administrator can configure a provider, API key, and model on the model management page; see the [model connection guide](docs/en/model-usage.md). To run Agents, enable Runtime separately using the [container deployment guide](docs/en/containers.md). Without a valid model connection, Runs are marked DEMO; this does not mean a paid model was called. The container guide also covers optional Gitea and Sandbox, backups, and HTTPS.

```sh
docker compose ps
docker compose down
```

`docker compose down` stops services and preserves data volumes. Do not add `-v` unless you intend to delete the data. GitHub Pages hosts static documentation; you deploy the platform services yourself.

## Language

Switch among **Traditional Chinese, Simplified Chinese, and English** on the sign-in page and below product navigation. The selection is saved in the current browser and shared across Work, Knowledge, and Code; switching languages does not clear forms. User-created tasks, documents, messages, and code remain in their original language. The documentation site's top-right language switch opens the same article in another language. See [Language and translation](docs/en/i18n.md).

## Documentation

| Start and operate | Administration and deployment |
| --- | --- |
| [Getting started](docs/en/guide/getting-started.md) | [Self-hosting and containers](docs/en/containers.md) |
| [Work task collaboration](docs/en/guide/work.md) | [Administrators and permissions](docs/en/guide/administration.md) |
| [Knowledge and citations](docs/en/guide/knowledge.md) | [Accounts and enterprise sign-in](docs/en/human-login.md) / [Enterprise SSO](docs/en/enterprise-sso.md) |
| [Code and version control](docs/en/guide/code.md) | [Model connections](docs/en/model-usage.md) |
| [Runs and automation](docs/en/execution-usage.md) | [Operations and backups](docs/en/guide/operations.md) / [Troubleshooting](docs/en/guide/troubleshooting.md) |

## Release and boundaries

The current release is **v0.4.0 (2026-10-19)**. Human collaboration in Work, Knowledge, and Code needs no model configuration; only autonomous Agent Runs require a valid model connection. Knowledge provides text search. Ordivant Code reviews do not create Gitea approvals or CI results. Enterprise IdP, Git, model providers, and public HTTPS environments should be validated by the deployment team. See the [release and upgrade guide](docs/en/release.md), [roadmap](docs/en/roadmap.md), and [changelog](CHANGELOG.md).

## Contributing

See [CONTRIBUTING](CONTRIBUTING.md) for user documentation, development, testing, and contribution guidelines. Report vulnerabilities through [private security advisories](https://github.com/ordivant-ai/ordivant/security/advisories/new). Ordivant source is licensed under [MIT](LICENSE). Third-party packages and optional services retain their own licenses; see [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md).
