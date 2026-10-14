<span id="v0-1-0-公開版本"></span>
<span id="v0-1-0-公开版本"></span>
<span id="public-release-v0-1-0"></span>
<span id="public-release-v0-2-0"></span>

# Ordivant v0.3.0 公開版本 {#public-release-v0-3-0}

發布日期：2026-10-15。授權：[MIT](../LICENSE)。原始碼與下載：[GitHub Releases](https://github.com/ordivant-ai/ordivant/releases/tag/v0.3.0)。

## 本版內容 {#included-in-this-release}
<span id="本版內容"></span>
<span id="本版内容"></span>

- **Work 團隊規劃**：看板與 Backlog 排序、Epic、工作類型、Sprint、里程碑、日期、自訂欄位和階段；登入後提報任務、事件規則、個人儲存查詢、工時、每週容量、觀察報表及 CSV 匯入／匯出。真人可認領或接受指派、交接、提交成果，再由另一位獲授權的人獨立審核。操作方式見 [Work 指南](./guide/work.md)。
- **跨模組協作**：Work、Knowledge 和 Code 的資源支援附件、提及、訂閱及通知；通知中心和跨產品文字搜尋只顯示目前獲授權的內容。
- **Knowledge 文件協作**：頁面階層、封存、PRD／會議／ADR／SOP 範本、留言回覆與解決、Markdown 工具和預覽、版本差異及受控還原。多人與 Agent 仍可共同編輯同一份草稿，發布後保留不可變版本。見 [Knowledge 指南](./guide/knowledge.md)。
- **Code 審查與證據**：PR 行內討論綁定 head SHA、檔案與行號；head 改變後會標示過期。可管理並讀回 Gitea 分支保護，查看目前提交的上游核准、檢查與 Actions；設定 GitHub／GitLab 部署來源後，可讀取同一 SHA 的部署紀錄。Ordivant 不會代替上游執行 CI 或部署。見 [Code 指南](./guide/code.md)。
- **企業身分與治理**：SCIM 2.0 Users／Groups、OIDC ACR／AMR 登入政策、SMTP 邀請與帳號復原，以及 Identity 稽核匯出與保留管理。見[管理指南](./guide/administration.md)及[企業 SSO](./enterprise-sso.md)。
- **無 LLM 也能使用**：一般真人任務、共同編輯、附件、搜尋和 Code 協作不需要模型；只有自主 Agent Run 需要模型連線。介面與操作文件提供繁體中文、簡體中文和英文。

## 升級與限制 {#upgrade-and-limitations}
<span id="升級與限制"></span>
<span id="升级与限制"></span>

由 v0.2.0 或更早版本升級前，先依[維運指南](./guide/operations.md)停止服務並備份該 Compose 專案的資料庫、所有持久化資料卷、服務機密及自訂 `.env`。加密金鑰必須與對應資料庫、資料卷一起保存；機密目錄預設為 `.data/container-secrets/`，自訂時備份 `ORDIVANT_SECRETS_DIR` 指定的位置。若使用企業機密掛載，也備份 `ORDIVANT_ENTERPRISE_SECRETS_DIR`。

將原有 repository 更新至 v0.3.0，沿用原有 Compose 專案名稱、`.env`、機密目錄、Compose 檔案組合及 profiles。服務啟動時會套用資料庫結構更新。從 repository root 執行：

```sh
docker compose up -d --build --wait
docker compose ps
```

原部署若使用 profiles 或多份 Compose 檔案，每次啟動、重建和升級都要加回相同選項。服務正常後，登入檢查既有專案、文件、PR 和權限。不要執行 `docker compose down -v` 或刪除資料卷。若需回復舊版，應一起還原升級前的資料庫、資料卷、機密與程式版本。

Knowledge 的共同編輯內容是 Markdown；未確認的離線修改只存在目前瀏覽器分頁記憶體，請在離開或重新載入前等候「已保存」。Git 寫入和合併需要 Gitea；Ordivant PR 審查不會建立 Gitea 核准。

本版尚未提供向量搜尋、內建 CI runner、全組織硬性金額預算或分散式執行。SCIM 不支援 bulk，也不會依 email 自動認領既有帳號；MFA 政策依賴已驗證的 IdP 宣告。SMTP 用於邀請和復原郵件，其他協作通知在平台內查看。正式使用前，請驗證自己的 IdP／SCIM 目錄、Git 服務、SMTP、模型與 HTTPS；GitHub／GitLab provider 的真實 CI 和成功部署結果需在實際環境確認。

## 選用企業整合 {#enterprise-setup}

SCIM、SMTP 和 GitHub／GitLab 部署來源由管理員依[容器部署指南](./containers.md#enterprise-secret-mounts)設定。使用 `compose.enterprise.yaml` 可將 Identity 和 Code 的機密目錄分別唯讀掛載。採用此設定後，啟動與升級需保留這份 overlay，例如：

```sh
docker compose -f compose.yaml -f compose.enterprise.yaml up -d --build --wait
docker compose -f compose.yaml -f compose.enterprise.yaml ps
```

若另有 Gitea、Runtime 或其他設定檔，請一併保留。沒有啟用企業整合時，仍可使用一般帳號及真人協作。

完整版本記錄見 [Changelog](https://github.com/ordivant-ai/ordivant/blob/main/CHANGELOG.md)；備份與還原方式見[維運指南](./guide/operations.md)。
