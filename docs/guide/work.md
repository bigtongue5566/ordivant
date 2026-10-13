# Ordivant Work

Work 用來整理專案、任務、Agent 執行、訊息、成果證據與獨立審核。Task 是業務工作；Run/Execution 是一次實際執行。執行完成不會自動把 Task 標成完成，必須由有權限且非提交者的審核者接受成果。

![Work 任務清單：以任務狀態追蹤示範專案](/screenshots/work-zh-TW.png)

<span id="建立專案與任務"></span>
<span id="创建项目与任务"></span>

## 建立專案與任務 {#create-projects-and-tasks}

1. 由 Identity 管理員在 Work 建立 Project，並把成員授權到這個 Project。成員只會看到自己獲授權的範圍。
2. 在 Project 的「任務」建立 Task，填寫目標、描述、輸入資料、執行範圍、限制、驗收條件和優先順序。
3. 在「負責者」選擇管理員已授權此 Project 的真人同事或 Agent，也可先留白讓合資格成員認領；在「指定審核者」選擇另一位獲授權的真人或 Agent。需要先完成的 Task 可加為 dependency。系統拒絕循環依賴；前置任務要完成獨立審核後，後續任務才可開始。
4. 儲存後在任務清單搜尋或依狀態查看工作。修改任務規格不會取代已保存的執行與審核歷程。

真人可指派對象必須已受邀、啟用，並具有 Work 角色及此 Project scope；即使受邀者尚未登入 Work，管理者仍可先將工作交給他。角色與範圍由 Identity 管理員設定，詳見[團隊設定](team-setup.md)。

<span id="執行並提交證據"></span>
<span id="运行并提交证据"></span>

## 執行並提交證據 {#execute-and-submit-evidence}

真人工作不需要 LLM 或 Agent。具有此 Project scope 的 Worker、Manager 或 Admin 可認領未指派給別人的待執行任務；若任務已指派給自己，也可認領。直接按「認領任務」，不必選 Agent。不能代替另一位同事認領。真人執行沒有 Agent 租約，工作從任務執行紀錄恢復，所以重新載入後可繼續處理。

處理中可使用「回報執行進度」留下進展與證據；需要等待外部資料時選擇「標記任務受阻」。受阻或成果被退回時，原負責者仍保留。若要交給其他人，選擇「交接並釋出」並寫下交接內容：目前執行會結束、交接會留在歷程，真人負責者清除，任務回到待執行，其他合資格同事即可認領。Manager/Admin 也能在尚未開始執行時改派負責者。

完成後提交摘要及一項或多項成果，例如文字、Artifact URI 或檔案／測試結果引用。提交會把 Task 移入待審核並保留執行、證據與交接歷程。請說明成果如何符合驗收條件；提交不等於任務已接受。另一位有權限且不是提交者的人選擇接受或退回；提交者不能審查自己的成果。

若派發給 Agent，管理員須先啟用 Agent 執行服務；Pi 自動 Run 才需要模型設定。Agent 執行仍使用自己的租約與 fencing token，與真人工作分開。派發操作詳見[Run 與自動化](../execution-usage.md)。

<span id="協作與引用"></span>
<span id="协作与引用"></span>

## 協作與引用 {#collaboration-and-citations}

在 Task 脈絡使用訊息向其他成員或 Agent 提問、回覆、交接工作或記錄決議。Project 的 Manager／Admin，或父任務的真人、Agent 負責人，可選擇「委派子任務」把工作交給具備此 Project 執行權的同事或 Agent；委派不會自動授予受託人其他 Project 的存取權。

若工作依賴 Knowledge 文件，將該文件的**特定版本引用 URI** 放入 Task 輸入或提交證據，並保留版本號。引用只是來源紀錄，不會替讀者授權 Knowledge Space；需要閱讀原文的成員必須另外獲授權。Knowledge 引用格式與操作見[Knowledge 指南](knowledge.md)。

Work 也能讀取已設定的既有 GitHub、GitLab 或 Gitea PR/check 狀態。這是專案範圍內的讀取與證據檢視；它不會合併 PR，也不會代替獨立審核。Code 中由 Gitea 管理的 repository 與 PR 操作見[Code 指南](code.md)。

<span id="run-控制"></span>

## Run 控制 {#run-controls}

在「Run 執行」查看每次執行的狀態、事件與用量。管理員或專案管理者可暫停、繼續、停止或重試。暫停會在下一個工具操作前生效，並保留任務；停止後，本次執行不能再更新任務。重試會建立新的 Run。已完成的外部操作不會因停止而撤銷，重試前請先核對結果。

控制台的 Run 狀態、等待與停止語意、沙箱和工具設定詳見[執行使用指南](../execution-usage.md)。工具外部副作用不會因重試而自動重播；不確定的操作結果應先到上游服務核對。

<span id="權限概覽"></span>
<span id="权限概览"></span>

## 權限概覽 {#permissions-overview}

- **Manager**：管理已授權 Project 的任務與執行安排。
- **Worker**：認領未指派或指派給自己的工作，提交成果並可交接釋出。
- **Reviewer**：審查提交的成果；不能批准自己的提交。Manager 和 Admin 也可在獲授權範圍審查。

組織管理員負責建立 Project、邀請成員及分配產品角色。Work 存取以 Project scope 與 manager、worker、reviewer 身分為準；沒有獨立的 Work Reader role。人類登入工作階段不會變成 Agent/runtime 憑證。
