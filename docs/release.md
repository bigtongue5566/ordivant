<span id="v0-1-0-公開版本"></span>
<span id="v0-1-0-公开版本"></span>
<span id="public-release-v0-1-0"></span>
<span id="public-release-v0-2-0"></span>
<span id="public-release-v0-3-0"></span>

# Ordivant v0.4.0 公開版本 {#public-release-v0-4-0}

發布日期：2026-10-19。授權：[MIT](../LICENSE)。原始碼與下載：[GitHub Releases](https://github.com/ordivant-ai/ordivant/releases/tag/v0.4.0)。

## 本版內容 {#included-in-this-release}
<span id="本版內容"></span>
<span id="本版内容"></span>

- **個人 API 與 MCP**：在「帳號與安全性 → API 與 MCP」建立限定產品及期限的個人權杖，複製目前環境的連線範例，並隨時撤銷。權杖代表本人的真人帳號，每次操作沿用目前角色及資源範圍，不會取得 Agent 身分或額外權限。見[連線指南](./guide/administration.md#personal-api-and-mcp-access)。
- **六種內建 Agent 範本**：PM、PG、SA、SD、QA 與 Reviewer。新增 Agent 時帶入可編輯的名稱、能力與工作指令；範本按組織保存為不可變版本，既有 Agent 不會被覆寫。見 [Work 指南](./guide/work.md#built-in-agent-templates)。
- **建立專案時一起建立其他產品**：Work 專案建立後，可選擇建立對應 Knowledge 空間及 Code 專案，也可略過。失敗項目可分別重試，已成功的項目不會重複建立；各產品仍獨立授權。
- **從 Provider 取得模型**：模型設定可向 OpenAI 相容服務的 `/models` 取得清單，搜尋並選取模型。只有上游明確提供時，才帶入 Context、輸出上限與推理強度，缺漏時仍需手填；不會測試模型推論。見[模型設定](./model-usage.md)。
- **更清楚的執行設定**：以「執行方式」、「由平台執行」和「由外部程式執行」說明 Agent 的運作；修正指定模型尚未填完整時的畫面錯誤，以及模型清單撐長側欄的問題。
- **開源協作指南**：重新整理 AGENTS 與貢獻規範，提供通用的目錄、契約、測試與 PR 指引，適用不同開發者和 coding agent。
- 新功能介面與操作文件支援繁體中文、簡體中文和英文；既有真人工作、文件共編與 Code 協作仍不需要 LLM。

個人權杖完整內容只顯示一次，每位使用者最多 50 個有效權杖，有效期限為 1 至 365 天。密碼變更、帳號復原與停用會撤銷既有權杖；「登出所有裝置」只撤銷瀏覽器工作階段，外部工具須另外撤銷權杖。MCP 目前為本機 stdio bridge，需 uv 與原始碼；不是遠端 Streamable HTTP MCP 服務。新增的連線範例使用佔位值，請在自己的用戶端安全設定權杖。

## 升級與限制 {#upgrade-and-limitations}
<span id="升級與限制"></span>
<span id="升级与限制"></span>

由 v0.3.0 或更早版本升級前，先依[維運指南](./guide/operations.md)停止服務並備份該 Compose 專案的資料庫、所有持久化資料卷、服務機密及自訂 `.env`。加密金鑰必須與對應資料庫、資料卷一起保存；機密目錄預設為 `.data/container-secrets/`，自訂時備份 `ORDIVANT_SECRETS_DIR` 指定的位置。若使用企業機密掛載，也備份 `ORDIVANT_ENTERPRISE_SECRETS_DIR`。

將原有 repository 更新至 v0.4.0，沿用原有 Compose 專案名稱、`.env`、機密目錄、Compose 檔案組合及 profiles。服務啟動時會套用資料庫結構更新。從 repository root 執行：

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
