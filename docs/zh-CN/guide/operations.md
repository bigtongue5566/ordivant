<span id="維運與備份"></span>
<span id="运维与备份"></span>

# 运维与备份 {#operations-and-backups}

本指南说明如何使用 Docker Compose 管理服务、备份数据及启用 Agent 自动执行。所有 Compose 命令都从 repository root 运行。默认部署名称为 `ordivant`，由 `compose.yaml` 固定；默认不需要创建 `.env`。如需自定义名称，请在 repository root 创建 `.env`，设置 `COMPOSE_PROJECT_NAME`，并在该部署期间保持不变。服务机密默认位于 `.data/container-secrets/`；如果设置了 `ORDIVANT_SECRETS_DIR`，请备份该实际路径。使用 enterprise overlay 时，还要备份 `.data/enterprise-secrets/` 或 `ORDIVANT_ENTERPRISE_SECRETS_DIR` 指定的位置。

<span id="服務狀態與更新"></span>
<span id="服务状态与更新"></span>

## 服务状态与更新 {#service-status-and-updates}

```sh
docker compose ps
docker compose logs --tail 100
docker compose up -d --build --wait
docker compose down
```

默认网址为 `http://127.0.0.1:8088`。上述命令使用默认部署名称 `ordivant`。停止服务会保留数据卷和机密文件，但不等于备份；`docker compose down -v` 会删除数据卷并造成数据丢失。

默认网页端口是 `8088`，Gitea 是 `3002`。若端口冲突，可在 repository root 的 `.env` 中设置 `ORDIVANT_WEB_PORT` 或 `ORDIVANT_GITEA_PORT`。如果安装时启用了 Runtime、Gitea 等 profile，每条命令都要使用相同的 `--profile` 选项。如果启用 Sandbox，所有命令也必须使用相同的 Compose 文件组合 `-f compose.yaml -f compose.sandbox.yaml`。允许团队从远程访问前，请设置 HTTPS、正式网站来源和安全 Cookie，详见[容器部署指南](../containers.md)。

如果使用 `compose.enterprise.yaml`，所有 Compose 命令（包括启动、停止、更新和备份操作）都要带上相同的 `-f compose.yaml -f compose.enterprise.yaml`，以保留 Identity／Code 只读挂载并维持一致的服务设置。

<span id="需要備份的資料"></span>
<span id="需要备份的数据"></span>

## 需要备份的数据 {#data-to-back-up}

备份时以 Compose project label 找出该环境的所有 volumes，依数据库产品与 data volume 作为同一组保存。典型完整套件包含：

| 区域 | Compose 数据卷／主机文件 | 内容 |
|---|---|---|
| Identity | `identity_postgres`、`identity_data` | 人员、会话、SSO 设置与 `sso.key` |
| Work | `work_postgres`、`work_data` | Work 任务、Agent、Run、Runtime 状态及 `model-settings.key` |
| Knowledge | `knowledge_postgres`、`knowledge_data` | Space 文档版本、决策与范围数据 |
| Code | `code_postgres`、`code_data` | Code 范围、repository 绑定、PR 与状态收据 |
| Gitea（若启用） | `gitea_data` | Repository、分支、提交、PR 的实际 Git 数据 |
| Keycloak broker（若激活） | `identity_broker_postgres` | Broker realm 与连接设置 |
| Compose 机密与设置 | `.data/container-secrets/` 或 `ORDIVANT_SECRETS_DIR`；使用 enterprise overlay 时还包括 `.data/enterprise-secrets/` 或 `ORDIVANT_ENTERPRISE_SECRETS_DIR`；自定义部署还包含 `.env` | 数据库密码／URL、Runtime 和内部服务 token、Gitea 设置、Identity／Code enterprise 配置与 token 文件、Compose 项目名称与端口设置 |

实际数据卷清单会依启用的产品和配置文件而异。Work 的 `model-settings.key` 用于解密模型及 MCP 工具连接设置；Identity 的 `sso.key` 用于解密企业 IdP 设置。加密密钥必须与对应数据库和数据卷一起备份，不可单独更换，否则无法解密已有密文。Agent 的执行状态位于 Work 数据卷。每次 sandbox 的工作目录都是临时数据，不是成果保存位置。

