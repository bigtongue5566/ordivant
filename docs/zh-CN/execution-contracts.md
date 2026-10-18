# Run 运行控制台、工作流程、Agent 范本与运行隔离 {#run-console-workflows-agent-templates-and-execution-isolation}

修订日期：2026-10-07。本文档规范用户选定的 F03、F04／F13 与 F05 实作。Python Work 负责业务授权、持久化控制与工作流程状态；Pi 负责 transcripts。公开用户端绝不可取得服务凭证。

## 交付范围 {#delivery-scope}

Run 查看与控制、不可变 Agent／工作流程范本、依赖关系感知的自动派送（支持手动／间隔触发）、项目范围内的外部 MCP 连接，以及每次 Run 专用的 Docker 工作区与文件／命令工具。结果仍必须经独立审查。每个页面都必须使用真实 API 状态，并清楚区分 DEMO 与即时收据。

## 责任范围与添加数据 {#ownership-and-additive-storage}

PM 负责本契约、根目录 Compose／辅助工具、集成检查与最终验收。Backend worker 负责 `backend/**`；runtime worker 负责 `runtime/**` 与添加的 `sandbox/**`；UI worker 负责 `frontend/src/**`。Worker 不得修改其他负责人的文件。添加数据表保存 Run 状态／事件／控制、Agent 运行设置、范本版本、工作流程定义／运行个体／步骤、工具连接与沙箱设置档。既有数据库必须能启动并保留数据，不得采破坏性迁移。

## Run 运行控制台 {#run-console}

`Run` 与业务 `Execution` 是不同记录。Run ID 等于其 dispatch／outbox ID。公开结构：`{id,project_id,task_id,agent_id,execution_id:null|string,status:"queued"|"running"|"paused"|"done"|"failed"|"aborted",desired_action:null|"pause"|"resume"|"stop",control_revision:number,retry_of:null|string,mode:"demo"|"live"|null,model_config:null|ModelSelection,receipt:null|RunReceipt,answer:null|string,error:null|string,created_at,updated_at,started_at:null|string,finished_at:null|string,sandbox:null|object}`。`done` 表示模型回合已提交；任务仍须经独立审查才能验收。未知的用量／币别金额维持 null。

`RunReceipt` 使用既有 Runtime 结构：`{mode:"demo"|"live",requested:ModelSelection|null,returned:{provider_id:string,model_id:string}|null,usage:{input_tokens:number|null,uncached_input_tokens:number|null,cached_input_tokens:number|null,cache_write_tokens:number|null,output_tokens:number|null,total_tokens:number|null}|null,tools:[{name:string,calls:number}],cost_usd:null}`。Input 包含未缓存输入、缓存读取与缓存写入。回传的身分与用量必须是实际完成时观察到的数据，不可从请求中继数据拷贝，并须标示为已测量。

