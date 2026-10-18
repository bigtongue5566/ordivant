<span id="v0-1-0-公開版本"></span>
<span id="v0-1-0-公开版本"></span>
<span id="public-release-v0-1-0"></span>
<span id="public-release-v0-2-0"></span>
<span id="public-release-v0-3-0"></span>

# Ordivant v0.4.0 公开版本 {#public-release-v0-4-0}

发布日期：2026-10-19。许可：[MIT](../../LICENSE)。源代码与下载：[GitHub Releases](https://github.com/ordivant-ai/ordivant/releases/tag/v0.4.0)。

## 本版内容 {#included-in-this-release}
<span id="本版內容"></span>
<span id="本版内容"></span>

- **个人 API 与 MCP**：在“账号与安全性 → API 与 MCP”创建限定产品和期限的个人令牌，复制当前环境的连接示例，并随时撤销。令牌代表本人的真人账号，每次操作沿用当前角色和资源范围，不会获得 Agent 身份或额外权限。见[连接指南](./guide/administration.md#personal-api-and-mcp-access)。
- **六种内置 Agent 模板**：PM、PG、SA、SD、QA 和 Reviewer。新建 Agent 时带入可编辑的名称、能力和工作指令；模板按组织保存为不可变版本，不会覆盖既有 Agent。见 [Work 指南](./guide/work.md#built-in-agent-templates)。
- **创建项目时一起创建其他产品**：Work 项目创建后，可选择创建对应 Knowledge 空间和 Code 项目，也可跳过。失败项目可分别重试，成功项目不会重复创建；各产品仍独立授权。
- **从 Provider 获取模型**：模型配置可向 OpenAI 兼容服务的 `/models` 获取列表，搜索并选择模型。仅在上游明确提供时，才带入 Context、输出上限和推理强度，缺失时仍需手填；不会测试模型推理。见[模型配置](./model-usage.md)。
- **更清楚的执行配置**：使用“执行方式”“由平台执行”和“由外部程序执行”说明 Agent 的运作；修复指定模型尚未填写完整时的界面错误，以及模型列表撑长侧栏的问题。
- **开源协作指南**：重新整理 AGENTS 和贡献规范，为不同开发者和 coding agent 提供通用的目录、契约、测试和 PR 指引。
- 新功能界面和操作文档支持繁体中文、简体中文和英文；既有真人工作、文档共同编辑和 Code 协作仍不需要 LLM。

个人令牌完整内容只显示一次，每位用户最多 50 个有效令牌，有效期为 1 至 365 天。密码变更、账号恢复和停用会撤销既有令牌；“退出所有设备”只撤销浏览器会话，外部工具须另外撤销令牌。MCP 当前使用本地 stdio bridge，需要 uv 和源代码，并非远程 Streamable HTTP MCP 服务。新增连接示例使用占位值，请在自己的客户端安全配置令牌。

## 升级与限制 {#upgrade-and-limitations}
<span id="升級與限制"></span>
<span id="升级与限制"></span>

从 v0.3.0 或更早版本升级前，先按[运维指南](./guide/operations.md)停止服务并备份该 Compose 项目的数据库、所有持久化数据卷、服务机密和自定义 `.env`。加密密钥必须与对应数据库、数据卷一起保存；机密目录默认为 `.data/container-secrets/`，自定义时备份 `ORDIVANT_SECRETS_DIR` 指定的位置。如果使用企业机密挂载，也备份 `ORDIVANT_ENTERPRISE_SECRETS_DIR`。

将现有 repository 更新到 v0.4.0，沿用原有 Compose 项目名称、`.env`、机密目录、Compose 文件组合和 profiles。服务启动时会应用数据库结构更新。从 repository root 运行：

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
