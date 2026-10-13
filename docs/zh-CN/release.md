<span id="v0-1-0-公開版本"></span>
<span id="v0-1-0-公开版本"></span>
<span id="public-release-v0-1-0"></span>

# Ordivant v0.2.0 公开版本 {#public-release-v0-2-0}

发布日期：2026-10-14。授权：[MIT](../../LICENSE)。源代码与下载：[GitHub Releases](https://github.com/ordivant-ai/ordivant/releases)。

## 本版内容 {#included-in-this-release}
<span id="本版內容"></span>
<span id="本版内容"></span>

- **Work**：管理者可以把任务指派给获授权的同事或 Agent。同事可以认领有权限处理的待办工作、持续回报进度、交接并提交成果，再由另一位获授权的人独立审核。真人执行记录保留在 Work 历史中，重新加载后可以继续处理。
- **Knowledge**：多人可以实时共同编辑同一份 Markdown 草稿，Agent 也能通过 REST/MCP 更新该草稿。断线后重新连接可合并尚未确认的内容；未确认的离线修改只存在当前浏览器标签页内存中。离开或发布前，请等待草稿显示已连接且已保存。发布会创建不可变版本并保留历史。
- **Code**：真人和 Agent 可以在 Ordivant 讨论 PR、发表评论并提交审核记录；每条记录都绑定 PR head SHA，head 改变后旧审核会标记为过期。Code 的 Git 写入与合并由 Gitea 处理；Ordivant 记录不会成为 Gitea 批准，也不代表上游 CI 结果。
- Work、Knowledge 和 Code 的常规人工协作不需要 LLM；只有自主 Agent Run 需要模型设置。Code 的 Git 操作仍需要 Gitea。
- 文档提供繁体中文、简体中文与英文版本，包括功能指南、团队设置和第一个项目完整教程。

## 升级与限制 {#upgrade-and-limitations}
<span id="升級與限制"></span>
<span id="升级与限制"></span>

从 v0.1.0 升级前，请依照[运维指南](./guide/operations.md)停止服务，并备份该 Compose 项目的数据库、所有持久化数据卷、服务机密及自定义 `.env`。加密密钥应与对应数据库和数据卷一起保存。机密目录默认为 `.data/container-secrets/`；如果设置了 `ORDIVANT_SECRETS_DIR`，请备份该变量指定的目录。

将现有 repository 更新到 v0.2.0，并沿用原有 Compose 项目名称、`.env`、机密目录、Compose 文件组合和 profiles。从 repository root 启动更新后的服务：

```sh
docker compose up -d --build --wait
docker compose ps
```

如果原部署使用自定义 profiles 或多份 Compose 文件，执行时也要加入相同选项。确认服务状态正常后，再从浏览器登录检查工作区。不要运行 `docker compose down -v` 或手动删除数据卷；升级必须保留现有数据。Knowledge 断线时，尚未确认的修改只保留在当前标签页内存中，离开或重新加载前请等待“已保存”。

本版不提供向量搜索、内置 CI、SCIM、硬性金额预算或分布式执行。Knowledge 搜索为文本搜索；Code 的 Ordivant PR 审核不等同 Gitea approval 或 CI。正式用于企业前，请验证自己的身份服务、Git 服务、模型供应商和 HTTPS 设置。

完整版本记录见 [Changelog](https://github.com/ordivant-ai/ordivant/blob/main/CHANGELOG.md)；备份与还原方式见[运维指南](./guide/operations.md)。
