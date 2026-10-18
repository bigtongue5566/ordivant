# 人類使用者驗證修訂（2026-10-06） {#human-authentication-revision-2026-10-06}

使用者要求在 development 與 production 提供可實際使用的人類帳號登入，且下拉選單能以滑鼠操作。此要求取代試行版瀏覽器 local-session／token 介面。保留 Agent／MCP bearer 授權與所有既有產品資料。

企業身分修訂透過同一個 Identity 服務新增 OIDC、帳號佈建、群組授權、生命週期撤銷與稽核。`sso-contracts.md` 定義新增的路由與欄位；以下原生帳號／工作階段契約仍然有效。

## 個人 API 與 MCP 存取權杖 {#personal-access-tokens}

- 真人在帳號設定建立 `ord_pat_` 個人權杖，資料庫只存 SHA-256 雜湊；原始值僅在建立回應中顯示一次。不得記錄原始值到日誌或稽核事件。
- `GET /api/auth/access-tokens` → `{tokens:[metadata]}`；`POST` 相同路徑，本文 `{name,products:["work"|"knowledge"|"code"],expires_in_days:1..365}`（預設 30）→ `{token,access_token:metadata}`；`DELETE /api/auth/access-tokens/{id}` → 204。只可管理自己的權杖，須 Cookie session；變更還須精確 Origin 與 CSRF。每位使用者最多 50 個有效權杖，建立序列化以防併發超額。
- Metadata：`{id,name,prefix,products,created_at,expires_at,last_used_at,revoked_at}`，時間為 UTC ISO 字串，未使用／未撤銷為 null；不包含雜湊或完整值。權杖建立及撤銷寫入 Identity 稽核。
- 內部 `POST /api/auth/access-tokens/introspect` 使用 service bearer，本文 `{access_token,product}` → `{user:User,token_id,expires_at}`。無效／撤銷／到期／停用為 401；產品不符為 403。該端點免除瀏覽器 Origin，但不免除服務驗證。所有回應 `Cache-Control: no-store`。
- 產品辨識個人權杖後，使用固定 Identity URL 與內部 secret introspect，逐次載入最新權限並同步相同的 human principal。無效 Authorization 不得退回 Cookie；網路或格式錯誤 fail closed 503。個人權杖不改變 claim、獨立 review、範圍或冪等規則，不授予 Agent 身分。
- 建立時僅允許使用者已獲授權產品；後續權限變更立即套用。密碼變更／帳號復原／停用撤銷既有權杖；`logout-all` 只撤瀏覽器 session，外部權杖須另撤。權杖不能呼叫管理路由來自行擴權或簽發新權杖。
- Work、Knowledge、Code 的 stdio MCP bridge 接受同一種 personal bearer，業務操作呼叫各自 REST API。`get_me` 可確認身分；建立資源工具接受 `request_id`，未提供時產生 UUID。介面依產品提供本機命令、環境變數和 API 根網址範例，值使用佔位符。

## 責任範圍 {#ownership}

- PM 負責這些契約、Compose／工具、下拉選單修正與最終驗收。
- Identity worker 僅負責 `products/identity/backend/**`：獨立的 Python／SQLAlchemy 身分服務、Dockerfile、測試與 lockfile。
- Bridge worker 負責 `backend/src/ordivant/{identity.py,api.py}`、`products/knowledge/backend/src/ordivant_knowledge/{identity.py,api.py}`、`products/code/backend/src/ordivant_code/{identity.py,main.py}`，以及各產品測試目錄新增的身分 bridge 針對性測試。不得修改既有領域模型／安全性／服務或根目錄工具。
- Frontend worker 負責 `frontend/src/App.tsx`、`frontend/src/api.ts`、`frontend/src/products/{knowledge/KnowledgeApp.tsx,code/CodeApp.tsx,shared/ProductLogin.tsx,shared/ProductShell.tsx,shared/productApi.ts}`，以及新增的 `frontend/src/auth/**`。不得修改 `main.tsx`、既有 CSS、套件清單或根目錄檔案；下拉選單 CSS 由 PM 負責。允許在 `auth/` 下新增 auth CSS。

## Identity 服務 {#identity-service}

使用獨立的 8030 埠；PostgreSQL 可透過 `ORDIVANT_IDENTITY_DATABASE_URL_FILE` 或 URL 設定（測試／原生環境允許 SQLite）。Python 套件為 `ordivant_identity`。路由前綴為 `/api/auth`。Nginx／Vite 將 `/auth-api/*` 轉送至 Identity 的 `/api/auth/*`。Identity 與產品資料不會直接讀取彼此的資料庫。

