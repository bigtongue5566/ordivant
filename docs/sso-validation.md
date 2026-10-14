<span id="企業-sso-驗收"></span>
<span id="企业-sso-验收"></span>

# 企業 SSO 驗收 {#enterprise-sso-acceptance}

日期：2026-10-07（Asia/Taipei）。範圍是本機 Ordivant 共用 Identity、標準 OIDC 與可選 Keycloak SAML 身分代理。一個 Identity 環境使用一組組織身分服務；Work、Knowledge、Code 各自保有資料庫與授權邊界。

本報告記錄 2026-10-07 的 OIDC／SAML 驗收，不包含其後加入的 SCIM 與 SMTP outbox。後續 Identity 檢查及客戶租戶待驗範圍見[現行 P0/P1 清單](project-plan.md#p0-p1-acceptance-ledger)。

<span id="已通過的協定與安全驗收"></span>
<span id="已通过的协定与安全验收"></span>

## 已通過的協定與安全驗收 {#protocol-and-security-checks-passed}

| 驗收 | 證據 | 結果 |
|---|---|---|
| Identity 安全與既有帳號相容性 | `products/identity/backend/tests`、lock 檢查、`compileall` | 28 項測試通過；包含簽章、issuer/audience/nonce/state、PKCE、Google 精確 issuer alias、受邀/JIT、明確 subject link、SSO-only、撤銷/replay、可信 proxy 與既有資料遷移 |
| Work／Knowledge／Code 業務回歸 | 各產品既有 pytest | 31／10／20 項測試通過 |
| 真實 Keycloak OIDC 與 SAML | `.data/validation/sso-32eb71e9/report.json` | 136 項檢查通過；不是模擬 provider 回應 |
| 加密儲存、日誌與重啟 | `.data/validation/sso-84b63356/storage-report.json` | 27 項檢查通過；實際重啟 QA Identity 與 Keycloak 容器 |
| 前端型別與獨立建置 | `npm run typecheck`、`build:suite`／`build:work`／`build:knowledge`／`build:code` | 全部以 exit 0 結束；包含三產品管理員建立入口與一般成員空狀態修訂 |
| 實際瀏覽器 OIDC／SAML 登入 | `.data/validation/sso-browser/report.json`、同目錄截圖 | 通過；企業登入、跨產品工作階段、390px 滑鼠選單、設定儲存後立即生效、SSO-only 管理員復原、企業成員密碼操作隱藏及三產品 scope 建立權限 |
| 主環境升級與保留初始化 | `.data/validation/sso-browser/main-environments.json` | 開發 `5173` 與本機正式模式 `8088` 的三個產品 health 及 Identity status 都為 200；仍由使用者建立第一位管理員 |

136 項 HTTP 驗收包含 confidential client 與 PKCE S256、真實 authorization/code exchange、JIT 和受邀成員、三產品精確資源授權、群組移除後的舊 session 撤銷與 403、既有管理員的明確 subject 連結、未受邀成員拒絕、SAML 上游登入與 signed assertion/response、SSO-only 拒絕一般成員密碼登入且保留管理員復原、停用成員、Keycloak 真正發送的 signed backchannel logout、偽造 state 拒絕、API/audit 密鑰遮罩，以及平台 cookie 和伺服器 session 登出。

Identity 中的 Code 權限使用公開 project ID。Code `/me` 的 membership Scope ID 是內部識別碼；驗收同時精確檢查 Identity 的公開 project 權限與 Code collection，並確認單一 opaque Scope ID 在不同授權登入間一致。HTTP suite 不直接讀取業務資料庫，也不修改產品 API 來暴露內部 ID。

27 項儲存驗收確認 PostgreSQL 持久化、Client Secret 密文可由原金鑰解密、`sso.key` 為 32 bytes 且 Linux 權限 `0600`、state/browser binding/nonce 僅保存 hash、PKCE verifier 加密、沒有 provider token 或 authorization code 欄位，以及既有 OIDC session 和設定在兩個容器重啟後仍有效。它也掃描 QA Identity、broker、web 日誌，只輸出通過與否，不保存原始日誌或 credential。

瀏覽器使用合成帳號，實際完成直接 OIDC 與上游 SAML 登入。SAML 成員沿用同一平台 session 進入 Work、Knowledge、Code；帳號抽屜標示企業登入且不提供本機密碼／復原碼操作。更新企業登入按鈕名稱後，沒有重新載入頁面便登出，登入畫面立即使用新名稱及 SSO-only 政策。管理員密碼復原仍可登入；一般成員沒有建立 Project／Space 的入口，而授權 scope 內的任務／文件入口保留。Code 的 QA 環境沒有 Gitea，介面明確顯示未設定並停用 repository 寫入，不把這個認證驗收當作 Git 寫入驗收。

<span id="可重現的隔離環境"></span>
<span id="可重现的隔离环境"></span>

## 可重現的隔離環境 {#reproducible-isolated-environment}

```powershell
.\scripts\sso-containers.ps1 -Action up
uv --cache-dir .cache/uv run --project products/identity/backend --no-sync python scripts/sso_acceptance.py
uv --cache-dir .cache/uv run --project products/identity/backend --no-sync python scripts/sso_storage_acceptance.py
.\scripts\sso-containers.ps1 -Action down
```

使用固定 project `ordivant-sso-qa`、app `127.0.0.1:8092`、Keycloak `127.0.0.1:8093`、獨立 PostgreSQL/volumes/service secrets，以及 `ordivant-qa` 與 `ordivant-qa-saml` 兩個合成 realm。測試密碼和 client credentials 是程式中的公開 QA fixture，不是使用者帳號。第一次執行只在這個 QA 工作區初始化合成管理員；後續執行沿用它。Docker 必須可由執行終端機存取。

Broker 使用 `quay.io/keycloak/keycloak:26.8.0`，本次拉取 digest `sha256:b0f60d489d51c5d113390bdf5461d4c06e6051be026c05549f2e1e10ec352bcc`。兩個 realm 檔案單獨掛載，manifest 不交給 realm importer。已存在的 realm 會被正常 startup 保留；要套用修改過的合成 fixture，使用 `-Action reimport`，它只在這個 QA broker 停止時替換上述兩個 realm。該操作不適用於真實企業 realm。

Keycloak 26.8 在 HTTP loopback 發送的 Secure flow cookie，Chromium 可以傳送，HTTPX 預設不會。HTTP acceptance 只針對上述兩個固定 QA origin 模擬此行為，仍檢查 host、path、expiry，且不把 IdP Cookie 注入 app callback。`diagnostics` 記錄此差異；`checks` 僅包含真正通過的條件，同名條件採 AND 累積。實際瀏覽器另行完成 OIDC 與 SAML 登入。產品的 cookie/TLS 驗證沒有為此放寬。

在 fixture 修正與重跑之間，PM 曾核對固定 QA container project label 後清除合成環境的 SSO request counter；主環境與產品的 20 starts／15 minutes 限流沒有變更。一般重跑需等前一限流窗口到期，不能將反覆跑完整 suite 的累計次數誤認為單一正常登入失敗。

SAML fixture 保持 `validateSignature`、`wantAssertionsSigned`，使用 `saml.assertion.signature` 與 `saml.server.signature` 啟用上游 assertion/response 簽章。Acceptance 核對 live client flags、AuthnRequest policy、metadata Entity ID/SSO endpoint，並確認 metadata 憑證對應上游公開 signing key。Broker 從 metadata 載入驗證金鑰，沒有關閉驗證來通過測試。

<span id="實際服務的配置邊界"></span>
<span id="实际服务的配置边界"></span>

## 實際服務的配置邊界 {#configuration-boundaries-for-real-services}

Entra ID、Google Workspace、Okta、Auth0、Keycloak 與通用 OIDC 已提供介面範本及 provider-specific claim 提示。協定相容性由真實 Keycloak 驗證，特定企業 tenant 仍須使用該組織的 Issuer、Client ID、Secret、claims 與 MFA 政策完成驗收。Google issuer alias 另有實際簽章 fixture；不是已連到使用者的 Google Workspace。

SAML 使用 Keycloak broker 的實際簽章 round trip 已通過。LDAP／AD 透過 Keycloak User Federation 串接，已提供維運設定，尚未連接真實目錄。就本報告日期而言，SCIM 2.0、企業離職同步、備份還原、負載測試與正式維運監控仍是獨立工作；SCIM／SMTP 後續實作與隔離檢查另見現行[驗收清單](project-plan.md#p0-p1-acceptance-ledger)。Identity/Keycloak restart persistence 不等同完整 backup restore。

驗收後已登出合成帳號、重設暫時 viewport 並關閉 QA 分頁；使用者原有 `5173/work` 分頁保留。QA 登入政策恢復 `password_and_sso` 後，使用 `down` 停止 `ordivant-sso-qa` 容器／網路，保留具名 volumes、service secrets 與本地報告供重現。主環境沒有加入合成帳號、企業 provider 設定或 QA realm。開發與本機正式模式資料各自獨立；此次沒有遠端部署、發布或 push。設定流程見 [企業登入](enterprise-sso.md)，容器流程見 [容器開發與部署](containers.md)。
