# Work 模型连接与 Agent 设置 {#work-model-connection-and-agent-configuration}

修订日期：2026-10-07。Python Work 负责授权与设置。Identity 凭证与 Provider 凭证互相独立。只有组织管理员可设置 Provider 连接；Agent 与范围受限的 member manager 不能读取或变更凭证。选择模型不会轮替 Provider key。

## Work 公开 API {#public-work-api}

- `POST /api/model-settings/discover`：仅组织管理员；Cookie 须通过 Origin／CSRF。请求 `{id,base_url,api_key?}` 读取 OpenAI 兼容的 `{base_url}/models`，返回 `{source:"provider_api",models:[{id,name,context_window?,max_output_tokens?,reasoning_efforts?}]}`。留空只会重用同组织、同 Provider ID、相同 Base URL 的已保存密钥。未提供的模型能力保持未知，不猜测数值；获取列表不改变现有设置和 revision。请求超时 15 秒、最大响应 1 MiB／2,000 项、不重试、不跟随重定向、不返回上游错误正文、不经过幂等缓存，响应带 `Cache-Control:no-store`。

- `GET /api/model-settings`：仅限组织管理员。回传 `{providers:Provider[], default:ModelSelection|null,revision:number}`。绝不回传 API key 或 ciphertext。
- `PUT /api/model-settings`：仅限组织管理员；Cookie 验证须通过 Origin／CSRF。本文 `{providers:[{id,name,base_url,api_key?:string,enabled:boolean,models:ModelDefinition[]}],default:ModelSelection|null}`。省略 `api_key` 或传入空值会保留该 Provider 现有 key。添加激活中的 Provider 必须提供 key。替换设置时，只能在目前组织及相同 Provider ID 范围内保留 key；变更 base URL 必须明确提供新 key。Key 在服务器端以本机 encryption key 加密后保存在被忽略的 Work 数据目录。凭证绝不可出现在幂等缓存、稽核、错误或一般回应中。若实作可行，写入应支持 revision／CAS 以避免更新遗失；mutation 不可缓存机密。
- `GET /api/model-catalog`：已授权 Work 人类用户或范围内 Agent 可调用。回传所属组织的 `{providers:Provider[],default:ModelSelection|null,revision:number}`，只含已激活／已设置的 Provider，并省略凭证。Agent 表单使用此数据。
- `Provider`：`{id,name,base_url,enabled,key_configured:boolean,models:ModelDefinition[]}`。
- `ModelDefinition`：`{id,name,context_window:number,max_output_tokens:number,reasoning_efforts:("low"|"medium"|"high"|"xhigh"|"max")[]}`。限制值是营运者提供的中继数据，不代表已验证付费 Provider。
- `ModelSelection`：`{provider_id:string,model_id:string,reasoning_effort:"low"|"medium"|"high"|"xhigh"|"max",max_output_tokens:number}`。验证时要求 Provider／model／effort 都属于设置选项，且 `16 <= output <=` 已设置模型上限；一般运行的默认值为 4096。Pi adapter 最小值为 16；遇到更小的选项必须拒绝，不可默默提高上限。所有 Provider 请求都强制 `store:false`。
- Agent create／patch 添加 `model_config:ModelSelection|null`。Null 表示继承组织默认值。为维持向下兼容，保留旧的字符串 `model` 字段。覆写值存于以 Agent ID 为 key 的独立数据表，避免对既有业务数据表运行不安全的 ALTER。Agent 清单包含 `model_config` 与 `effective_model_config`；创建与编辑接口提供相同字段。PATCH 明确传入 null 时确实清除覆写。
- Dispatch 解析目前生效的选项，并在 outbox `payload.model_config` 记录不含机密的快照。变更默认值／Agent 设置只影响下一次 dispatch，不影响已受理的 Run。未设置 Provider 时仍支持并明确标示 Demo；已设置的即时 Run 失败时必须回报失败，不可切回 Demo。

## Runtime 内部交接 {#internal-runtime-handoff}

受信任的主机营运者可使用仅供 Python 调用的 `import_model_settings(session, organization_id, body)` 导入连接设置。此入口共用 API 验证、加密与 revision 检查，会留下营运者稽核记录，且没有 HTTP 路由。此功能用来设置用户授权的 development 连接，不会创建人类账号或弱化 Identity admin 检查。`scripts/configure_test_model.py` 只会操作自有 development 项目，并通过 Docker exec stdin 发送本机 key file。

`POST /api/runtime/outbox/{id}/configuration`：本文 `{worker_id,delivery_token}`。只有同组织／项目、目前尚未到期 outbox 的拥有者且 fencing token 有效的 Runtime principal 可调用。回传 `{agent:{id,token},model_config:ModelSelection|null,provider:{id,name,base_url,api_key,models:ModelDefinition[]}|null}`，并带有 `Cache-Control:no-store`。此含机密端点必须绕过一般幂等回应缓存，且不可让人类／Agent 凭证调用。只为事件指定的 Agent 签发范围 token（AuthToken 只保存哈希；重试时维持稳定，delivery 结束时撤销）。Runtime 凭证本身绝不运行 Agent 业务操作。不可将 Provider／Agent 机密保存于 Pi transcripts 或 Run records。
`POST /api/runtime/outbox/{id}/renew`：使用相同拥有权本文，仅以既有 fence 续期目前有效的租约。模型运行期间 Runtime 必须同时维持 delivery 与 task 租约有效。
Dispatch 至新创建的项目时，须在同一个 dispatch transaction 中，明确授予同组织的作用中 Runtime delivery principal 对该项目的访问权。这不会授予 Agent 访问权或跨组织权限。既有的 outbox 范围检查仍然有效。

## Pi 运行环境 {#pi-runtime}

使用已安装的实际 Pi Durable Harness／SQLite 与 Pi AI Responses Provider。营运者设置模型时应自行注册，不可假设套件静态 OpenAI catalog 已包含 `gpt-6.1-sol`。申领前先取得内部交接数据；key 只保留在服务器内存。套用 Provider base URL、选定模型、支持的 reasoning effort 与输出上限；强制 `store:false`。重试时遵从已受理的快照，且只持久化非机密的选项。

即使进程层 fallback 模式设为 demo，Runtime 仍应依各事件取得的设置交接选择即时运行。未设置的事件维持文档所述 demo 行为。调用失败时不可 fallback。从上游 completion event 记录实际回传的模型身分、token 使用量及观察到的工具名称／调用次数，并放入安全 Run receipt；除非另行设置／测量，币别金额维持未知。`input_tokens` 包含 `uncached_input_tokens`、`cached_input_tokens` 及 `cache_write_tokens`，不能将 Pi 的 uncached input 重新标示为总输入量。未知使用量为 null。停用自动模型生成重试与 Provider 重新导向。API health 用来识别默认／fallback 模式，不能证明已完成即时模型调用。重复 request ID 与 resume 具幂等性；服务重启后仍待处理的即时 Run 必须重新取得授权交接。

## 本机验收 {#local-acceptance}

使用用户明确授权的 HTTPS endpoint／model；不可将凭证传往其他位置、改选其他模型或无限重试。外部 prompt 只含合成验收数据。检查实际 Responses completion 与模型发出的平台工具调用、任务提交后进入 `in_review`、具授权的独立审查者分离，以及重启后 receipt 持久化。回报请求与回传的模型 ID、token 使用量、实际工具证据及限制。保留用户账号与无关任务。Development 和 production 使用独立设置／数据库；除非后续测试明确需要隔离 QA instance，提供的测试连接只设置在 development。
