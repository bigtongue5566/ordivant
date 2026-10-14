# 自行部署 Ordivant {#container-workflow}

<span id="development"></span>

用 Docker Compose 在自己的电脑或服务器安装 Ordivant。以下命令适用于 Linux、macOS，以及使用 Docker Desktop 的 Windows；不需要 PowerShell 7，也不用在主机安装 Python 或 Node.js。已加入团队的成员可直接阅读[开始使用](guide/getting-started.md)。

## 安装前准备 {#deployment-prerequisites}

准备 Git、Docker Engine 或 Docker Desktop，以及 Docker Compose v2。Docker Desktop 请使用 Linux containers。确认 `docker compose version` 能运行；首次构建需要网络连接下载镜像与依赖。

默认部署名称为 `ordivant`，网址为 `http://127.0.0.1:8088`。若需要不同名称或端口，在仓库根目录创建 `.env`，可从 `.env.compose.example` 复制。请在首次安装前选定部署名称与机密目录，之后沿用相同设置。

## 安装并启动 {#production-targets}

先选择今天需要的功能；完整安装可以之后再启用自动执行及代码服务：

| 想做的事 | 需要的服务 | 安装后的操作 |
| --- | --- | --- |
| 人工安排任务、提交成果与审核 | 下方基本安装即可 | 建立团队与第一个项目 |
| 让 Agent 使用模型自动执行 | 基本安装，加上 Runtime | 设置自己的模型连接与 Pi Agent |
| 保存规范、文档版本与决策 | 基本安装包含 Knowledge | 建立 Space，发布文档并引用版本 |
| 建立代码分支、commit 与 PR | 基本安装，加上 Gitea | 在 Code 建立项目与 repository |
| 让 Agent 执行受限命令 | Runtime，加上沙箱服务 | 建立沙箱配置并指定给 Agent |

在终端依序运行：

```sh
git clone https://github.com/ordivant-ai/ordivant.git
cd ordivant
docker compose -f compose.init.yaml run --rm init
docker compose up -d --build --wait
```

第一个 Compose 工作会创建必要的服务设置；不会创建人员账号，也不会加入示范任务。第二个命令构建并启动 Work、Knowledge、Code 与共用登录。首次构建需要一些时间；`--wait` 会等待服务健康。

打开 `http://127.0.0.1:8088/work`，依画面创建初始管理员并保存复原码。平台没有默认人员密码。同一部署中的三个产品共用登录，但项目和权限各自管理。Code 的 repository 操作还需完成下方 Gitea 设置。

### 确认可以开始使用 {#verify-installation}

运行 `docker compose ps`，确认各服务已启动且健康。浏览器应显示登录或初始管理员创建画面。若安装命令失败或页面打不开，先查看 `docker compose logs --tail 100 web identity-api work-api`；确认 Docker 已启动、8088 未被其他服务占用，并使用同一份部署设置。其他情况请见[疑难排解](guide/troubleshooting.md)。

![新部署的登录入口：创建初始管理员或接受团队邀请](/screenshots/login-zh-CN.png)

### 安装后完成第一个成果 {#after-installation}

1. 初始管理员登录后，在 Work 创建项目，例如 `LAUNCH`／「产品上线准备」。
2. 邀请另一位成员并授予该项目的适当角色；同一位提交者不能审核自己的成果。
3. 选择执行方式：人工认领与提交可先不使用外部模型；自动执行则先完成下方 Runtime 与模型设置。
4. 创建具备目标、输入和验收条件的任务，提交实际成果与来源，再由另一位授权成员审核。

[第一个项目完整教程](guide/first-project.md)提供逐栏示例、Agent 创建、人工与自动路线及审核步骤。[建立团队](guide/team-setup.md)说明邀请及三个产品的资源授权。

### 让 Agent 自动运行 {#enable-agent-execution}

若要让 Pi Agent 自动处理任务，再运行：

```sh
docker compose exec work-api python -m ordivant.bootstrap_runtime
docker compose --profile runtime up -d --build --wait runtime
```

