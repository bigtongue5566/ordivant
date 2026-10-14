<span id="維運與備份"></span>
<span id="运维与备份"></span>

# 維運與備份 {#operations-and-backups}

本指南說明以 Docker Compose 管理服務、備份資料及啟用 Agent 自動執行。所有 Compose 命令都從 repository root 執行。預設部署名稱是 `ordivant`，由 `compose.yaml` 固定；不需要先建立 `.env`。若要自訂名稱，請在 repository root 建立 `.env` 並設定 `COMPOSE_PROJECT_NAME`，此後保持不變。服務機密預設位於 `.data/container-secrets/`；若設定 `ORDIVANT_SECRETS_DIR`，請改備份該路徑。使用 enterprise overlay 時，還要備份 `.data/enterprise-secrets/` 或 `ORDIVANT_ENTERPRISE_SECRETS_DIR` 指定的位置。

<span id="服務狀態與更新"></span>
<span id="服务状态与更新"></span>

## 服務狀態與更新 {#service-status-and-updates}

```sh
docker compose ps
docker compose logs --tail 100
docker compose up -d --build --wait
docker compose down
```

預設網頁位址為 `http://127.0.0.1:8088`。上述命令使用預設部署名稱 `ordivant`。停止服務會保留資料卷和機密檔案，但不等於備份；`docker compose down -v` 會刪除資料卷，造成資料遺失。

預設網頁連接埠是 `8088`，Gitea 是 `3002`。若連接埠衝突，可在 repository root 的 `.env` 設定 `ORDIVANT_WEB_PORT` 或 `ORDIVANT_GITEA_PORT`。若安裝時啟用了 Runtime、Gitea 等 profile，執行每個命令時都加上相同的 `--profile` 選項。若啟用 Sandbox，所有命令也須使用相同的 Compose 檔案組合 `-f compose.yaml -f compose.sandbox.yaml`。提供團隊遠端使用前，請設定 HTTPS、正式網站來源及安全 Cookie，詳見[容器部署指南](../containers.md)。

若使用 `compose.enterprise.yaml`，所有 Compose 命令（包括啟動、停止、更新與備份時的操作）都要帶上相同的 `-f compose.yaml -f compose.enterprise.yaml`，才能維持 Identity／Code 唯讀掛載與一致的服務設定。

<span id="需要備份的資料"></span>
<span id="需要备份的数据"></span>

## 需要備份的資料 {#data-to-back-up}

備份時以 Compose project label 找出該環境的所有 volumes，依資料庫產品與 data volume 作為同一組保存。典型完整套件包含：

| 區域 | Compose 資料卷／主機檔案 | 內容 |
|---|---|---|
| Identity | `identity_postgres`、`identity_data` | 人員、工作階段、SSO 設定與 `sso.key` |
| Work | `work_postgres`、`work_data` | Work 任務、Agent、Run、Runtime 狀態及 `model-settings.key` |
| Knowledge | `knowledge_postgres`、`knowledge_data` | Space 文件版本、決策與範圍資料 |
| Code | `code_postgres`、`code_data` | Code 範圍、repository 綁定、PR 與狀態收據 |
| Gitea（若啟用） | `gitea_data` | Repository、分支、提交、PR 的實際 Git 資料 |
| Keycloak broker（若啟用） | `identity_broker_postgres` | Broker realm 與連線設定 |
| Compose 機密與設定 | `.data/container-secrets/` 或 `ORDIVANT_SECRETS_DIR`；enterprise overlay 另含 `.data/enterprise-secrets/` 或 `ORDIVANT_ENTERPRISE_SECRETS_DIR`；自訂部署另含 `.env` | 資料庫密碼／URL、Runtime 與內部服務 token、Gitea 設定、Identity／Code enterprise 設定與 token 檔、Compose 專案名稱與連接埠設定 |

實際資料卷清單會依啟用的產品和設定檔而異。Work 的 `model-settings.key` 用於解密模型及 MCP 工具連線設定；Identity 的 `sso.key` 用於解密企業 IdP 設定。加密金鑰必須與對應資料庫及資料卷一起備份，不可單獨更換，否則無法解密既有密文。Agent 的執行狀態位於 Work 資料卷。每次 sandbox 的工作目錄都是暫存資料，不是成果保存位置。

