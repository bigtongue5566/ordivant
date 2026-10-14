# 企業身分修訂（2026-10-07） {#enterprise-identity-revision-2026-10-07}

本契約記錄 2026-10-07 的 OIDC 企業身分修訂，為既有共用 Identity 服務定義 Entra ID／Google Workspace／Okta／Auth0／Keycloak／通用 OIDC 範本、受限佈建、群組權限、生命週期撤銷與身分稽核。SAML 與 LDAP／AD 身分提供者透過選配的 Keycloak broker 串接；原生 SAML 不在支援範圍。當時 SCIM 尚未支援；2026-10-15 新增的 SCIM 與 assurance 擴充見下方契約。未設定的供應商租戶仍不得宣稱已完成驗證。

## 責任範圍 {#ownership}

- PM 負責本契約、根目錄 Compose／工具、整合與最終驗收。
- SSO backend worker 負責 `products/identity/backend/**`，包含相依套件、lockfile 與具實質意義的安全性測試。
- SSO frontend worker 負責 `frontend/src/auth/**`，包含新增的 SSO 設定／稽核元件。最後的權限調整也只將新 scope 建立可見性、handler 保護及空狀態文字指派到 `frontend/src/App.tsx`、`frontend/src/products/knowledge/KnowledgeApp.tsx`、`frontend/src/products/code/CodeApp.tsx`。保留其他 worker 的變更；既有 scope 的業務授權維持不變。
- SSO QA worker 僅負責 `scripts/sso_acceptance.py`、`scripts/sso_fixture.py` 與 `tests/fixtures/sso/**`。建立 fixture realm／client 匯入設定，涵蓋直接 OIDC，以及聯邦至 broker realm 的上游 Keycloak SAML realm。PM 負責啟動真實 Keycloak fixture 的 Compose overlay。
- 所有 worker 開始前先閱讀 `docs/contracts.md`、`docs/project-plan.md`、`docs/auth-contracts.md` 與本契約。共用資料結構若要變更，先向 PM 提出。

## 設定與 API {#configuration-and-api}

每個 Identity 環境（一個本機組織）設定一個 OIDC provider。所有新增公開路由位於 `/api/auth` 下；瀏覽器使用 `/auth-api`。設定會持久化、採 singleton 並以 revision fence 保護；僅限 admin，變更操作須通過 Origin + CSRF。Client secret 使用專用且持久化的 `/data/sso.key` 加密；絕不回傳、記錄或放入驗證錯誤／稽核。若 issuer／client ID 相同，client_secret 為空或省略時保留既有值；變更任一項都必須明確提供替換值。絕不可依 IdP claims 推導 admin 角色。

`GET /sso/settings` 與 `PUT /sso/settings` 回傳：

```json
{
  "revision": 0,
  "enabled": false,
  "display_name": "企業帳號",
  "issuer_url": "",
  "client_id": "",
  "client_secret_configured": false,
  "redirect_uri": "http://127.0.0.1:5173/auth-api/oidc/callback",
  "scopes": ["openid", "profile", "email"],
  "allowed_email_domains": [],
  "email_claim": "email",
  "require_email_verified": true,
  "groups_claim": "groups",
  "provisioning": "invited_only",
  "default_permissions": {},
  "group_mappings": [],
  "login_policy": "password_and_sso"
}
```

PUT 接受這些可編輯欄位及只能寫入的 `client_secret`；不接受衍生欄位 `redirect_uri` 與 `client_secret_configured`。首次寫入時也必須提供目前 revision（0），revision 過期時回傳 409。`group_mappings` 項目為 `{group:string,permissions:Permissions}`，使用既有產品角色與精確資源 ID。合併預設權限及相符群組權限時，scope ID 去除重複。Work 角色優先順序為 manager > reviewer > worker；Knowledge／Code 為 manager > writer > reader。不得授予萬用資源、Suite admin 權限或來自 claim 的操作者身分。

`enabled=true` 必須有有效的 issuer、client ID、已儲存的 secret、非空的 allowed_email_domains，且已完成首次 admin 設定。`login_policy=sso_only` 必須先啟用 SSO。固定公開 callback 從 `ORDIVANT_SSO_PUBLIC_ORIGIN` 或第一個精確的 `ORDIVANT_AUTH_ORIGINS` origin 推導，且必須位於受信任 origins 清單中。Request Host 與 query parameters 絕不可決定 callback origin。