初始化命令只创建运行服务的机器身份，不加入 DEMO 项目、Agent 或人员账号；重跑会沿用有效设置。它也可用于已有工作数据的部署。登录 Work 后，在“模型连接”设置供应商与模型，再在“Agent 名录”创建 Pi 执行者；从任务详细资料选择 Agent 并按“派发给 Agent”。详见[模型设置](model-usage.md)及[入门操作](guide/getting-started.md)。

尚未设置模型的 Run 会标示 DEMO，不调用付费模型。若只需要人工追踪、提交成果与审核，可省略运行服务。要让一般重启命令继续启用运行服务，在 `.env` 加入 `COMPOSE_PROFILES=runtime`。

## 只安装需要的产品 {#individual-products}

在全新的部署中，先于 `.env` 选择产品，再运行初始化及表中的启动命令。使用不同部署名称及机密目录，可与另一套 Ordivant 保持数据隔离；同时运行时也需指定不同 `ORDIVANT_WEB_PORT`。

| 产品 | `.env` 的产品设置 | 启动命令 |
| --- | --- | --- |
| Work | `ORDIVANT_PRODUCT_MODE=work`、`ORDIVANT_WEB_API_UPSTREAM=http://work-api:8000` | `docker compose up -d --build --wait work-api web` |
| Knowledge | `ORDIVANT_PRODUCT_MODE=knowledge`、`ORDIVANT_WEB_API_UPSTREAM=http://knowledge-api:8010` | `docker compose up -d --build --wait knowledge-api web` |
| Code | `ORDIVANT_PRODUCT_MODE=code`、`ORDIVANT_WEB_API_UPSTREAM=http://code-api:8020` | `docker compose up -d --build --wait code-api web` |

必要的登录服务与数据库会一起启动。Work 与 Knowledge 不需要 Code 或 Gitea；Code 要修改 repository 时，还需下方的 Gitea。

## 启用可选功能 {#optional-services}

### Code 与 Gitea {#enable-gitea}

在相同部署中运行：

```sh
docker compose --profile gitea up -d --wait gitea
docker compose -f compose.yaml -f compose.gitea-init.yaml --profile gitea run --build --rm gitea-init
docker compose up -d --no-deps --force-recreate --wait code-api
```

初始化工作会替 Code 设置服务连接；不会创建供人员使用的默认登录密码。完成后回到 Code 创建项目、repository 和 PR。Gitea 默认网址是 `http://127.0.0.1:3002`。在 `.env` 的 `COMPOSE_PROFILES` 保留 `gitea`，例如 `runtime,gitea`，让之后重启仍包含它。

### 运行沙箱 {#enable-sandbox}

先完成 Agent 运行服务的初始化，再构建沙箱工作镜像并启动：

```sh
docker compose -f compose.yaml -f compose.sandbox.yaml --profile sandbox build sandbox-job-image
docker compose -f compose.yaml -f compose.sandbox.yaml --profile runtime --profile sandbox up -d --build --wait runtime
```

若已启用 Gitea，在第二个命令另加 `--profile gitea`。在 `.env` 保存启用设置，后续即可沿用一般 `docker compose` 命令：

```dotenv
COMPOSE_PATH_SEPARATOR=,
COMPOSE_FILE=compose.yaml,compose.sandbox.yaml
COMPOSE_PROFILES=runtime,gitea,sandbox
```

