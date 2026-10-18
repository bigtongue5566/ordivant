# Run 執行控制台、工作流程、Agent 範本與執行隔離 {#run-console-workflows-agent-templates-and-execution-isolation}

修訂日期：2026-10-07。本文件規範使用者選定的 F03、F04／F13 與 F05 實作。Python Work 負責業務授權、持久化控制與工作流程狀態；Pi 負責 transcripts。公開用戶端絕不可取得服務憑證。

## 交付範圍 {#delivery-scope}

Run 檢視與控制、不可變 Agent／工作流程範本、依賴關係感知的自動派送（支援手動／間隔觸發）、專案範圍內的外部 MCP 連線，以及每次 Run 專用的 Docker 工作區與檔案／命令工具。結果仍必須經獨立審查。每個頁面都必須使用真實 API 狀態，並清楚區分 DEMO 與即時收據。

## 責任範圍與新增資料 {#ownership-and-additive-storage}

PM 負責本契約、根目錄 Compose／輔助工具、整合檢查與最終驗收。Backend worker 負責 `backend/**`；runtime worker 負責 `runtime/**` 與新增的 `sandbox/**`；UI worker 負責 `frontend/src/**`。Worker 不得修改其他負責人的檔案。新增資料表保存 Run 狀態／事件／控制、Agent 執行設定、範本版本、工作流程定義／執行個體／步驟、工具連線與沙箱設定檔。既有資料庫必須能啟動並保留資料，不得採破壞性遷移。

## Run 執行控制台 {#run-console}

`Run` 與業務 `Execution` 是不同記錄。Run ID 等於其 dispatch／outbox ID。公開結構：`{id,project_id,task_id,agent_id,execution_id:null|string,status:"queued"|"running"|"paused"|"done"|"failed"|"aborted",desired_action:null|"pause"|"resume"|"stop",control_revision:number,retry_of:null|string,mode:"demo"|"live"|null,model_config:null|ModelSelection,receipt:null|RunReceipt,answer:null|string,error:null|string,created_at,updated_at,started_at:null|string,finished_at:null|string,sandbox:null|object}`。`done` 表示模型回合已提交；任務仍須經獨立審查才能驗收。未知的用量／幣別金額維持 null。

`RunReceipt` 使用既有 Runtime 結構：`{mode:"demo"|"live",requested:ModelSelection|null,returned:{provider_id:string,model_id:string}|null,usage:{input_tokens:number|null,uncached_input_tokens:number|null,cached_input_tokens:number|null,cache_write_tokens:number|null,output_tokens:number|null,total_tokens:number|null}|null,tools:[{name:string,calls:number}],cost_usd:null}`。Input 包含未快取輸入、快取讀取與快取寫入。回傳的身分與用量必須是實際完成時觀察到的資料，不可從請求中繼資料複製，並須標示為已測量。

