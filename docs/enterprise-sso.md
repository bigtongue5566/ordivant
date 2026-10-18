<span id="企業登入與身分管理"></span>
<span id="企业登录与身分管理"></span>

# 企業登入與身分管理 {#enterprise-sign-in-and-identity-management}

Ordivant Work、Knowledge、Code 共用一個 Identity 服務。管理員可以接上企業既有的 OIDC 身分服務，並控制成員佈建、產品／專案權限、登入政策及工作階段。企業密碼與 MFA 驗證由身分服務處理，Ordivant 不接收企業密碼。

<span id="管理員設定"></span>
<span id="管理员设置"></span>

## 管理員設定 {#administrator-setup}

1. 以要設定的 Ordivant 管理員帳號登入。不同部署各自保存帳號及 SSO 設定，請確認使用正確的服務網址。
2. 開啟「組織管理 → 企業 SSO」。選擇身分服務範本，再填入組織專屬 Issuer URL、Client ID、Client Secret。
3. 在身分服務建立 confidential OIDC Web application，允許 Authorization Code 和 PKCE S256。把 Ordivant 顯示的 Callback URL 完整註冊為 Redirect URI；不要使用萬用字元。
4. 設定允許的完整電子郵件網域、成員佈建方式、預設權限及群組對應。先儲存，再執行「測試連線」。這項測試檢查 discovery/JWKS；真正登入仍需由身分服務授權。
5. 先用一位企業成員完成登入、產品存取及登出驗收，再切換「僅企業 SSO」。本機管理員帳密入口保留作為復原途徑。

Client Secret 留白會保留既有值；改變 Issuer 或 Client ID 必須明確填入新值。儲存後介面清空 Secret，API 只回傳是否已設定。公開設定網址以管理員設定的 canonical origin 為準；從 localhost／127.0.0.1 的其他別名開始登入時，介面先切到該網址。

<span id="常見身分服務"></span>
<span id="常见身分服务"></span>

## 常見身分服務 {#common-identity-providers}

| 身分服務 | Issuer／應用設定 | 注意事項 |
|---|---|---|
| Microsoft Entra ID | `https://login.microsoftonline.com/TENANT_ID/v2.0`；Web 平台、組織專屬 tenant | 使用明確租戶；依實際 token claims 選 email 或 preferred_username。Entra 未提供 email_verified 時，僅在確認租戶與網域政策後關閉此驗證。群組 claims 必須由管理員配置；group overage 不會被當成群組授權。 |
| Google Workspace | `https://accounts.google.com`；Web 應用程式 OAuth 用戶端 | 限制允許網域；IdP 的 hd 提示不取代後端網域檢查。Google 不預設提供產品所需 groups，請使用明確預設權限或手動授權。 |
| Okta | 組織自己的 OIDC authorization server issuer | 設定 groups claim 發到 ID token；名稱須與權限對應完全一致。 |
| Auth0 | `https://YOUR_TENANT.REGION.auth0.com/` 或設定的 custom domain | OIDC ID token 的標準 claims；需要群組時由 Action 加入自訂 claim，並在 Ordivant 填入相同 claim 名稱。 |
| Keycloak | `https://IDP_HOST/realms/REALM` | confidential client、PKCE S256、將 groups mapper 加入 ID token；可代理 SAML 或 LDAP／AD。 |
| 其他 OIDC | 服務公開的精確 issuer | 必須提供 discovery、JWKS、Authorization Code、signed ID token，以及可用的身分 claims。 |

這些範本提供標準設定方式。實際企業 tenant 仍需使用該組織配置進行登入驗收，不能以本機 Keycloak 驗收推定所有 vendor tenant 均已通過。