可用 Compose 專案標籤查出此環境實際建立的資料卷名稱：

```sh
docker volume ls --filter "label=com.docker.compose.project=ordivant"
```

若自訂了 `COMPOSE_PROJECT_NAME`，請將篩選值改成 `.env` 中的名稱。請將列出的所有產品、Identity 及已啟用 profile 的資料卷納入備份；實際清單以命令結果為準，不要只依範例名稱猜測。

<span id="一致性與還原"></span>
<span id="一致性与还原"></span>

## 一致性與還原 {#consistency-and-restoration}

1. 確認備份目標是正確的 Compose 專案名稱。使用 `docker compose down` 停止該環境，讓檔案資料與 PostgreSQL 資料卷保持一致；這不會刪除資料。
2. 使用組織核准的 Docker 資料卷快照或備份工具，備份該專案標籤下需要的全部資料卷。也要一併保存預設的 `.data/container-secrets/` 目錄，或 `ORDIVANT_SECRETS_DIR` 指定的實際目錄；若使用 enterprise overlay，還須保存 `.data/enterprise-secrets/` 或 `ORDIVANT_ENTERPRISE_SECRETS_DIR` 指定的目錄，其中包含 Identity／Code 設定與 token 檔。如有自訂 `.env`，也應加密保存。
3. 將備份和主機上的機密目錄加密保存、限制存取，並定期測試還原。不要把 `.data`、初始設定 token 或 Gitea／服務憑證上傳到公開 issue、聊天或 Git。
4. 還原時先恢復同名 Compose 資料卷及原有機密，再使用相同部署名稱、profile 和 Compose 檔案組合啟動。不要混用不同環境的加密金鑰和資料庫。

若使用單一產品或部分產品模式，請備份該模式建立的所有資料卷及共用 Identity 資料卷。Knowledge 引用和 Code PR 的來源追溯資訊不能代替目標產品資料備份；也需保存來源產品及實際 Gitea 資料。

<span id="執行與排程"></span>
<span id="运行与调度"></span>

## 執行與排程 {#execution-and-scheduling}

首次部署先依[容器部署指南](../containers.md)完成 Compose 初始化與服務啟動。一般正式安裝接著在瀏覽器建立第一位人員管理員，再由管理員於模型管理頁設定 provider、API key 與 model；只有實際派發後才會呼叫已設定模型。未設定有效模型時，Run 會標示為 DEMO。

若要在全新環境試用 DEMO，請在 Compose 初始化與服務啟動後、首次登入及首次執行 `bootstrap_runtime` 之前建立範例資料。此選項只適用於尚未建立任何真實資料的全新試用環境；只執行想試用產品的其中一項。Seed 完成後再於瀏覽器建立第一位人員管理員。既有部署不可執行 Seed：

```sh
docker compose exec work-api python -m ordivant.seed
docker compose exec knowledge-api python -m ordivant_knowledge.seed
docker compose exec code-api python -m ordivant_code.seed
```

若要啟用 Agent Runtime，確認 Work API 已健康後執行：

```sh
docker compose exec work-api python -m ordivant.bootstrap_runtime
docker compose --profile runtime up -d --build --wait runtime
```

`bootstrap_runtime` 只初始化 Runtime 機器身分，不會建立 DEMO、人員或專案；可在已有正式資料的環境執行。若已存在有效的 `runtime_token`，重新執行不會輪替該 token。若同時使用 Sandbox，Runtime 啟動時必須沿用安裝時的 Compose 檔案與 profile：

```sh
docker compose -f compose.yaml -f compose.sandbox.yaml --profile runtime --profile sandbox up -d --build --wait runtime
```

定期間隔工作流程需要 Work Runtime 持續執行。服務停止期間錯過的排程不會全部補跑；同一排程已有進行中的工作流程時，不會重疊啟動。每次沙箱工作區都有資源界限，並在 Run 結束時清理，不應用來長期保存檔案。Run、成果物和 Knowledge 文件請透過相應產品保存。

執行控制、工具允許連線的主機及沙箱限制見[執行使用指南](../execution-usage.md)。Runtime 未設定有效模型時會使用 DEMO 後備模式；DEMO 不代表付費模型執行，也不是費率估算。
