<span id="帳號與登入"></span>
<span id="账号与登录"></span>

# 帳號與登入 {#accounts-and-sign-in}

Work、Knowledge、Code 共用這一套環境的帳號。首次啟動時開啟工作區，會顯示「建立管理員帳號」：輸入姓名、電子郵件與至少 12 個字元的密碼，再次確認後送出。系統只允許建立一位初始管理員，沒有預設帳號或密碼。請直接在網頁輸入，不要把密碼傳給 agent。

建立完成會登入並提供十組一次性復原碼。碼預設隱藏，只在這次建立或修改密碼後提供，請自行保存到安全的位置。每次改密碼或復原後，先前的復原碼都會失效。

之後使用「電子郵件」與「密碼」登入。重新整理頁面、切換三個產品會維持登入；登出會立即撤銷伺服器上的工作階段。閒置超過 30 分鐘或登入超過 12 小時，需要重新登入。

<span id="帳號與安全性"></span>
<span id="账号与安全性"></span>

## 帳號與安全性 {#accounts-and-security}

側欄底部的帳號選單提供「帳號設定」，只管理自己的帳號、安全性與 API／MCP。管理員另有側欄「組織管理」入口，管理使用者與邀請、企業 SSO、企業治理與身分稽核。兩者使用獨立畫面；桌面版使用左側導覽，小螢幕改用選單。重新整理會保留所在設定頁。你可以：

- 查看帳號資訊、修改密碼；修改成功後其他登入裝置立即失效。
- 查看自己的工作階段、撤銷其他登入，或登出全部工作階段。

管理員可在「組織管理」邀請成員、停用帳號、修改成員的產品角色與專案／知識空間存取範圍。

邀請碼由管理員建立，24 小時有效，僅能使用一次；管理員自行將邀請碼提供給成員。平台不會假裝已寄出郵件。成員在登入頁選「接受邀請」，貼上邀請碼並自行設定密碼，即可使用授予的權限。

成員只可存取明確授予的 Work 專案、Knowledge 空間與 Code 專案。建立新的專案／知識空間由管理員負責。變更權限或停用帳號會撤銷其既有工作階段，需要重新登入。

忘記密碼時選「使用復原碼」，輸入電子郵件、一組未使用的復原碼與新密碼。平台會撤銷所有舊登入、消耗該碼並提供新復原碼；沒有復原碼就無法透過這條流程重設。

<span id="環境與部署"></span>
<span id="环境与部署"></span>

## 環境與部署 {#environments-and-deployment}

使用管理員提供的部署網址開啟 Ordivant。每個獨立部署各自保存帳號與業務資料；若使用多個部署，需在每個環境分別建立初始管理員。`-Seed` 只加入明確標示的業務示範資料，不會建立人的密碼帳號。

Docker helper 自動建立 Identity API、獨立 PostgreSQL 與內部服務憑證。產品只透過內部驗證服務查詢登入狀態，不讀 Identity 資料庫。瀏覽器工作階段使用 HttpOnly／SameSite cookie，寫入操作檢查 Origin 與 CSRF；agent REST／MCP 使用原有受限 bearer token。

對外部署需要 HTTPS、`ORDIVANT_AUTH_COOKIE_SECURE=true` 和明確的 `ORDIVANT_AUTH_ORIGINS`。只有 literal localhost／127.0.0.1／::1 的 HTTP Origin 可使用本地例外；設定不完整或服務離線時拒絕登入與人員業務授權。若產品資料庫有多個組織，Compose／launcher 分別設定 `ORDIVANT_WORK_IDENTITY_ORG_ID`、`ORDIVANT_KNOWLEDGE_IDENTITY_ORG_ID`、`ORDIVANT_CODE_IDENTITY_ORG_ID`，它們傳入各產品自己的 `ORDIVANT_IDENTITY_ORG_ID`；不得把不同組織的專案混在同一個登入範圍。

Identity volumes、業務 volumes 與部署設定的服務機密儲存位置必須一起保留及備份。停止容器不會刪除資料；企業設定還需要 Identity data volume 中的 `sso.key` 才能解密還原。

<span id="企業-sso"></span>
<span id="企业-sso"></span>

## 企業 SSO {#enterprise-sso}

管理員在「組織管理 → 企業 SSO」設定企業 OIDC 服務。支援 Entra ID、Google Workspace、Okta、Auth0、Keycloak 與通用 OIDC；SAML、LDAP／AD 可經可選 Keycloak broker 接入。設定流程、群組授權及容器操作見 [企業登入與身分管理](enterprise-sso.md)。

啟用後，登入頁出現企業登入按鈕，密碼與 MFA 在企業身分服務完成。成員首次登入必須符合允許網域及受邀／JIT 政策，並取得明確產品範圍權限。三模組共用同一個平台工作階段，登入成功不代表能存取全部專案。SSO 帳號不使用本機密碼復原。

切換「僅企業 SSO」會撤銷一般成員的密碼工作階段；本機管理員入口保留作為復原途徑。既有本機帳號不會只因 email 相同而自動合併，須由管理員明確連結企業 subject。
