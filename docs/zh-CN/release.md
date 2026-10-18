<span id="v0-1-0-公開版本"></span>
<span id="v0-1-0-公开版本"></span>
<span id="public-release-v0-1-0"></span>
<span id="public-release-v0-2-0"></span>
<span id="public-release-v0-3-0"></span>
<span id="public-release-v0-4-0"></span>

# Ordivant v0.5.0 公开版本 {#public-release-v0-5-0}

发布日期：2026-10-19。许可：[MIT](../../LICENSE)。源代码与下载：[GitHub Releases](https://github.com/ordivant-ai/ordivant/releases/tag/v0.5.0)。

## 本版内容 {#included-in-this-release}
<span id="本版內容"></span>
<span id="本版内容"></span>

- **项目设置与范围导航**：侧栏固定显示当前项目或空间，顶部显示当前位置；Work 的“项目设置”可管理名称、说明、跟踪预算与成员访问权限。并发修改会提示冲突，避免覆盖他人的设置。见 [Work 指南](./guide/work.md#project-settings)。
- **分开个人与组织管理**：“账号设置”管理个人资料、安全性及 API／MCP；“组织管理”集中用户、企业 SSO、治理与身份审计，仅管理员可使用。
- **Agent 生命周期**：支持停用后重新启用、归档保留历史，以及永久删除未使用的 Agent。仍有未完成工作或启用中的自动化引用时，服务会拒绝退役操作。归档会撤销凭证且无法恢复。
- **刷新后保留位置**：三个模块会保留网址中的页面与资源选择；侧栏账号操作收进菜单，设置页面改用清晰的分区导航，并支持小屏幕。
- **人工维护三语翻译**：移除 OpenCC.js 与自动繁简转换，逐条校订简体中文；翻译检查验证完整性及插值且不改写词库。

Work 可按项目授予访问权限，但同一成员的 Work 角色在各授权项目共用；目前不支持各项目独立角色或 Work 只读角色。只有系统管理员可调整真人成员访问权限。Knowledge 空间与 Code 项目保持独立授权，同名不代表共享权限。

个人令牌完整内容只显示一次，每位用户最多 50 个有效令牌，有效期为 1 至 365 天。密码变更、账号恢复和停用会撤销既有令牌；“退出所有设备”只撤销浏览器会话，外部工具须另外撤销令牌。MCP 当前使用本地 stdio bridge，需要 uv 和源代码，并非远程 Streamable HTTP MCP 服务。新增连接示例使用占位值，请在自己的客户端安全配置令牌。

## 升级与限制 {#upgrade-and-limitations}
<span id="升級與限制"></span>
<span id="升级与限制"></span>

从 v0.4.0 或更早版本升级前，先按[运维指南](./guide/operations.md)停止服务并备份该 Compose 项目的数据库、所有持久化数据卷、服务机密和自定义 `.env`。加密密钥必须与对应数据库、数据卷一起保存；机密目录默认为 `.data/container-secrets/`，自定义时备份 `ORDIVANT_SECRETS_DIR` 指定的位置。如果使用企业机密挂载，也备份 `ORDIVANT_ENTERPRISE_SECRETS_DIR`。

将现有 repository 更新到 v0.5.0，沿用原有 Compose 项目名称、`.env`、机密目录、Compose 文件组合和 profiles。服务启动时会应用数据库结构更新。从 repository root 运行：

```sh
docker compose up -d --build --wait
docker compose ps
```

原部署如果使用 profiles 或多份 Compose 文件，每次启动、重建和升级都要加回相同选项。服务正常后，登录检查既有项目、文档、PR 和权限。不要运行 `docker compose down -v` 或删除数据卷。需要回退旧版时，应一起还原升级前的数据库、数据卷、机密和程序版本。

Knowledge 的共同编辑内容是 Markdown；未确认的离线修改仅存在于当前浏览器分页内存，请在离开或重新加载前等待“已保存”。Git 写入和合并需要 Gitea；Ordivant PR 审查不会创建 Gitea 批准。

本版尚未提供向量搜索、内置 CI runner、全组织硬性金额预算或分布式运行。SCIM 不支持 bulk，也不会按 email 自动认领现有账号；MFA 政策依赖已验证的 IdP 声明。SMTP 用于邀请和恢复邮件，其他协作通知在平台内查看。正式使用前，请验证自己的 IdP／SCIM 目录、Git 服务、SMTP、模型和 HTTPS；GitHub／GitLab provider 的真实 CI 和成功部署结果需在实际环境确认。

## 可选企业集成 {#enterprise-setup}

SCIM、SMTP 和 GitHub／GitLab 部署来源由管理员按[容器部署指南](./containers.md#enterprise-secret-mounts)配置。使用 `compose.enterprise.yaml` 可将 Identity 和 Code 的机密目录分别只读挂载。采用此配置后，启动和升级需保留这份 overlay，例如：

```sh
docker compose -f compose.yaml -f compose.enterprise.yaml up -d --build --wait
docker compose -f compose.yaml -f compose.enterprise.yaml ps
```

如果另有 Gitea、Runtime 或其他配置文件，请一并保留。未启用企业集成时，仍可使用普通账号和真人协作。

完整版本记录见 [Changelog](https://github.com/ordivant-ai/ordivant/blob/main/CHANGELOG.md)；备份与还原方式见[运维指南](./guide/operations.md)。
