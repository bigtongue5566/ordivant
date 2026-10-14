# 自行部署 Ordivant {#container-workflow}

<span id="development"></span>

用 Docker Compose 在自己的電腦或伺服器安裝 Ordivant。以下命令適用於 Linux、macOS，以及使用 Docker Desktop 的 Windows；不需要 PowerShell 7，也不用在主機安裝 Python 或 Node.js。已加入團隊的成員可直接閱讀[開始使用](guide/getting-started.md)。

## 安裝前準備 {#deployment-prerequisites}

準備 Git、Docker Engine 或 Docker Desktop，以及 Docker Compose v2。Docker Desktop 請使用 Linux containers。確認 `docker compose version` 能執行；首次建置需要網路連線下載映像與依賴。

預設部署名稱為 `ordivant`，網址為 `http://127.0.0.1:8088`。若需要不同名稱或連接埠，在倉庫根目錄建立 `.env`，可從 `.env.compose.example` 複製。請在首次安裝前選定部署名稱與機密目錄，之後沿用相同設定。

## 安裝並啟動 {#production-targets}

先選擇今天需要的功能；完整安裝可以之後再啟用自動執行及程式碼服務：

| 想做的事 | 需要的服務 | 安裝後的操作 |
| --- | --- | --- |
| 人工安排任務、提交成果與審核 | 下方基本安裝即可 | 建立團隊與第一個專案 |
| 讓 Agent 使用模型自動執行 | 基本安裝，加上 Runtime | 設定自己的模型連線與 Pi Agent |
| 保存規格、文件版本與決策 | 基本安裝包含 Knowledge | 建立 Space，發布文件並引用版本 |
| 建立程式碼分支、commit 與 PR | 基本安裝，加上 Gitea | 在 Code 建立專案與 repository |
| 讓 Agent 執行受限命令 | Runtime，加上沙箱服務 | 建立沙箱設定檔並指定給 Agent |

在終端機依序執行：

```sh
git clone https://github.com/ordivant-ai/ordivant.git
cd ordivant
docker compose -f compose.init.yaml run --rm init
docker compose up -d --build --wait
```

第一個 Compose 工作會建立必要的服務設定；不會建立人員帳號，也不會加入示範任務。第二個命令建置並啟動 Work、Knowledge、Code 與共用登入。首次建置需要一些時間；`--wait` 會等待服務健康。

開啟 `http://127.0.0.1:8088/work`，依畫面建立初始管理員並保存復原碼。平台沒有預設人員密碼。同一部署中的三個產品共用登入，但專案和權限各自管理。Code 的 repository 操作還需完成下方 Gitea 設定。

### 確認可以開始使用 {#verify-installation}

執行 `docker compose ps`，確認各服務已啟動且健康。瀏覽器應顯示登入或初始管理員建立畫面。若安裝命令失敗或畫面打不開，先查看 `docker compose logs --tail 100 web identity-api work-api`；確認 Docker 已啟動、8088 未被其他服務占用，並使用同一份部署設定。其他情況請見[疑難排解](guide/troubleshooting.md)。

![新部署的登入入口：建立初始管理員或接受團隊邀請](/screenshots/login-zh-TW.png)

### 安裝後完成第一個成果 {#after-installation}

1. 初始管理員登入後，在 Work 建立專案，例如 `LAUNCH`／「產品上線準備」。
2. 邀請另一位成員並授予該專案的適當角色；同一位提交者不能審核自己的成果。
3. 選擇執行方式：人工認領與提交可先不使用外部模型；自動執行則先完成下方 Runtime 與模型設定。
4. 建立具備目標、輸入和驗收條件的任務，提交實際成果與來源，再由另一位授權成員審核。

[第一個專案完整教學](guide/first-project.md)提供逐欄範例、Agent 建立、人工與自動路線及審核步驟。[建立團隊](guide/team-setup.md)說明邀請及三產品的資源授權。

### 讓 Agent 自動執行 {#enable-agent-execution}

若要讓 Pi Agent 自動處理任務，再執行：

```sh
docker compose exec work-api python -m ordivant.bootstrap_runtime
docker compose --profile runtime up -d --build --wait runtime
```

