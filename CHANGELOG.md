# Changelog

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