- `GET /api/runs?project_id=&task_id=&status=` 回傳範圍內的 Run，依建立時間由新到舊排列，最多 200 筆。
- `GET /api/runs/{id}` 回傳範圍內的 Run。
- `GET /api/runs/{id}/events?after_sequence=0` 回傳依序排列的事件 `{sequence,kind,created_at,data}`。每個 Run 最多保存 1000 筆經界定且清理過的事件。類型包含 start、model、tool_start、tool_end、error、control、status 與 sandbox。絕不可儲存工具驗證資料、租約 token、Provider key 或任意請求標頭。
- `POST /api/runs/{id}/control` 本文 `{action:"pause"|"resume"|"stop"|"retry"}`；僅具該專案權限的 manager／admin 可呼叫，且具冪等性。控制操作回傳 Run，retry 回傳新 Run。Pause 採合作式暫停：阻止下一個工具操作（或排隊中的受理），同時 dispatcher 續期同一個有效 execution 租約。已在執行的模型／工具呼叫可完成。`desired_action=pause` 是待處理請求；只有控制閘確實等待時才回報 `status=paused`。UI 說明 Run 會在下一個工具操作前暫停。Resume 只有在擁有權仍有效時，才會為同一個 submission／execution 開啟該閘。Pi 1.0.3 沒有公開 pause API：不可用 abort 終止 submission 再改標為暫停來模擬。全域逾時包含暫停時間。Stop 會立即以 fence 保護／釋放任何正在執行的業務 execution，讓 task 保持 ready，接著要求 Runtime 實際 abort／清理。取消 task 也會阻止尚未受理的 Run，並停止作用中的 Run。待處理的 stop 必須阻止新的 claim。Retry 僅接受 task 已是 ready 狀態的終止 failed／aborted Run；它會建立新的 dispatch／Run，之後再建立新的 execution，並記錄 `retry_of`。不可默默重新開啟已審查／完成的 task。互相衝突的生命週期操作回傳 409。
- `GET /api/runtime/runs/controls?worker_id=` 僅供 Runtime 呼叫，且只限擁有／獲授權的 Run。回傳 `{id,desired_action,control_revision}` 記錄；不得讓人類端點代理任意 URL 或暴露 Runtime 憑證。
- `POST /api/runtime/runs/{id}/sync` 本文 `{worker_id,delivery_token,sequence,status,execution_id?,mode?,receipt?,answer?,error?,events?:[{kind,data}],sandbox?}`。驗證目前 outbox 擁有權／fence 與專案／組織；相同 delivery sequence 可冪等接受，過期擁有者則拒絕。只有連結的 execution 確實提交 artifact 時才可設為 `done`；若審查在終止同步前搶先完成（accept 或 reject），也不會撤銷該次提交。待處理的 stop 不能變成 `done`。Dispatcher 必須先確認冪等業務提交，再做終止同步；拒絕或未確認的提交絕不可呈現為成功。只持久化安全的公開中繼資料。已停止的 outbox 會保留 fence，直到回報／確認 abort，讓實際狀態得以調和。終止時撤銷 delivery credentials；若回應遺失後重播完全相同的終止同步，仍會驗證原始 worker 與 token fingerprint。
- Run 作用期間（包含暫停狀態），Dispatcher 都會處理 control revision。Abort／resume 路徑與程序重新啟動時都會重新驗證業務擁有權。私有且受 fence 保護的 Runtime 交接可能回傳 `execution_lease:null|{task_id,execution_id,agent_id,lease_token,expires_at}`，條件是該 Run 已連結、仍在執行、租約未到期，而且仍由同一 Agent 與 task 擁有。Python transaction 會輪替 lease token，並只把新 token 交給獲授權的 worker；舊 token 仍無效。Dispatcher 會比對持久化的 execution ID，復原時使用該租約，而不是重播已過期的快取 claim token。Pi 或 RunStore 絕不可保存租約／Provider／工具憑證。若復原的 checkpoint 已失去 execution 或租約過期，須以可採取行動的理由標記失敗；絕不可用過期租約繼續執行。即時與 Demo 生成都套用所有限制。
- Runtime 會序列化每個 Run 中會受租約影響的 Python callback 與續期操作。進度、釋放與有範圍限制的平台變更會在該佇列中取得目前 token，不會與 token 輪替競爭，也不會使自己的有效 execution 被 fence。只有在進度更新、heartbeat 停止及佇列中的續期全部完成後，最終提交才會擷取不可變本文。外部 MCP／sandbox 呼叫與模型請求不會占用此佇列，因此租約 heartbeat 可在其執行期間持續。
- 終止 Run 的同步會等到引擎完成清理後再讀取最新持久化記錄；模型提早回報 `done` 時不得發布過時的 workspace `ready` 快照。Executor 成功刪除時回報 `stopped`；未能確認刪除時，回報 sandbox `failed` 與固定且已清理的錯誤。復原的終止記錄若暫存工作區仍標示可用，則回報 sandbox `lost` 並明確說明清理未獲確認。不得重播模型結果，也不可從持久化資料還原憑證／能力。

## Agent 執行設定與不可變範本 {#agent-execution-settings-and-immutable-templates}

`ExecutionConfig`：`{instructions:string,tool_connection_ids:string[],sandbox_profile_id:null|string,limits:{max_turns:number,timeout_seconds:number}}`。Instructions 最多 16000 字元；預設為空指令／無外部連線／無 sandbox，20 回合與 600 秒；可設定範圍為 1..100 回合、30..3600 秒。Backend 會檢查每一項參照資源與模型選項。