初始化命令只建立執行服務的機器身分，不加入 DEMO 專案、Agent 或人員帳號；重跑會沿用有效設定。它也可用於已有工作資料的部署。登入 Work 後，在「模型連線」設定供應商與模型，再在「Agent 名錄」建立 Pi 執行者；從任務詳細資料選擇 Agent 並按「派發給 Agent」。詳見[模型設定](model-usage.md)及[入門操作](guide/getting-started.md)。

尚未設定模型的 Run 會標示 DEMO，不呼叫付費模型。若只需要人工追蹤、提交成果與審核，可省略執行服務。要讓一般重啟命令繼續啟用執行服務，在 `.env` 加入 `COMPOSE_PROFILES=runtime`。

## 只安裝需要的產品 {#individual-products}

在全新的部署中，先於 `.env` 選擇產品，再執行初始化及表中的啟動命令。使用不同部署名稱及機密目錄，可與另一套 Ordivant 保持資料隔離；同時運行時也需指定不同 `ORDIVANT_WEB_PORT`。

| 產品 | `.env` 的產品設定 | 啟動命令 |
| --- | --- | --- |
| Work | `ORDIVANT_PRODUCT_MODE=work`、`ORDIVANT_WEB_API_UPSTREAM=http://work-api:8000` | `docker compose up -d --build --wait work-api web` |
| Knowledge | `ORDIVANT_PRODUCT_MODE=knowledge`、`ORDIVANT_WEB_API_UPSTREAM=http://knowledge-api:8010` | `docker compose up -d --build --wait knowledge-api web` |
| Code | `ORDIVANT_PRODUCT_MODE=code`、`ORDIVANT_WEB_API_UPSTREAM=http://code-api:8020` | `docker compose up -d --build --wait code-api web` |

必要的登入服務與資料庫會一起啟動。Work 與 Knowledge 不需要 Code 或 Gitea；Code 要修改 repository 時，還需下方的 Gitea。

## 啟用選用功能 {#optional-services}

### Code 與 Gitea {#enable-gitea}

在相同部署中執行：

```sh
docker compose --profile gitea up -d --wait gitea
docker compose -f compose.yaml -f compose.gitea-init.yaml --profile gitea run --build --rm gitea-init
docker compose up -d --no-deps --force-recreate --wait code-api
```

初始化工作會替 Code 設定服務連線；不會建立供人員使用的預設登入密碼。完成後回到 Code 建立專案、repository 和 PR。Gitea 預設網址是 `http://127.0.0.1:3002`。在 `.env` 的 `COMPOSE_PROFILES` 保留 `gitea`，例如 `runtime,gitea`，讓之後重啟仍包含它。

### 執行沙箱 {#enable-sandbox}

先完成 Agent 執行服務的初始化，再建置沙箱工作映像並啟動：

```sh
docker compose -f compose.yaml -f compose.sandbox.yaml --profile sandbox build sandbox-job-image
docker compose -f compose.yaml -f compose.sandbox.yaml --profile runtime --profile sandbox up -d --build --wait runtime
```

若已啟用 Gitea，在第二個命令另加 `--profile gitea`。在 `.env` 保存啟用設定，後續即可沿用一般 `docker compose` 指令：

```dotenv
COMPOSE_PATH_SEPARATOR=,
COMPOSE_FILE=compose.yaml,compose.sandbox.yaml
COMPOSE_PROFILES=runtime,gitea,sandbox
```

