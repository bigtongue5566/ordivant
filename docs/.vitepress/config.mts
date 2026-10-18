import { defineConfig } from 'vitepress'
import path from 'node:path'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
import { excludedDocumentPaths } from '../../scripts/docs_pages.mjs'

const docsRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = path.resolve(docsRoot, '..')
const repository = 'https://github.com/ordivant-ai/ordivant'
const base = process.env.DOCS_BASE ?? '/'
// Preserve organization project-site bookmarks after moving to the root site.
const legacyProjectRedirect = "if(location.hostname==='ordivant-ai.github.io'&&(location.pathname==='/ordivant'||location.pathname.startsWith('/ordivant/'))){const path=location.pathname.slice('/ordivant'.length)||'/';location.replace('https://ordivant-ai.github.io'+path+location.search+location.hash)}"

const localeTheme = (prefix: string, language: 'zh-Hant' | 'en' | 'zh-Hans') => {
  const isEnglish = language === 'en'
  const isSimplified = language === 'zh-Hans'
  const text = isEnglish ? {
    start: 'Get started', deploy: 'Self-host', usage: 'User guides',
    startGroup: 'Get started', overview: 'About Ordivant', features: 'Feature tour', install: 'Quick introduction', tutorial: 'First project, step by step', team: 'Set up your team', release: 'Release notes',
    guide: 'Daily work', work: 'Work tasks and collaboration', runs: 'Runs, templates and automation',
    knowledge: 'Knowledge and citations', code: 'Code and version control', models: 'Model settings', login: 'Accounts and login',
    admin: 'Administration and deployment', permissions: 'Permissions and organization', sso: 'Enterprise SSO',
    containers: 'Self-host Ordivant', ops: 'Backup and operations', troubleshooting: 'Troubleshooting',
    roadmap: 'Features and limits',
    outline: 'On this page', previous: 'Previous page', next: 'Next page', updated: 'Last updated',
    languageMenu: 'Change language', menu: 'Open navigation menu', appearance: 'Appearance', lightMode: 'Switch to light theme',
    darkMode: 'Switch to dark theme', returnTop: 'Return to top', skipContent: 'Skip to content',
    missing: 'Page not found', missingDescription: 'This page is unavailable. Return to the documentation home page.', home: 'Return home',
    footer: 'MIT licensed · Self-hosted',
  } : isSimplified ? {
    start: '开始使用', deploy: '自行部署', usage: '操作指南',
    startGroup: '开始使用', overview: '产品介绍', features: '功能导览', install: '快速入门', tutorial: '第一个项目完整教程', team: '建立团队与邀请成员', release: '版本说明',
    guide: '日常操作', work: 'Work 任务与协作', runs: 'Run、模板与自动化',
    knowledge: 'Knowledge 文档与引用', code: 'Code 与版本控制', models: '模型设置', login: '账号与登录',
    admin: '管理与部署', permissions: '权限与组织管理', sso: '企业 SSO',
    containers: '自行部署 Ordivant', ops: '备份与运维', troubleshooting: '问题排查',
    roadmap: '功能与限制',
    outline: '本页内容', previous: '上一页', next: '下一页', updated: '最后更新',
    languageMenu: '切换语言', menu: '打开导航菜单', appearance: '外观', lightMode: '切换到浅色主题',
    darkMode: '切换到深色主题', returnTop: '返回顶部', skipContent: '跳到正文',
    missing: '找不到页面', missingDescription: '此页面不存在，请返回文档首页。', home: '返回首页',
    footer: 'MIT 许可 · 自行部署',
  } : {
    start: '開始使用', deploy: '自行部署', usage: '操作指南',
    startGroup: '開始使用', overview: '產品介紹', features: '功能導覽', install: '快速入門', tutorial: '第一個專案完整教學', team: '建立團隊與邀請成員', release: '版本說明',
    guide: '日常操作', work: 'Work 任務與協作', runs: 'Run、範本與自動化',
    knowledge: 'Knowledge 文件與引用', code: 'Code 與版控', models: '模型設定', login: '帳號與登入',
    admin: '管理與部署', permissions: '權限與組織管理', sso: '企業 SSO',
    containers: '自行部署 Ordivant', ops: '備份與維運', troubleshooting: '問題排查',
    roadmap: '功能與限制',
    outline: '本頁內容', previous: '上一頁', next: '下一頁', updated: '最後更新',
    languageMenu: '切換語言', menu: '開啟導覽選單', appearance: '外觀', lightMode: '切換為淺色主題',
    darkMode: '切換為深色主題', returnTop: '回到頁首', skipContent: '跳至正文',
    missing: '找不到頁面', missingDescription: '此頁面不存在，請返回文件首頁。', home: '返回首頁',
    footer: '以 MIT 授權釋出 · 自行部署',
  }
  const route = (path: string) => `${prefix === '/' ? '' : prefix}${path}`
  return {
    nav: [
      { text: text.start, link: route('/guide/first-project') },
      { text: text.features, link: route('/features') },
      { text: text.usage, link: route('/guide/work') },
      { text: text.deploy, link: route('/containers') },
      { text: 'v0.5.0', link: route('/release') },
    ],
    sidebar: [
      { text: text.startGroup, items: [
        { text: text.overview, link: route('/overview') },
        { text: text.features, link: route('/features') },
        { text: text.install, link: route('/guide/getting-started') },
        { text: text.tutorial, link: route('/guide/first-project') },
        { text: text.login, link: route('/human-login') },
        { text: text.release, link: route('/release') },
        { text: text.roadmap, link: route('/roadmap') },
      ] },
      { text: text.guide, items: [
        { text: text.work, link: route('/guide/work') },
        { text: text.runs, link: route('/execution-usage') },
        { text: text.knowledge, link: route('/guide/knowledge') },
        { text: text.code, link: route('/guide/code') },
        { text: text.models, link: route('/model-usage') },
      ] },
      { text: text.admin, items: [
        { text: text.team, link: route('/guide/team-setup') },
        { text: text.permissions, link: route('/guide/administration') },
        { text: text.sso, link: route('/enterprise-sso') },
        { text: text.containers, link: route('/containers') },
        { text: text.ops, link: route('/guide/operations') },
        { text: text.troubleshooting, link: route('/guide/troubleshooting') },
      ] },
    ],
    socialLinks: [{ icon: 'github', link: repository }],
    outline: { label: text.outline, level: [2, 3] },
    notFound: { title: text.missing, quote: text.missingDescription, linkText: text.home, linkLabel: text.home },
    docFooter: { prev: text.previous, next: text.next },
    lastUpdated: { text: text.updated },
    langMenuLabel: text.languageMenu,
    sidebarMenuLabel: text.menu,
    darkModeSwitchLabel: text.appearance,
    lightModeSwitchTitle: text.lightMode,
    darkModeSwitchTitle: text.darkMode,
    returnToTopLabel: text.returnTop,
    skipToContentLabel: text.skipContent,
    footer: { message: text.footer, copyright: '© 2026 Ordivant contributors' },
  }
}