Agent create／edit／list 新增 `execution_config:ExecutionConfig` 與 `template_id:null|string`（精確的不可變版本 ID）。建立時若提供 `template_id` 就套用其定義；明確指定的執行／模型覆寫都會經過驗證。編輯設定不會改變既有 Run。Dispatch 會保存不含機密的執行／模型／工具／設定檔快照。Runtime 只會透過既有受 fence 保護且 no-store 的設定交接取得連線驗證資料，絕不保存至 Pi／store。範本變更只影響新套用的版本。

`AgentTemplate`：`{id,key,version,name,description,definition:{role:"worker"|"reviewer",capabilities:string[],instructions:string,model_config:null|ModelSelection,tool_connection_ids:string[],sandbox_profile_id:null|string,limits:{max_turns,timeout_seconds}},created_at}`。

內建範本另有唯讀 `builtin_key:"pm"|"pg"|"sa"|"sd"|"qa"|"reviewer"|null`。啟動時為既有組織補齊六個 v1，新組織建立時同步提供；重複初始化不覆蓋既有資料。自訂範本及衍生新版本回傳 null，僅確切的內建版本在介面本地化。PM／PG／SA／SD／QA 使用 worker，Reviewer 使用 reviewer；不預先綁定模型、工具或 Sandbox。

- `GET /api/agent-templates` 列出目前可見的組織版本；只有 manager／admin 可變更。
- `POST /api/agent-templates` 本文 `{key,name,description?,definition}` 建立 v1；重複 key 會回報衝突。
- `POST /api/agent-templates/{id}/versions` 本文 `{name,description?,definition}` 發布該 key 的新不可變版本。舊版本維持原樣。並行發布不得產生重複版本號。
- 既有的 `POST/PATCH /api/agents` 支援套用精確的 `template_id` 及手動設定；Agent 憑證的一次性簽發規則不變。UI 在建立與編輯時都會顯示範本、指令、工具綁定、sandbox 設定檔及 Run 限制。

## 工作流程與自動派送 {#workflows-and-automatic-dispatch}

`WorkflowStep`：`{key,title,goal,description:string,acceptance_criteria:string[],dependency_keys:string[],agent_id:null|string,capabilities:string[],reviewer_id:null|string,priority:"urgent"|"high"|"medium"|"low"}`。步驟數為 1..20，key 必須唯一，相依關係不得形成循環，且 Agent／reviewer 必須屬於同一專案並在授權範圍內。明確指定 Agent，或以確定性方式依 worker capability 選擇；Agent 不可用／忙碌時應等待，不得捏造結果。不可自動自行審查。

`Workflow`：`{id,project_id,key,version,name,description,steps:WorkflowStep[],schedule:{enabled:boolean,interval_minutes:number,max_runs:number},next_run_at:null|string,created_at}`。定義／步驟為不可變版本；排程可另外編輯。間隔為 1..525600 分鐘；排程執行的 max_runs 為 1..1000。`WorkflowInstance`：`{id,workflow_id,project_id,status:"running"|"waiting"|"completed"|"failed"|"cancelled",trigger:"manual"|"schedule",inputs:string,steps:[{key,task_id,status,run_id:null|string,error:null|string}],created_at,updated_at}`。每個 instance 固定使用一個工作流程版本，保存穩定的 task ID，只有所有步驟都經獨立驗收後才會完成。blocked／failed 工作必須可見並可復原，絕不可回報為已驗收。