`POST /sso/test`（admin + CSRF）使用已儲存設定，不啟動登入，只驗證 discovery／JWKS，並回傳 `{status:"ok",issuer,authorization_endpoint,redirect_uri,supported_algs:string[]}`。若失敗，回報真實且安全的上游／設定錯誤；不可捏造通過資料。

`GET /status` 保留 setup_required，並新增 `sso:{enabled,display_name,login_policy,configured,public_origin}`。不得回傳 secret 或私人 discovery response。`public_origin` 是受信任的標準瀏覽器 origin，避免別名使瀏覽器 binding Cookie 無法使用。若 Frontend 從不同 origin 觸發 SSO，須先帶一次性 `enterprise_login=1` flag 前往標準產品路徑；取得 status 並確認 SSO 已啟用後，才能消耗 flag 並開始登入。Backend start 要求此標準 Origin，否則回傳 sso_origin_mismatch。`User` 新增 `credential_type:"local"|"sso"` 及 `permissions_source:"manual"|"sso"`；不可破壞產品 introspection bridge 的 schema。Session JSON 新增 `authentication:{method:"password"|"oidc",provider_name?:string}`。SSO-only 使用者不能變更／復原密碼，也不會收到本機 recovery codes。

## 登入流程 {#login-flow}

- `POST /oidc/start` 使用 `{return_to:"/work"|"/knowledge"|"/code"}`，須有受信任的 Origin，回傳 `{authorization_url}`，並設定一個獨立的 HttpOnly／SameSite=Lax／依設定決定 Secure 的瀏覽器 binding Cookie。必須已啟用 SSO 且完成初始設定。對 start／callback 實施速率限制。使用 Authorization Code + PKCE S256 + 隨機 state + nonce。
- 只持久化 state 雜湊與瀏覽器 binding、nonce 雜湊、加密後且短期有效的 PKCE verifier、固定 return path、設定 revision 及到期時間（五分鐘）。State 透過原子條件寫入，只能消耗一次。拒絕缺少／錯誤的 binding、已到期或 Provider 設定已變更的要求。此機制須支援 PostgreSQL，且程序重啟後仍有效。
- `GET /oidc/callback` 驗證 binding／state、在伺服器端交換 code、依 discovery JWKS 驗證已簽署的 ID token，然後建立既有的 Suite HttpOnly 工作階段。Provider token 不得放入瀏覽器儲存、API JSON、URL redirect、資料庫或 log。成功與失敗時都清除 binding Cookie。
- Callback 以 303 重新導向至受信任的公開 origin 與已儲存產品路徑。失敗只能使用有界的 `auth_error` code；絕不可使用原始 Provider error／code／token。若 Provider 拒絕但 state 有效，仍須消耗 state；無效 state 不得造成外部重新導向。API／伺服器存取 log 不得記錄 callback query string。
- 明確只允許 RS256／ES256；驗證簽章、精確 issuer、audience、必要時的 azp、expiry、nbf／iat、nonce、非空且穩定的 sub，以及正規化後有效的電子郵件。預設要求 `email_verified=true`。特定租戶的 Entra 部署可先選擇精確 tenant issuer 與允許網域，再明確選擇停用此要求；不可默默推定電子郵件擁有權，也不可只憑電子郵件連結既有使用者。
- Discovery issuer 必須與設定完全相符。驗證所有 URL；拒絕憑證、fragment、無效 port、link-local／metadata／unspecified 目標、非預期 endpoint host 及 redirect。除了明確信任的本機測試／私人 HTTP host，其他連線一律使用 HTTPS；設定嚴格逾時與回應大小上限；停用 trust_env。
- Google OIDC discovery 的 backchannel endpoint 合法使用 oauth2.googleapis.com 與 www.googleapis.com；將這兩個精確且只允許 HTTPS 的供應商 host 加入內建 endpoint host allowlist。其他不同 host 必須由營運者明確列入 allowlist。Provider 範本只是設定輔助，不代表模擬了 Provider 整合。
- Google 文件僅列出兩種已簽署 ID token issuer 寫法：`https://accounts.google.com` 與 `accounts.google.com`。只有設定的 canonical issuer 是 `https://accounts.google.com` 時，才接受這兩個精確別名；identity binding 仍使用 canonical issuer，並將舊版 verified-email 字串 `"true"` 正規化。其他 issuer 與 verified-email 字串一律嚴格處理。使用已簽署 token fixture 驗證此行為；不可泛用 issuer 前綴比對。
- `ORDIVANT_SSO_HTTP_HOSTS` 以逗號分隔受信任 HTTP hostname（本機允許 loopback）；`ORDIVANT_SSO_ALLOWED_ENDPOINT_HOSTS` 明確允許使用不同於 issuer host 的 discovery endpoint。`ORDIVANT_SSO_BACKCHANNEL_OVERRIDES` JSON 將精確的公開 issuer prefix 對應至受信任的內部 issuer prefix，只用於容器網路路由。仍須驗證公開 discovery issuer／endpoints／token issuer，再只針對符合項目改寫 backchannel HTTP 的 prefix。Production 預設沒有 override。
- Reverse proxy 速率限制使用 `ORDIVANT_AUTH_TRUSTED_PROXY_HOSTS`（明確列出的 hostname／IP）。只有 socket peer 符合已解析的受信任 proxy 時，才可用一個有效 X-Real-IP 作為節流身分。Compose 只信任 web；Nginx 將 X-Real-IP 覆寫為 remote_addr。忽略直接／不受信任用戶端提供的 forwarding header。不可一概信任所有來源 IP。