環境變數：`ORDIVANT_IDENTITY_DATA_DIR=/data`；`ORDIVANT_IDENTITY_SERVICE_TOKEN_FILE`（內部 introspection 機密）；`ORDIVANT_AUTH_COOKIE_NAME`（每個 Compose 專案各自唯一）；`ORDIVANT_AUTH_ORIGINS`（以逗號分隔、必須精確符合的受信任瀏覽器 origin）；`ORDIVANT_AUTH_COOKIE_SECURE`（HTTPS 部署設為 true，loopback HTTP 設為 false）。Identity 在容器內綁定 `0.0.0.0`。測試環境以外，若設定不完整且不安全，必須拒絕啟動或請求，不可默默開放存取。

Identity 使用 Argon2id 密碼雜湊、正規化後唯一的電子郵件、持久化節流、隨機且雜湊後保存的工作階段代碼，以及閒置與絕對到期時間；Cookie 屬性為 HttpOnly／SameSite=Lax／Path=/（本機 HTTP 可設定 Secure）。JSON／log 絕不可暴露密碼、雜湊或工作階段代碼。所有 auth 回應使用 Cache-Control: no-store。瀏覽器變更操作必須有允許的精確 Origin；已驗證的變更操作還必須帶有 `X-CSRF-Token`。以 HMAC(service secret, raw session handle) 計算 CSRF token，在 session JSON 回傳，並以常數時間比較。Introspection 必須使用 `Authorization: Bearer <service secret>`；此憑證絕不是瀏覽器可用的公開憑證。

- `GET /api/auth/status` -> `{setup_required:boolean}`。
- `POST /api/auth/setup` `{name,email,password}` 僅能以原子 singleton row／DB constraint 建立一次第一位 admin，在全新且未 Seed 的系統也能使用。不提供人類帳號預設密碼。-> session JSON + Cookie + 一次性 recovery codes。並行競爭失敗者回傳 409。
- `POST /api/auth/login` `{email,password}` -> session JSON + Cookie。憑證無效、未知、停用或鎖定時均回傳一般化錯誤；達到門檻後節流並回傳 429。每次登入都使用新的 session handle，避免 session fixation。
- `GET /api/auth/me` -> session JSON 或 401。
- `POST /api/auth/logout` `{}` 撤銷目前工作階段並使 Cookie 到期。
- `POST /api/auth/logout-all` `{}` 撤銷使用者所有工作階段並使 Cookie 到期。
- `POST /api/auth/change-password` `{current_password,new_password}` 驗證目前密碼、更新雜湊、撤銷所有舊工作階段，並簽發新工作階段與一次性 recovery codes。
- `POST /api/auth/recover` `{email,recovery_code,new_password}` 以原子操作消耗一次性雜湊 recovery code，變更密碼／撤銷工作階段，並回傳新工作階段與 recovery codes。失敗訊息一般化並實施節流；這是真正的離線復原，不會假裝已寄出 email／SMTP。
- `GET /api/auth/sessions` -> `{sessions:[{id,created_at,last_seen_at,expires_at,current:boolean}]}`。
- `DELETE /api/auth/sessions/{id}` 只能操作自己的工作階段；撤銷該工作階段，若為目前工作階段則清除 Cookie。
- `GET /api/auth/users` 僅限 admin -> `{users:[User]}`。
- `POST /api/auth/invitations` 僅限 admin，本文 `{email,name,role:"admin"|"member",permissions:Permissions}` -> `{invitation_code,expires_at}`，建立一次性邀請。資料庫只保存邀請雜湊，原始代碼只在簽發回應中出現。
- `POST /api/auth/accept-invitation` `{invitation_code,password}` 僅能成功一次地使用有效、未到期邀請 -> 新工作階段 + recovery codes。
- `PATCH /api/auth/users/{id}` 僅限 admin，本文 `{active?,name?,permissions?}`。不可停用最後一位 admin，也不可讓管理者鎖住自己；停用或變更權限時撤銷受影響的工作階段。
- `POST /api/auth/introspect` 使用內部 secret + `{session_token}` -> `{user:User,csrf_token,session_id,expires_at}` 或 401。絕不回傳 session_token。

Session JSON：`{user:User,csrf_token:string,expires_at:string,recovery_codes?:string[]}`。
User：`{id,email,name,role:"admin"|"member",active:boolean,permissions:Permissions}`。
Permissions：`{work?:{role:"manager"|"worker"|"reviewer",scope_ids:string[]},knowledge?:{role:"manager"|"writer"|"reader",scope_ids:string[]},code?:{role:"manager"|"writer"|"reader",scope_ids:string[]}}`。Admin 可存取同一個本機組織中的所有資源；member 不會自動取得任何授權。新增帳號須透過邀請，不開放不受限制的公開註冊。

