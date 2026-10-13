# Ordivant Code

使用 Ordivant Code 管理專案 repository 的分支、檔案變更、commit 與 Pull Request，並在 Ordivant 留下綁定版本的討論與審查紀錄。Git 歷程、合併與 Gitea 核准仍由 Gitea 管理。一般真人 Code 協作不需要 LLM；使用 Code 的 Git 功能需要部署 Gitea。

![Code 合併請求：查看實際示範儲存庫的程式碼變更](/screenshots/code-zh-TW.png)

<span id="啟用-gitea"></span>
<span id="激活-gitea"></span>

## 啟用 Gitea {#enable-gitea}

Gitea 是選用服務。若尚未啟用，Code 無法建立或更新 repository、branch、commit、Pull Request 與狀態；若以 Docker Compose 安裝，可請部署管理員啟用 Compose 中的 Gitea。Ordivant 的 PR 討論與審查紀錄是 Code 功能，不能取代 Gitea。請依[容器部署指南](../containers.md)確認部署方式。

<span id="repository-到-pr"></span>

## 從 Repository 建立 PR {#from-repository-to-pull-request}

1. 在 Code 選擇有權限的專案。Manager 可建立及管理專案；若清單中沒有需要的專案，請聯絡管理員。
2. 有 Writer 權限的成員可在專案中建立 private repository，或選擇已有的 repository。
3. 選擇來源 branch 並建立工作 branch；在 branch 中新增或更新檔案，輸入清楚的 commit message 後提交變更。
4. 建立 PR，選擇 head branch 與 base branch，填寫標題和說明。可附上 Work、Knowledge 或外部來源，方便審查者了解變更背景。
5. 在 PR 詳情查看變更、來源與 Gitea 狀態。在「討論與審查記錄」新增留言或提交一般意見、要求修改、核准等 Ordivant 審查；紀錄會標明作者是真人或 Agent。
6. 依組織的 Gitea 流程進行正式審查與合併。建立 PR 或送出 Ordivant 審查都不會自動核准 Work 任務，也不會替 Gitea 留下核准。

Code 專案中的角色決定可用操作：**Manager** 管理專案，**Writer** 在已授權專案建立 repository、branch、commit 與 PR，**Reader** 檢視資料。加入來源參考只說明工作關聯，不會自動授予 Work、Knowledge 或其他系統的存取權。

<span id="pr-狀態與證據"></span>
<span id="pr-状态与证据"></span>

## PR 狀態與證據 {#pr-status-and-evidence}

「回報狀態」可將指定 commit 標記為 pending、success、failure 或 error。若狀態標為 `agent_reported`，代表 Agent 回報了結果，不表示測試真的執行過。`gitea_webhook` 表示狀態來自 Gitea webhook；要確認測試內容與結果，請開啟 Gitea 中對應的檢查紀錄。

PR 狀態可協助追蹤工作，但不能取代實際測試、Gitea 審查或合併程序。

每筆 Ordivant 審查會綁定提交時的 PR **head SHA**。若 PR head 改變，舊審查仍保留供追溯，但會標示為已過期；請載入最新審查紀錄後，對目前的 head 重新檢視並留下新紀錄。Ordivant 的討論與審查紀錄不是 Gitea approval、CI 執行結果或 Work 任務驗收。

真人和 Agent 都可依 Code 專案權限參與討論與審查。使用者檢視與撰寫這些紀錄不需要 Agent 或模型；Git repository 與 PR 操作仍需可用的 Gitea 服務。人員角色和專案範圍見[團隊設定](team-setup.md)。
