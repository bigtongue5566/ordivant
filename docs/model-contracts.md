# Work 模型連線與 Agent 設定 {#work-model-connection-and-agent-configuration}

修訂日期：2026-10-07。Python Work 負責授權與設定。Identity 憑證與 Provider 憑證互相獨立。只有組織管理員可設定 Provider 連線；Agent 與範圍受限的 member manager 不能讀取或變更憑證。選擇模型不會輪替 Provider key。

## Work 公開 API {#public-work-api}

- `POST /api/model-settings/discover`：僅組織管理員；Cookie 仍須通過 Origin／CSRF。本文 `{id,base_url,api_key?}`，讀取 OpenAI 相容的 `{base_url}/models`，回傳 `{source:"provider_api",models:[{id,name,context_window?,max_output_tokens?,reasoning_efforts?}]}`。留白只會重用同組織、同 Provider ID、相同 Base URL 的已儲存 key。未提供的模型能力維持未知，不臆測數值；清單僅供選取加入，既有設定與 revision 不變。請求逾時 15 秒、最大回應 1 MiB／2,000 項、不重試、不跟隨重新導向、不回傳上游錯誤本文、不經冪等快取，回應帶 `Cache-Control:no-store`。

- `GET /api/model-settings`：僅限組織管理員。回傳 `{providers:Provider[], default:ModelSelection|null,revision:number}`。絕不回傳 API key 或 ciphertext。
- `PUT /api/model-settings`：僅限組織管理員；Cookie 驗證須通過 Origin／CSRF。本文 `{providers:[{id,name,base_url,api_key?:string,enabled:boolean,models:ModelDefinition[]}],default:ModelSelection|null}`。省略 `api_key` 或傳入空值會保留該 Provider 現有 key。新增啟用中的 Provider 必須提供 key。替換設定時，只能在目前組織及相同 Provider ID 範圍內保留 key；變更 base URL 必須明確提供新 key。Key 在伺服器端以本機 encryption key 加密後儲存在被忽略的 Work 資料目錄。憑證絕不可出現在冪等快取、稽核、錯誤或一般回應中。若實作可行，寫入應支援 revision／CAS 以避免更新遺失；mutation 不可快取機密。
- `GET /api/model-catalog`：已授權 Work 人類使用者或範圍內 Agent 可呼叫。回傳所屬組織的 `{providers:Provider[],default:ModelSelection|null,revision:number}`，只含已啟用／已設定的 Provider，並省略憑證。Agent 表單使用此資料。
- `Provider`：`{id,name,base_url,enabled,key_configured:boolean,models:ModelDefinition[]}`。
- `ModelDefinition`：`{id,name,context_window:number,max_output_tokens:number,reasoning_efforts:("low"|"medium"|"high"|"xhigh"|"max")[]}`。限制值是營運者提供的中繼資料，不代表已驗證付費 Provider。
- `ModelSelection`：`{provider_id:string,model_id:string,reasoning_effort:"low"|"medium"|"high"|"xhigh"|"max",max_output_tokens:number}`。驗證時要求 Provider／model／effort 都屬於設定選項，且 `16 <= output <=` 已設定模型上限；一般執行的預設值為 4096。Pi adapter 最小值為 16；遇到更小的選項必須拒絕，不可默默提高上限。所有 Provider 請求都強制 `store:false`。
- Agent create／patch 新增 `model_config:ModelSelection|null`。Null 表示繼承組織預設值。為維持向下相容，保留舊的字串 `model` 欄位。覆寫值存於以 Agent ID 為 key 的獨立資料表，避免對既有業務資料表執行不安全的 ALTER。Agent 清單包含 `model_config` 與 `effective_model_config`；建立與編輯介面提供相同欄位。PATCH 明確傳入 null 時確實清除覆寫。
- Dispatch 解析目前生效的選項，並在 outbox `payload.model_config` 記錄不含機密的快照。變更預設值／Agent 設定只影響下一次 dispatch，不影響已受理的 Run。未設定 Provider 時仍支援並明確標示 Demo；已設定的即時 Run 失敗時必須回報失敗，不可切回 Demo。

