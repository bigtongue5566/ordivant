---
layout: home
title: 开源 Agent 协作平台
description: 认识 Ordivant 的任务协作、Agent 执行、工作流程、知识与程式码管理，跟着完整教学部署并完成第一个项目。
hero:
  name: Ordivant
  text: 让团队与 Agent 一起把工作完成。
  tagline: 把目标拆成任务，让 Agent 带着规格与工具执行；团队掌握进度、保留知识，并用成果证据确认交付。
  image:
    src: /screenshots/work-zh-CN.png
    alt: Ordivant Work 任务工作区
  actions:
    - theme: brand
      text: 完成第一个项目
      link: /zh-CN/guide/first-project
    - theme: alt
      text: Docker Compose 安装
      link: /zh-CN/containers
    - theme: alt
      text: 看功能画面
      link: /zh-CN/#product-tour
---

<span id="從規格-到經過驗收的成果"></span>
<span id="从规格-到经过验收的成果"></span>

## 从规格，到经过验收的成果 {#from-specifications-to-reviewed-results}

Ordivant 是开源、可自行部署的 Agent 项目协作平台。它把**要做的工作、执行的过程、交付的成果，以及团队的审核**放在同一个项目里：先写清楚目标和验收条件，交给人员或 Agent，查看每次尝试，最后由独立审查者决定是否完成。

团队可以从一个文件整理任务开始，逐步加入模型、工具、知识库与自动工作流程。每个人的权限、Agent 能使用的工具及执行环境，都由你自己的部署与管理者设定。

**这个网站是产品介绍与使用手册。** 使用平台时，开启团队提供的 Ordivant 网址，或依[安装指南](./containers.md)在自己的环境启动；网站本身不提供云端帐号或模型服务。

## 哪些工作适合交给 Ordivant？ {#use-cases}

| 想完成的工作 | 交给平台的数据与安排 | 团队可以检查的交付 |
| --- | --- | --- |
| 准备产品上线 | 产品规格、服务清单、待办任务、依赖关系 | 有负责人与状态的上线清单，以及逐项成果证据 |
| 整理团队知识 | 操作文件、需求、会议决策与来源 | 可搜索的文件、发布版本、引用及决策纪录 |
| 协作程式码变更 | 变更目标、范围、验收条件、规格引用 | 分支、commit、PR 和测试证据，连回相关任务 |
| 执行重复性工作 | Agent 范本、固定步骤、前置依赖、执行输入 | 每次流程产生的任务、Run、提交成果与审核纪录 |

例如每周整理发布准备情况：先整理你提供的数据，再检查缺漏、提出待确认事项，经审核后才让依赖它的下一个步骤开始。若需要读取外部系统，管理者先连接对应工具并授权；数据不会因为写入网址就自动取得。

## 没有 LLM 也能让团队一起工作 {#collaboration-without-llm}

真人可以在 Work 创建任务；有管理权限的人可以指派给同事，有项目权限的执行者可以认领未指派或指派给自己的任务。提交成果后，仍须由另一位获授权的人独立审核。

Knowledge 允许多位获授权成员实时共同编辑同一份草稿；已保存的草稿可以发布为不可变版本。Agent 也可以通过 REST 或 MCP 参与同一份草稿，但这些人工工作不需要 LLM。

Code 可以在 Ordivant 中保存绑定 PR head SHA 的讨论与审查记录。Code 的 Git 操作需要 Gitea；Gitea 负责 Git、合并及其自身的批准流程。只有自主 Agent 执行需要模型设置。

## 一次看懂主要功能 {#product-tour}

切换下方产品，查看实际界面及适用的工作。每张文档截图都能点击放大，也能切回原始尺寸查看字段。画面以示例数据展示平台功能；DEMO Run 用来说明操作，不代表付费模型已完成任务。

<FeatureExplorer />

### Work：任务、协作与独立审核 {#work-preview}

在任务规格写下目标、输入数据、范围、限制及验收条件。管理者可以指派给同事或 Agent；有项目权限的执行者也可以认领未指派或指派给自己的任务。遇到问题时，从任务发起求助或委派子任务，让讨论与交付保留在同一脉络；提交后由另一位获授权的人独立审核。

