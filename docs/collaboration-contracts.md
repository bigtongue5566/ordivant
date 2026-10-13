# 真人與 Agent 協作契約 {#human-agent-contracts}

本次擴充以共用 Identity、產品資源範圍及 Python 授權為基礎。LLM 不得成為一般任務、文件或 Code 操作的前置條件。

## Work

- 保留既有 `assignee_id`、`reviewer_id` 作為 Agent ID；新增 `assignee_principal_id`、`reviewer_principal_id` 作為真人 Principal ID。每一種指派只能選真人或 Agent 其中之一。API 回傳 `assignee` 與 `reviewer`，格式為 `{id,principal_id,name,kind:"human"|"agent"}` 或 null。
- `GET /api/projects/{id}/participants` 回傳已授權、啟用的真人與 Agent：`{id,principal_id,name,kind,role}` 陣列。真人的 id 是本地 principal ID，Agent 的 id 是 Agent ID。Identity 服務的受保護 directory 提供已受邀但尚未登入 Work 的人員；不得要求同事先登入才可指派。
- 真人以自己的帳號呼叫既有 `POST /tasks/{id}/claim`，不帶 `agent_id`。worker、manager、admin 可認領未指派或指派給自己的 ready 任務；不得代替其他真人認領，也不可認領自己被指定審查的任務。舊有管理者代執行 Agent 的明確 `agent_id` 路徑保留。
- 真人 Execution 的 `agent_id`、`lease_token`、`lease_expires_at` 為 null；由 claimed_by_principal_id 表示執行者。真人工作持久保存，不使用 Agent 逾時租約。Agent 仍有防護 token 與租約。Execution 回傳 `executor_id`、`executor_kind`、`executor_name`、`claimed_by_principal_id`、`submitted_by_principal_id`。
- 真人回報、提交、釋出與受阻仍使用既有 action，body 的 lease_token 可省略；每次由 Python 檢查目前帳號就是執行持有人及仍有專案權限。重新載入可從 context.executions 的 running 真人工作繼續。
- 提交與獨立審查保持分離，真人／Agent 均不得審查自己的提交。管理者可指派具 scope 的真人 worker／manager 或 Agent worker；真人 reviewer／manager 可被指定審查。其他人不能搶領已指派任務。
- 真人交接並釋出會保存 handoff、結束舊執行、清除真人負責者並回到 ready，讓同事接手認領。受阻與被退回則保留負責者。
- 任務訊息、求助、委派與接收者均支援已授權真人與 Agent；人員委派不增加其他產品或專案的權限。自動 Pi 派發只接受 Agent 指派，不能覆蓋真人任務。

## Knowledge

- 使用 Yjs 相容的 CRDT，Python 使用 pycrdt。文件正文是根 `Y.Text("body")`。草稿與正式不可變版本分開保存於 PostgreSQL／SQLite；每次 update 成功持久化後才確認。
- `GET /api/documents/{id}/draft` 回傳 `{document_id,base_version,revision,published_revision,title,body,update}`；update 是標準 base64 編碼的 Yjs v1 update。reader 可讀、writer／manager 可編輯。
- `POST /api/documents/{id}/draft/updates` 本文 `{update}`，與既有 Idempotency-Key／Bearer／Cookie CSRF 共用檢查。Python 合併 CRDT update 並回傳同一草稿結構。Agent 使用 REST／MCP 可讀取並編輯同一草稿；禁止直接覆蓋其他編輯者未發佈的草稿。
- `POST /api/documents/{id}/draft/publish` 本文 `{expected_revision,change_summary,title?,source_refs?}`；授權 writer／manager 可把這個 revision 原子發佈為新不可變版本，保留 CRDT ID 並更新 base_version／published_revision；回傳既有 DocumentVersion。並行更新時回傳 409，不悄悄丟棄內容。舊版本 API 與共同草稿的衝突要明確回報。
- `WS /api/documents/{id}/collaborate` 用相同 scope 檢查。瀏覽器只使用 HttpOnly Cookie；首次訊息 `{type:"authenticate",csrf_token}`，每次連線嚴格驗證 Origin，定期重新驗證 session／scope。不得在 URL 帶憑證。未驗證前不傳文件或 presence。
- 伺服器訊息 `{type:"sync",draft:上述結構,participants:[{id,name,kind}]}`；client update `{type:"update",update,request_id}`，成功回 `{type:"ack",request_id,draft}`；presence `{type:"presence",participants}`；錯誤 `{type:"error",code,message,request_id?}`。伺服器主動傳已提交的最新 CRDT，並以 DB 輪詢支援多程序與重啟。重連須合併本地尚未確認的更新，UI 清楚表示未保存或失去權限；不能顯示虛假的已保存。
- 更新大小、文件大小、頻率與連線數有上限；reader 不能 update。presence 的身分由伺服器取得，不能由 client 冒用。編輯與發佈稽核標示真人或 Agent。

## Code 與驗收 {#code-acceptance}

Code 保留 Gitea 作為 Git／PR／合併權威來源。Ordivant 另外保存真人及 Agent 共用的 PR 討論與審查收據；不能冒充 Gitea 核准、CI 或 Work 驗收。操作者由伺服器驗證，不由本文指定。

- `GET /api/repositories/{repository_id}/pulls/{number}/collaboration` 回傳 `{pull_request_id,head_sha,proposer,comments,reviews}`；author／proposer 為 `{id,name,kind}`，無法從已驗證的建立紀錄識別 proposer 時為 null，不推測上游服務帳號就是操作者。
- `POST .../comments` 本文 `{body}`；`POST .../reviews` 本文 `{decision:"approve"|"request_changes"|"comment",comment,expected_head_sha}`。沿用 Idempotency-Key、scope 與 writer／manager／admin 權限，reader 只能讀取。
- 審查讀取 Gitea 目前 head，與 expected_head_sha 不符時回傳 409；提案者不得核准或要求變更自己的 PR，已關閉 PR 只能留下 comment。歷史保留 head_sha，GET 依目前 head 計算 is_current；程式碼變更使舊審查失效而不刪除歷史。
- REST 與 MCP 呼叫共用服務；本地討論及審查與稽核、冪等收據在同一交易保存。Gitea API 失敗不得使用假資料回覆成功。

驗收涵蓋未設定 LLM 的兩人指派／認領／成果／獨立審查，兩位文件編輯者與 Agent 的並行合併、斷線重連、重啟持久性、跨範圍／reader／登出拒絕、Gitea PR 討論與審查，以及三語 UI 與容器模式。不得使用真實使用者密碼或付費模型測試。