## Runtime 內部交接 {#internal-runtime-handoff}

受信任的主機營運者可使用僅供 Python 呼叫的 `import_model_settings(session, organization_id, body)` 匯入連線設定。此入口共用 API 驗證、加密與 revision 檢查，會留下營運者稽核記錄，且沒有 HTTP 路由。此功能用來設定使用者授權的 development 連線，不會建立人類帳號或弱化 Identity admin 檢查。`scripts/configure_test_model.py` 只會操作自有 development 專案，並透過 Docker exec stdin 傳送本機 key file。

`POST /api/runtime/outbox/{id}/configuration`：本文 `{worker_id,delivery_token}`。只有同組織／專案、目前尚未到期 outbox 的擁有者且 fencing token 有效的 Runtime principal 可呼叫。回傳 `{agent:{id,token},model_config:ModelSelection|null,provider:{id,name,base_url,api_key,models:ModelDefinition[]}|null}`，並帶有 `Cache-Control:no-store`。此含機密端點必須繞過一般冪等回應快取，且不可讓人類／Agent 憑證呼叫。只為事件指定的 Agent 簽發範圍 token（AuthToken 只儲存雜湊；重試時維持穩定，delivery 結束時撤銷）。Runtime 憑證本身絕不執行 Agent 業務操作。不可將 Provider／Agent 機密保存於 Pi transcripts 或 Run records。
`POST /api/runtime/outbox/{id}/renew`：使用相同擁有權本文，僅以既有 fence 續期目前有效的租約。模型執行期間 Runtime 必須同時維持 delivery 與 task 租約有效。
Dispatch 至新建立的專案時，須在同一個 dispatch transaction 中，明確授予同組織的作用中 Runtime delivery principal 對該專案的存取權。這不會授予 Agent 存取權或跨組織權限。既有的 outbox 範圍檢查仍然有效。

## Pi 執行環境 {#pi-runtime}

使用已安裝的實際 Pi Durable Harness／SQLite 與 Pi AI Responses Provider。營運者設定模型時應自行註冊，不可假設套件靜態 OpenAI catalog 已包含 `gpt-6.1-sol`。申領前先取得內部交接資料；key 只保留在伺服器記憶體。套用 Provider base URL、選定模型、支援的 reasoning effort 與輸出上限；強制 `store:false`。重試時遵從已受理的快照，且只持久化非機密的選項。

即使程序層 fallback 模式設為 demo，Runtime 仍應依各事件取得的設定交接選擇即時執行。未設定的事件維持文件所述 demo 行為。呼叫失敗時不可 fallback。從上游 completion event 記錄實際回傳的模型身分、token 使用量及觀察到的工具名稱／呼叫次數，並放入安全 Run receipt；除非另行設定／測量，幣別金額維持未知。`input_tokens` 包含 `uncached_input_tokens`、`cached_input_tokens` 及 `cache_write_tokens`，不能將 Pi 的 uncached input 重新標示為總輸入量。未知使用量為 null。停用自動模型生成重試與 Provider 重新導向。API health 用來識別預設／fallback 模式，不能證明已完成即時模型呼叫。重複 request ID 與 resume 具冪等性；服務重啟後仍待處理的即時 Run 必須重新取得授權交接。

## 本機驗收 {#local-acceptance}

使用使用者明確授權的 HTTPS endpoint／model；不可將憑證傳往其他位置、改選其他模型或無限重試。外部 prompt 只含合成驗收資料。檢查實際 Responses completion 與模型發出的平台工具呼叫、任務提交後進入 `in_review`、具授權的獨立審查者分離，以及重啟後 receipt 持久化。回報請求與回傳的模型 ID、token 使用量、實際工具證據及限制。保留使用者帳號與無關任務。Development 和 production 使用獨立設定／資料庫；除非後續測試明確需要隔離 QA instance，提供的測試連線只設定在 development。
