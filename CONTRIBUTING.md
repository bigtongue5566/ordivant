# Contributing to Ordivant

Thank you for contributing to Ordivant. This repository is a self-hosted collaboration platform for people and Agents: Work, Identity, Knowledge, Code, Runtime, and the isolated Sandbox have separate responsibilities and deployment boundaries. Human collaboration does not require an LLM. Coding agents can use [AGENTS.md](AGENTS.md) for repository conventions.

## 開發環境

Python 服務使用 Python 3.12 與 `uv`（CI 固定為 0.12.20）；Runtime 和 React 前端使用 Node.js 24 與 npm。可從 repo 根目錄執行以下命令；各 Python 專案會在自己的目錄建立獨立 `.venv`。

```sh
uv sync --project backend --frozen --extra dev
uv sync --project products/identity/backend --frozen --extra dev
uv sync --project products/knowledge/backend --frozen --extra dev
uv sync --project products/code/backend --frozen --extra dev
uv sync --project sandbox --frozen --group dev
npm ci --prefix runtime
npm ci --prefix frontend
```

容器化與 PostgreSQL 完整驗收需要 Docker Engine 與 Docker Compose v2；Windows/macOS 可使用 Docker Desktop。一般 Python/Node 測試與 CI 不需要 Docker daemon。Windows 開發者也可選用 PowerShell 輔助腳本，例如 `scripts/setup.ps1 -SkipSeed`、`scripts/validate.ps1` 和 `scripts/containers.ps1`。

## 本機檢查

容器開發可直接使用以下入口；首次建立專用開發環境時，`-Seed` 會加入明確標示的 DEMO 資料，不會建立人的密碼帳號。既有資料不要重複初始化。

```powershell
pwsh -NoProfile -File .\scripts\containers.ps1 -Development -ProjectName ordivant-dev -Seed -WithGitea -WithRuntime -WithSandbox
```

開發模式掛載原始碼並啟用重新載入，網頁預設為 `http://127.0.0.1:5173`。狀態、日誌及停止命令使用相同的 `-Development` 與 `-ProjectName`。若開發與正式部署同時執行，需設定不同的專案名稱及主機連接埠。

架構、REST 欄位與 MCP 整合見[開發參考](docs/reference.md)。API 映像包含各產品的 stdio MCP server；用戶端應透過自己的安全環境設定受範圍限制的 Agent token，再執行對應模組。例如 Knowledge：

```powershell
$env:ORDIVANT_SECRETS_DIR = Join-Path (Get-Location) '.data/container-secrets/ordivant-dev'
docker compose -p ordivant-dev -f compose.yaml -f compose.dev.yaml exec -T -e ORDIVANT_KNOWLEDGE_API_TOKEN knowledge-api python -m ordivant_knowledge.mcp_server
```

Work 使用 `ORDIVANT_API_TOKEN` 與 `ordivant.mcp_server`；Code 使用 `ORDIVANT_CODE_API_TOKEN` 與 `ordivant_code.mcp_server`。不要將憑證放入命令參數、版控或日誌。

Python 測試必須在各自的專案環境執行：

```sh
uv run --directory backend --frozen --no-sync pytest
uv run --directory products/identity/backend --frozen --no-sync pytest
uv run --directory products/knowledge/backend --frozen --no-sync pytest
uv run --directory products/code/backend --frozen --no-sync pytest
uv run --directory sandbox --frozen --no-sync python -c "import sys; sys.path.insert(0, '..'); import pytest; raise SystemExit(pytest.main())"
```

Runtime 測試同時執行 TypeScript build 與 Node test suite：

```sh
npm --prefix runtime test
```

前端 typecheck 包含在各 build 中，四種產品入口都要維持可建置：

```sh
npm --prefix frontend run build:suite
npm --prefix frontend run build:work
npm --prefix frontend run build:knowledge
npm --prefix frontend run build:code
```

整合驗收在隔離的本機資料目錄啟動服務。Work REST/MCP/Pi 驗收前要先建置 Runtime；產品 smoke 會依序啟動 Knowledge 與 Code，不需要 Gitea 或 Docker：

