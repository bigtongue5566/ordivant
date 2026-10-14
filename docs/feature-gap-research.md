<span id="ordivant-功能缺口研究"></span>

# Ordivant 功能缺口研究 {#ordivant-feature-gap-research}

更新：2026-10-08（Asia/Taipei）。原研究於 2026-10-07 由 PM 與三位 luna-worker 盤點程式、契約及驗收紀錄，參考官方協定與產品文件。使用者已選定 **F03 Run 控制台、F04 自動流程／Agent 範本、F05 工具連接／沙箱**，已完成實作與本機整合驗收；本頁同步區分第一版能力與仍待開發的範圍。

本頁的功能缺口與 F11 SCIM 候選是 2026-10-08 的歷史快照。2026-10-15 已加入 SCIM 實作；目前的客戶租戶驗收狀態見[專案計畫](project-plan.md#p0-p1-acceptance-ledger)。

本輪功能說明與證據見 [執行功能](execution-usage.md)／[驗收](execution-validation.md)。接續優先候選是 **執行前審批、總 token／金額治理、通知與真實 CI 整合**；企業文件匯入、既有版控、SCIM 等需求仍保留。

排序先假設「一家企業私有部署，團隊共同使用」。如果改為同一套服務承載多家客戶，租戶隔離與每個租戶的 Identity／IdP 設定必須提前。

<span id="現有能力與判讀方式"></span>
<span id="现有能力与判读方式"></span>

## 現有能力與判讀方式 {#existing-capabilities-and-status-definitions}

「部分」表示相關基礎已存在，候選是補足缺少的範圍。「未實作」指候選能力未見對應的完整 service／API／UI。「尚未驗證」表示已有設定或維運說明，但沒有該項端到端交付證據。

已存在的功能包括：共用 Identity、原生帳號與 OIDC、Keycloak SAML broker、邀請／JIT、專案／Space 授權、登入時群組同步、工作階段撤銷；Work 的任務／執行分離、依賴、原子 claim、lease fencing、委派、求助、訊息、冪等、outbox 與獨立成果驗收；Knowledge 的不可變版本、文字搜尋與精確引用；Code 的真實 Gitea repo／branch／commit／PR／status 操作。這些不是本輪要重做的功能。

<span id="優先候選"></span>
<span id="优先候选"></span>

## 優先候選 {#priority-candidates}

P0 是下一輪核心操作能力；P1 是企業日常使用與導入功能；P2 是依使用量、整合對象或採購要求擴展。排序是 PM 判斷，尚未提供工期估算。

| ID | 優先 | 候選 | 目前已有 | 缺少的能力與常見用途 |
|---|---|---|---|---|
| F01 | P0 | 執行前審批與工具政策 | 任務成果 review、角色／資源授權 | 執行敏感操作前產生持久審批請求；核准／拒絕／逾時後按政策恢復。部署、合併 PR、對外發送、資料變更可以各有規則。持久暫停與批准後恢復可參考 [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)。 |
| F02 | P0 | 執行與成本上限 | 單次 output token ceiling、實際 token receipt；新增每 Run turn／總時間上限及沙箱資源限制 | 總 token／併發配額、請求前預留金額、版本化定價與原子結算仍待開發。USD／cache 費率與帳單對帳需另外配置。按 key／team 設 budget 與 rate limit 可參考 [LiteLLM virtual keys](https://docs.litellm.ai/docs/proxy/virtual_keys)。 |
| F03 | 本輪 | Run 執行控制台 | 專案 Run 列表／詳細頁、持久事件／錯誤／模型用量、queued stop、工具邊界 pause／resume、具來源連結的 retry、重啟／提交冪等與獨立 review | 後續可加入任意人工輸入續談、死信處理與跨 Run 統計。正在進行的外部呼叫可先結束；Run done 仍不等於 task 獨立驗收完成。 |
| F04 | 本輪 | 自動協作與可重用工作流程 | 不可變 DAG 版本、手動／分鐘間隔觸發、能力選 Agent、自動派工、review 依賴與取消；Agent 範本可套用建立／編輯 | 條件分支、webhook／Cron 觸發、跨系統事件與自由協作喚醒仍待開發。現有流程不自動假造 CI 或獨立 review 結果。 |
| F05 | 本輪 | Agent 工具連接與隔離工作區 | 專案 MCP Streamable HTTP／Bearer、tools/list 與 allowlist、加密金鑰；每 Run 無網路 Docker workspace、檔案／命令工具、資源限制與清理 | 互動式 OAuth、host stdio launcher、授權 repo checkout、可控網路／套件安裝及 VM 執行器仍待開發。固定 job image 內含 Python／Node／Git。 |
| F06 | P1 | 通知、mentions、到期與 SLA | 指定 recipient 的協作訊息與收件匣 | 待審、阻塞、失敗、逾期通知；通知中心／即時更新、Email／Teams／Slack、訂閱與去重。建立 due date／SLA 才能做逾期與升級處理；Teams 可透過 [Workflows webhook／Adaptive Card](https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-incoming-webhook?tabs=dotnet) 接入。 |
| F07 | P1 | 文件與任務附件匯入 | Markdown body、版本；成果的 URI／文字 reference | 上傳 PDF／Word／檔案、抽取文字與必要的 OCR，保存來源／hash／版本及匯入狀態；對附件儲存、大小、存取與刪除生命週期做管理。現有 `kind=file` 不包含二進位上傳服務。 |
| F08 | P1；先匯入再強化檢索 | 權限感知的語意搜尋／RAG／跨產品搜尋 | Knowledge 文字搜尋、Space 權限、snippet／版本引用；後端可搜尋多個授權 Space | 語意／混合檢索、自然語言問答與引用；統一查找任務、文件與 PR。檢索、cache 與回覆都須維持當前授權與精確版本。來源 ACL 與 query-time filtering 的設計可參考 [Microsoft 文件權限搜尋](https://learn.microsoft.com/en-us/azure/search/search-document-level-access-overview)。 |
| F09 | P1 | 企業既有版控與 Jira 整合 | Work 可唯讀查詢 GitHub／GitLab／Gitea PR／checks；Code 可寫入 Gitea | GitHub／GitLab 的授權連接、repo binding、branch／commit／PR 寫入、webhook 與 Jira issue 同步；Bitbucket／Azure DevOps 按第一批客戶選用。Work 保持能直接整合既有 forge，不把 Code 變成必要依賴。 |
| F10 | P1；正式程式交付前需要 | 真實 CI／測試證據整合 | Code 可回報 status、驗證／去重 Gitea webhook；Work 可讀 provider checks | 觸發／查看／重試／取消 pipeline，取得測試報告、log／artifact，將結果綁定 commit SHA／execution 並供獨立 reviewer 驗收。可以先接企業現有 runner；[GitLab pipelines API](https://docs.gitlab.com/api/pipelines/) 已提供 pipeline 與 test report 接口。 |
| F11 | P1；人員目錄強制同步時提前 | SCIM 與自動入離職／調職同步 | 邀請／JIT、登入時群組同步、管理員停用、backchannel logout | SCIM 2.0 Users／Groups、群組與權限變更、active=false 後撤銷平台 session；事件冪等、重試與對帳。這是目錄生命週期通道；[Entra provisioning](https://learn.microsoft.com/en-us/entra/identity/app-provisioning/how-provisioning-works) 說明建立／維護／停用同步。 |
| F12 | P1 | 一般 Agent 權杖生命週期 | Work token hash、Agent 停用；runtime delivery token 有期限且完成後撤銷 | 一般 Agent token 的 expires_at、單把撤銷、輪替／過渡期、最後使用、最小 scope 與管理介面。避免長期自動化只靠重新建立 Agent 來更換憑證。 |
| F13 | 部分納入本輪 | Agent 配置版本、角色指令與多協定模型 | 不可變 Agent 範本；角色／能力／指令／模型／工具／沙箱／限制、派工快照與個別覆寫 | 原生 Anthropic／Gemini 等 adapter、獨立 skill registry 與配置品質評估仍待開發。現有多個 base_url／model metadata 都走 `openai-responses`，不代表已驗收其他供應商的原生協定。 |
| F14 | P1／P2，依文件協作頻率 | 文件留言、送審與發布核准 | Knowledge 不可變版本、Decision 與來源 reference | 行內留言、指定 reviewer、草稿／送審／核准／退回與批准後發布；保存版本及審查證據，供多人維護正式規格、SOP 或制度文件。 |
| F15 | P2；持續跑 Agent 時提前 | Agent 品質評估與可觀測性 | 執行／稽核紀錄、Pi 持久化、模型用量 receipt | 脫敏工具／模型 trace、延遲／成功率／成本指標；資料集與固定評分規則，比較 prompt／model／Agent 版本，將真實失敗轉成回歸案例。可參考 [LangSmith datasets／evaluation](https://docs.langchain.com/langsmith/evaluation) 與 [OpenTelemetry traces](https://opentelemetry.io/docs/concepts/signals/traces/)。 |
| F16 | P2；需要雲端 Agent 接入時提前 MCP | 遠端 MCP gateway 與 A2A | 各產品本機 stdio MCP、受限 bearer REST bridge | Streamable HTTP MCP、遠端 token/scope 管理與工具目錄；之後以 A2A Agent Card／Task lifecycle 接入獨立 Agent。設計參照 [MCP authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) 與 [A2A specification](https://a2a-protocol.org/latest/specification/)。 |
| F17 | P2；多客戶 SaaS 時為 P0 | 團隊管理與完整多租戶 | 組織／團隊欄位、專案授權；Identity 環境綁定單一組織／IdP | 部門與團隊管理、團隊授權；多組織 membership、租戶切換、各自的 IdP／模型／配額／audit、跨租戶隔離驗收。企業各自獨立部署時可較晚做多租戶。 |

<span id="本輪第一版與後續候選"></span>
<span id="本轮第一版与后续候选"></span>

## 本輪第一版與後續候選 {#this-release-and-later-candidates}

<span id="f03-執行控制台"></span>
<span id="f03-运行控制台"></span>

### F03：執行控制台 {#f03-run-console}

本輪提供執行列表、詳細頁、模型／token／工具事件與錯誤、停止，以及有明確資格條件的暫停／恢復／重跑。所有操作由 Python 驗證當前使用者與專案權限；瀏覽器不持有 runtime 服務 token。精確契約見 [execution-contracts.md](execution-contracts.md)。

本輪驗收涵蓋 pending 停止、實際暫停／恢復、過期 lease／專案拒絕、重啟與回應遺失重試。新的一次重做有新 execution 與來源連結；同一次 resume 保留冪等界線。完整死信與操作人員處理介面仍為後續項。

<span id="f01-可持久化的執行前審批"></span>
<span id="f01-可持久化的运行前审批"></span>

### F01：可持久化的執行前審批 {#f01-durable-pre-execution-approvals}

第一版定義 ApprovalRequest、批准者、原因、工具／資源／參數摘要及 hash、有效期限。核准只授權對應動作，內容改變後需重新判定。政策位於 Python，共用 REST／MCP；Pi 只負責執行暫停／恢復。

驗收要涵蓋：未批准時無副作用、越權／自批拒絕、逾時／取消、核准後參數遭修改、重放與重啟、批准後相同副作用只執行一次。現有成果 review 保持自己的業務規則。持久 interrupt 的相關行為可參考 [LangGraph 官方文件](https://docs.langchain.com/oss/python/langgraph/interrupts)。

<span id="f02-先有可執行的上限-再有金額治理"></span>
<span id="f02-先有可运行的上限-再有金额治理"></span>

### F02：先有可執行的上限，再有金額治理 {#f02-enforce-limits-before-cost-governance}

第一版可先落實總 token／turn／工具呼叫／執行時間與併發配額，並顯示達限原因。要宣稱 USD hard budget，還需要已知且版本化的定價、請求前預留、完成後結算／釋放，以及多個 execution 同時搶用剩餘預算的原子控制。

驗收要涵蓋：預算不足時不發新模型請求、併發不能共同超用可預留額度、未知 usage／價格的顯式政策、失敗與取消後結算、cache 費率、重複 receipt 的去重。已發送請求的費用可能仍會由上游結算；不能承諾事後 abort 會退費。供應商的發票／實際帳單對帳屬另一個交付項目。

<span id="企業採購或正式維運時的附加項"></span>
<span id="企业采购或正式运维时的附加项"></span>

## 企業採購或正式維運時的附加項 {#additional-enterprise-procurement-and-operations-candidates}

| 候選 | 現況 | 建議啟動條件與最小交付 |
|---|---|---|
| 本機管理員 MFA／Passkey | 企業 MFA 可交給 IdP；本機帳號沒有 TOTP／WebAuthn | 若管理員復原帳號也必須第二因素，提供 enrollment／驗證／復原政策及安全審計。 |
| 稽核整合、SIEM 與防竄改 | Identity 已有受限 JSONL 匯出、複合游標分頁及明確套用的保留期；尚無 SIEM 推送、簽章／hash chain 或 WORM 防竄改儲存 | 當組織需集中關聯 Identity 與產品事件時，先提供有界、可重試的 SIEM／事件匯出整合；如需防竄改，再加入簽章／hash chain／WORM 儲存與驗證。 |
| Vault／KMS／Secret Manager | 用戶端密鑰／模型金鑰已在本機加密；Compose 機密以掛載檔案提供 | 當金鑰管理要集中或跨節點時，增加外部機密後端、憑證輪替與復原流程。 |
| 自動備份、還原演練、監控與 HA | 有 health、具名 volumes、重啟持久化及手動備份說明；完整 restore／HA 未驗收 | 正式運行前制定 RPO／RTO，驗證資料庫、key、Pi 與 Git／附件一致還原；加入告警／metrics，需求升高後再處理 worker partition／HA。Pi storage 維持單一擁有者。 |

<span id="分期與依賴"></span>
<span id="分期与依赖"></span>

## 分期與依賴 {#phases-and-dependencies}

1. **本輪執行基礎**：F03／F04／F05 與 F13 配置範本，共用既有 Identity、Work 服務、outbox 與 Pi。完成證據集中於 `execution-validation.md`。
2. **第一批企業流程深化**：F01 審批、F02 金額／配額、基本通知、自有程式碼託管平台與 CI（F09／F10），或知識匯入與檢索（F07／F08）。先支援一個確定的 Git／文件來源並端到端驗收，再擴充供應商。
3. **持續企業導入**：F11／F12、人員與 token 生命週期、品質評估、SIEM／備份維運，再依需求加入團隊／多租戶、遠端 MCP／A2A、MFA／Vault。

文件匯入與來源權限要先於大量 RAG 索引；審批、scope 與執行隔離要納入 shell／部署／merge 類工具；CI 結果需綁定實際 commit／execution。跨產品搜尋與工具連接透過 API／事件整合，每個產品維持自己的業務授權及資料庫。這些是具體實作的設計前提，尚未改寫現有契約。

<span id="程式碼證據"></span>
<span id="代码证据"></span>

## 程式碼證據 {#code-evidence}

| 盤點 | 來源 |
|---|---|
| 成果 review 與取消／人工操作 | [Work 服務](../backend/src/ordivant/service.py):542、828、865；[Work UI](../frontend/src/App.tsx):1144、1336；[runtime 伺服器](../runtime/src/server.ts):95 |
| 指令範本與自動派發 | [Agent 結構定義](../backend/src/ordivant/schemas.py):145；[Work 服務](../backend/src/ordivant/service.py):1111、1159；[派送器](../runtime/src/dispatcher.ts):25、169 |
| 既有限制性重試與工具註冊 | [Work 服務](../backend/src/ordivant/service.py):1226；[派送器](../runtime/src/dispatcher.ts):285；[執行引擎](../runtime/src/engine.ts):455；[平台工具](../runtime/src/platform-tools.ts):160；[runtime `Dockerfile`](../runtime/Dockerfile):28 |
| 金額預算與固定模型協定 | [Work 服務](../backend/src/ordivant/service.py):1346；[執行引擎](../runtime/src/engine.ts):423；[已設定的 Provider](../runtime/src/configured-provider.ts):42 |
| 尚未有 runtime 人工等待狀態；receipt 金額未知 | [runtime 型別](../runtime/src/types.ts) 的 `RunStatus`／`RunReceipt`；[模型契約](model-contracts.md) |
| 預算與自陳成本 UI | [`App.tsx`](../frontend/src/App.tsx):1149、1214；[前端型別](../frontend/src/types.ts):106 |
| 通知／mentions／due date 與附件 | [`App.tsx`](../frontend/src/App.tsx):427、951、1216；[Work 結構定義](../backend/src/ordivant/schemas.py):91、185；[契約](contracts.md):20 |
| Knowledge 匯入／搜尋／直接發布 | [Knowledge 結構定義](../products/knowledge/backend/src/ordivant_knowledge/schemas.py):25；[Knowledge API](../products/knowledge/backend/src/ordivant_knowledge/api.py):227、382；[Knowledge UI](../frontend/src/products/knowledge/KnowledgeApp.tsx):144、469、528 |
| Code Gitea；Work 多 forge 唯讀 | [Code 主程式](../products/code/backend/src/ordivant_code/main.py):177；[Work 版控](../backend/src/ordivant/vcs.py):15、50；[Work API](../backend/src/ordivant/api.py):405 |
| CI status／webhook 的目前範圍 | [Code 服務](../products/code/backend/src/ordivant_code/service.py):714；[Code UI](../frontend/src/products/code/CodeApp.tsx):523、538；[Suite 契約](suite-contracts.md):63 |
| 單組織 Identity／IdP | [SSO 契約](sso-contracts.md):15；[驗證契約](auth-contracts.md):50；[組織模型](../backend/src/ordivant/models.py):11 |
| SCIM／MFA／現有停用與撤銷 | [SSO 契約](sso-contracts.md):64；[企業登入](enterprise-sso.md):78、80；[專案計畫](project-plan.md) 的後續企業驗收門檻 |
| Agent token 生命週期 | [Token 模型](../backend/src/ordivant/models.py):37；[安全性](../backend/src/ordivant/security.py):31；[契約](contracts.md):18、58 |
| Audit 範圍與金鑰管理 | [SSO 契約](sso-contracts.md):15、73；[SSO API](../products/identity/backend/src/ordivant_identity/sso.py):1266；[Identity 模型](../products/identity/backend/src/ordivant_identity/models.py):143；[Compose 機密](../compose.yaml):209 |
| 已驗收與尚未驗收的正式維運 | [SSO 驗收](sso-validation.md):48；[驗收清單](validation.md)；[專案計畫](project-plan.md) 的後續企業驗收門檻 |

上表行號與舊範圍是 2026-10-07 的盤點位置，實作後可能位移；F03／F04／F05／F13 的目前證據以 execution-contracts.md 與 execution-validation.md 為準。官方資料只用來評估候選功能，不能作為 Ordivant 已具備該功能的證據。