- `GET /api/runs?project_id=&task_id=&status=` 回传范围内的 Run，依创建时间由新到旧排列，最多 200 笔。
- `GET /api/runs/{id}` 回传范围内的 Run。
- `GET /api/runs/{id}/events?after_sequence=0` 回传依序排列的事件 `{sequence,kind,created_at,data}`。每个 Run 最多保存 1000 笔经界定且清理过的事件。类型包含 start、model、tool_start、tool_end、error、control、status 与 sandbox。绝不可保存工具验证数据、租约 token、Provider key 或任意请求标头。
- `POST /api/runs/{id}/control` 本文 `{action:"pause"|"resume"|"stop"|"retry"}`；仅具该项目权限的 manager／admin 可调用，且具幂等性。控制操作回传 Run，retry 回传新 Run。Pause 采合作式暂停：阻止下一个工具操作（或排队中的受理），同时 dispatcher 续期同一个有效 execution 租约。已在运行的模型／工具调用可完成。`desired_action=pause` 是待处理请求；只有控制闸确实等待时才回报 `status=paused`。UI 说明 Run 会在下一个工具操作前暂停。Resume 只有在拥有权仍有效时，才会为同一个 submission／execution 打开该闸。Pi 1.0.3 没有公开 pause API：不可用 abort 终止 submission 再改标为暂停来仿真。全域逾时包含暂停时间。Stop 会立即以 fence 保护／释放任何正在运行的业务 execution，让 task 保持 ready，接着要求 Runtime 实际 abort／清理。取消 task 也会阻止尚未受理的 Run，并停止作用中的 Run。待处理的 stop 必须阻止新的 claim。Retry 仅接受 task 已是 ready 状态的终止 failed／aborted Run；它会创建新的 dispatch／Run，之后再创建新的 execution，并记录 `retry_of`。不可默默重新打开已审查／完成的 task。互相冲突的生命周期操作回传 409。
- `GET /api/runtime/runs/controls?worker_id=` 仅供 Runtime 调用，且只限拥有／获授权的 Run。回传 `{id,desired_action,control_revision}` 记录；不得让人类端点代理任意 URL 或暴露 Runtime 凭证。
- `POST /api/runtime/runs/{id}/sync` 本文 `{worker_id,delivery_token,sequence,status,execution_id?,mode?,receipt?,answer?,error?,events?:[{kind,data}],sandbox?}`。验证目前 outbox 拥有权／fence 与项目／组织；相同 delivery sequence 可幂等接受，过期拥有者则拒绝。只有链接的 execution 确实提交 artifact 时才可设为 `done`；若审查在终止同步前抢先完成（accept 或 reject），也不会撤销该次提交。待处理的 stop 不能变成 `done`。Dispatcher 必须先确认幂等业务提交，再做终止同步；拒绝或未确认的提交绝不可呈现为成功。只持久化安全的公开中继数据。已停止的 outbox 会保留 fence，直到回报／确认 abort，让实际状态得以调和。终止时撤销 delivery credentials；若回应遗失后重播完全相同的终止同步，仍会验证原始 worker 与 token fingerprint。
- Run 作用期间（包含暂停状态），Dispatcher 都会处理 control revision。Abort／resume 路径与进程重新启动时都会重新验证业务拥有权。私有且受 fence 保护的 Runtime 交接可能回传 `execution_lease:null|{task_id,execution_id,agent_id,lease_token,expires_at}`，条件是该 Run 已链接、仍在运行、租约未到期，而且仍由同一 Agent 与 task 拥有。Python transaction 会轮替 lease token，并只把新 token 交给获授权的 worker；旧 token 仍无效。Dispatcher 会比对持久化的 execution ID，复原时使用该租约，而不是重播已过期的缓存 claim token。Pi 或 RunStore 绝不可保存租约／Provider／工具凭证。若复原的 checkpoint 已失去 execution 或租约过期，须以可采取行动的理由标记失败；绝不可用过期租约继续运行。即时与 Demo 生成都套用所有限制。
- Runtime 会串行化每个 Run 中会受租约影响的 Python callback 与续期操作。进度、释放与有范围限制的平台变更会在该队列中取得目前 token，不会与 token 轮替竞争，也不会使自己的有效 execution 被 fence。只有在进度更新、heartbeat 停止及队列中的续期全部完成后，最终提交才会截取不可变本文。外部 MCP／sandbox 调用与模型请求不会占用此队列，因此租约 heartbeat 可在其运行期间持续。
- 终止 Run 的同步会等到引擎完成清理后再读取最新持久化记录；模型提早回报 `done` 时不得发布过时的 workspace `ready` 快照。Executor 成功删除时回报 `stopped`；未能确认删除时，回报 sandbox `failed` 与固定且已清理的错误。复原的终止记录若暂存工作区仍标示可用，则回报 sandbox `lost` 并明确说明清理未获确认。不得重播模型结果，也不可从持久化数据还原凭证／能力。

## Agent 运行设置与不可变范本 {#agent-execution-settings-and-immutable-templates}

`ExecutionConfig`：`{instructions:string,tool_connection_ids:string[],sandbox_profile_id:null|string,limits:{max_turns:number,timeout_seconds:number}}`。Instructions 最多 16000 字符；默认为空指令／无外部连接／无 sandbox，20 回合与 600 秒；可设置范围为 1..100 回合、30..3600 秒。Backend 会检查每一项参照资源与模型选项。