export default defineConfig({
  lang: 'zh-Hant', title: 'Ordivant',
  description: '開源、自行部署的 Agent 協作平台：Work、Knowledge、Code。',
  base, cleanUrls: false, lastUpdated: true,
  srcExclude: excludedDocumentPaths(),
  themeConfig: {
    logo: '/logo.svg', siteTitle: 'Ordivant', i18nRouting: true,
    search: { provider: 'local', options: { locales: {
      root: { translations: {
        button: { buttonText: '搜尋文件', buttonAriaLabel: '搜尋文件' },
        modal: { noResultsText: '找不到相關文件', resetButtonTitle: '清除搜尋', footer: { selectText: '選取', navigateText: '切換', closeText: '關閉' } },
      } },
      en: { translations: {
        button: { buttonText: 'Search docs', buttonAriaLabel: 'Search docs' },
        modal: { noResultsText: 'No results found', resetButtonTitle: 'Clear search', footer: { selectText: 'Select', navigateText: 'Navigate', closeText: 'Close' } },
      } },
      'zh-CN': { translations: {
        button: { buttonText: '搜索文档', buttonAriaLabel: '搜索文档' },
        modal: { noResultsText: '未找到相关文档', resetButtonTitle: '清除搜索', footer: { selectText: '选择', navigateText: '切换', closeText: '关闭' } },
      } },
    } } },
  },
  locales: {
    root: { label: '繁體中文', lang: 'zh-Hant', themeConfig: localeTheme('/', 'zh-Hant') },
    en: { label: 'English', lang: 'en', title: 'Ordivant', description: 'An open-source, self-hosted collaboration platform for agents.', themeConfig: localeTheme('/en', 'en') },
    'zh-CN': { label: '简体中文', lang: 'zh-Hans', title: 'Ordivant', description: '开源、自行部署的 Agent 协作平台。', themeConfig: localeTheme('/zh-CN', 'zh-Hans') },
  },
  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: `${base}logo.svg` }],
    ['script', {}, legacyProjectRedirect],
  ],
  sitemap: { hostname: 'https://ordivant-ai.github.io/' },
  markdown: {
    config(md) {
      const copyLabel = (env: any) => {
        const source = env.path ?? env.filePath ?? ''
        const relative = path.relative(docsRoot, source).split(path.sep).join('/')
        return relative.startsWith('en/') ? 'Copy code' : relative.startsWith('zh-CN/') ? '复制代码' : '複製程式碼'
      }
      const image = md.renderer.rules.image!
      md.renderer.rules.image = (tokens, index, options, env, renderer) => {
        const token = tokens[index]
        const src = token.attrGet('src') ?? ''
        if (/^\/screenshots\/[a-zA-Z0-9-]+\.png$/.test(src)) {
          return `<DocScreenshot src="${md.utils.escapeHtml(src)}" alt="${md.utils.escapeHtml(token.content)}" />`
        }
        return image(tokens, index, options, env, renderer)
      }
      const fence = md.renderer.rules.fence!
      md.renderer.rules.fence = (tokens, index, options, env, renderer) => {
        const label = copyLabel(env)
        return fence(tokens, index, options, env, renderer).replace(/<button title="[^"]*" class="copy">/g, `<button title="${label}" aria-label="${label}" class="copy">`)
      }
      md.core.ruler.push('localized-section-labels', (state) => {
        const source = state.env.path ?? state.env.filePath ?? ''
        const relative = path.relative(docsRoot, source).split(path.sep).join('/')
        const label = relative.startsWith('en/') ? 'Link to section' : relative.startsWith('zh-CN/') ? '链接到章节' : '連至章節'
        const visit = (tokens: any[]) => tokens.forEach(token => {
          if (token.type === 'link_open' && token.attrGet('class') === 'header-anchor') {
            const previous = token.attrGet('aria-label') ?? ''
            token.attrSet('aria-label', previous.replace(/^Permalink to/, label))
          }
          if (token.children) visit(token.children)
        })
        visit(state.tokens)
      })
      // Source links stay useful both in GitHub Markdown and in the published site.
      md.core.ruler.after('inline', 'repository-source-links', (state) => {
        const source = state.env.path ?? state.env.filePath
        if (!source) return
        const visit = (tokens: any[]) => tokens.forEach(token => {
          if (token.type === 'link_open') {
            const href = token.attrGet('href')
            if (href && !/^(?:[a-z]+:|\/|#)/i.test(href)) {
              const [pathname, anchor] = href.split('#')
              const target = path.resolve(path.dirname(source), decodeURIComponent(pathname))
              if (fs.existsSync(target) && !target.startsWith(docsRoot + path.sep)) {
                const relative = path.relative(repoRoot, target).split(path.sep).join('/')
                if (!relative.startsWith('..')) token.attrSet('href', `${repository}/blob/main/${relative}${anchor ? '#' + anchor : ''}`)
              }
            }
          }
          if (token.children) visit(token.children)
        })
        visit(state.tokens)
      })
    },
  },
})
