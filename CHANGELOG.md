# Changelog

## 0.4.0 — 2026-10-19

- **API／MCP 個人連線**：新增限產品、具期限且可撤銷的個人存取權杖；沿用真人目前角色與資源範圍，提供三個產品的連線範例及入門工具。密碼／復原／停用流程同步撤銷權杖。
- **Agent 範本與執行設定**：提供 PM、PG、SA、SD、QA、Reviewer 六種按組織保存的內建版本；可編輯名稱、能力及指令，以「由平台執行／由外部程式執行」說明用途。
- **跨產品建立流程**：建立 Work 專案後可選建 Knowledge 空間與 Code 專案；保留各產品授權，提供分別重試及冪等保護。
- **Provider 模型清單**：透過 OpenAI 相容 `/models` 搜尋、選取並帶入上游明確提供的模型能力；不補造缺漏資料、不執行模型推論。
- 修正 Agent 指定模型未填完整時的畫面錯誤，以及長模型清單撐長側欄的版面問題。
- 更新三語操作文件、AGENTS、貢獻指南及安全政策，供外部開發者與不同 coding agent 使用。

## 0.3.0 — 2026-10-15

- **Work**：新增看板／Backlog 排序、工作類型與 Epic、Sprint／里程碑、日期、自訂欄位／階段、登入後任務提報及事件規則；提供個人儲存查詢、工時、明確設定的每週容量、觀察報表和安全 CSV 匯入／匯出。
- **跨模組協作**：Work、Knowledge、Code 新增具資源權限的附件、提及、訂閱與通知，並提供跨產品搜尋及通知中心；真人操作不需設定 LLM。
- **Knowledge**：新增頁面階層／封存、引用錨定留言／回覆／解決、文件範本、Markdown 工具與預覽、版本差異及受控還原，保留多人共同 Markdown 草稿。
- **Code**：新增綁定目前 head SHA 的行內討論、上游分支保護管理與讀回，以及 Gitea Actions／GitHub／GitLab 部署證據的讀取。這些功能不會代替上游執行 CI 或部署。
- **企業身分**：新增 SCIM 2.0 Users／Groups、已驗證 OIDC ACR／AMR 政策、SMTP 邀請／復原寄送 outbox，以及 Identity 稽核匯出／保留。可透過選用的 `compose.enterprise.yaml` 分別掛載 Identity 與 Code 機密。
- 新功能提供繁體中文、簡體中文與英文。升級與設定方式見三語使用者文件；真實客戶 IdP／SCIM 目錄，以及 GitHub／GitLab 成功部署資料仍需在各自環境驗證。
- 更新 pytest 至 9.1.1，修補 GHSA-6w46-j5rx-g56g，並更新相容的 pytest-asyncio。

## 0.2.0 — 2026-10-14

讓團隊可先以真人協作使用 Work、Knowledge 與 Code；只有自主 Agent 執行需要模型設定。

- 以原生 Docker Compose 初始化服務機密與 Gitea；Runtime 機器身分可獨立初始化，正式安裝無須加入 DEMO 資料。
- 任務詳細資料新增 Pi Agent 派發入口，使用既有權限與冪等 API，並與人工認領操作分開。
- **Work**：任務可指派給獲授權同事或 Agent；同事可認領合適的待辦工作、持續回報進度、交接成果，並由另一位獲授權的人獨立審核。
- **Knowledge**：多人可即時共同編輯 Markdown 草稿；Agent 可透過 REST／MCP 更新同一草稿。重新連線時會合併尚未確認的內容；未確認的離線修改僅保留在目前瀏覽器分頁記憶體。只有即時且已保存的草稿可發布為不可變版本。
- **Code**：真人與 Agent 可在 Ordivant 留下綁定 PR head SHA 的討論與審查紀錄；head 變更後舊紀錄會標示過期。Git、合併與 Gitea 自身的核准仍由 Gitea 處理；Ordivant 紀錄不代表上游 CI 結果或核准。
- 統一成果證據、任務規格、協作訊息、Run 回覆、Knowledge 決策及 PR 描述的 Markdown 顯示，並更新三語審核截圖。
- 新增三語功能導覽、第一個專案完整教學與團隊設定指南；首頁加入實際工作情境、交付範例、操作路徑及產品截圖。
- 文件新增可切換的產品導覽和可放大檢視的實際截圖，涵蓋 Agent、模型、範本、工作流程、工具與獨立審核。
- 平台與 GitHub Pages 提供繁體中文、簡體中文及英文；登入、產品、Run、自動化、模型、工具及 SSO 管理可切換語言。
- 整合瀏覽器語言偏好、跨分頁同步、日期／數字格式及介面元件語系，並保留使用者內容原文。
- 補齊對應文件路由與各語言搜尋，並檢查翻譯詞條、插值、文件正文和跨語言章節識別碼。
- 將原始碼與文件網站整理至 Ordivant 公開組織及其專用 GitHub Pages 網域。

## 0.1.0 — 2026-10-08

首次公開版本，提供可自行部署的 Ordivant Suite：

- **Work**：專案與規格任務、認領／租約、Agent 求助與委派、成果證據、獨立驗收、REST/MCP 與稽核。
- **Run**：Pi Durable 執行、事件與真實用量收據、工具邊界暫停／繼續、停止／重跑、重啟恢復及歷史。
- **自動化**：不可變 Agent／工作流程範本、DAG 依賴、獨立 review 後派工、手動及分鐘間隔排程。
- **工具**：Streamable HTTP MCP、加密 Bearer credential、主機及工具白名單、每次 Run 的受限 Docker 沙箱。
- **Knowledge**：不可變文件版本、文字檢索、精確版本引用、決策及來源追溯。
- **Code**：選配 Gitea 整合、真實 Git/PR 操作及簽章 webhook；Work 支援直接讀取既有 Git provider。
- **Identity**：人員帳號、session、邀請／復原／停用、企業 OIDC、權限群組及可選 Keycloak SAML/LDAP broker。
- **交付**：Docker 開發與部署、各產品獨立建置、公開 CI、GitHub Pages 文件與 MIT 授權。

### 已知邊界

這是早期公開版本；企業自己的 IdP、私有 Git 及模型連線需各自驗證。尚未提供 SCIM、硬性金額預算、內建外部 CI runner、互動式 MCP OAuth 或 VM 沙箱。Knowledge 的搜尋是文字檢索。詳見 [路線圖](docs/roadmap.md) 與 [驗收紀錄](docs/validation.md)。