Agent create／edit／list 添加 `execution_config:ExecutionConfig` 与 `template_id:null|string`（精确的不可变版本 ID）。创建时若提供 `template_id` 就套用其定义；明确指定的运行／模型覆写都会经过验证。编辑设置不会改变既有 Run。Dispatch 会保存不含机密的运行／模型／工具／设置档快照。Runtime 只会通过既有受 fence 保护且 no-store 的设置交接取得连接验证数据，绝不保存至 Pi／store。范本变更只影响新套用的版本。

`AgentTemplate`：`{id,key,version,name,description,definition:{role:"worker"|"reviewer",capabilities:string[],instructions:string,model_config:null|ModelSelection,tool_connection_ids:string[],sandbox_profile_id:null|string,limits:{max_turns,timeout_seconds}},created_at}`。

内建范本另有唯读 `builtin_key:"pm"|"pg"|"sa"|"sd"|"qa"|"reviewer"|null`。启动时为既有组织补齐六个 v1，新组织建立时同步提供；重复初始化不覆盖既有资料。自订范本及衍生新版本回传 null，仅确切的内建版本在介面本地化。PM／PG／SA／SD／QA 使用 worker，Reviewer 使用 reviewer；不预先绑定模型、工具或 Sandbox。

- `GET /api/agent-templates` 列出目前可见的组织版本；只有 manager／admin 可变更。
- `POST /api/agent-templates` 本文 `{key,name,description?,definition}` 创建 v1；重复 key 会回报冲突。
- `POST /api/agent-templates/{id}/versions` 本文 `{name,description?,definition}` 发布该 key 的新不可变版本。旧版本维持原样。并行发布不得产生重复版本号。
- 既有的 `POST/PATCH /api/agents` 支持套用精确的 `template_id` 及手动设置；Agent 凭证的一次性签发规则不变。UI 在创建与编辑时都会显示范本、指令、工具绑定、sandbox 设置档及 Run 限制。

## 工作流程与自动派送 {#workflows-and-automatic-dispatch}

`WorkflowStep`：`{key,title,goal,description:string,acceptance_criteria:string[],dependency_keys:string[],agent_id:null|string,capabilities:string[],reviewer_id:null|string,priority:"urgent"|"high"|"medium"|"low"}`。步骤数为 1..20，key 必须唯一，相依关系不得形成循环，且 Agent／reviewer 必须属于同一项目并在授权范围内。明确指定 Agent，或以确定性方式依 worker capability 选择；Agent 不可用／忙碌时应等待，不得捏造结果。不可自动自行审查。

`Workflow`：`{id,project_id,key,version,name,description,steps:WorkflowStep[],schedule:{enabled:boolean,interval_minutes:number,max_runs:number},next_run_at:null|string,created_at}`。定义／步骤为不可变版本；调度可另外编辑。间隔为 1..525600 分钟；调度运行的 max_runs 为 1..1000。`WorkflowInstance`：`{id,workflow_id,project_id,status:"running"|"waiting"|"completed"|"failed"|"cancelled",trigger:"manual"|"schedule",inputs:string,steps:[{key,task_id,status,run_id:null|string,error:null|string}],created_at,updated_at}`。每个 instance 固定使用一个工作流程版本，保存稳定的 task ID，只有所有步骤都经独立验收后才会完成。blocked／failed 工作必须可见并可复原，绝不可回报为已验收。

