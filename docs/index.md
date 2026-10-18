---
layout: home
title: 開源 Agent 協作平台
description: 認識 Ordivant 的任務協作、Agent 執行、工作流程、知識與程式碼管理，跟著完整教學部署並完成第一個專案。
hero:
  name: Ordivant
  text: 讓團隊與 Agent 一起把工作完成。
  tagline: 把目標拆成任務，讓 Agent 帶著規格與工具執行；團隊掌握進度、保留知識，並用成果證據確認交付。
  image:
    src: /screenshots/work-zh-TW.png
    alt: Ordivant Work 任務工作區
  actions:
    - theme: brand
      text: 完成第一個專案
      link: /guide/first-project
    - theme: alt
      text: Docker Compose 安裝
      link: /containers
    - theme: alt
      text: 看功能畫面
      link: /#product-tour
---

<span id="從規格-到經過驗收的成果"></span>
<span id="从规格-到经过验收的成果"></span>

## 從規格，到經過驗收的成果 {#from-specifications-to-reviewed-results}

Ordivant 是開源、可自行部署的 Agent 專案協作平台。它把**要做的工作、執行的過程、交付的成果，以及團隊的審核**放在同一個專案裡：先寫清楚目標和驗收條件，交給人員或 Agent，查看每次嘗試，最後由獨立審查者決定是否完成。

團隊可以從一個文件整理任務開始，逐步加入模型、工具、知識庫與自動工作流程。每個人的權限、Agent 能使用的工具及執行環境，都由你自己的部署與管理者設定。

**這個網站是產品介紹與使用手冊。** 使用平台時，開啟團隊提供的 Ordivant 網址，或依[安裝指南](./containers.md)在自己的環境啟動；網站本身不提供雲端帳號或模型服務。

## 哪些工作適合交給 Ordivant？ {#use-cases}

| 想完成的工作 | 交給平台的資料與安排 | 團隊可以檢查的交付 |
| --- | --- | --- |
| 準備產品上線 | 產品規格、服務清單、待辦任務、依賴關係 | 有負責人與狀態的上線清單，以及逐項成果證據 |
| 整理團隊知識 | 操作文件、需求、會議決策與來源 | 可搜尋的文件、發布版本、引用及決策紀錄 |
| 協作程式碼變更 | 變更目標、範圍、驗收條件、規格引用 | 分支、commit、PR 和測試證據，連回相關任務 |
| 執行重複性工作 | Agent 範本、固定步驟、前置依賴、執行輸入 | 每次流程產生的任務、Run、提交成果與審核紀錄 |

例如每週整理發布準備情況：先整理你提供的資料，再檢查缺漏、提出待確認事項，經審核後才讓依賴它的下一個步驟開始。若需要讀取外部系統，管理者先連接對應工具並授權；資料不會因為寫入網址就自動取得。

## 沒有 LLM 也能讓團隊一起工作 {#collaboration-without-llm}

真人可在 Work 建立任務；有管理權限的人可指派給同事，具專案權限的執行者可認領未指派或指派給自己的任務。提交成果後，仍須由另一位獲授權的人獨立審核。

Knowledge 讓多位獲授權成員即時共同編輯同一份草稿；已保存的草稿可發布為不可變版本。Agent 也能透過 REST 或 MCP 參與同一份草稿，但這些人工工作不需要 LLM。

Code 可在 Ordivant 內保存綁定 PR head SHA 的討論與審查紀錄。Code 的 Git 操作需要 Gitea；Gitea 負責 Git、合併及其自身的核准流程。只有自主 Agent 執行需要模型設定。

## 一次看懂主要功能 {#product-tour}

切換下方產品，查看實際介面及適用的工作。每張文件截圖都能點擊放大，也能切回原始尺寸查看欄位。畫面以示範資料展示平台功能；DEMO Run 用來說明操作，不代表付費模型已完成任務。

<FeatureExplorer />

### Work：任務、協作與獨立審核 {#work-preview}

在任務規格寫下目標、輸入資料、範圍、限制及驗收條件。管理者可指派給同事或 Agent；有專案權限的執行者也可認領未指派或指派給自己的任務。遇到問題時，從任務發起求助或委派子任務，讓討論與交付保留在同一脈絡；提交後由另一位獲授權的人獨立審核。

