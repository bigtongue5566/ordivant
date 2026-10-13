# Ordivant Knowledge

Knowledge 用來保存可追溯的規格、決策和背景資料。每個 Space 都有獨立成員範圍；文件內容採不可變版本，搜尋依目前實際保存的標題和正文做文字比對。

![Knowledge 文件：查看正文、已發佈版本與引用](/screenshots/knowledge-zh-TW.png)

<span id="建立文件與版本"></span>
<span id="创建文档与版本"></span>

## 建立文件與版本 {#create-a-document-and-publish-versions}

1. 由 Identity 管理員建立 Space 及其資源範圍，填入唯一 key、名稱與說明；Space 建立後，再授權 Knowledge manager、writer 或 reader。
2. 選擇 Space，建立文件，填入標題、摘要、正文和標籤。初次建立會同時保存文件及 `v1`。
3. 在「來源與 provenance」加入文件採用的 Work、Code 或外部來源。來源是可追溯引用，不代表讀者自動取得來源產品的存取權。
4. 修改已存在的文件時，先在最新版本頁面的「共同草稿」編輯正文。等草稿顯示「已保存」後選擇「發佈新版本」，填入變更摘要、選用的版本標題及引用，再確認發佈。系統建立新版本；舊版本、內容 hash 和引用保持不變。若草稿已被其他人更新，會提示衝突，請檢視合併後的最新內容再發佈。

文件讀者可用標題、正文文字和標籤搜尋，打開文件後切換檢視任一精確版本。畫面會顯示版本 URI、建立時間、內容 SHA-256、變更摘要和來源。搜尋是持久化文字搜尋；本產品不提供向量索引或 RAG 搜尋。

## 多人共同編輯草稿 {#shared-draft-collaboration}

Knowledge Writer 和 Manager 可在同一份文件的最新版本頁面編輯共同 Markdown 草稿；Reader 可看共同草稿但不能修改。文件 Space 的授權範圍同樣適用於 Agent。這項工作不需要 LLM。

1. 開啟文件的最新版本。在「共同草稿」區選擇「編輯」，撰寫或修訂正文；需要檢查格式時切換「預覽」。線上協作者名單顯示已登入的共同編輯成員；Agent 透過 REST 或 MCP 更新草稿時，作者會記錄在稽核事件中。
2. 留意草稿狀態：**已連線**且顯示**已保存**，代表伺服器已確認保存，其他連線會收到合併後的內容。**正在重新連線**或**尚有變更待保存**時先不要離開頁面；未確認的離線變更只保留在目前瀏覽器分頁的記憶體中，關閉或重新載入頁面可能遺失。
3. 其他 Writer／Manager 可同時編輯，變更會合併到同一草稿。Agent 也能透過 REST 或 MCP 讀寫這份草稿；不要用其他 API 直接覆蓋整篇正文。
4. 要留下可引用的正式內容，等連線恢復且狀態為**已保存**後，選擇「發佈新版本」，輸入變更摘要並確認發佈。只有即時連線、且已保存的草稿可發佈。發佈會建立不可變版本，舊版本保留在版本歷程。

若發佈時遇到版本衝突，先重新載入共同草稿，核對最新版本與合併內容，補上需要的修改並等待顯示已保存，再發佈。若權限失效，草稿會轉為唯讀；請聯絡管理員恢復 Space 授權後再繼續。

<span id="引用特定版本"></span>

## 引用特定版本 {#cite-an-exact-version}

文件版本的標準 URI 格式如下：

```text
ordivant://knowledge/spaces/{space_id}/documents/{document_id}/versions/{version}
```

從版本閱讀頁複製完整 URI，引用時保留 `/versions/{version}`，不要只連到可變動的文件首頁。可在 Work Task 的輸入／證據中記錄該 URI，或在 Code 建立 PR 時加入 Knowledge 來源引用。Knowledge 的版本引用不會替其他產品查詢或授權資料；讀者仍須有該 Space 的權限。

<span id="記錄決策"></span>
<span id="记录决策"></span>

## 記錄決策 {#record-decisions}

在「決策紀錄」建立標題與內容，可選擇關聯文件，再附上依據來源。決策紀錄保留建立者與引用，適合記錄採用的方向、取捨和生效版本；後續改變決策時另建新紀錄，避免抹除歷史脈絡。

<span id="權限與範圍"></span>
<span id="权限与范围"></span>

## 權限與範圍 {#permissions-and-scope}

- **Manager**：管理 Space 與授權範圍，可建立文件、發佈版本和決策。
- **Writer**：在已授權 Space 建立文件、共同編輯草稿、發佈新版本和記錄決策。
- **Reader**：閱讀共同草稿與歷史版本、搜尋及複製引用；不可編輯或發佈。

Identity 管理員授予成員明確 Space 範圍。登入 Knowledge 不代表能讀取所有 Space；同一個 URI 也不是跨產品權限。管理員與成員管理方式見[管理指南](administration.md)。