[任务与审核操作](./guide/work.md) · [求助与委派](./features.md#work-help-and-delegation)

### Run：Agent 执行与自动化 {#runs-preview}

派发给 Pi Agent 后，在 Run 查看状态、执行事件、工具结果、产出及供应商回报的用量。获授权的人员可要求暂停、继续、停止或重试。常用设定保存为 Agent 范本；工作流程可以手动或定期启动，依赖步骤会等待前置成果通过审核。

[Run、范本与工作流程操作](./execution-usage.md) · [模型连线与 Agent 设定](./model-usage.md)

### Knowledge：文件版本与决策依据 {#knowledge-preview}

用 Space 整理项目文件，搜索标题、内容与标签。多位获授权成员可以实时共同编辑同一份 Markdown 草稿；Agent 也可通过 REST 或 MCP 参与。发布会保存不可变版本，任务或 PR 可引用确切版本。引用保留来源，读取权限仍由 Space 管理。

[文件、版本、搜索与引用操作](./guide/knowledge.md)

### Code：程式码交付与 PR {#code-preview}

Code 可以为 PR 保存绑定当前 head SHA 的 Ordivant 本地讨论与审查记录，这些记录不等同 Gitea 核准。Code 的 Git 操作需要 Gitea；Gitea 负责 Git、合并及其自身的批准流程。使用既有 GitHub 或 GitLab 的团队，可在 Work 设置只读连接以查看 PR 与检查结果。

[Code 操作指南](./guide/code.md) · [选择需要的产品](./overview.md#four-service-boundaries)

## 团队每个角色可以做什么？ {#team-roles}

| 角色 | 日常工作 |
| --- | --- |
| 项目负责人 | 建立项目与规格、拆分任务、安排依赖和人员、派发 Agent、处理阻碍 |
| 执行者 | 依规格完成工作、提出问题、保存来源及成果、提交审核 |
| 审查者 | 对照验收条件检查成果与证据，接受或说明需要修改的地方 |
| 知识维护者 | 发布与更新文件、记录决策、提供可追溯的版本引用 |
| 部署与组织管理员 | 设定帐号、资源权限、模型连线、企业 SSO、工具与沙箱 |

一个帐号可在同一部署登入三个产品；Work 项目、Knowledge Space、Code 项目各自授权。人员帐号与 Agent 是分开的身分，建立 Agent 不会替团队成员授予权限。[建立团队与邀请成员](./guide/team-setup.md)

<span id="開始第一個專案"></span>
<span id="开始第一个项目"></span>

## 跟着完成第一个项目 {#start-your-first-project}

完整教学使用「整理产品上线清单」作为范例。你会从空白工作区建立 LAUNCH 项目，填写一份可执行的规格，走完提交与审核；可以选择 Pi Agent 或人工执行路线。

1. **登入与建立团队**：新部署先建立初始管理员；既有团队接受邀请或用企业帐号登入。邀请另一位成员，让执行与审核由不同人负责。
2. **建立项目与数据背景**：建立「产品上线准备」项目。已有规格时，发布到 Knowledge，保存版本引用；也可先把必要数据放入任务输入。
3. **准备执行者**：自动执行需要启用 Runtime，设定自己的模型供应商与金钥，建立有项目权限的 Pi Agent。人工路线可先不设定外部模型。
4. **新增具体任务**：填写目标、输入、范围、限制与逐项验收条件；范例字段和可以复制的内容都在教学中。
5. **派发并查看过程**：从任务选择 Pi Agent 并派发，到 Run 查看进度。人工执行者则先认领任务，完成实际清单后提交。
6. **检查交付与独立审核**：执行者提交摘要、清单及来源证据；另一位有权限的人接受或退回。审核接受后，任务才标示完成。
7. **建立后续流程**：为下一项工作设定依赖，让它等待这份清单被接受，再将常用 Agent 设定和步骤保存为范本及工作流程。

![成果审核：检查示范清单、提交证据与审核结果](/screenshots/review-zh-CN.png)

[开始第一个项目完整教学 →](./guide/first-project.md)

## 如何写一份 Agent 能使用的任务？ {#writing-a-useful-task}

先提供可取得的数据，再说清楚交付格式与界线。以下是教学中的规格方向：

| 字段 | 「整理产品上线清单」的例子 |
| --- | --- |
| 目标 | 根据提供的产品背景，整理上线前必须确认的项目 |
| 输入与范围 | 提供登入、备份及操作指南的现况；只整理清单与缺漏 |
| 限制 | 未提供的资讯标为待确认，不自行声称已完成检查或变更外部服务 |
| 验收条件 | 每项列出负责角色、状态及来源；至少涵盖登入、备份与使用说明 |
| 成果证据 | 实际清单内容、来源引用，以及哪些项目仍待人员确认 |

遇到 Agent 缺乏数据或工具时，先补充输入、授权合适的工具，或拆出需要人员处理的工作。一次模型回复、Run 已提交或一笔自报状态，都要由审查者对照实际成果。[查看完整字段与提交范例](./guide/first-project.md)

## 选择你的开始方式 {#choose-your-start}

**已加入团队**：取得管理者提供的平台网址与邀请，阅读[快速入门](./guide/getting-started.md)。看不到项目时，请管理者授予对应资源权限。

**自己安装**：准备 Git 与 Docker Compose v2，依[部署指南](./containers.md)下载、初始化并启动，开启平台建立第一个管理员。需要自动 Agent 执行、Code 或沙箱时，再启用对应服务。

**企业导入**：先由[团队设定](./guide/team-setup.md)安排角色及资源，再串接[企业 SSO](./enterprise-sso.md)、[模型](./model-usage.md)和经允许的[工具及沙箱](./execution-usage.md#external-mcp-tools)。同时规划[备份与运维](./guide/operations.md)。

## 找到你需要的操作指南 {#find-your-guide}

| 想做的事 | 从这里开始 |
| --- | --- |
| 了解每项功能怎么用 | [功能导览](./features.md) |
| 从空白工作区完成第一个成果 | [第一个项目完整教学](./guide/first-project.md) |
| 邀请成员、安排执行与审核角色 | [建立团队](./guide/team-setup.md) |
| 设定 API 连线与 Agent 模型 | [模型设定](./model-usage.md) |
| 管理 Run、范本及多步骤工作 | [执行与自动化](./execution-usage.md) |
| 发布项目文件、决策与引用 | [Knowledge 指南](./guide/knowledge.md) |
| 提交程式码变更与 PR | [Code 指南](./guide/code.md) |
| 串接公司登入与资源权限 | [企业 SSO](./enterprise-sso.md)・[组织管理](./guide/administration.md) |
| 安装、升级、备份及排解问题 | [Docker Compose](./containers.md)・[运维](./guide/operations.md)・[疑难排解](./guide/troubleshooting.md) |

<span id="部署在自己的環境"></span>
<span id="部署在自己的环境"></span>

## 部署在自己的环境 {#deploy-in-your-own-environment}

Ordivant 采 **MIT 授权**，可自行使用、修改及部署。Work、Knowledge 与 Code 可各自部署；数据由你管理。共用登入支援本地帐号与企业 OIDC，选用 Keycloak 可桥接 SAML／LDAP。

当前版本为 **v0.2.0（2026-10-14）**。Work、Knowledge、Code 的真人协作不需要 LLM；只有自主 Agent Run 需要模型设置。Knowledge 提供文本搜索，Code 的 Git 写入需要 Gitea；尚未提供向量搜索、内置 CI、SCIM、硬性金额预算或分布式执行。Docker 沙箱没有网络或主机目录访问，使用已备妥的工具执行工作；需要更强隔离时应配置 VM 执行环境。查看[版本与升级说明](./release.md)。

外部模型与工具需自行提供连线及授权，可能产生供应商费用。未设定模型的 DEMO 只演示执行流程；真实交付请核对成果、来源与供应商用量。

[自行部署 →](./containers.md) · [现有功能与规划](./roadmap.md) · [GitHub 原始码](https://github.com/ordivant-ai/ordivant)
