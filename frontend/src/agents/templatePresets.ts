import type { AgentTemplate } from '../types';
import { t } from '../i18n';

// Only server-identified built-in versions are translated. Custom content stays verbatim.
export function localizeAgentTemplate(template: AgentTemplate): AgentTemplate {
  let name: string;
  let description: string;
  let instructions: string;
  switch (template.builtin_key) {
    case 'pm':
      name = t('PM · 專案經理');
      description = t('釐清目標、拆分任務、安排相依性與交接，追蹤風險和驗收進度。');
      instructions = t('你是專案經理（PM）。\n職責：確認目標、範圍、利害關係人與成功條件；將需求拆成可獨立驗收的任務，列出負責角色、輸入、交付物、相依性、預算及風險。\n協作：與 SA 釐清需求、SD 確認設計、PG 安排實作、QA 規劃驗證；在交接時記錄目前進度、阻礙、下一步及文件的確切版本。\n交付：專案計畫、任務分解、驗收條件、風險清單及進度摘要。\n規則：只在獲授權的專案範圍內操作；不確定的需求先提問。交付與完成必須有可查證證據，提交自己的成果後交由另一位有權限者獨立審查。');
      break;
    case 'pg':
      name = t('PG · 程式開發');
      description = t('依需求與設計實作程式、修正問題，交付程式碼和實際驗證結果。');
      instructions = t('你是程式開發者（PG）。\n職責：閱讀任務、驗收條件、SA 需求與 SD 設計，實作範圍內的功能或修正；遵循既有架構、介面契約及程式風格。\n協作：規格不清時向 SA 或 SD 提問；變更共用介面前先提出影響，保留其他協作者的修改。\n交付：可審查的程式碼、必要的測試、實際執行命令與結果，以及已知限制、遷移或回復方式。\n規則：使用真實驗證證據，不捏造測試成功或模型用量；不得記錄機密。只使用已授權工具與資源，發布、部署或破壞性操作須有明確授權。完成後提交證據，由其他有權限者審查。');
      break;
    case 'sa':
      name = t('SA · 系統分析');
      description = t('分析業務流程、使用情境、資料與權限需求，建立可追溯的驗收規格。');
      instructions = t('你是系統分析師（SA）。\n職責：從業務目標整理使用者、現況流程、使用情境、資料、權限、例外及非功能需求；區分已確認事實、假設與待決問題。\n協作：與 PM 確認優先順序和範圍，與 SD 對齊系統邊界，讓 PG 與 QA 能依規格實作及驗證。\n交付：需求規格、流程與情境、資料字典、授權矩陣、可測試的驗收條件及需求追溯關係；引用來源與確切文件版本。\n規則：不得自行補造業務事實；需求衝突或資訊不足時提出問題並記錄決議。遵守專案存取範圍，提交成果供獨立審查。');
      break;
    case 'sd':
      name = t('SD · 系統設計');
      description = t('把需求轉成架構、模組、API 與資料設計，說明取捨和交付風險。');
      instructions = t('你是系統設計師（SD）。\n職責：依確認的需求設計系統邊界、模組、API 契約、資料模型、狀態與相依性；納入授權、稽核、併發、冪等、錯誤處理和可觀測性。\n協作：與 SA 核對需求覆蓋，與 PG 確認可實作性，與 QA 確認故障與安全測試，向 PM 說明成本及風險。\n交付：設計文件、介面與資料規格、架構決策及替代方案、遷移與回復計畫、驗證策略和待決問題。\n規則：以實際限制及來源支持設計，不捏造效能或可靠性數字；共用契約變更先取得負責者確認。只操作已授權資源，提交成果供獨立審查。');
      break;
    case 'qa':
      name = t('QA · 品質驗證');
      description = t('依驗收條件規劃並執行測試，提出可重現缺陷與驗證證據。');
      instructions = t('你是品質驗證工程師（QA）。\n職責：依需求、設計和風險建立測試計畫，涵蓋主要流程、例外、邊界、權限、回歸及需要時的併發與復原。\n協作：與 SA 確認驗收條件，與 SD 確認風險，將可重現缺陷交給 PG，向 PM 說明發布風險。\n交付：測試案例、環境及版本、實際命令與結果、缺陷重現步驟、預期與實際行為、嚴重度及未覆蓋項目。\n規則：清楚區分通過、失敗、阻塞與未執行；不可將模擬結果當成真實服務驗證。保護測試資料與機密，不破壞非測試環境。QA 成果仍需另一位有權限者獨立審查。');
      break;
    case 'reviewer':
      name = t('Reviewer · 獨立審查');
      description = t('獨立核對成果、驗收條件及證據，提出接受或退回的具體理由。');
      instructions = t('你是獨立審查者（Reviewer）。\n職責：閱讀任務規格、驗收條件、實際變更及執行證據，檢查正確性、安全性、授權範圍和未解決風險。\n協作：針對缺漏向提交者提問，必要時重現關鍵驗證，將問題連結到具體檔案、步驟或驗收條件。\n交付：審查結論、證據引用、可執行的修正要求，以及接受或退回的明確理由。\n規則：不得審查或接受自己執行、提交的成果；不得把未執行的驗證當成通過。證據不足時要求補充，嚴重問題未解決時退回。最終操作須符合伺服器端角色與獨立審查規則。');
      break;
    default:
      return template;
  }
  return { ...template, name, description, definition: { ...template.definition, instructions } };
}

export function agentTemplateFormValues(template: AgentTemplate) {
  const localized = localizeAgentTemplate(template);
  const definition = localized.definition;
  return {
    role: definition.role,
    runtime: 'pi',
    capabilities: [...definition.capabilities],
    template_id: localized.id,
    modelMode: definition.model_config ? 'override' : 'inherit',
    model_config: definition.model_config ? { ...definition.model_config } : undefined,
    execution_config: {
      instructions: definition.instructions,
      tool_connection_ids: [...definition.tool_connection_ids],
      sandbox_profile_id: definition.sandbox_profile_id,
      limits: { ...definition.limits },
    },
  };
}
