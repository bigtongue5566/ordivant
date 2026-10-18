<span id="模型連線與-agent-設定"></span>
<span id="模型连接与-agent-设置"></span>

# 模型连接与 Agent 设置 {#model-connections-and-agent-settings}

Work 组织管理员负责设置模型连接。所有 Agent 都可以继承组织预设，也可以单独选择模型；变更只会应用到之后派发的任务。

<span id="管理員設定全域連線"></span>
<span id="管理员设置全域连接"></span>

## 管理员设置全局连接 {#configure-a-global-connection-as-an-administrator}

1. 登录 Work，从侧栏打开「模型连接」。只有组织管理员可以管理供应商连接。
2. 添加供应商，填写名称、标识、HTTPS API base URL 和 API key。兼容 Responses API 的网址通常以 `/v1` 结尾。
3. 点击「从 API 取得模型」，搜索并选择要添加的模型，再点击「加入所选模型」。此操作使用当前填写或已保存的密钥，调用 Base URL 下的 `/models`。API 未提供的 context、单次输出上限和推理强度需自行补填；也可手动添加模型。获取列表会保留现有模型设置，保存后才生效。
4. 选择组织预设的供应商、模型、推理选项和输出上限，然后保存。

API key 会安全保存，重新打开设置时不会再次显示；留空后保存可以保留现有 key。更换 API 网址时，请输入该供应商提供的 key。如果页面提示其他管理员已经更新设置，请重新加载后再修改。

<span id="建立或編輯-agent"></span>
<span id="创建或编辑-agent"></span>

![模型连接：输入供应商网址与支持的模型，API Key 使用自己的供应商密钥](/screenshots/models-zh-CN.png)

## 创建或编辑 Agent {#create-or-edit-an-agent}

在「Agent 名录」添加或编辑 Agent，并选择模型设置方式：

| 模式 | 说明 |
|---|---|
| 继承全局预设 | 新派发的任务使用组织当前的默认模型和选项。 |
| Agent 单独设置 | 为这个 Agent 选择供应商、模型、推理选项和输出上限；使用该供应商已设置的 key。 |

编辑 Agent 时也可以切换这两种模式。切回继承后，名录会显示实际生效的全局选项。设置变更不会影响已经派发的任务，从下一次派工开始生效。

由外部程序运行的 Agent 不会由 Work 代为调用模型；模型名称仅供辨识。

<span id="provider-設定範例"></span>
<span id="provider-设置范例"></span>

![Agent 设置：选择 Pi Durable、能力标签与模型继承方式](/screenshots/agent-zh-CN.png)

## Provider 设置范例 {#provider-configuration-example}

请使用模型供应商提供的 HTTPS 网址、模型 ID 和选项。`https://api.example.com/v1` 仅为格式示例，不能直接连接。Ordivant 不附带模型服务或 API key。

context 上限表示模型可处理的内容范围；输出上限限制单次回复长度。请填写供应商实际支持的数值，并先用较低的输出上限测试。这些设置不是整体费用上限；模型费率与计费方式以供应商为准。如需限制实际支出，请在供应商账户设置用量或费用上限。

不同 Work 环境分别保存设置；如有多个 Work 地址，需要分别配置供应商连接。

<span id="執行與證據"></span>
<span id="运行与证据"></span>

## 运行与成果 {#execution-and-evidence}

将任务派发给已设置模型的 Agent 时，会调用该供应商服务，可能产生费用。未设置模型时，系统会清楚标示为 DEMO；DEMO 不会调用付费模型。供应商调用失败会显示失败，不会改用 DEMO 假装成功。

Run 记录可能显示供应商回报的模型名称与 token 用量，但不一定能取得美元费用。token 数不等于账单；供应商回报的模型名称也不能单独证明中转服务底层实际使用的路由。请以供应商的用量和账单页面确认实际费用。

Agent 提交成果后，任务仍需由另一位有权限的审查者接受才算完成。操作方式请参阅[Work 任务指南](guide/work.md)和[执行与自动化指南](execution-usage.md)；自架服务和数据备份方式请参阅[容器部署指南](containers.md)。
