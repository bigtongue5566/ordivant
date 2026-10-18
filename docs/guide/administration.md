<span id="管理員、角色與企業登入"></span>
<span id="管理员、角色与企业登录"></span>

# 管理員、角色與企業登入 {#administrators-roles-and-enterprise-sign-in}

Ordivant 的瀏覽器登入由共用 Identity 服務提供；Work、Knowledge、Code 各自檢查產品角色和資源範圍。SSO 登入成功只建立使用者的平台工作階段，不會直接授予 Agent token、Runtime 身分或 Gitea 憑證。

<span id="初始管理員與成員"></span>
<span id="初始管理员与成员"></span>

## 初始管理員與成員 {#first-administrator-and-members}

每個 Compose 專案／環境都有自己的 Identity 資料。第一次開啟 Web 時，請為該環境建立第一位管理員；系統沒有預設使用者帳號。管理員可邀請成員、停用帳號、撤銷工作階段，並授予產品角色，以及 Work Project、Knowledge Space、Code Project 的明確資源範圍。

若管理員已設定 SMTP，Identity 會將邀請和本機帳號復原郵件放入持久佇列並寄送；否則不會嘗試寄信，管理員須安全地以其他方式提供一次性邀請碼。郵件中的連結會過期且只能使用一次；本機帳號仍可使用登入時提供的復原碼。一般成員只能查看明確授權的資源。建立新的 Project 或 Space 由管理員負責。

<span id="產品角色"></span>
<span id="产品角色"></span>

## 產品角色 {#product-roles}

| 產品 | 角色 | 主要權限 |
|---|---|---|
| Work | Manager | 管理已授權專案的工作與執行安排 |
| Work | Worker | 執行獲授權任務並提交成果 |
| Work | Reviewer | 獨立審查成果；不可接受自己的提交 |
| Knowledge | Manager | 管理已授權 Space 內的文件和決策；新增 Space 由 Identity 管理員建立 |
| Knowledge | Writer | 建立文件、發佈新版本、記錄決策 |
| Knowledge | Reader | 搜尋與閱讀已授權 Space |
| Code | Manager | 管理已授權 Code Project |
| Code | Writer | 在已授權 Project 建立 repository 及變更 |
| Code | Reader | 查閱 Project、repository、PR 和狀態收據 |

Identity 的組織管理員（`admin`）可管理成員和授權；產品角色是另一層權限。同一人在三個產品可以有不同角色或範圍。Agent 使用各自獨立且受資源範圍限制的身分；不能用一個產品的權限推導另一個產品的存取權。

<span id="設定企業-oidc"></span>
<span id="设置企业-oidc"></span>

## 設定企業 OIDC {#configure-enterprise-oidc}

1. 以管理員登入該環境，開啟「組織管理 → 企業 SSO」。
2. 在企業 IdP 建立機密用戶端類型的 OIDC Web 應用程式，啟用 Authorization Code 與 PKCE S256。
3. 將 Ordivant 介面顯示的完整 `Callback URL` 註冊為 `Redirect URI`，不可使用萬用字元。
4. 輸入該組織的 `Issuer`、`Client ID`、`Client Secret`、允許網域與成員佈建政策；需要群組時，設定 IdP 的 `groups` claim 及明確的產品／範圍對應。
5. 儲存後執行連線測試，再以一般成員測試登入、產品存取及登出。確認管理員復原路徑可用後，才考慮啟用 `SSO-only`。

成員依受邀或明確設定的 JIT 政策加入；相同電子郵件網域本身不會授予全組織權限。Client Secret 會加密保存，表單不會回填明文。直接 OIDC 是登入協定；若企業只提供 SAML 或 LDAP／Active Directory，可選擇 Keycloak broker。啟用 required_acr 或 required_amr 時，成員登入政策必須是 SSO-only；Identity 會檢查已驗證 IdP 權杖中的 assurance claim，平台本身不提供 MFA 因子。詳細設定見[企業登入說明](../enterprise-sso.md)。

