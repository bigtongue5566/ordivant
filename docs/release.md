<span id="v0-1-0-公開版本"></span>
<span id="v0-1-0-公开版本"></span>
<span id="public-release-v0-1-0"></span>

# Ordivant v0.2.0 公開版本 {#public-release-v0-2-0}

發布日期：2026-10-14。授權：[MIT](../LICENSE)。原始碼與下載：[GitHub Releases](https://github.com/ordivant-ai/ordivant/releases)。

## 本版內容 {#included-in-this-release}
<span id="本版內容"></span>
<span id="本版内容"></span>

- **Work**：管理者可將任務指派給獲授權的同事或 Agent；同事可認領符合權限的待辦工作、持續回報進度、交接並提交成果，再由另一位獲授權的人獨立審核。真人工作會保留在 Work 執行歷程中，重新載入後可繼續處理。
- **Knowledge**：多人可即時共同編輯同一份 Markdown 草稿，Agent 也能透過 REST／MCP 更新該草稿。斷線後可重新連線合併尚未確認的內容；未確認的離線修改只存在目前瀏覽器分頁記憶體。請等候草稿顯示已連線且已保存，再離開或發布。發布會建立不可變版本，保留歷史。
- **Code**：真人與 Agent 可在 Ordivant 討論 PR、提交評論及審查紀錄；每筆紀錄綁定 PR head SHA，head 改變後舊審查會標示過期。Code 的 Git 寫入與合併由 Gitea 處理；Ordivant 紀錄不會成為 Gitea 核准，也不代表上游 CI 結果。
- 一般真人 Work、Knowledge 與 Code 協作不需要 LLM；只有自主 Agent Run 需要設定模型。Code 的 Git 操作仍需 Gitea。
- 文件提供繁體中文、簡體中文及英文版本，包含功能導覽、團隊設定與第一個專案完整教學。

## 升級與限制 {#upgrade-and-limitations}
<span id="升級與限制"></span>
<span id="升级与限制"></span>

由 v0.1.0 升級前，先依[維運指南](./guide/operations.md)停止服務並備份該 Compose 專案的資料庫、所有持久化資料卷、服務機密及自訂 `.env`。加密金鑰要和對應資料庫、資料卷一起保存；機密目錄預設為 `.data/container-secrets/`，自訂時請備份 `ORDIVANT_SECRETS_DIR` 指定的位置。

更新原本的 repository 至 v0.2.0，並沿用原有 Compose 專案名稱、`.env`、機密目錄、Compose 檔案組合及 profiles。從 repository root 啟動更新後的服務：

```sh
docker compose up -d --build --wait
docker compose ps
```

若原部署使用自訂 profiles 或多份 Compose 檔案，執行時也要加回相同選項。確認服務狀態正常後，再由瀏覽器登入檢查工作區。不要執行 `docker compose down -v` 或手動刪除資料卷；升級需要保留既有資料。Knowledge 斷線時，尚未確認的修改只保留於目前分頁記憶體，請在離開或重新載入前等候「已保存」。

本版不宣稱提供向量搜尋、內建 CI、SCIM、硬性金額預算或分散式執行。Knowledge 搜尋為文字搜尋；Code 的 Ordivant PR 審查不等同 Gitea approval 或 CI。正式投入企業使用前，請驗證自己的 IdP、Git 服務、模型供應商與 HTTPS 設定。

完整版本記錄見 [Changelog](https://github.com/ordivant-ai/ordivant/blob/main/CHANGELOG.md)；備份與還原方式見[維運指南](./guide/operations.md)。