## 帳號佈建與生命週期 {#provisioning-and-lifecycle}

- 將 issuer + sub 保留為具唯一資料庫 constraint 的穩定身分。第一位 admin 一律在本機明確建立。絕不可依 IdP 電子郵件自動合併既有本機帳號；應回傳 account_link_required。
- `invited_only`：已驗證且符合允許條件的電子郵件可原子消耗一筆有效 member 邀請，並建立具有明確權限的 SSO-only member。因 IdP 已證明電子郵件，無須邀請代碼。Admin 邀請不能自動建立 SSO 管理員。拒絕未知／未受邀身分。
- `jit`：已驗證且符合允許條件的身分可依預設／相符群組權限建立 SSO-only member；若沒有授權，帳號就沒有產品存取權。後續每次 SSO 登入都同步此類帳號的受管理權限；權限縮減／變更時撤銷既有工作階段。群組缺席時移除先前由群組授予的權限。新登入絕不可重新啟用已停用使用者。
- 既有手動授權仍維持手動。管理者編輯權限時，SSO 管理的 member 會改為手動權限，避免下次登入時暗中覆寫管理者的變更。`POST /sso/links` admin + CSRF `{user_id,subject,managed_permissions?:false}` 明確將既有使用者連結至目前 issuer；初次登入時，電子郵件須符合該使用者。`GET /sso/links` admin 回傳 `{links:[{id,user_id,issuer,subject,managed_permissions}]}`。`DELETE /sso/links/{id}` admin + CSRF 會解除連結並撤銷受影響使用者的 SSO 工作階段。每個 issuer／subject 僅能有一個連結，不可默默重新指派。
- `sso_only` 拒絕非 admin 使用密碼登入、復原或以密碼接受邀請，並撤銷既有非 admin 密碼工作階段。本機 admin 密碼登入仍保留作為明確的復原途徑。停用／變更 Provider 身分時撤銷受影響的 OIDC 工作階段；已停用使用者／權限變更使用三個產品既有的即時撤銷機制。
- `POST /oidc/backchannel-logout` 接受表單 logout_token，僅免除瀏覽器 Origin／CSRF 檢查。依設定 issuer／JWKS 驗證已簽署的 logout JWT、aud、iat、必要的 backchannel event、sub 或 sid、不含 nonce，並以 jti 防止重播。只撤銷相符的 OIDC 工作階段；保留本機 admin／密碼工作階段。持久化重播防護記錄。絕不保存或回傳原始 logout_token。
- Identity 資料遷移必須保留既有帳號雜湊與工作階段。優先新增資料表，不可假設 create_all 會修改既有資料表。容器重建／重新啟動後，加密金鑰與 DB volumes 都必須保留。

## 稽核與使用者介面 {#audit-and-user-interface}

