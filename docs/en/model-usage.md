<span id="模型連線與-agent-設定"></span>
<span id="模型连接与-agent-设置"></span>

# Model connections and Agent settings {#model-connections-and-agent-settings}

A Work organization administrator configures model connections. Agents can inherit the organization default or use an Agent-specific selection. Changes apply to tasks dispatched afterward.

<span id="管理員設定全域連線"></span>
<span id="管理员设置全域连接"></span>

## Configure a global connection as an administrator {#configure-a-global-connection-as-an-administrator}

1. Sign in to Work and open **Model connections** in the sidebar. Only organization administrators can manage provider connections.
2. Add a provider with a name, ID, HTTPS API base URL, and API key. A Responses API-compatible URL commonly ends in `/v1`.
3. Click **Fetch models from API**, search and select models, then click **Add selected models**. This calls `/models` under the Base URL using the entered or saved key. Fill in context, output limits, and reasoning options that the API does not provide. You can also add models manually. Fetching preserves existing model settings; changes apply only after saving.
4. Select the organization's default provider, model, reasoning option, and output limit, then save.

The API key is stored securely and is not shown again when you reopen settings. Leaving the key field blank and saving preserves the current key. When changing the API URL, enter the key supplied for that provider. If the page says another administrator changed the settings, reload before making your update.

<span id="建立或編輯-agent"></span>
<span id="创建或编辑-agent"></span>

![Model connection: enter the provider URL and supported models, using your own provider-issued API key](/screenshots/models-en.png)

## Create or edit an Agent {#create-or-edit-an-agent}

In **Agent directory**, add or edit an Agent and choose how it gets model settings:

| Mode | Description |
|---|---|
| Inherit global default | New tasks use the organization's current default model and options. |
| Agent-specific | Choose a provider, model, reasoning option, and output limit for this Agent; it uses the key already configured for that provider. |

You can switch between these modes when editing an Agent. When you switch back to inheritance, the directory shows the global options that will apply. Changes do not affect tasks that have already been dispatched; they apply on the next dispatch.

An Agent run by an external program is not called by Work. Its model name is only a label.

<span id="provider-設定範例"></span>
<span id="provider-设置范例"></span>

![Agent settings: select Pi Durable, capability tags, and model inheritance](/screenshots/agent-en.png)

## Provider configuration example {#provider-configuration-example}

Use the HTTPS URL, model ID, and options supplied by your model provider. `https://api.example.com/v1` is only a format example and cannot be called directly. Ordivant does not include a model service or API key.

The context limit controls how much content a model can process; the output limit caps the length of one response. Enter values supported by your provider and start with a low output limit. These settings are not an overall spending cap. Rates and billing are determined by the provider. To limit actual spending, set a usage or spending limit in your provider account.

Each Work environment stores its own settings. Configure the provider separately for each Work address you use.

<span id="執行與證據"></span>
<span id="运行与证据"></span>

## Runs and evidence {#execution-and-evidence}

Dispatching a task to an Agent with a configured model calls that provider and may incur charges. When no model is configured, the system clearly marks the run as DEMO; DEMO does not call a paid model. A provider failure is shown as a failure and is never presented as a successful DEMO.

A Run record may show the model name and token usage returned by the provider, but dollar cost may be unavailable. Token counts are not an invoice, and a reported model name alone cannot prove which route an intermediary service used. Check the provider's usage and billing pages for actual charges.

After an Agent submits work, another authorized reviewer must accept the result before the task is complete. See the [Work task guide](guide/work.md) and [execution and automation guide](execution-usage.md) for the workflow, or the [container deployment guide](containers.md) for self-hosting and data backups.
