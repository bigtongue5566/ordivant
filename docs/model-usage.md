<span id="模型連線與-agent-設定"></span>
<span id="模型连接与-agent-设置"></span>

# 模型連線與 Agent 設定 {#model-connections-and-agent-settings}

模型連線由 Work 組織管理員設定。你可以讓所有 Agent 使用組織預設，也可以為個別 Agent 選擇不同模型；設定變更會套用到之後新派發的任務。

<span id="管理員設定全域連線"></span>
<span id="管理员设置全域连接"></span>

## 管理員設定全域連線 {#configure-a-global-connection-as-an-administrator}

1. 登入 Work，從側欄開啟「模型連線」。只有組織管理員可以管理供應商連線。
2. 新增供應商，填入名稱、識別碼、HTTPS API base URL 與 API key。相容 Responses API 的網址通常以 `/v1` 結尾。
3. 按「從 API 取得模型」，搜尋並選擇要加入的模型，再按「加入所選模型」。此操作使用目前填入或已儲存的金鑰，呼叫 Base URL 下的 `/models`。API 未提供的 context、單次輸出上限及推理強度需自行補填；也可手動新增模型。取得清單不會改變既有模型設定，儲存後才生效。
4. 選擇組織預設的供應商、模型、推理強度與輸出上限，然後儲存。

API key 會安全保存，重新開啟設定時不會再次顯示；留白後儲存可保留現有 key。更換 API 網址時，請一併輸入該供應商提供的 key。若畫面提示設定已被其他管理員更新，請重新載入後再修改。

<span id="建立或編輯-agent"></span>
<span id="创建或编辑-agent"></span>

![模型連線：輸入供應商網址與支援的模型，API Key 使用自己的供應商金鑰](/screenshots/models-zh-TW.png)

## 建立或編輯 Agent {#create-or-edit-an-agent}

在「Agent 名錄」新增 Agent，並選擇模型設定方式：

| 模式 | 說明 |
|---|---|
| 繼承全域預設 | 新派發的任務會使用組織目前的預設模型與選項。 |
| Agent 個別設定 | 為這個 Agent 選擇供應商、模型、推理強度與輸出上限；使用該供應商已設定的 key。 |

編輯 Agent 時也可以切換兩種模式。改為繼承後，Agent 名錄會顯示實際套用的全域選項。設定更新不會改變已派發的任務，會從下次派工開始生效。

由外部程式執行的 Agent 不會由 Work 代為呼叫模型；其模型名稱僅供辨識。

<span id="provider-設定範例"></span>
<span id="provider-设置范例"></span>

![Agent 設定：選擇 Pi Durable、能力標籤與模型繼承方式](/screenshots/agent-zh-TW.png)

## Provider 設定範例 {#provider-configuration-example}

請使用模型供應商提供的 HTTPS 網址、模型 ID 和選項。`https://api.example.com/v1` 僅為說明格式的範例，不能直接連線；Ordivant 不附贈模型服務或 API key。

context 上限代表模型可處理的內容範圍；輸出上限則限制單次回覆長度。請填入供應商實際支援的數值，並先以較低的輸出上限測試。這些設定不是整體費用上限；模型費率與計費方式以供應商為準。若要限制實際支出，請在供應商帳戶設定用量或費用上限。

不同 Work 環境各自保存設定；若有多個 Work 網址，需分別設定供應商連線。

<span id="執行與證據"></span>
<span id="运行与证据"></span>

## 執行與證據 {#execution-and-evidence}

任務派發給使用已設定模型的 Agent 時，會呼叫該供應商的服務，可能產生費用。未設定模型時，系統會清楚標示為 DEMO；DEMO 不會呼叫付費模型。供應商呼叫失敗會顯示失敗，不會改以 DEMO 假裝成功。

Run 記錄可能顯示供應商回報的模型名稱及 token 用量，但不一定能取得美元費用。token 數不是帳單；供應商回報的模型名稱也不能單獨證明轉接服務底層實際使用的路由。請以供應商的用量與帳單頁面確認實際費用。

Agent 提交成果後，任務仍須由另一位有權限的審查者接受才算完成。操作方式請參閱[Work 任務指南](guide/work.md)及[執行與自動化指南](execution-usage.md)；自架服務與資料備份方式請參閱[容器部署指南](containers.md)。