## SCIM、MFA、郵件與稽核治理 {#enterprise-provisioning-mfa-mail-audit}

管理員在側欄開啟「組織管理」→「企業治理」，可查看 SCIM／郵件服務狀態、設定群組權限對應與稽核保留政策、匯出 Identity 稽核紀錄，以及查看或重試可重試的郵件。SCIM 端點由此畫面顯示；部署管理員須另外提供 ORDIVANT_SCIM_TOKEN_FILE，並將該專用 bearer credential 設定在企業佈建服務。SCIM 支援 Users 和 Groups；目前不支援 SCIM bulk 操作。

在「儲存群組授權」前，先依 IdP 提供的群組完整名稱建立對應，再用權限編輯器選取明確的產品角色及資源 ID。SCIM 群組不會取得組織 admin；使用萬用資源範圍也會被拒絕。一般 SCIM User PATCH 若嘗試修改由 SCIM 管理的產品權限，會回傳 HTTP 409；不能透過一般 PATCH 手動切換權限管理來源。請更新 IdP 群組成員或這裡的群組對應，再讓 SCIM 同步。明確連結 OIDC 帳號時，須使用 `managed_permissions=false`，保留 SCIM 作為群組權限的管理來源。SCIM 建立使用者時若同一電子郵件已屬於既有 Ordivant 帳號，佈建會回報衝突，不會自動認領、合併或改變帳號；請先經明確的管理員帳號連結／移轉流程處理。SCIM 停用使用者或改變群組授權會撤銷其既有 Identity sessions。