- `GET/POST /api/workflows?project_id=`；建立本文 `{project_id,key,name,description?,steps,schedule?}`。
- `POST /api/workflows/{id}/versions` 發布定義 `{name,description?,steps}`；key／project 必須相同，舊版本不可修改。
- `PATCH /api/workflows/{id}/schedule` 本文 `{enabled,interval_minutes,max_runs}`；僅限 manager／admin。
- `POST /api/workflows/{id}/start` 本文 `{inputs?:string}`；manager／admin 可冪等呼叫，回傳每個步驟恰好建立一個 task 的 instance，並含 task dependency IDs。文字輸入有長度限制；不執行任意程式碼或插值 eval。
- `GET /api/workflow-runs?project_id=`；`GET /api/workflow-runs/{id}`。
- `POST /api/workflow-runs/{id}/cancel` `{}`；manager／admin 使用同一個 fence／control service 取消未完成的 task／Run。
- `POST /api/runtime/workflows/tick` `{}` 僅限範圍內 Runtime。以原子操作受理到期排程，避免重疊／追趕風暴；取得工作流程排程狀態的擁有權，使並行 tick 只產生一組 task／outbox 記錄。只有相依任務完成且有可用的獲准 Pi worker（包含尚未完成的 dispatch 預約）時，才派送 ready 步驟。Dispatcher 定期呼叫可讓已驗收的上游步驟自動推進，不須手動派送。不可要求 Knowledge／Code 服務也必須啟動。
- MCP 新增精簡且受範圍限制的 wrapper，供檢視／控制 Run、檢視／啟動範本與工作流程、檢視工具／設定檔；使用相同 REST／業務授權與冪等檢查。

## 專案工具連線 {#project-tool-connections}

第一個 adapter 使用官方 MCP Streamable HTTP。不可提供任意主機 subprocess／stdio launcher。連線以專案為範圍；Runtime 只註冊明確允許且已探索到的工具。提供給 Pi 的工具名稱會加上 namespace，以避免與平台工具衝突。外部工具預設不得安全重播；若副作用結果不確定，不可默默重試。

`ToolConnection`：`{id,project_id,name,endpoint,enabled,allowed_tools:string[],key_configured:boolean,created_at,updated_at}`。變更本文 `{project_id?,name,endpoint,enabled,allowed_tools,auth_token?:string}`；省略 token 或傳入空值時保留加密後的 secret。若原本已設定憑證，變更 endpoint 時必須明確提供新憑證。Secret 只能寫入，以 Work key 加密，且不納入稽核／冪等快取／錯誤。Admin 設定連線；專案範圍內的成員可列出安全中繼資料並使用已授權的綁定。

- `GET/POST /api/tool-connections?project_id=`；`PATCH /api/tool-connections/{id}`。
- `POST /api/tool-connections/{id}/test` `{}` 僅限 admin -> `{ok:true,tools:[{name,description,input_schema}]}`，或回報明確且安全的失敗，不得提供假 fallback。這只是唯讀的 tools/list protocol 檢查，不會任意執行工具。限制回應大小與執行時間。
- 營運者環境變數 `ORDIVANT_TOOL_ALLOWED_HOSTS` 明確允許精確 endpoint host；使用 HTTP 時還須設定 `ORDIVANT_TOOL_HTTP_HOSTS`；每種模式下，只要 DNS 解析到私人／非全球位址，就必須設定 `ORDIVANT_TOOL_PRIVATE_HOSTS`。預設為空，代表拒絕外部 endpoint。拒絕 userinfo／fragment／redirect 及非 HTTP(S) scheme。儲存、探測與 Runtime 每次連線都必須套用政策；只有 QA 可在三個清單中個別允許內部 QA fixture host。私人 HTTPS 服務仍須通過有效 TLS。API 本文無法繞過 host 政策。
- 對已停用／不存在的綁定連線，Dispatch 必須明確失敗。綁定會依執行中的專案篩選；不能繼承其他專案的存取權。受 fence 保護的交接新增 `execution_config`、`tool_connections:[{id,name,endpoint,allowed_tools,auth_token:null|string}]` 及 `sandbox_profile` 快照。對已受理的 Run 而言，模型選擇、執行設定與 MCP／profile 快照皆不可變。Provider 憑證透過既有私有模型交接及目前 Provider 可用性政策解析；不會凍結在公開快照或 Pi 儲存資料中。

## 每次 Run 的執行沙箱 {#per-run-execution-sandboxes}