```sh
npm --prefix runtime ci
npm --prefix runtime run build
uv run --project backend --frozen --no-sync python scripts/integration.py

uv sync --project products/knowledge/backend --frozen
uv sync --project products/code/backend --frozen
uv run --project products/knowledge/backend --frozen --no-sync python scripts/product_smoke.py --product all
```

CI 使用 `demo` Runtime 模式，不呼叫付費模型。除非測試明確要求，不要設定或轉送真實 provider key、工作階段 cookie、agent/runtime token、Gitea 憑證或其他私人服務設定。

個人 API／MCP 連線可另執行 `uv run --project backend --frozen --no-sync python scripts/verify_personal_mcp.py`。先安裝四個產品的依賴；腳本會建立臨時資料庫、動態連接埠及合成帳號，驗證三個產品的 REST、stdio MCP 與撤銷流程，結束後清理，不使用既有帳號或模型連線。CI 也會執行這個流程。

## 範圍與責任

- `backend/` 維護 Work 業務 API、MCP 與權限；所有業務授權必須由 Python service 執行。
- `products/identity/backend/`、`products/knowledge/backend/`、`products/code/backend/` 分別維護獨立產品身分、文件知識與程式碼整合邊界。
- `runtime/` 維護 Pi Durable 執行、派送與執行回報；不得取代業務服務的授權或租約檢查。
- `sandbox/` 維護隔離 command 執行器；不得把 Docker socket 或主機目錄掛載至不受信任服務。
- `frontend/` 維護共用 React UI 與各產品 build mode；前端狀態不能取代伺服器授權。
- 跨模組、共用契約及根目錄 tooling 的變更，請在 PR 說明相容性、遷移與整合影響，由維護者審查。貢獻不需要指定的 PM 或 Agent；多人同時開發時，先協調重疊的修改範圍，並保留他人的既有變更。

請保持產品資料、API、MCP 與部署邊界清楚。Task 與 execution 是不同紀錄；完成結果需要證據並由獨立 reviewer 驗收。Mutation 的冪等、租約 fencing、依賴循環、跨專案授權、重啟復原及協作 round trip 應依變更風險補上測試。

## Pull request

請使用 PR 範本說明行為變更、影響邊界、風險、執行過的檢查與文件狀態。移除或遮蔽日誌中的 secret、個人資料與私人服務位址；不要提交 `.data/`、`.env*`、`.venv/`、`node_modules/`、build 產物或本機 bootstrap 憑證。

安全漏洞請透過 [GitHub 私下安全回報](https://github.com/ordivant-ai/ordivant/security/advisories/new)，不要建立公開 Issue、PR 或貼上可利用細節。若私下回報功能尚未啟用，請聯絡 repo 維護者以設定安全聯絡方式。

## 介面與文件翻譯

介面訊息使用 `frontend/src/i18n` 的 `t`／`useI18n`，英文詞庫依模組存放，禁止翻譯使用者內容與 API 值。修改後執行 `npm --prefix frontend run i18n:generate` 與 `npm --prefix frontend run i18n:check`。新增文件時，請同時維護原始繁中、`docs/zh-CN`、`docs/en` 的同路徑頁面。完整流程見 [語言與翻譯](docs/i18n.md)。

文件站只發布 `docs/.vitepress/public-pages.json` 明確列出的文章及其三語版本。新增 Markdown 不會自動進入網站、搜尋或 sitemap；新增公開文章時須同步更新清單、導覽及相關連結。PM 台帳、需求研究、開發契約及驗收紀錄保留於 GitHub，供維護者協作與重跑測試。這是網站的內容範圍，不是保密機制；公開 repo 中仍不得放入憑證或私人資料。

文件變更至少執行 `npm --prefix docs run build`、`uv run --project backend --no-sync python scripts/check_docs.py` 和 `node scripts/build_docs_redirects.mjs`。建置檢查會拒絕清單外的 HTML、搜尋索引或 sitemap 項目，避免內部紀錄再次進入文件站。
