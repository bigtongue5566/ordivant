<span id="v0-1-0-公開版本"></span>
<span id="v0-1-0-公开版本"></span>
<span id="public-release-v0-1-0"></span>
<span id="public-release-v0-2-0"></span>

# Ordivant v0.3.0 公开版本 {#public-release-v0-3-0}

发布日期：2026-10-15。许可：[MIT](../../LICENSE)。源代码与下载：[GitHub Releases](https://github.com/ordivant-ai/ordivant/releases/tag/v0.3.0)。

## 本版内容 {#included-in-this-release}
<span id="本版內容"></span>
<span id="本版内容"></span>

- **Work 团队规划**：看板与 Backlog 排序、Epic、工作类型、Sprint、里程碑、日期、自定义字段和阶段；登录后提报任务、事件规则、个人保存查询、工时、每周容量、观察报表及 CSV 导入／导出。真人可认领或接受指派、交接、提交成果，再由另一位获授权的人独立审查。操作方式见 [Work 指南](./guide/work.md)。
- **跨模块协作**：Work、Knowledge 和 Code 的资源支持附件、提及、订阅及通知；通知中心和跨产品文本搜索只显示当前获授权的内容。
- **Knowledge 文档协作**：页面层级、归档、PRD／会议／ADR／SOP 模板、评论回复与解决、Markdown 工具和预览、版本差异及受控还原。多人和 Agent 仍可共同编辑同一份草稿，发布后保留不可变版本。见 [Knowledge 指南](./guide/knowledge.md)。
- **Code 审查与证据**：PR 行内讨论绑定 head SHA、文件与行号；head 改变后会标示过期。可管理并读回 Gitea 分支保护，查看当前提交的上游批准、检查与 Actions；配置 GitHub／GitLab 部署来源后，可读取同一 SHA 的部署记录。Ordivant 不会代替上游运行 CI 或部署。见 [Code 指南](./guide/code.md)。
- **企业身份与治理**：SCIM 2.0 Users／Groups、OIDC ACR／AMR 登录政策、SMTP 邀请与账号恢复，以及 Identity 审计导出与保留管理。见[管理指南](./guide/administration.md)及[企业 SSO](./enterprise-sso.md)。
- **无 LLM 也能使用**：普通真人任务、共同编辑、附件、搜索和 Code 协作不需要模型；只有自主 Agent Run 需要模型连接。界面和操作文档提供繁体中文、简体中文和英文。

## 升级与限制 {#upgrade-and-limitations}
<span id="升級與限制"></span>
<span id="升级与限制"></span>

从 v0.2.0 或更早版本升级前，先按[运维指南](./guide/operations.md)停止服务并备份该 Compose 项目的数据库、所有持久化数据卷、服务机密和自定义 `.env`。加密密钥必须与对应数据库、数据卷一起保存；机密目录默认为 `.data/container-secrets/`，自定义时备份 `ORDIVANT_SECRETS_DIR` 指定的位置。如果使用企业机密挂载，也备份 `ORDIVANT_ENTERPRISE_SECRETS_DIR`。

将现有 repository 更新到 v0.3.0，沿用原有 Compose 项目名称、`.env`、机密目录、Compose 文件组合和 profiles。服务启动时会应用数据库结构更新。从 repository root 运行：

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
