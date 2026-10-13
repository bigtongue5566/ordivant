<span id="開始使用-ordivant"></span>
<span id="开始使用-ordivant"></span>

# 開始使用 Ordivant {#getting-started-with-ordivant}

這是快速認識平台的入門頁。第一次建立自己的工作區，請跟著[第一個專案完整教學](first-project.md)建立專案與任務，再由真人認領、提交成果並完成獨立審核；這條流程不需要先建立 Agent。管理員邀請成員時，請搭配[建立團隊](team-setup.md)。

以「整理產品上線清單」為例，帶你從登入、建立任務到審查成果。使用團隊提供的 Ordivant 網址；若是自己部署，請先完成安裝，再開啟你的平台網址。

<span id="準備環境"></span>
<span id="准备环境"></span>
<span id="prepare-the-environment"></span>

## 登入與介面語言 {#sign-in-and-language}

若是全新安裝，請依首次畫面建立初始管理員並保存復原碼；之後便使用自己的帳號登入。若加入既有團隊，在登入頁選擇「接受邀請」，輸入邀請碼並設定自己的密碼。若組織使用單一登入，請選擇登入頁顯示的組織身分服務。Ordivant 沒有預設人員帳號或密碼；若沒有邀請或無法登入，請聯絡管理員。其他登入方式見[帳號與登入](../human-login.md)。

登入後可使用「介面語言」選擇「繁體中文」、「简体中文」或「English」。切換語言會改變平台介面文字，不會自動翻譯成員建立的任務、文件或留言。

![登入頁：受邀成員可登入或接受邀請](/screenshots/login-zh-TW.png)

## 選擇工作區與專案 {#choose-workspace-and-project}

在產品導覽選擇 **Work**，再從「選擇專案」清單開啟管理員授予你存取權的專案。接下來用「整理產品上線清單」作為第一個任務範例。若你是初始管理員，按「建立專案」，填入專案代碼與名稱；例如 LAUNCH、產品上線準備。一般成員若沒有可選專案，請聯絡管理員授予存取權；登入平台不會自動取得所有專案的存取權。

<span id="複製並啟動"></span>
<span id="拷贝并启动"></span>
<span id="clone-and-start"></span>
<span id="create-task-and-review"></span>

## 建立第一個任務 {#create-first-task}

在任務頁按「新增任務」，把「整理產品上線清單」填入任務名稱。目標可寫成「整理產品正式上線前需要完成的準備事項」，再依需要補上輸入資料、工作範圍和限制。

在「驗收條件」中逐行寫出可核對的標準，例如「列出所有上線前準備事項」、「每項標明負責人與目前狀態」、「附上可追溯的來源或證據」。填完後按「建立任務」儲存。任務可先保持未指派，讓有專案權限的 worker 認領；manager 或 admin 也可指派給同事或 Agent。欄位說明見[Work 任務與審核指南](work.md)。

<span id="seed-與-runtime"></span>
<span id="seed-与-runtime"></span>
<span id="seed-and-runtime"></span>
<span id="create-project-and-agent"></span>

![任務詳細資料：查看目標與驗收條件，選擇 Pi Agent 派發](/screenshots/task-zh-TW.png)

## 以真人或 Agent 執行 {#select-agent-and-run}

**真人執行**：使用自己的帳號開啟任務，直接按「認領任務」即可認領未指派或指派給自己的工作。你不必選 Agent、建立 Run 或設定模型；重新載入頁面後可繼續進行中的工作。真人執行沒有 Agent 租約，也不能認領指派給其他同事的任務。Manager 或 admin 可將任務指派給同事；只有在明確代表 Agent 執行時，才選擇獲准存取此專案的 Agent 來代為認領。

**Agent 自動執行**：由 manager 或 admin 在任務詳情選擇獲准存取此專案的 Pi Agent，再按「派發給 Agent」。這會建立 Run；開啟側欄的「Run 執行」即可檢視進度、事件與成果。Agent 自動執行需要管理員啟用 Runtime 並設定有效模型連線。

尚未設定模型時，仍可由真人認領、完成工作、提交成果並審核。Run 若標示為 DEMO，代表它不是付費模型呼叫。管理員可參閱[執行與自動化指南](../execution-usage.md)了解 Agent 執行設定。

<span id="檢查與停止"></span>
<span id="检查与停止"></span>
<span id="check-and-stop"></span>

![Run 控制台：查看 DEMO 執行的事件與提交結果](/screenshots/run-zh-TW.png)

## 提交成果並完成審核 {#submit-and-review}

以上線清單為例，執行者完成整理後，提交摘要及清單、來源連結等證據。任務會進入待審核；另一位 Reviewer 對照驗收條件檢查證據後，可接受成果或退回修改。執行者不能接受自己的提交。Run 顯示完成不代表任務已完成，只有獨立審核接受後，任務才會標示完成。詳細操作見[Work 任務與審核指南](work.md)。

<span id="self-host"></span>

## 功能導覽 {#product-overview}

- **Work**：把任務指派給同事或 Agent，也可由真人認領；提交證據後由另一位獲授權的人獨立審核。
- **Knowledge**：多人即時共同編輯草稿，再發布不可變版本；Agent 可透過 REST 或 MCP 參與同一份草稿。
- **Code**：在 Ordivant 留存綁定 PR head SHA 的討論與審查；Git 操作及合併由 Gitea 負責。

<span id="接下來"></span>
<span id="接下来"></span>

## 下一步 {#next-steps}

- [Work：任務與審核](work.md)
- [Knowledge：文件、版本與引用](knowledge.md)
- [Code：Repository 與 Pull Request](code.md)
- [管理員、角色與 SSO](administration.md)
- [帳號與登入](../human-login.md)

- [第一個專案完整教學](first-project.md)
- [建立團隊與邀請成員](team-setup.md)
- [功能導覽](../features.md)