沒有啟用 Gitea 時移除清單中的 `gitea`。沙箱不連接網路，也不掛載主機資料；需要保存的成果必須在 Run 結束前提交。[工具與沙箱操作](execution-usage.md#sandboxes)

### 企業登入與外部工具 {#enterprise-and-tools}

OIDC 可直接連接公司的身分服務，無須額外容器。SAML／LDAP 可使用選用的 Keycloak；依[企業 SSO 指南](enterprise-sso.md#saml-ldap-and-active-directory)啟動與設定。自訂 Compose 檔案時，請把它加入既有 `COMPOSE_FILE`，不要覆蓋已啟用的沙箱設定。

外部 MCP 工具需先在 `.env` 的 `ORDIVANT_TOOL_ALLOWED_HOSTS` 加入精確主機名稱，再重啟 Work 與執行服務。不要把模型金鑰或人員密碼放入 `.env`；模型金鑰請在管理介面輸入。[工具連線操作](execution-usage.md#external-mcp-tools)

### 企業機密檔案與 deployment provider {#enterprise-secret-mounts}

企業整合可選用唯讀 Compose overlay。預設在倉庫根目錄建立 `.data/enterprise-secrets/identity/` 與 `.data/enterprise-secrets/code/`；如使用其他位置，先在 `.env` 設定 `ORDIVANT_ENTERPRISE_SECRETS_DIR`。將 SCIM token 與 SMTP password file 放在 `identity/`，將 Code 的 `deployment-providers.json` 及其 `token_file` 檔案放在 `code/`。兩個目錄分別只讀掛載至 Identity 與 Code 容器的 `/run/ordivant-enterprise`，不會互相暴露。

`.env.compose.example` 列有檔案路徑設定。常用路徑為 `ORDIVANT_SCIM_TOKEN_FILE=/run/ordivant-enterprise/scim-token`、`ORDIVANT_SMTP_PASSWORD_FILE=/run/ordivant-enterprise/smtp-credential` 及 `ORDIVANT_CODE_DEPLOYMENT_CONFIG_FILE=/run/ordivant-enterprise/deployment-providers.json`。此處只設定容器內檔案路徑；credential 值只存於伺服器上的檔案，不要貼入 `.env`。

安裝檔案並完成 `.env` 路徑設定後，用相同的 Compose overlay 建置啟動：

```sh
docker compose -f compose.yaml -f compose.enterprise.yaml up -d --build
```

後續啟動、更新或重建也須帶上相同的兩個 `-f` 檔案，才能保留唯讀掛載設定。

## 狀態、停止與備份 {#actions-and-data}

從同一倉庫目錄，使用安裝時相同的 `.env` 和 Compose 設定：

```sh
docker compose -f compose.yaml -f compose.enterprise.yaml ps
docker compose -f compose.yaml -f compose.enterprise.yaml logs --tail 100 work-api identity-api
docker compose -f compose.yaml -f compose.enterprise.yaml down
docker compose -f compose.yaml -f compose.enterprise.yaml up -d --wait
```

只有啟用 enterprise overlay 時才使用上方命令；一般部署沿用[基本容器操作方式](guide/operations.md)。使用 overlay 時，每次啟動、停止、更新和重建都須帶上相同的 `-f compose.yaml -f compose.enterprise.yaml`。`down` 保留資料卷；不要加入 `-v`，那會刪除資料。備份需包含各產品資料庫、資料卷、`.data/container-secrets/`（或自訂機密目錄），以及 `.data/enterprise-secrets/`（或 `ORDIVANT_ENTERPRISE_SECRETS_DIR` 指定的位置）。Enterprise secrets 目錄中的 Identity／Code 設定與 token 檔都必須保留，並與模型、SSO 的加密金鑰一起保存。[備份與還原步驟](guide/operations.md)

只有在尚未建立任何實際帳號或業務資料的全新試用環境，才可選擇加入 DEMO 範例；請在執行服務初始化與首次登入之前執行：

```sh
docker compose exec work-api python -m ordivant.seed
docker compose exec knowledge-api python -m ordivant_knowledge.seed
docker compose exec code-api python -m ordivant_code.seed
```

範例會建立示範專案及 Agent，不會建立人員密碼或串接模型。一般正式安裝無須執行這三個命令；已有資料的環境不要重新加入範例。

## 使用 HTTPS 提供團隊存取 {#https-access}

預設網頁只綁定本機 `127.0.0.1:8088`。若要讓團隊遠端使用，請在伺服器設定 HTTPS 反向代理，轉送到此本機位址，並在 `.env` 使用實際網址：

```dotenv
ORDIVANT_AUTH_ORIGINS=https://ordivant.example.com
ORDIVANT_AUTH_COOKIE_SECURE=true
ORDIVANT_SSO_PUBLIC_ORIGIN=https://ordivant.example.com
```

再執行 `docker compose up -d --wait` 重新套用設定。若反向代理在另一個容器內，需將它連到同一 Compose 網路並轉送至 `web:80`；主機的 `127.0.0.1` 不是另一個容器的本機位址。啟用企業登入時，另需核對身分服務的 Callback URL。[企業登入設定](enterprise-sso.md)