- `GET/POST /api/workflows?project_id=`；创建本文 `{project_id,key,name,description?,steps,schedule?}`。
- `POST /api/workflows/{id}/versions` 发布定义 `{name,description?,steps}`；key／project 必须相同，旧版本不可修改。
- `PATCH /api/workflows/{id}/schedule` 本文 `{enabled,interval_minutes,max_runs}`；仅限 manager／admin。
- `POST /api/workflows/{id}/start` 本文 `{inputs?:string}`；manager／admin 可幂等调用，回传每个步骤恰好创建一个 task 的 instance，并含 task dependency IDs。文本输入有长度限制；不运行任意代码或插值 eval。
- `GET /api/workflow-runs?project_id=`；`GET /api/workflow-runs/{id}`。
- `POST /api/workflow-runs/{id}/cancel` `{}`；manager／admin 使用同一个 fence／control service 取消未完成的 task／Run。
- `POST /api/runtime/workflows/tick` `{}` 仅限范围内 Runtime。以原子操作受理到期调度，避免重叠／追赶风暴；取得工作流程调度状态的拥有权，使并行 tick 只产生一组 task／outbox 记录。只有相依任务完成且有可用的获准 Pi worker（包含尚未完成的 dispatch 预约）时，才派送 ready 步骤。Dispatcher 定期调用可让已验收的上游步骤自动推进，不须手动派送。不可要求 Knowledge／Code 服务也必须启动。
- MCP 添加精简且受范围限制的 wrapper，供查看／控制 Run、查看／启动范本与工作流程、查看工具／设置档；使用相同 REST／业务授权与幂等检查。

## 项目工具连接 {#project-tool-connections}

第一个 adapter 使用官方 MCP Streamable HTTP。不可提供任意主机 subprocess／stdio launcher。连接以项目为范围；Runtime 只注册明确允许且已探索到的工具。提供给 Pi 的工具名称会加上 namespace，以避免与平台工具冲突。外部工具默认不得安全重播；若副作用结果不确定，不可默默重试。

`ToolConnection`：`{id,project_id,name,endpoint,enabled,allowed_tools:string[],key_configured:boolean,created_at,updated_at}`。变更本文 `{project_id?,name,endpoint,enabled,allowed_tools,auth_token?:string}`；省略 token 或传入空值时保留加密后的 secret。若原本已设置凭证，变更 endpoint 时必须明确提供新凭证。Secret 只能写入，以 Work key 加密，且不纳入稽核／幂等缓存／错误。Admin 设置连接；项目范围内的成员可列出安全中继数据并使用已授权的绑定。

- `GET/POST /api/tool-connections?project_id=`；`PATCH /api/tool-connections/{id}`。
- `POST /api/tool-connections/{id}/test` `{}` 仅限 admin -> `{ok:true,tools:[{name,description,input_schema}]}`，或回报明确且安全的失败，不得提供假 fallback。这只是唯读的 tools/list protocol 检查，不会任意运行工具。限制回应大小与运行时间。
- 营运者环境变量 `ORDIVANT_TOOL_ALLOWED_HOSTS` 明确允许精确 endpoint host；使用 HTTP 时还须设置 `ORDIVANT_TOOL_HTTP_HOSTS`；每种模式下，只要 DNS 解析到私人／非全球地址，就必须设置 `ORDIVANT_TOOL_PRIVATE_HOSTS`。默认为空，代表拒绝外部 endpoint。拒绝 userinfo／fragment／redirect 及非 HTTP(S) scheme。保存、探测与 Runtime 每次连接都必须套用政策；只有 QA 可在三个清单中个别允许内部 QA fixture host。私人 HTTPS 服务仍须通过有效 TLS。API 本文无法绕过 host 政策。
- 对已停用／不存在的绑定连接，Dispatch 必须明确失败。绑定会依运行中的项目筛选；不能继承其他项目的访问权。受 fence 保护的交接添加 `execution_config`、`tool_connections:[{id,name,endpoint,allowed_tools,auth_token:null|string}]` 及 `sandbox_profile` 快照。对已受理的 Run 而言，模型选择、运行设置与 MCP／profile 快照皆不可变。Provider 凭证通过既有私有模型交接及目前 Provider 可用性政策解析；不会冻结在公开快照或 Pi 保存数据中。

## 每次 Run 的运行沙箱 {#per-run-execution-sandboxes}

