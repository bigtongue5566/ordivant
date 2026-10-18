# 安全政策 / Security policy

Ordivant 是可自行部署的開源協作平台。維護與安全修正以 `main` 和最新公開版本為主；舊版使用者應依升級指南備份並更新。目前沒有商業 SLA。

## 回報漏洞

請使用 [GitHub private vulnerability reporting](https://github.com/ordivant-ai/ordivant/security/advisories/new) 私下回報認證繞過、跨專案資料存取、憑證洩漏或沙箱逃逸。請提供受影響版本、最小重現方式、預期／實際行為及影響範圍。不要在公開 issue 放入有效金鑰、session cookie、使用者資料或完整資料庫。

若私人回報功能暫時無法使用，請先開不含利用方式及敏感內容的 issue，要求維護者提供私人聯絡方式。請勿測試他人的公開實例。

## 部署邊界

- 預設只綁定 loopback。遠端使用必須自行配置 HTTPS、正確的 Origin、secure cookie 與受信任反向代理。
- 首位管理員由安裝者建立；沒有預設人員密碼。Agent token 與人員 session 是分開的身分。
- 每個產品有獨立資料庫，授權由 Python 業務服務執行。不要把資料庫或內部 Identity/runtime/sandbox API 公開到網際網路。
- `sandbox-api` 是受信任的 Docker 控制服務，持有 daemon socket；每個 job 不持有 socket、主機掛載或認證。Docker 使用共享 kernel，不能視為 VM 安全邊界。
- 外部 MCP 工具可以造成外部副作用，應限制服務主機和 tool allowlist。模型輸出仍須獨立 review。
- `.data/`、`.env*`、資料庫、私鑰和 logs 不應加入版本控制。備份需加密並同時保留資料庫及相應加密金鑰。

詳見 [維運指南](docs/guide/operations.md)、[企業 SSO](docs/enterprise-sso.md) 與 [執行安全契約](docs/execution-contracts.md)。