[任務與審核操作](./guide/work.md) · [求助與委派](./features.md#work-help-and-delegation)

### Run：Agent 執行與自動化 {#runs-preview}

派發給 Pi Agent 後，在 Run 查看狀態、執行事件、工具結果、產出及供應商回報的用量。獲授權的人員可要求暫停、繼續、停止或重試。常用設定保存為 Agent 範本；工作流程可以手動或定期啟動，依賴步驟會等待前置成果通過審核。

[Run、範本與工作流程操作](./execution-usage.md) · [模型連線與 Agent 設定](./model-usage.md)

### Knowledge：文件版本與決策依據 {#knowledge-preview}

用 Space 整理專案文件，搜尋標題、內容與標籤。多位獲授權成員可即時共同編輯同一份 Markdown 草稿；Agent 也可透過 REST 或 MCP 參與。發布會保存不可變版本，任務或 PR 可引用確切版本。引用保留來源，讀取權限仍由 Space 管理。

[文件、版本、搜尋與引用操作](./guide/knowledge.md)

### Code：程式碼交付與 PR {#code-preview}

Code 可為 PR 保存綁定目前 head SHA 的 Ordivant 本地討論與審查紀錄，這些紀錄不等同 Gitea 核准；Git 操作需要 Gitea，並由 Gitea 負責合併及其自身的核准流程。使用既有 GitHub 或 GitLab 的團隊，可在 Work 設定唯讀連線以查看 PR 與檢查結果。

[Code 操作指南](./guide/code.md) · [選擇需要的產品](./overview.md#four-service-boundaries)

## 團隊每個角色可以做什麼？ {#team-roles}

| 角色 | 日常工作 |
| --- | --- |
| 專案負責人 | 建立專案與規格、拆分任務、安排依賴和人員、派發 Agent、處理阻礙 |
| 執行者 | 依規格完成工作、提出問題、保存來源及成果、提交審核 |
| 審查者 | 對照驗收條件檢查成果與證據，接受或說明需要修改的地方 |
| 知識維護者 | 發布與更新文件、記錄決策、提供可追溯的版本引用 |
| 部署與組織管理員 | 設定帳號、資源權限、模型連線、企業 SSO、工具與沙箱 |

一個帳號可在同一部署登入三個產品；Work 專案、Knowledge Space、Code 專案各自授權。人員帳號與 Agent 是分開的身分，建立 Agent 不會替團隊成員授予權限。[建立團隊與邀請成員](./guide/team-setup.md)

<span id="開始第一個專案"></span>
<span id="开始第一个项目"></span>

## 跟著完成第一個專案 {#start-your-first-project}

完整教學使用「整理產品上線清單」作為範例。你會從空白工作區建立 LAUNCH 專案，填寫一份可執行的規格，走完提交與審核；可以選擇 Pi Agent 或人工執行路線。

1. **登入與建立團隊**：新部署先建立初始管理員；既有團隊接受邀請或用企業帳號登入。邀請另一位成員，讓執行與審核由不同人負責。
2. **建立專案與資料背景**：建立「產品上線準備」專案。已有規格時，發布到 Knowledge，保存版本引用；也可先把必要資料放入任務輸入。
3. **準備執行者**：自動執行需要啟用 Runtime，設定自己的模型供應商與金鑰，建立有專案權限的 Pi Agent。人工路線可先不設定外部模型。
4. **新增具體任務**：填寫目標、輸入、範圍、限制與逐項驗收條件；範例欄位和可以複製的內容都在教學中。
5. **派發並查看過程**：從任務選擇 Pi Agent 並派發，到 Run 查看進度。人工執行者則先認領任務，完成實際清單後提交。
6. **檢查交付與獨立審核**：執行者提交摘要、清單及來源證據；另一位有權限的人接受或退回。審核接受後，任務才標示完成。
7. **建立後續流程**：為下一項工作設定依賴，讓它等待這份清單被接受，再將常用 Agent 設定和步驟保存為範本及工作流程。

![成果審核：檢查示範清單、提交證據與審核結果](/screenshots/review-zh-TW.png)

[開始第一個專案完整教學 →](./guide/first-project.md)

## 如何寫一份 Agent 能使用的任務？ {#writing-a-useful-task}

先提供可取得的資料，再說清楚交付格式與界線。以下是教學中的規格方向：

| 欄位 | 「整理產品上線清單」的例子 |
| --- | --- |
| 目標 | 根據提供的產品背景，整理上線前必須確認的項目 |
| 輸入與範圍 | 提供登入、備份及操作指南的現況；只整理清單與缺漏 |
| 限制 | 未提供的資訊標為待確認，不自行聲稱已完成檢查或變更外部服務 |
| 驗收條件 | 每項列出負責角色、狀態及來源；至少涵蓋登入、備份與使用說明 |
| 成果證據 | 實際清單內容、來源引用，以及哪些項目仍待人員確認 |

遇到 Agent 缺乏資料或工具時，先補充輸入、授權合適的工具，或拆出需要人員處理的工作。一次模型回覆、Run 已提交或一筆自報狀態，都要由審查者對照實際成果。[查看完整欄位與提交範例](./guide/first-project.md)

## 選擇你的開始方式 {#choose-your-start}

**已加入團隊**：取得管理者提供的平台網址與邀請，閱讀[快速入門](./guide/getting-started.md)。看不到專案時，請管理者授予對應資源權限。

**自己安裝**：準備 Git 與 Docker Compose v2，依[部署指南](./containers.md)下載、初始化並啟動，開啟平台建立第一個管理員。需要自動 Agent 執行、Code 或沙箱時，再啟用對應服務。

**企業導入**：先由[團隊設定](./guide/team-setup.md)安排角色及資源，再串接[企業 SSO](./enterprise-sso.md)、[模型](./model-usage.md)和經允許的[工具及沙箱](./execution-usage.md#external-mcp-tools)。同時規劃[備份與維運](./guide/operations.md)。

## 找到你需要的操作指南 {#find-your-guide}

| 想做的事 | 從這裡開始 |
| --- | --- |
| 了解每項功能怎麼用 | [功能導覽](./features.md) |
| 從空白工作區完成第一個成果 | [第一個專案完整教學](./guide/first-project.md) |
| 邀請成員、安排執行與審核角色 | [建立團隊](./guide/team-setup.md) |
| 設定 API 連線與 Agent 模型 | [模型設定](./model-usage.md) |
| 管理 Run、範本及多步驟工作 | [執行與自動化](./execution-usage.md) |
| 發布專案文件、決策與引用 | [Knowledge 指南](./guide/knowledge.md) |
| 提交程式碼變更與 PR | [Code 指南](./guide/code.md) |
| 串接公司登入與資源權限 | [企業 SSO](./enterprise-sso.md)・[組織管理](./guide/administration.md) |
| 安裝、升級、備份及排解問題 | [Docker Compose](./containers.md)・[維運](./guide/operations.md)・[疑難排解](./guide/troubleshooting.md) |

<span id="部署在自己的環境"></span>
<span id="部署在自己的环境"></span>

## 部署在自己的環境 {#deploy-in-your-own-environment}

Ordivant 採 **MIT 授權**，可自行使用、修改及部署。Work、Knowledge 與 Code 可各自部署；資料由你管理。共用登入支援本地帳號與企業 OIDC，選用 Keycloak 可橋接 SAML／LDAP。

目前公開版本為 **v0.4.0（2026-10-19）**。此版本的 Work、Knowledge、Code 真人協作不需要 LLM；只有自主 Agent Run 需要模型設定。Knowledge 提供文字搜尋，Code 的 Git 寫入需要 Gitea；此版本尚未提供向量搜尋、內建 CI、硬性金額預算或分散式執行。Docker 沙箱沒有網路或主機目錄存取，使用已備妥的工具執行工作；需要更強隔離時應配置 VM 執行環境。查看[版本與升級說明](./release.md)。

## v0.4.0：快速建立團隊與外部連線 {#unreleased-p0-p1}

用六種職務範本建立 Agent，從 Provider 取得可用模型，並在建立 Work 專案時選擇一起建立 Knowledge 空間和 Code 專案。真人也可建立個人權杖，透過 API 或 MCP 使用自己獲授權的功能。查看[版本說明](./release.md)及[連線教學](./guide/administration.md#personal-api-and-mcp-access)。

外部模型與工具需自行提供連線及授權，可能產生供應商費用。未設定模型的 DEMO 只演示執行流程；真實交付請核對成果、來源與供應商用量。

[自行部署 →](./containers.md) · [現有功能與規劃](./roadmap.md) · [GitHub 原始碼](https://github.com/ordivant-ai/ordivant)
