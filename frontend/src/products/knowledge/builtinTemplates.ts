const builtins: Record<string, { name: string; description: string; body: string }> = {
  "builtin:prd": {
    "name": "產品需求文件 (PRD)",
    "description": "規劃問題、目標、範圍與驗收條件。",
    "body": "# 產品需求\n\n## 問題\n\n## 目標與範圍\n\n## 使用者與情境\n\n## 需求\n\n## 驗收條件\n"
  },
  "builtin:meeting": {
    "name": "會議記錄",
    "description": "整理議程、討論、決議與待辦。",
    "body": "# 會議記錄\n\n## 日期與參與者\n\n## 議程\n\n## 討論\n\n## 決議\n\n## 待辦事項\n"
  },
  "builtin:adr": {
    "name": "架構決策紀錄 (ADR)",
    "description": "保留背景、選項、決定及其後果。",
    "body": "# 架構決策\n\n## 狀態\n\n## 背景\n\n## 考慮過的選項\n\n## 決定\n\n## 後果\n"
  },
  "builtin:sop": {
    "name": "標準作業程序 (SOP)",
    "description": "說明適用範圍、前置條件與可核對步驟。",
    "body": "# 標準作業程序\n\n## 目的與範圍\n\n## 角色\n\n## 前置條件\n\n## 程序\n\n## 驗證與復原\n"
  }
};

export function localizeTemplate<T extends { id: string; builtin: boolean; name: string; description: string; body: string }>(template: T, t: (message: string) => string): T {
  const builtin = template.builtin ? builtins[template.id] : undefined;
  return builtin ? { ...template, name: t(builtin.name), description: t(builtin.description), body: t(builtin.body) } : template;
}