使用共用領域錯誤格式 `{detail:{code,message}}`。具意義的安全性測試須涵蓋 setup 競爭、未以明文儲存、無效登入／節流、到期、logout／revoke／密碼變更／復原、重複使用邀請，以及最後一位 admin 的保護。

## 產品 Bridge {#product-bridge}

若請求帶有 Authorization header，現有 bearer 驗證仍具權威性；即使提供的 token 無效，也不得改用 Cookie。若沒有 Authorization header，只讀取 `ORDIVANT_AUTH_COOKIE_NAME` 指定的 Cookie，並使用 `ORDIVANT_IDENTITY_URL=http://identity-api:8030` 與 service secret file 執行 introspection（httpx 設定逾時、不跟隨重新導向／trust_env，不接受用戶端提供的 URL）。Identity 無法連線時必須 fail closed。

已驗證瀏覽器的變更操作，須強制檢查設定的精確 Origin 與 introspection 回傳的 `X-CSRF-Token`，並以常數時間比較。GET／HEAD 為唯讀。已簽署的 Gitea webhook 與 bearer 操作維持既有政策。

使用新的本機 `IdentityBinding` table（subject 唯一）將身分 subject 對應至明確的本機 principal。只在一個已設定／本機組織內對應。Admin 對應為人類 manager（Work 允許 admin），並具有該組織明確的本機成員資格；member 使用產品權限角色，且只能使用屬於該組織、已存在的 scope ID。每次驗證請求同步目前角色／成員資格，但不修改 Agent principal。業務變更前安全地 flush／commit 對應結果；處理首次請求的競爭情況。Principal.active 跟隨 introspection 的身分啟用狀態。若 Identity 使用者沒有產品權限，回傳明確易懂的 403，不可自動授權。不可匯入其他產品的 ORM。

`ORDIVANT_IDENTITY_ORG_ID` 可選擇現有本機組織。未設定時，若只存在一個組織就使用該組織；若資料庫為空就建立具確定 ID 的本機 Identity 組織；若有多個組織且無法判定則拒絕。絕不從呼叫端 scope ID 決定組織。保存 `IdentityBinding.identity_admin`；身分綁定的 member manager 只能操作指派給自己的 scope，且僅 Identity admin 可建立新 project／space。

保留 local-session endpoint 供舊的明確測試工具使用；產品設定 Identity 後，該 endpoint 必須拒絕繞過登入。Frontend 不會顯示此 endpoint。

## 瀏覽器 {#browser}

Permission `scope_ids` 指各產品公開的資源識別碼：Work project ID、Knowledge space ID、Code project ID。Code 會將公開 project ID 對應到自己的內部 Scope 成員資格；UI 不需要知道私有 ORM scope 識別碼。

Work／Knowledge／Code 共用 Identity Cookie 登入。首次載入時檢查 `/auth-api/status` 與 `/auth-api/me`；全新安裝顯示 admin 設定頁，否則顯示 email／password 登入。邀請與復原必須是真正可操作的表單。一般登入 UI 不提供人類 bearer-token 欄位或 local-session 按鈕。

憑證只保留在密碼輸入欄位的 state 中，完成或卸載時清除；不可寫入瀏覽器儲存空間。Fetch 使用 `credentials=same-origin`。已驗證的寫入請求加上來自 Identity me／login 的記憶體 CSRF token。未授權請求會清除 UI 身分並顯示登入畫面；工作階段到期時提供易懂訊息。切換產品或重新載入頁面後會恢復 Cookie 工作階段。登出先呼叫伺服器 logout，再清除 UI 狀態。

提供帳號設定：變更密碼、一次性 recovery-code 顯示、工作階段清單／撤銷／全部登出，以及 admin 邀請／停用使用者／指派存取權。將 codes 視為憑證：不可記錄到 console，截圖須遮蔽或隱藏其值。呈現真實的服務不可用／權限錯誤。保留既有業務介面與獨立建置模式。

## 容器驗收 {#container-acceptance}

每個選定產品都可搭配自己的資料庫及共用 Identity 服務／資料庫部署；不得引入 Work／Knowledge／Code 彼此的服務依賴。Development 與 production 使用分開的 Identity 資料及 Cookie 名稱。保留既有業務 volume。使用自有隔離 QA Identity 資料測試人類帳號流程；絕不可用測試密碼初始化使用者的第一個 admin。讓實際安裝環境保持可用，供使用者在應用程式中建立自己的 admin。
