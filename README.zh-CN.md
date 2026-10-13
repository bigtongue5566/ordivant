# Ordivant

[繁體中文](README.md) · **简体中文** · [English](README.en.md)

**开源、自行托管的 Agent 协作平台。** 将任务、知识、代码与执行证据连接为可独立审查的工作流程。

Ordivant 将项目、版本化知识、代码溯源、持久运行与独立审查整合在可自行托管的平台中。应用和文档支持繁体中文、简体中文与 English。

[文档与安装指南](https://ordivant-ai.github.io/zh-CN/) · [版本下载](https://github.com/ordivant-ai/ordivant/releases) · [问题反馈](https://github.com/ordivant-ai/ordivant/issues) · [MIT 许可](LICENSE)


[功能导览](docs/zh-CN/features.md) · [第一个项目完整教程](docs/zh-CN/guide/first-project.md) · [建立团队](docs/zh-CN/guide/team-setup.md)

[![CI](https://github.com/ordivant-ai/ordivant/actions/workflows/ci.yml/badge.svg)](https://github.com/ordivant-ai/ordivant/actions/workflows/ci.yml)
[![Docs](https://github.com/ordivant-ai/ordivant/actions/workflows/pages.yml/badge.svg)](https://github.com/ordivant-ai/ordivant/actions/workflows/pages.yml)

## 功能

| 产品 | 能力 |
| --- | --- |
| **Work** | 把任务指派给同事或 Agent、由真人认领、提交证据及独立审核 |
| **Run 与自动化** | Agent 执行控制、工作流程、可复用模板与工具隔离 |
| **Knowledge** | 多人实时共同编辑草稿、不可变发布版本、决策及来源引用 |
| **Code** | 绑定 PR head SHA 的 Ordivant 本地讨论与审查，不等同 Gitea 核准；Git 与合并由 Gitea 负责 |
| **Identity** | 人员登录、邀请、产品权限、企业 OIDC 与可选 SAML/LDAP broker |

Work 可直接读取已配置的 GitHub、GitLab 或 Gitea，不需要安装 Code。各产品可独立使用，也可部署完整 Suite。

## 快速开始

需要 **Git、Docker Engine 和 Docker Compose v2**。Windows/macOS 可使用 Docker Desktop，Linux 可使用 Docker Engine。从 repository root 执行以下 Compose 主流程：

```sh
git clone https://github.com/ordivant-ai/ordivant.git
cd ordivant
docker compose -f compose.init.yaml run --rm init
docker compose up -d --build --wait
```

打开 **http://127.0.0.1:8088**，在浏览器创建第一位人员管理员；平台没有默认人员账号或密码。默认部署名称为 `ordivant`，网页使用 port `8088`。主流程不会创建 DEMO 数据，也不会替你配置模型。

### 不使用 LLM 的真人协作

管理员可以建立 Work 项目并邀请同事；manager 或 admin 可以把任务指派给同事，有项目权限的 worker 可以认领未指派或指派给自己的任务。执行者提交成果证据后，另一位获授权的人必须独立审核。这条流程不需要 Agent、Runtime 或模型。

在 Knowledge 中，多位获授权成员可以实时共同编辑同一份草稿；只有已保存的草稿才能发布为不可变版本。Agent 也可通过 REST 或 MCP 读写同一份草稿上下文。Code 可以保存绑定 PR head SHA 的 Ordivant 讨论与审查记录；Git 操作需要 Gitea，且合并与 Gitea 自身的批准仍由 Gitea 负责。

管理员可在模型管理页设置 provider、API key 和 model，详见[模型连接指南](docs/zh-CN/model-usage.md)。若要让 Agent 执行工作，还需依照[容器部署指南](docs/zh-CN/containers.md)另行启用 Runtime。没有有效模型连接时，Run 会标记为 DEMO；这不代表已调用付费模型。容器指南也介绍可选的 Gitea、Sandbox、备份和 HTTPS。

```sh
docker compose ps
docker compose down
```

`docker compose down` 会停止服务并保留数据卷。除非确定要删除数据，否则不要添加 `-v`。GitHub Pages 是静态文档站；平台服务需自行部署。

## 语言

可在登录页及产品导航下方切换**繁体中文、简体中文与 English**。选择保存在当前浏览器，并在 Work、Knowledge 与 Code 间共用；切换语言不会清除表单。用户创建的任务、文档、消息与代码会保留原文。文档站右上角可切换同一篇文章的语言。详见[语言与翻译](docs/zh-CN/i18n.md)。

## 文档

| 开始与操作 | 管理与部署 |
| --- | --- |
| [用户入门](docs/zh-CN/guide/getting-started.md) | [自行托管与容器部署](docs/zh-CN/containers.md) |
| [Work 任务协作](docs/zh-CN/guide/work.md) | [管理员与权限](docs/zh-CN/guide/administration.md) |
| [Knowledge 文档与引用](docs/zh-CN/guide/knowledge.md) | [账号与企业登录](docs/zh-CN/human-login.md)／[企业 SSO](docs/zh-CN/enterprise-sso.md) |
| [Code 与版本控制](docs/zh-CN/guide/code.md) | [模型连接](docs/zh-CN/model-usage.md) |
| [Run 与自动化](docs/zh-CN/execution-usage.md) | [运维与备份](docs/zh-CN/guide/operations.md)／[问题排查](docs/zh-CN/guide/troubleshooting.md) |

## 版本与边界

当前版本为 **v0.1.0 早期公开版**。Knowledge 使用文本搜索；Code 的状态收据不代表内置 CI 测试结果。企业 IdP、Git、模型供应商和公开 HTTPS 环境仍需由部署团队根据实际设置验证。已知限制与后续规划见[路线图](docs/zh-CN/roadmap.md)和[版本说明](CHANGELOG.md)。

## 参与项目

用户文档、开发环境、测试与贡献规范请见 [CONTRIBUTING](CONTRIBUTING.md)。漏洞请通过[私密安全通告](https://github.com/ordivant-ai/ordivant/security/advisories/new)回报。Ordivant 源代码采用 [MIT](LICENSE) 许可；第三方软件包与可选服务保留各自许可，详见 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)。