`SandboxProfile`：`{id,project_id,name,enabled,limits:{timeout_seconds:number,memory_mb:number,cpu_count:number,pids_limit:number,output_bytes:number,workspace_mb:number},created_at,updated_at}`。政策固定为：无网络、使用营运者提供的固定工作 image、非 root、root filesystem 唯读、移除 capabilities、no-new-privileges，且不挂载主机目录／socket／secret。限制范围：timeout 1..120 秒、memory 64..1024 MiB、CPU 0.25..2、pids 16..128、output 1024..65536 bytes、workspace 1..128 MiB。每个 Run 的 tmpfs 工作区只在该 Run 运行命令期间存在；清理前必须将结果文件／测试内容截取为证据。重启会遗失暂存工作区，且必须明确回报。

- `GET/POST /api/sandbox-profiles?project_id=`；`PATCH /api/sandbox-profiles/{id}` 仅限 admin 写入，读取则依授权范围限制。
- Sandbox Runtime 工具：`sandbox_write_file(path,content)`、`sandbox_read_file(path)`、`sandbox_list_files(path?)`、`sandbox_execute(command:string[],timeout_seconds?)`。只允许工作区相对路径；防止路径穿越／symlink 脱逸。Command 是 argv，绝不是主机 shell。若需要 shell 语法，明确运行 `/bin/sh -lc`，且只能在隔离工作中运行。所有结果都含 exit_code／stdout／stderr／truncated／duration；失败与逾时必须保持可见，不可转成通过的测试。
- 添加的 `sandbox-api` 使用内部 8040 端口、独立产生的服务 secret 与持久化拥有权中继数据。只有此受信任 executor 可持有 Docker daemon socket；Runtime 与 web 都不可持有。Executor 接受有界限的创建／命令／文件／停止操作，并以 Run 拥有权／capability fence 保护。Job 使用唯一名称、拥有者标签及隔离 tmpfs 工作区；同一 Run 的命令／文件操作须串行化。限制并行 job 数量。Run 完成／abort／逾时及服务重新启动时清理；只能删除 executor 自己创建且有标签的 job。调用端不能选择 image、mount、network、environment、Docker flags 或权限。
- Executor endpoints：`GET /health`；`POST /sandboxes` `{run_id,profile:{limits}}` -> `{run_id,status:"ready",token}`，提供每个 Run 一次性 capability；`POST /sandboxes/{run_id}/execute` `{command,timeout_seconds?}`；`POST /sandboxes/{run_id}/files/write` `{path,content}`；`POST /sandboxes/{run_id}/files/read` `{path}`；`POST /sandboxes/{run_id}/files/list` `{path?:"."}`；`DELETE /sandboxes/{run_id}`。Service bearer 保护创建操作；回传的每 Run bearer 保护 Run 操作。Runtime 交接前先完成 Work 授权。Sandbox secret 绝不可进入模型工具参数／transcripts 或公开状态。
- 根目录提供 `compose.sandbox.yaml`、`-WithSandbox` helper（需要 Work／Runtime）、产生的 `sandbox_service_token`、image build 及明确的本机 Docker 隔离检查。停用 sandbox 的既有安装仍可使用。私人部署须由营运者控制受信任 executor／daemon；容器隔离不等同 VM 边界。

## 必要验收 {#required-acceptance}

Run 控制：排队中的 stop 会阻止受理；即时／Demo 中断能安全恢复；过期租约不能提交；停止／重试的记录维持分开；重复控制／tick 不会重复运行工作；receipt／事件可在服务重启后保留，跨项目访问会遭拒。范本：不可变版本／套用快照、创建／编辑设置持久化。工作流程：手动与间隔触发、并行 tick 仅运行一次、能力不足时等待、相依性／审查分离与取消。工具：使用合成 fixture 实际运行 MCP tools/list 与工具调用、验证 allowlist、机密加密／no-store 及项目权限拒绝。沙箱：实际文件写入／读取及成功／失败命令、跨 Run 文件拒绝、路径穿越／symlink 拒绝、逾时／资源／网络隔离、abort／重启清理。UI：实际 API 鼠标操作及桌面／390px popup。更新本机主要容器前先完成隔离 QA；保留人类账号及主要 IdP／模型设置。