Docker Compose 部署可選用唯讀的 `compose.enterprise.yaml`，把 Identity 與 Code 的機密目錄分開掛載。SCIM token 與 SMTP 密碼檔放在 Identity 的掛載目錄；Code 部署設定及其 token 檔放在 Code 的目錄。操作步驟見[容器部署指南](../containers.md#enterprise-secret-mounts)與[Code 部署證據設定](code.md#upstream-governance-and-deployment-evidence)。不要把機密值寫入 `.env`。

MFA 由企業 IdP 執行。在「組織管理」→「企業 SSO」設定必須符合的登入強度 acr 值，及必須包含的驗證方式 amr（例如 mfa），再要求使用 SSO-only 成員登入。acr 必須符合清單中的其中一個值，amr 必須包含全部指定方式；請先確認 IdP 實際簽發的已驗證登入權杖包含這些 claims，再測試一般成員和管理員復原路徑。

寄送邀請與帳號復原郵件前，部署管理員須設定 SMTP host、port、sender、TLS，及需要時的帳號與密碼檔（ORDIVANT_SMTP_HOST、ORDIVANT_SMTP_PORT、ORDIVANT_SMTP_SENDER、ORDIVANT_SMTP_STARTTLS、ORDIVANT_SMTP_USERNAME、ORDIVANT_SMTP_PASSWORD_FILE）。正式環境要求 STARTTLS；未設定必要欄位時 Identity 不會寄信。到「企業治理」查看郵件佇列狀態；暫時或失敗項目可重試，過期郵件不可重試。資源追蹤與協作中心通知只顯示於 Ordivant，不會經此 SMTP 寄送。

稽核匯出是受管理員權限保護的 JSONL 檔，內容只含 Identity 稽核允許匯出的欄位，不是 Work、Knowledge、Code 三個產品事件的合併匯出。介面會自動分頁，但最多匯出 100,000 筆或 50 MiB；超過任一上限時會拒絕產生不完整檔案，請改用 API 分批匯出。Identity 管理員 API `GET /auth-api/audit/export` 接受 `limit=1..10000`；下一頁使用回應標頭 `X-Next-Before` 與 `X-Next-Before-Id` 的值，一起作為 `before` 和 `before_id` 複合游標。先匯出需要保存的紀錄，再設定 30 至 3650 天保留期並明確選擇套用；套用會刪除超過期限的 Identity 稽核列。

<span id="agent-與模型連線"></span>
<span id="agent-与模型连接"></span>

## Agent 與模型連線 {#agents-and-model-connections}

組織管理員先設定模型供應商、API 網址、金鑰及模型，再選擇組織預設值。建立或編輯 Agent 時，可繼承預設值或選用其他已設定模型。已保存的金鑰與工具存取權杖不會回填明文；要更換時請輸入新的值。操作步驟見[模型設定](../model-usage.md)與[Run 及工具指南](../execution-usage.md)。

正式環境使用前，請檢查 TLS、可信任的網站來源（Origin）、允許的成員佈建策略、Project／Space 授權範圍，以及復原碼的保管方式。SSO 不會取代各產品的伺服器端授權。

## 使用者 API 與 MCP {#personal-api-and-mcp-access}

在側欄帳號選單開啟「帳號設定 → API 與 MCP」，輸入用途名稱、允許的產品與有效期限，再建立個人存取權杖。完整權杖只顯示一次；清單只顯示前綴、到期時間與上次使用時間。此處也提供目前環境的 API 和 MCP 連線範例。

權杖透過 `Authorization: Bearer <PERSONAL_ACCESS_TOKEN>` 使用。它代表你的真人帳號，沿用目前的產品角色及 Project／Space 範圍，不會取得 Agent 身分或額外權限。管理員可建立資源；一般成員只能操作獲授權的資源。三個產品的本機 API 根網址如下：

以下以預設 Docker Compose 的 `http://127.0.0.1:8088` 為例；若你使用不同連接埠或 HTTPS 網域，請改用自己環境的網址。介面會依目前網站產生對應範例。

| 產品 | 本機 API 根網址 | 起始操作 |
|---|---|---|
| Work | `http://127.0.0.1:8088/api` | `GET /me`、`GET /projects` |
| Knowledge | `http://127.0.0.1:8088/knowledge-api` | `GET /me`、`GET /spaces` |
| Code | `http://127.0.0.1:8088/code-api` | `GET /me`、`GET /projects` |

例如先確認 Work 身分：

```sh
curl "http://127.0.0.1:8088/api/me" -H "Authorization: Bearer <PERSONAL_ACCESS_TOKEN>"
```

MCP 使用本機 stdio bridge，需安裝 uv 並取得 Ordivant 原始碼。把介面的設定範例加入支援 stdio 的 MCP 用戶端；替換原始碼目錄與權杖後，以各產品自己的 Python 專案啟動：

| 產品 | 專案目錄 | 模組 | 環境變數 |
|---|---|---|---|
| Work | `backend` | `ordivant.mcp_server` | `ORDIVANT_API_URL`、`ORDIVANT_API_TOKEN` |
| Knowledge | `products/knowledge/backend` | `ordivant_knowledge.mcp_server` | `ORDIVANT_KNOWLEDGE_API_URL`、`ORDIVANT_KNOWLEDGE_API_TOKEN` |
| Code | `products/code/backend` | `ordivant_code.mcp_server` | `ORDIVANT_CODE_API_URL`、`ORDIVANT_CODE_API_TOKEN` |

啟動命令形式為 `uv run --project <專案絕對路徑> python -m <模組>`。網址使用上表的 API 根網址；權杖須允許對應產品。先呼叫 `get_me` 確認身分，再使用 Work 的 `list_projects`、Knowledge 的 `list_spaces` 或 Code 的 `list_code_projects`。建立資源的工具分別為 `create_project`、`create_space`、`create_code_project`；這些工具及既有業務工具都交由 REST API 執行相同授權。變更操作接受 `request_id`，重試同一次操作時請重用該值。

可隨時在權杖清單撤銷連線；到期、帳號停用或產品權限變更會影響後續請求。變更密碼或完成帳號復原也會撤銷既有權杖。「登出所有裝置」只撤銷瀏覽器工作階段；外部工具須另外撤銷權杖。權杖不能管理或建立其他權杖，管理操作仍需瀏覽器登入及 CSRF 驗證。