`SandboxProfile`：`{id,project_id,name,enabled,limits:{timeout_seconds:number,memory_mb:number,cpu_count:number,pids_limit:number,output_bytes:number,workspace_mb:number},created_at,updated_at}`。政策固定為：無網路、使用營運者提供的固定工作 image、非 root、root filesystem 唯讀、移除 capabilities、no-new-privileges，且不掛載主機目錄／socket／secret。限制範圍：timeout 1..120 秒、memory 64..1024 MiB、CPU 0.25..2、pids 16..128、output 1024..65536 bytes、workspace 1..128 MiB。每個 Run 的 tmpfs 工作區只在該 Run 執行命令期間存在；清理前必須將結果檔案／測試內容擷取為證據。重啟會遺失暫存工作區，且必須明確回報。

- `GET/POST /api/sandbox-profiles?project_id=`；`PATCH /api/sandbox-profiles/{id}` 僅限 admin 寫入，讀取則依授權範圍限制。
- Sandbox Runtime 工具：`sandbox_write_file(path,content)`、`sandbox_read_file(path)`、`sandbox_list_files(path?)`、`sandbox_execute(command:string[],timeout_seconds?)`。只允許工作區相對路徑；防止路徑穿越／symlink 脫逸。Command 是 argv，絕不是主機 shell。若需要 shell 語法，明確執行 `/bin/sh -lc`，且只能在隔離工作中執行。所有結果都含 exit_code／stdout／stderr／truncated／duration；失敗與逾時必須保持可見，不可轉成通過的測試。
- 新增的 `sandbox-api` 使用內部 8040 埠、獨立產生的服務 secret 與持久化擁有權中繼資料。只有此受信任 executor 可持有 Docker daemon socket；Runtime 與 web 都不可持有。Executor 接受有界限的建立／命令／檔案／停止操作，並以 Run 擁有權／capability fence 保護。Job 使用唯一名稱、擁有者標籤及隔離 tmpfs 工作區；同一 Run 的命令／檔案操作須序列化。限制並行 job 數量。Run 完成／abort／逾時及服務重新啟動時清理；只能刪除 executor 自己建立且有標籤的 job。呼叫端不能選擇 image、mount、network、environment、Docker flags 或權限。
- Executor endpoints：`GET /health`；`POST /sandboxes` `{run_id,profile:{limits}}` -> `{run_id,status:"ready",token}`，提供每個 Run 一次性 capability；`POST /sandboxes/{run_id}/execute` `{command,timeout_seconds?}`；`POST /sandboxes/{run_id}/files/write` `{path,content}`；`POST /sandboxes/{run_id}/files/read` `{path}`；`POST /sandboxes/{run_id}/files/list` `{path?:"."}`；`DELETE /sandboxes/{run_id}`。Service bearer 保護建立操作；回傳的每 Run bearer 保護 Run 操作。Runtime 交接前先完成 Work 授權。Sandbox secret 絕不可進入模型工具參數／transcripts 或公開狀態。
- 根目錄提供 `compose.sandbox.yaml`、`-WithSandbox` helper（需要 Work／Runtime）、產生的 `sandbox_service_token`、image build 及明確的本機 Docker 隔離檢查。停用 sandbox 的既有安裝仍可使用。私人部署須由營運者控制受信任 executor／daemon；容器隔離不等同 VM 邊界。

## 必要驗收 {#required-acceptance}

Run 控制：排隊中的 stop 會阻止受理；即時／Demo 中斷能安全恢復；過期租約不能提交；停止／重試的記錄維持分開；重複控制／tick 不會重複執行工作；receipt／事件可在服務重啟後保留，跨專案存取會遭拒。範本：不可變版本／套用快照、建立／編輯設定持久化。工作流程：手動與間隔觸發、並行 tick 僅執行一次、能力不足時等待、相依性／審查分離與取消。工具：使用合成 fixture 實際執行 MCP tools/list 與工具呼叫、驗證 allowlist、機密加密／no-store 及專案權限拒絕。沙箱：實際檔案寫入／讀取及成功／失敗命令、跨 Run 檔案拒絕、路徑穿越／symlink 拒絕、逾時／資源／網路隔離、abort／重啟清理。UI：實際 API 滑鼠操作及桌面／390px popup。更新本機主要容器前先完成隔離 QA；保留人類帳號及主要 IdP／模型設定。
