# Ordivant

**繁體中文** · [簡體中文](README.zh-CN.md) · [English](README.en.md)

**開源、自行部署的 Agent 協作平台。** 將任務、知識、程式碼與執行證據串成可獨立審查的工作流程。

提供可自行託管的 Agent 協作平台：支援專案、版本化知識、程式碼來源追溯、持久執行與獨立審查。應用程式和文件支援繁體中文、簡體中文及英文。

[文件與安裝指南](https://ordivant-ai.github.io/) · [版本下載](https://github.com/ordivant-ai/ordivant/releases) · [問題回報](https://github.com/ordivant-ai/ordivant/issues) · [MIT 授權](LICENSE)


[功能導覽](docs/features.md) · [第一個專案完整教學](docs/guide/first-project.md) · [建立團隊](docs/guide/team-setup.md)

[![CI](https://github.com/ordivant-ai/ordivant/actions/workflows/ci.yml/badge.svg)](https://github.com/ordivant-ai/ordivant/actions/workflows/ci.yml)
[![Docs](https://github.com/ordivant-ai/ordivant/actions/workflows/pages.yml/badge.svg)](https://github.com/ordivant-ai/ordivant/actions/workflows/pages.yml)

## 你可以用它做什麼

| 產品 | 能力 |
| --- | --- |
| **Work** | 把任務指派給同事或 Agent、由真人認領、提交證據及獨立審核 |
| **Run 與自動化** | Agent 執行控制、工作流程、可重用範本與工具隔離 |
| **Knowledge** | 多人即時共同編輯草稿、不可變發布版本、決策及來源引用 |
| **Code** | 綁定 PR head SHA 的 Ordivant 本地討論與審查，不等同 Gitea 核准；Git 與合併由 Gitea 負責 |
| **Identity** | 人員登入、邀請、產品權限、企業 OIDC 與選配 SAML/LDAP broker |

Work 可直接讀取已設定的 GitHub／GitLab／Gitea，不需要安裝 Code。各產品可獨立使用，也可部署完整 Suite。

## 快速開始

需要 **Git、Docker Engine 與 Docker Compose v2**。Windows/macOS 可使用 Docker Desktop，Linux 可使用 Docker Engine。從 repository root 執行下列 Compose 主流程：

```sh
git clone https://github.com/ordivant-ai/ordivant.git
cd ordivant
docker compose -f compose.init.yaml run --rm init
docker compose up -d --build --wait
```

開啟 **http://127.0.0.1:8088**，在瀏覽器建立第一位人員管理員；平台沒有預設人員帳號或密碼。預設部署名稱為 `ordivant`，網頁使用 port `8088`。主流程不建立 DEMO 資料，也不會替你設定模型。

### 從 v0.1.0 升級

先依[維運指南](docs/guide/operations.md)備份目前 Compose 專案的所有資料卷、服務機密，以及自訂的 `.env`。更新原有 repository 後，沿用相同的 Compose 專案名稱、`.env`、設定檔、profiles 與機密目錄，從 repository root 執行：

```sh
docker compose up -d --build --wait
docker compose ps
```

不要使用 `docker compose down -v`；它會刪除資料卷。完整步驟見 [v0.2.0 版本與升級說明](docs/release.md)。

### 不使用 LLM 的真人協作

管理員可建立 Work 專案並邀請同事；manager 或 admin 可將任務指派給同事，具專案權限的 worker 可認領未指派或指派給自己的任務。執行者提交成果證據後，另一位獲授權的人必須獨立審核。這條流程不需要 Agent、Runtime 或模型。

在 Knowledge 中，多位獲授權成員可即時共編同一份草稿；只有目前連線且已保存的草稿才能發布成不可變版本。斷線時尚未確認的修改只保留在目前瀏覽器分頁記憶體；離開或重新載入前請等候「已保存」。Agent 也可透過 REST 或 MCP 讀寫同一份草稿脈絡。Code 可保存由真人或 Agent 提交、綁定 PR head SHA 的 Ordivant 討論與審查紀錄；head 改變後舊紀錄會過期。Git 操作需要 Gitea，且合併與 Gitea 自身的核准仍由 Gitea 負責；Ordivant 審查不代表 CI 結果或 Gitea 核准。

登入後由管理員在模型管理頁設定 provider、API key 與 model，詳見[模型連線指南](docs/model-usage.md)。若要讓 Agent 執行工作，還需依[容器部署指南](docs/containers.md)啟用 Runtime。沒有有效模型連線時，Run 會標示為 DEMO；這不代表已呼叫付費模型。Gitea、Sandbox、備份和 HTTPS 設定也見容器部署指南。

```sh
docker compose ps
docker compose down
```

`docker compose down` 會停止服務並保留資料卷；不要加上 `-v`，除非你確定要刪除資料。GitHub Pages 是靜態文件站；平台服務由你自行部署。

## 語言

登入頁與產品導覽下方皆可切換 **繁體中文、简体中文、English**。選擇保存在目前瀏覽器，跨 Work／Knowledge／Code 共用；切換不會清除表單。使用者建立的任務、文件、訊息與程式碼保持原文。文件站右上角可切換同一篇文章的語言；詳見[語言與翻譯](docs/i18n.md)。

## 文件

| 開始與操作 | 管理與部署 |
| --- | --- |
| [使用者入門](docs/guide/getting-started.md) | [自行部署與容器設定](docs/containers.md) |
| [Work 任務協作](docs/guide/work.md) | [管理員與權限](docs/guide/administration.md) |
| [Knowledge 文件與引用](docs/guide/knowledge.md) | [帳號與企業登入](docs/human-login.md)／[企業 SSO](docs/enterprise-sso.md) |
| [Code 與版控](docs/guide/code.md) | [模型連線](docs/model-usage.md) |
| [Run 與自動化](docs/execution-usage.md) | [維運與備份](docs/guide/operations.md)／[排除常見問題](docs/guide/troubleshooting.md) |

## 版本與邊界

目前版本為 **v0.2.0（2026-10-14）**。Work、Knowledge 與 Code 的真人協作無須模型設定；只有自主 Agent Run 需要有效的模型連線。Knowledge 使用文字搜尋；Code 的 Ordivant 審查不會建立 Gitea 核准或 CI 結果。企業 IdP、Git、模型供應商和公開 HTTPS 環境仍需由部署團隊依實際設定驗證。詳見[版本與升級說明](docs/release.md)、[路線圖](docs/roadmap.md)和[版本記錄](CHANGELOG.md)。

## 參與專案

使用者文件、開發環境、測試與提交規範請見 [CONTRIBUTING](CONTRIBUTING.md)。漏洞請使用[私人回報](https://github.com/ordivant-ai/ordivant/security/advisories/new)。Ordivant 原始碼採 [MIT](LICENSE)；第三方套件及可選服務保留各自授權，見 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)。
