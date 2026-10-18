<span id="v0-1-0-公開版本"></span>
<span id="v0-1-0-公开版本"></span>
<span id="public-release-v0-1-0"></span>
<span id="public-release-v0-2-0"></span>
<span id="public-release-v0-3-0"></span>
<span id="public-release-v0-4-0"></span>

# Ordivant v0.5.0 公開版本 {#public-release-v0-5-0}

發布日期：2026-10-19。授權：[MIT](../LICENSE)。原始碼與下載：[GitHub Releases](https://github.com/ordivant-ai/ordivant/releases/tag/v0.5.0)。

## 本版內容 {#included-in-this-release}
<span id="本版內容"></span>
<span id="本版内容"></span>

- **專案設定與範圍導覽**：側欄固定顯示目前專案／空間，頂端顯示所在位置；Work 的「專案設定」可管理名稱、說明、追蹤預算與成員存取權。並行修改會提示衝突，避免覆蓋他人設定。見 [Work 指南](./guide/work.md#project-settings)。
- **分開個人與組織管理**：「帳號設定」管理個人資料、安全性及 API／MCP；「組織管理」集中使用者、企業 SSO、治理與身分稽核，僅管理員可使用。
- **Agent 生命週期**：支援停用後重新啟用、封存保留歷史，以及永久刪除未使用的 Agent。仍有未完成工作或啟用中的自動化引用時，服務會拒絕退役操作。封存會撤銷憑證且不能還原。
- **重新整理後保留位置**：三個模組會保留網址中的頁面與資源選擇；側欄帳號操作收進選單，設定頁改用可讀的分區導覽，並支援小螢幕。
- **人工維護三語翻譯**：移除 OpenCC.js 與自動繁簡轉換，逐條校訂簡體中文；翻譯檢查驗證完整性及插值且不改寫詞庫。

Work 可逐專案授權存取，但同一成員的 Work 角色在各授權專案共用；目前不支援各專案獨立角色或 Work 唯讀角色。系統管理員才可調整真人成員存取權。Knowledge 空間與 Code 專案維持獨立授權，同名不代表共用權限。

個人權杖完整內容只顯示一次，每位使用者最多 50 個有效權杖，有效期限為 1 至 365 天。密碼變更、帳號復原與停用會撤銷既有權杖；「登出所有裝置」只撤銷瀏覽器工作階段，外部工具須另外撤銷權杖。MCP 目前為本機 stdio bridge，需 uv 與原始碼；不是遠端 Streamable HTTP MCP 服務。新增的連線範例使用佔位值，請在自己的用戶端安全設定權杖。

## 升級與限制 {#upgrade-and-limitations}
<span id="升級與限制"></span>
<span id="升级与限制"></span>

由 v0.4.0 或更早版本升級前，先依[維運指南](./guide/operations.md)停止服務並備份該 Compose 專案的資料庫、所有持久化資料卷、服務機密及自訂 `.env`。加密金鑰必須與對應資料庫、資料卷一起保存；機密目錄預設為 `.data/container-secrets/`，自訂時備份 `ORDIVANT_SECRETS_DIR` 指定的位置。若使用企業機密掛載，也備份 `ORDIVANT_ENTERPRISE_SECRETS_DIR`。

將原有 repository 更新至 v0.5.0，沿用原有 Compose 專案名稱、`.env`、機密目錄、Compose 檔案組合及 profiles。服務啟動時會套用資料庫結構更新。從 repository root 執行：

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