官方設定參考：[Entra OIDC](https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc)、[Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect)、[Okta OIDC](https://developer.okta.com/docs/guides/implement-grant-type/authcode/main/)、[Auth0 Regular Web Apps](https://auth0.com/docs/get-started/authentication-and-authorization-flow/authorization-code-flow)、[Keycloak 管理指南](https://www.keycloak.org/docs/latest/server_admin/index.html)。

<span id="成員與權限"></span>
<span id="成员与权限"></span>

## 成員與權限 {#members-and-permissions}

- **僅受邀成員**：先由管理員建立 member 邀請。企業身分的電子郵件通過驗證並符合允許網域後，可以直接使用 SSO 接受邀請，沿用邀請中指定的產品與資源權限。企業登入不會自動建立管理員。
- **JIT 自動佈建**：首次登入建立一般成員，套用明確的預設與群組權限。沒有設定權限的成員無法存取產品資料；同網域不代表全組織可見。
- **群組同步**：JIT 管理的成員每次登入同步群組。移除群組會移除相應授權並撤銷舊工作階段；成員仍只能存取獲授權的產品與資源。
- **既有帳號連結**：電子郵件相同不會自動合併帳號。管理員必須明確指定現有使用者與 IdP subject，並在登入時驗證對應。解除連結會撤銷企業登入工作階段。
- **手動權限**：管理員明確修改成員權限後改為手動管理，避免下一次登入悄悄覆蓋設定。要恢復群組管理，透過身分連結重新指定管理方式。

登入成功只建立平台工作階段，不直接授予 agent 或版控服務的 credential。Agent REST／MCP 仍使用專案受限的獨立身分。

<span id="saml、ldap-與-active-directory"></span>
<span id="saml、ldap-与-active-directory"></span>

## SAML、LDAP 與 Active Directory {#saml-ldap-and-active-directory}

Ordivant 採 OIDC 接入協定。SAML-only 或 LDAP／AD 企業系統可以使用可選 Keycloak 身分代理：在 Keycloak 建立 SAML Identity Provider 或 LDAP User Federation，將它對外提供的 OIDC realm 接到 Ordivant。Work／Knowledge／Code 不必各自保存 LDAP 密碼或實作不同登入協定。

SAML 串接時，在 Keycloak 新增 SAML Identity Provider，匯入上游 metadata，向上游登記該 broker 顯示的 Entity ID 與 ACS／Redirect URI。保持 assertion 簽章驗證，配置電子郵件與姓名 mapper，再依企業的電子郵件驗證政策決定是否啟用 Trust Email。群組需要另外配置 broker mapper，讓最終 OIDC ID token 的 groups claim 包含 Ordivant 對應的完整群組名稱；SAML 的群組不會自動變成平台權限。

LDAP／AD 串接時，在 Keycloak 的 User Federation 新增 LDAP provider，填入企業提供的目錄位址、Users DN、搜尋條件與 username／email attribute，配置群組 mapper，並使用 LDAPS 或 StartTLS 與可信 CA。目錄 Bind Credential 與人員密碼由企業管理員直接在身分服務輸入。先驗證目錄連線與單一成員同步，再建立 OIDC client 接到 Ordivant；平台端仍套用允許網域、受邀／JIT 與明確資源授權。

如需 SAML 或 LDAP／AD，先完成[容器部署](containers.md)的初始化。在同一倉庫根目錄的 `.env` 加入以下設定，再啟動選用的 Keycloak 與獨立資料庫；若已使用其他 Compose 設定檔，請一併保留：

```dotenv
ORDIVANT_BROKER_PUBLIC_URL=http://127.0.0.1:8093
ORDIVANT_SSO_HTTP_HOSTS=identity-broker
ORDIVANT_SSO_BACKCHANNEL_OVERRIDES={"http://127.0.0.1:8093":"http://identity-broker:8080"}
```

```sh
docker compose -f compose.yaml -f compose.identity-broker.yaml --profile identity-broker up -d --wait identity-broker identity-api
```

broker 預設只綁定 `127.0.0.1:8093`。可由呼叫端指定 `ORDIVANT_BROKER_PORT` 及 `ORDIVANT_BROKER_PUBLIC_URL`；跨電腦的企業部署使用固定 HTTPS 網址與可信反向代理。其他 OIDC 身分服務可直接設定，不需要啟用 broker 容器。

broker 不會建立預設的人員管理員。以下命令以 `ordivant` 為例；請使用啟動 broker 時相同的專案名稱與機密資料夾。密碼由管理員直接在 tmux 的互動提示中輸入。Windows 可先開啟 WSL 工作階段，並確認 Docker Desktop 已啟用 WSL 整合：

```sh
wsl -- tmux new-session -A -s ordivant-idp-admin
```

Linux 可使用 `tmux new-session -A -s ordivant-idp-admin`。在 tmux 終端中切換至倉庫目錄，再執行一次性初始化：

```sh
docker compose -f compose.yaml -f compose.identity-broker.yaml --profile identity-broker stop identity-broker
docker compose -f compose.yaml -f compose.identity-broker.yaml --profile identity-broker run --rm identity-broker bootstrap-admin user --username temp-admin
docker compose -f compose.yaml -f compose.identity-broker.yaml --profile identity-broker up -d identity-broker
```

請勿將密碼放入聊天、命令、環境變數或檔案。以暫時管理員登入 broker 後建立正式管理員，再移除暫時管理員。[Keycloak 官方初始化與復原說明](https://www.keycloak.org/server/bootstrap-admin-recovery)

<span id="工作階段、安全與稽核"></span>
<span id="工作阶段、安全与审核"></span>

## 工作階段、安全與稽核 {#sessions-security-and-audit}

平台保留 HttpOnly、SameSite 與 Origin／CSRF 保護。OIDC 使用單次 state、browser binding、nonce、PKCE S256 與簽章／issuer／audience 驗證。Client Secret 加密存放；authorization code、ID token、access token 不進入業務資料庫、API 回應或登入日誌。

停用帳號、變更權限、解除企業身分或停用／更換身分服務會撤銷相關工作階段。啟用 SSO-only 時撤銷一般成員的密碼工作階段。若 IdP 支援 OIDC Back-Channel Logout，可將 URL 設為 `https://APP_HOST/auth-api/oidc/backchannel-logout`；只有通過簽章與重放檢查的登出通知才能撤銷對應企業登入。

Ordivant 登出會撤銷三個模組共用的工作階段；企業其他應用的工作階段由 IdP 管理。企業 MFA、Conditional Access、密碼規則與人員離職流程需在 IdP 設定。若平台的 SSO 政策填入 required_acr／required_amr，Identity 會驗證已簽署的 IdP claims；acr 必須符合其中一個要求值，amr 必須包含全部指定方式。這些 claim 只是驗證條件，實際 MFA 因子由 IdP 執行。若 IdP 不發送 backchannel logout，管理員應在平台同步停用成員，而不能把 IdP 停用誤認為現有平台 session 立即失效。

「身分稽核」記錄登入、佈建、設定與權限變更、連結／解除連結及登出事件。只有管理員可以檢視或從「組織管理」→「企業治理」匯出 Identity 記錄；匯出不包含 Work、Knowledge 或 Code 的產品事件，也不含密碼、cookie、client secret 或 provider token。

<span id="維運與備份"></span>
<span id="运维与备份"></span>

## 維運與備份 {#operations-and-backups}

保留 Identity PostgreSQL、`identity_data`（包含 `sso.key`）、Compose service secrets。使用 broker 時還要保留 `identity_broker_postgres`。資料庫與加密金鑰須一起備份；只有資料庫無法還原已加密的 client secret。

正式 HTTPS 環境設定 `ORDIVANT_AUTH_COOKIE_SECURE=true`、明確 `ORDIVANT_AUTH_ORIGINS` 和 `ORDIVANT_SSO_PUBLIC_ORIGIN`。若 provider discovery 的 token/JWKS endpoint 使用不同 host，使用 `ORDIVANT_SSO_ALLOWED_ENDPOINT_HOSTS` 指定額外可信 host。Google 的精確 HTTPS token/JWKS hosts 已受支援。私有 HTTP broker 需明確 `ORDIVANT_SSO_HTTP_HOSTS`；上述 `.env` 設定將 broker 的回程連線導向其內部網址，外部 provider 不需此例外。

私有企業 CA 可將 PEM trust bundle 掛載到 Identity 容器，再設定 `ORDIVANT_SSO_CA_BUNDLE` 為該檔案路徑；TLS 憑證驗證持續啟用。Compose 信任指定的 `web` proxy，由 Nginx 覆寫 `X-Real-IP`，依實際來源進行登入限流。自訂反向代理需在 `ORDIVANT_AUTH_TRUSTED_PROXY_HOSTS` 列出精確 proxy host／IP，並由它覆寫此 header；直接連到 Identity API 的偽造 header 不會被採用。

Ordivant 以 OIDC 作為身分整合協定，SAML 與 LDAP／AD 透過選配的 Keycloak broker 聯邦；平台沒有原生 SAML 端點。Identity 提供 SCIM 2.0 Users／Groups 佈建端點，但不支援 bulk，且不會依 email 自動連結既有帳號；各客戶的 IdP tenant 與 LDAP／AD 目錄尚未逐一驗證。上線前請依[管理指南](./guide/administration.md)設定 SCIM 專用憑證、群組資源授權、郵件、稽核與由 IdP 執行的 MFA，並逐一核對各組織的 claims、網域限制及資源授權政策。