可用 Compose 项目标记查出此环境实际创建的数据卷名称：

```sh
docker volume ls --filter "label=com.docker.compose.project=ordivant"
```

如果自定义了 `COMPOSE_PROJECT_NAME`，请将筛选值改为 `.env` 中的名称。请将列出的所有产品、Identity 及已启用 profile 的数据卷纳入备份；实际清单以命令结果为准，不要只依范例名称猜测。

<span id="一致性與還原"></span>
<span id="一致性与还原"></span>

## 一致性与还原 {#consistency-and-restoration}

1. 确认备份目标是正确的 Compose 项目名称。使用 `docker compose down` 停止该环境，让文件数据与 PostgreSQL 数据卷保持一致；这不会删除数据。
2. 使用组织批准的 Docker 数据卷快照或备份工具，备份该项目标记下需要的全部数据卷。也要一并保存默认的 `.data/container-secrets/` 目录，或 `ORDIVANT_SECRETS_DIR` 指定的实际目录；如果使用 enterprise overlay，还须保存 `.data/enterprise-secrets/` 或 `ORDIVANT_ENTERPRISE_SECRETS_DIR` 指定的目录，其中包含 Identity／Code 配置与 token 文件。如有自定义 `.env`，也应加密保存。
3. 将备份和主机上的机密目录加密保存、限制访问，并定期测试还原。不要把 `.data`、初始设置 token 或 Gitea／服务凭证上传到公开 issue、聊天或 Git。
4. 还原时先恢复同名 Compose 数据卷及原有机密，再使用相同部署名称、profile 和 Compose 文件组合启动。不要混用不同环境的加密密钥和数据库。

若使用单一产品或部分产品模式，请备份该模式创建的所有数据卷及共用 Identity 数据卷。Knowledge 引用和 Code PR 的来源追溯信息不能代替目标产品数据备份；也需保存来源产品及实际 Gitea 数据。

<span id="執行與排程"></span>
<span id="运行与调度"></span>

## 运行与调度 {#execution-and-scheduling}

首次安装请先按照[容器部署指南](../containers.md)完成 Compose 初始化和服务启动。一般正式安装接着在浏览器创建第一位人员管理员，再由管理员在模型管理页设置 provider、API key 和 model；只有实际派发任务后才会调用已配置模型。没有有效模型时，Run 会标记为 DEMO。

如果要在全新环境试用 DEMO，请在 Compose 初始化和服务启动后、首次登录及首次运行 `bootstrap_runtime` 之前创建示例数据。此选项只适用于尚未创建任何真实数据的全新试用环境；只运行所需产品对应的命令。Seed 完成后再在浏览器创建第一位人员管理员。既有部署不可执行 Seed：

```sh
docker compose exec work-api python -m ordivant.seed
docker compose exec knowledge-api python -m ordivant_knowledge.seed
docker compose exec code-api python -m ordivant_code.seed
```

要启用 Agent Runtime，请确认 Work API 已健康，然后运行：

```sh
docker compose exec work-api python -m ordivant.bootstrap_runtime
docker compose --profile runtime up -d --build --wait runtime
```

`bootstrap_runtime` 只初始化 Runtime 机器身份，不会创建 DEMO、人员或项目，可在已有正式数据的环境中运行。如果已存在有效的 `runtime_token`，重新运行不会轮换该 token。如果同时使用 Sandbox，启动 Runtime 时必须沿用安装时的 Compose 文件和 profile：

```sh
docker compose -f compose.yaml -f compose.sandbox.yaml --profile runtime --profile sandbox up -d --build --wait runtime
```

定期间隔工作流程需要 Work Runtime 持续运行。服务停止期间错过的计划不会全部补跑；同一计划已有进行中的工作流程时，不会重叠启动。每次沙箱工作区都有资源限制，并在 Run 结束时清理，不应用来长期保存文件。Run、成果物和 Knowledge 文档请通过相应产品保存。运行控制、工具允许连接的主机及沙箱限制见[运行使用指南](../execution-usage.md)。