没有启用 Gitea 时移除清单中的 `gitea`。沙箱不连接网络，也不挂载主机数据；需要保存的成果必须在 Run 结束前提交。[工具与沙箱操作](execution-usage.md#sandboxes)

### 企业登录与外部工具 {#enterprise-and-tools}

OIDC 可直接连接公司的身份服务，无须额外容器。SAML／LDAP 可使用可选的 Keycloak；依[企业 SSO 指南](enterprise-sso.md#saml-ldap-and-active-directory)启动与设置。自定义 Compose 文件时，请把它加入现有 `COMPOSE_FILE`，不要覆盖已启用的沙箱设置。

外部 MCP 工具需先在 `.env` 的 `ORDIVANT_TOOL_ALLOWED_HOSTS` 加入精确主机名称，再重启 Work 与运行服务。不要把模型密钥或人员密码放入 `.env`；模型密钥请在管理界面输入。[工具连接操作](execution-usage.md#external-mcp-tools)

### 企业机密文件与 deployment provider {#enterprise-secret-mounts}

企业整合可选用只读 Compose overlay。默认在仓库根目录建立 `.data/enterprise-secrets/identity/` 与 `.data/enterprise-secrets/code/`；如使用其他位置，先在 `.env` 设置 `ORDIVANT_ENTERPRISE_SECRETS_DIR`。将 SCIM token 与 SMTP password file 放在 `identity/`，将 Code 的 `deployment-providers.json` 及其 `token_file` 文件放在 `code/`。两个目录分别只读挂载至 Identity 与 Code 容器的 `/run/ordivant-enterprise`，不会互相暴露。

`.env.compose.example` 列有文件路径设置。常用路径为 `ORDIVANT_SCIM_TOKEN_FILE=/run/ordivant-enterprise/scim-token`、`ORDIVANT_SMTP_PASSWORD_FILE=/run/ordivant-enterprise/smtp-credential` 与 `ORDIVANT_CODE_DEPLOYMENT_CONFIG_FILE=/run/ordivant-enterprise/deployment-providers.json`。这里仅设置容器内文件路径；credential 值只存于服务器文件，不要写入 `.env`。

准备好文件并在 `.env` 设置路径后，使用相同的 Compose overlay 建置启动：

```sh
docker compose -f compose.yaml -f compose.enterprise.yaml up -d --build
```

之后启动、更新或重建也要带上相同的两个 `-f` 文件，才能保留只读挂载设定。

## 状态、停止与备份 {#actions-and-data}

从同一仓库目录，使用安装时相同的 `.env` 和 Compose 设置：

```sh
docker compose -f compose.yaml -f compose.enterprise.yaml ps
docker compose -f compose.yaml -f compose.enterprise.yaml logs --tail 100 work-api identity-api
docker compose -f compose.yaml -f compose.enterprise.yaml down
docker compose -f compose.yaml -f compose.enterprise.yaml up -d --wait
```

仅在启用 enterprise overlay 时使用上方命令；一般部署请沿用[基本容器操作方式](guide/operations.md)。使用 overlay 时，每次启动、停止、更新和重建都要带上相同的 `-f compose.yaml -f compose.enterprise.yaml`。`down` 会保留数据卷；不要加入 `-v`，否则会删除数据。备份需包含各产品数据库、数据卷、`.data/container-secrets/`（或自定义机密目录）以及 `.data/enterprise-secrets/`（或 `ORDIVANT_ENTERPRISE_SECRETS_DIR` 指定的位置）。Enterprise secrets 目录中的 Identity／Code 配置与 token 文件都必须保留，并与模型、SSO 的加密密钥一起保存。[备份与还原步骤](guide/operations.md)

只有在尚未创建任何实际账号或业务数据的全新试用环境，才可选择加入 DEMO 示例；请在运行服务初始化与首次登录之前运行：

```sh
docker compose exec work-api python -m ordivant.seed
docker compose exec knowledge-api python -m ordivant_knowledge.seed
docker compose exec code-api python -m ordivant_code.seed
```

示例会创建示范项目及 Agent，不会创建人员密码或连接模型。一般正式安装无须运行这三个命令；已有数据的环境不要重新加入示例。

## 使用 HTTPS 提供团队访问 {#https-access}

默认网页只绑定本机 `127.0.0.1:8088`。若要让团队远程使用，请在服务器设置 HTTPS 反向代理，转送到此本机地址，并在 `.env` 使用实际网址：

```dotenv
ORDIVANT_AUTH_ORIGINS=https://ordivant.example.com
ORDIVANT_AUTH_COOKIE_SECURE=true
ORDIVANT_SSO_PUBLIC_ORIGIN=https://ordivant.example.com
```

再运行 `docker compose up -d --wait` 重新应用设置。若反向代理在另一个容器内，需将它连到同一 Compose 网络并转送至 `web:80`；主机的 `127.0.0.1` 不是另一个容器的本机地址。启用企业登录时，另需核对身份服务的 Callback URL。[企业登录设置](enterprise-sso.md)
