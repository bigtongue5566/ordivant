<script setup lang="ts">
import { computed, ref } from 'vue'
import { useData, withBase } from 'vitepress'
import DocScreenshot from './DocScreenshot.vue'

const { lang } = useData()
const selected = ref(0)
const content = computed(() => lang.value === 'en' ? {
  label: 'Explore the products', suffix: 'en', prefix: '/en',
  items: [
    { key: 'work', title: 'Work', heading: 'Give every task a goal, an owner, and evidence.', text: 'Managers assign work to coworkers or Agents; people can claim their own eligible tasks. Keep submissions and independent reviews together.', action: 'Create your first project', path: '/guide/first-project', alt: 'Work task list showing owners, progress, and review status' },
    { key: 'workflow', title: 'Runs & automation', heading: 'Turn a repeatable process into a workflow.', text: 'Reuse an Agent template, put steps in order, and start manually or on an interval. A dependent step waits for the preceding result to pass review.', action: 'Explore execution and workflows', path: '/execution-usage', alt: 'Workflow editor with dependent steps in a demonstration project' },
    { key: 'knowledge', title: 'Knowledge', heading: 'Edit project knowledge together.', text: 'Collaborate on a shared draft in real time, then publish immutable versions and cite exact sources. Agents can use the same draft through REST or MCP.', action: 'Organize project knowledge', path: '/guide/knowledge', alt: 'Knowledge document with its published version and source details' },
    { key: 'code', title: 'Code', heading: 'Discuss PRs against the exact code revision.', text: 'Ordivant keeps discussions and reviews tied to the PR head SHA. Gitea remains responsible for Git operations and merging.', action: 'Follow the code workflow', path: '/guide/code', alt: 'Code pull request showing a real demonstration branch and commit' },
  ],
} : lang.value === 'zh-Hans' ? {
  label: '探索产品功能', suffix: 'zh-CN', prefix: '/zh-CN',
  items: [
    { key: 'work', title: 'Work', heading: '每项工作都有目标、负责人和成果证据。', text: '管理者可把工作指派给同事或 Agent；成员也可认领自己有权处理的任务。提交与独立审核记录集中保留。', action: '建立第一个项目', path: '/guide/first-project', alt: 'Work 任务清单：查看负责人、进度和审核状态' },
    { key: 'workflow', title: '运行与自动化', heading: '把经常做的事整理成工作流程。', text: '重复使用 Agent 模板、排列步骤，再手动或定期启动。后续步骤会等待前置成果通过审核，才继续运行。', action: '了解运行与工作流程', path: '/execution-usage', alt: '工作流程设置：安排示范项目的步骤与依赖' },
    { key: 'knowledge', title: 'Knowledge', heading: '与团队一起编辑项目知识。', text: '多人实时共同编辑同一份草稿，再发布不可变版本并引用确切来源。Agent 可通过 REST 或 MCP 访问同一份草稿。', action: '整理项目知识', path: '/guide/knowledge', alt: 'Knowledge 文件：查看发布版本与来源资料' },
    { key: 'code', title: 'Code', heading: '针对准确代码版本讨论 PR。', text: 'Ordivant 将讨论与审查绑定 PR head SHA。Git 操作与合并仍由 Gitea 负责。', action: '跟着代码流程操作', path: '/guide/code', alt: 'Code 合并请求：查看实际示范分支与提交' },
  ],
} : {
  label: '探索產品功能', suffix: 'zh-TW', prefix: '',
  items: [
    { key: 'work', title: 'Work', heading: '每項工作都有目標、負責人與成果證據。', text: '管理者可把工作指派給同事或 Agent；成員也可認領自己有權處理的任務。提交與獨立審核紀錄集中保留。', action: '建立第一個專案', path: '/guide/first-project', alt: 'Work 任務清單：查看負責人、進度與審核狀態' },
    { key: 'workflow', title: '執行與自動化', heading: '把經常做的事整理成工作流程。', text: '重複使用 Agent 範本、排列步驟，再手動或定期啟動。後續步驟會等待前置成果通過審核，才繼續執行。', action: '了解執行與工作流程', path: '/execution-usage', alt: '工作流程設定：安排示範專案的步驟與依賴' },
    { key: 'knowledge', title: 'Knowledge', heading: '和團隊一起編輯專案知識。', text: '多人即時共同編輯同一份草稿，再發布不可變版本並引用確切來源。Agent 可透過 REST 或 MCP 存取同一份草稿。', action: '整理專案知識', path: '/guide/knowledge', alt: 'Knowledge 文件：查看發布版本與來源資料' },
    { key: 'code', title: 'Code', heading: '針對確切程式碼版本討論 PR。', text: 'Ordivant 將討論與審查綁定 PR head SHA。Git 操作與合併仍由 Gitea 負責。', action: '跟著程式碼流程操作', path: '/guide/code', alt: 'Code 合併請求：查看實際示範分支與提交' },
  ],
})
const item = computed(() => content.value.items[selected.value])
function move(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  selected.value = event.key === 'Home' ? 0 : event.key === 'End' ? 3 : (selected.value + (event.key === 'ArrowRight' ? 1 : 3)) % 4
  const group = (event.currentTarget as HTMLElement).closest('[role="tablist"]')
  ;(group?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[selected.value])?.focus()
}
</script>

<template>
  <div class="feature-explorer">
    <div class="feature-tabs" role="tablist" :aria-label="content.label">
      <button v-for="(tab, index) in content.items" :id="`feature-tab-${tab.key}`" :key="tab.key" type="button" role="tab" :aria-selected="selected === index" :tabindex="selected === index ? 0 : -1" :aria-controls="`feature-panel-${tab.key}`" @click="selected = index" @keydown="move">{{ tab.title }}</button>
    </div>
    <section :id="`feature-panel-${item.key}`" :key="item.key" class="feature-panel" role="tabpanel" :aria-labelledby="`feature-tab-${item.key}`">
      <h3>{{ item.heading }}</h3>
      <p>{{ item.text }}</p>
      <DocScreenshot :src="`/screenshots/${item.key}-${content.suffix}.png`" :alt="item.alt" />
      <a class="feature-action" :href="withBase(`${content.prefix}${item.path}.html`)">{{ item.action }} <span aria-hidden="true">→</span></a>
    </section>
  </div>
</template>