成功變更 Identity 時，在同一個 transaction 寫入持久化身分稽核事件。記錄 SSO 成功／失敗、設定變更／測試、佈建／連結／解除連結、logout／backchannel logout、本機登入、邀請與管理權限／停用變更。絕不可包含密碼、secret、authorization code／state／nonce、Cookie 或 Provider token。稽核匯出僅限 admin；Identity 服務路徑為 `GET /api/auth/audit/export?limit=100`，瀏覽器／proxy 路徑為 `GET /auth-api/audit/export?limit=100`。limit 範圍為 1 至 10000。分頁以 `before` 和 `before_id` 作為 `(created_at,id)` 複合游標；有下一頁時，回應標頭 `X-Next-Before` 與 `X-Next-Before-Id` 提供下一組值。

登入頁顯示已設定的企業登入按鈕；SSO-only 政策會明顯優先顯示此按鈕，並保留清楚標示的管理員密碼復原入口。消耗／移除有界限的 auth_error query parameter，並顯示易懂的繁體中文訊息。不可捏造登入成功。Admin 帳號／安全 UI 包含完整的 Enterprise SSO 設定頁籤、連線測試、手動 subject 連結／解除連結與身分稽核頁籤。預設／群組權限使用既有資源選擇器，並清楚說明精確電子郵件網域與權限管理。SSO-only 帳號隱藏密碼／復原操作。儲存或卸載後清除 client_secret 輸入值。既有四種建置模式都必須通過，且表單／下拉選單須適合 390px viewport。

## SCIM 與驗證強度擴充（2026-10-15） {#scim-and-mfa-extension-2026-10-15}

此擴充定義目前的 SCIM 2.0 Users／Groups 範圍，並補充由外部 IdP 強制 MFA 的登入驗證條件。SCIM 入口為 /api/scim/v2，使用部署管理員另行配置的 ORDIVANT_SCIM_TOKEN_FILE。支援 Users、Groups 與受限篩選；不支援 bulk。新增使用者若 email 已屬於既有 Ordivant 帳號，須回報衝突，不依 email 自動認領或合併。管理員需先明確連結／移轉；群組只套用明確配置的產品和資源權限，不得授予 admin。停用使用者或撤銷授權須撤銷現有 sessions。

OIDC required_acr 設定值符合其中之一，required_amr 指定方式必須全部出現在已驗證的 ID token。任一 assurance 要求啟用時，成員使用 SSO-only 政策；Ordivant 驗證 IdP 聲明，不自行提供第二因素。客戶租戶與目錄的互通性驗收仍待逐一進行，不能以 fixture 或 API 存在取代該驗收。

SMTP 邀請／復原使用 Identity 持久 outbox；未配置寄件服務不發信。管理員可查看重試狀態。Identity 稽核匯出受權限和筆數／時間界限保護，排除機密欄位；保留期只有明確套用時才刪除舊資料。完整整合範圍與待驗收項目見[專案計畫](project-plan.md#p0-p1-acceptance-ledger)。

## 驗收 {#acceptance}

使用隔離的 QA PostgreSQL 資料庫、產生的合成身分，以及固定版本的真實 Keycloak container；其中設定要求 PKCE S256 的 confidential OIDC client 與 groups mapper。不可初始化或修改使用者主要人類帳號／Provider 設定。驗證 Work／Knowledge／Code 的實際 redirect／login／code exchange／簽署 JWT／session、產品 scope、reload／logout／disable、群組權限降級、invited-only 與 JIT、明確連結、SSO-only 復原途徑、secret 加密／CAS／無外洩、狀態持久化／重啟，以及偽造 state／nonce／audience／issuer／signature、backchannel logout／重播與本機帳號回歸。新增 SCIM 驗收需覆蓋既有 email 衝突、User／Group 授權、停用撤銷、不得授予 admin 與 bulk 不支援。Fixture 測試是安全性證據；Keycloak 整合是通訊協定互通性證據，不代表已驗證未設定的客戶租戶。文件須列出具體 Entra／Keycloak 設定、由 IdP 強制的 MFA、備份／金鑰需求，以及仍未完成的原生 SAML／客戶租戶工作。

主要參考資料：[OIDC Core](https://openid.net/specs/openid-connect-core-1_0.html)、[PKCE](https://www.rfc-editor.org/rfc/rfc7636.html)、[OAuth security BCP](https://www.rfc-editor.org/rfc/rfc9700.html)、[Keycloak containers](https://www.keycloak.org/server/containers)。
