import type { LocalizedMessage } from '../i18n';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Form,
  Input,
  InputNumber,
  Segmented,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Typography,
} from 'antd';
import type { FormInstance } from 'antd/es/form';
import { DeleteOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { api } from '../api';
import { formatNumber, useI18n, useLocalizedForm, localized } from '../i18n';
import type { Agent, DiscoveredModel, ModelCatalog, ModelDefinition, ModelProvider, ModelSelection, ModelSettings, ModelSettingsUpdate, ReasoningEffort } from '../types';
import './model-settings.css';

const { Text } = Typography;
const reasoningEffortLabels: Record<ReasoningEffort, string> = {
  low: '低',
  medium: '中',
  high: '高',
  xhigh: '極高',
  max: '最高',
};

type ProviderFormValue = ModelProvider & { api_key?: string };
type SettingsFormValue = {
  providers: ProviderFormValue[];
  has_default: boolean;
  default?: Partial<ModelSelection>;
};

function isCompleteModelSelection(selection: Partial<ModelSelection> | null | undefined): selection is ModelSelection {
  return Boolean(selection?.provider_id && selection.model_id
    && selection.reasoning_effort && Object.hasOwn(reasoningEffortLabels, selection.reasoning_effort)
    && typeof selection.max_output_tokens === 'number'
    && Number.isInteger(selection.max_output_tokens) && selection.max_output_tokens >= 16);
}

function errorText(error: unknown) {
  if (error instanceof Error && 'sourceMessage' in error) return String(error.sourceMessage);
  return error instanceof Error ? error.message : '發生未預期的模型設定錯誤。';
}

function asSettingsForm(settings: ModelSettings): SettingsFormValue {
  return {
    providers: settings.providers.map((provider) => ({
      id: provider.id,
      name: provider.name,
      base_url: provider.base_url,
      enabled: provider.enabled,
      key_configured: provider.key_configured,
      models: provider.models.map((model) => ({
        id: model.id,
        name: model.name,
        context_window: model.context_window,
        max_output_tokens: model.max_output_tokens,
        reasoning_efforts: [...model.reasoning_efforts],
      })),
      api_key: undefined,
    })),
    has_default: Boolean(settings.default),
    default: settings.default ?? undefined,
  };
}

export function ModelSettings() {
  const { t } = useI18n();
  const [form] = Form.useForm<SettingsFormValue>();
  useLocalizedForm(form);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | LocalizedMessage>('');
  const [notice, setNotice] = useState('');
  const [revision, setRevision] = useState<number | undefined>();
  const providers = Form.useWatch('providers', form) ?? [];
  const defaultProviderId = Form.useWatch(['default', 'provider_id'], form) as string | undefined;
  const defaultModelId = Form.useWatch(['default', 'model_id'], form) as string | undefined;
  const hasDefault = Form.useWatch('has_default', form) as boolean | undefined;
  const defaultProviders = useMemo(() => providers.filter((provider) => provider.enabled), [providers]);
  const defaultProvider = defaultProviders.find((provider) => provider.id === defaultProviderId);
  const defaultModel = defaultProvider?.models.find((model) => model.id === defaultModelId);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    setError('');
    setNotice('');
    try {
      const settings = await api.modelSettings();
      setRevision(settings.revision);
      form.setFieldsValue(asSettingsForm(settings));
      setLoaded(true);
      return true;
    } catch (loadError) {
      setError(localized('模型連線設定無法載入：{{error}}', { error: localized(errorText(loadError)) }));
      return false;
    } finally {
      setLoading(false);
    }
  }, [form]);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  function clearApiKeyFields() {
    const currentProviders = form.getFieldValue('providers') ?? [];
    currentProviders.forEach((_: ProviderFormValue, index: number) => {
      form.setFieldValue(['providers', index, 'api_key'], undefined);
    });
  }

  async function saveSettings(values: SettingsFormValue) {
    if (revision === undefined) {
      setError('缺少模型設定 revision，請重新整理後再儲存。');
      return;
    }
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const update: ModelSettingsUpdate = {
        revision,
        providers: values.providers.map((provider) => ({
          id: provider.id,
          name: provider.name,
          base_url: provider.base_url,
          enabled: provider.enabled,
          models: provider.models,
          ...(provider.api_key ? { api_key: provider.api_key } : {}),
        })),
        default: values.has_default ? values.default as ModelSelection : null,
      };
      await api.saveModelSettings(update);
      clearApiKeyFields();
      const refreshed = await loadSettings();
      if (refreshed) setNotice('模型連線設定已儲存。');
      else setError('設定已送出，但重新載入失敗；請重新整理確認目前設定。');
    } catch (saveError) {
      setError(localized('模型連線設定儲存失敗：{{error}}', { error: localized(errorText(saveError)) }));
    } finally {
      clearApiKeyFields();
      setSaving(false);
    }
  }

  return (
    <section className="model-settings-page">
      <div className="model-settings-toolbar">
        <Text>{t('全域管理員設定 provider 連線與可用模型；Agent 只會取得選模 metadata。')}</Text>
        <Button icon={<ReloadOutlined />} onClick={() => void loadSettings()} loading={loading}>{t('重新整理')}</Button>
      </div>
      {error && <Alert className="model-settings-alert" type="error" showIcon message={t(error)} />}
      {notice && <Alert className="model-settings-alert" type="success" showIcon message={t(notice)} />}
      {!loaded && loading && <div className="model-settings-loading"><Spin /><Text type="secondary">{t('正在載入模型連線設定')}</Text></div>}
      {!loaded && !loading && error && <div className="model-settings-retry"><Button onClick={() => void loadSettings()}>{t('重試')}</Button></div>}
      {loaded && (
        <Form form={form} layout="vertical" onFinish={(values) => void saveSettings(values)}>
          <Alert
            className="model-settings-security-note"
            type="info"
            showIcon
            message={t('Provider 金鑰由全域管理員管理')}
            description={t('API Key 不會從服務端回填。留白會保留現有金鑰；更換 Base URL 時請提供新金鑰。請使用 HTTPS API base URL。')}
          />

          <Form.List name="providers">
            {(fields, { add, remove }) => (
              <section className="model-settings-section">
                <div className="model-settings-section-heading">
                  <div><strong>{t('Provider 連線')}</strong><Text type="secondary">{t('{{count}} 個設定', { count: formatNumber(fields.length) })}</Text></div>
                  <Button icon={<PlusOutlined />} onClick={() => add({ id: '', name: '', base_url: '', enabled: true, key_configured: false, models: [], api_key: undefined })}>{t('新增 Provider')}</Button>
                </div>
                {fields.length === 0 && <div className="model-settings-empty">{t('尚未設定 Provider。')}</div>}
                {fields.map((field) => (
                  <ProviderEditor
                    key={field.key}
                    providerIndex={field.name}
                    form={form}
                    onRemove={() => remove(field.name)}
                  />
                ))}
              </section>
            )}
          </Form.List>

          <section className="model-settings-section model-default-section">
            <div className="model-settings-section-heading">
              <div><strong>{t('全域預設模型')}</strong><Text type="secondary">{t('Agent 選擇繼承時套用')}</Text></div>
              <Form.Item name="has_default" valuePropName="checked" noStyle>
                <Switch checkedChildren={t('啟用')} unCheckedChildren={t('不設定')} />
              </Form.Item>
            </div>
            {hasDefault && (
              <div className="model-default-grid">
                <Form.Item
                  name={['default', 'provider_id']}
                  label={t('Provider')}
                  rules={[
                    { required: true, message: t('請選擇 Provider') },
                    { validator: async (_, value: string) => { if (value && !defaultProviders.some((provider) => provider.id === value)) throw new Error(t('請選擇已啟用的 Provider')); } },
                  ]}
                >
                  <Select
                    placeholder={t('選擇 Provider')}
                    options={defaultProviders.map((provider) => ({ value: provider.id, label: provider.name }))}
                    onChange={(providerId: string) => form.setFieldValue('default', { provider_id: providerId, model_id: undefined, reasoning_effort: undefined, max_output_tokens: undefined })}
                  />
                </Form.Item>
                <Form.Item
                  name={['default', 'model_id']}
                  label={t('Model')}
                  rules={[
                    { required: true, message: t('請選擇模型') },
                    { validator: async (_, value: string) => { if (value && !defaultProvider?.models.some((model) => model.id === value)) throw new Error(t('此模型目前不可用')); } },
                  ]}
                >
                  <Select
                    placeholder={t('選擇模型')}
                    disabled={!defaultProvider}
                    options={defaultProvider?.models.map((model) => ({ value: model.id, label: model.name })) ?? []}
                    onChange={(modelId: string) => {
                      const model = defaultProvider?.models.find((item) => item.id === modelId);
                      form.setFieldValue('default', {
                        ...(form.getFieldValue('default') ?? {}),
                        model_id: modelId,
                        reasoning_effort: undefined,
                        max_output_tokens: model ? Math.min(4096, model.max_output_tokens) : undefined,
                      });
                    }}
                  />
                </Form.Item>
                <Form.Item
                  name={['default', 'reasoning_effort']}
                  label={t('推理強度')}
                  rules={[
                    { required: true, message: t('請選擇推理強度') },
                    { validator: async (_, value: ReasoningEffort) => { if (value && !defaultModel?.reasoning_efforts.includes(value)) throw new Error(t('此模型不支援該推理強度')); } },
                  ]}
                >
                  <Select
                    placeholder={t('選擇推理強度')}
                    disabled={!defaultModel}
                    options={defaultModel?.reasoning_efforts.map((effort) => ({ value: effort, label: t(reasoningEffortLabels[effort]) })) ?? []}
                  />
                </Form.Item>
                <Form.Item
                  name={['default', 'max_output_tokens']}
                  label={t('輸出上限')}
                  rules={[
                    { required: true, type: 'number', min: 16, message: t('輸出上限至少為 16 tokens') },
                    { validator: async (_, value: number) => { if (value !== undefined && defaultModel && value > defaultModel.max_output_tokens) throw new Error(t('不可超過此模型上限 {{max}}', { max: formatNumber(defaultModel.max_output_tokens) })); } },
                  ]}
                >
                  <InputNumber min={16} max={defaultModel?.max_output_tokens} precision={0} disabled={!defaultModel} className="full-width" />
                </Form.Item>
              </div>
            )}
            {!defaultProviders.length && <Text className="model-settings-help" type="secondary">{t('啟用至少一個 Provider 並設定模型後，即可選取全域預設。')}</Text>}
          </section>

          <div className="model-settings-actions">
            <Button type="primary" htmlType="submit" loading={saving} disabled={loading}>{t('儲存模型設定')}</Button>
          </div>
        </Form>
      )}
    </section>
  );
}

function ProviderEditor({ providerIndex, form, onRemove }: { providerIndex: number; form: FormInstance<SettingsFormValue>; onRemove: () => void }) {
  const { t } = useI18n();
  const provider = (Form.useWatch(['providers', providerIndex], form) ?? {}) as Partial<ProviderFormValue>;
  const models = (Form.useWatch(['providers', providerIndex, 'models'], form) ?? []) as ModelDefinition[];
  const [discovering, setDiscovering] = useState(false);
  const [discovered, setDiscovered] = useState<DiscoveredModel[] | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [discoveryError, setDiscoveryError] = useState<string | LocalizedMessage>('');
  const requestVersion = useRef(0);

  useEffect(() => {
    requestVersion.current += 1;
    setDiscovered(null);
    setSelected([]);
    setDiscoveryError('');
    setDiscovering(false);
    return () => { requestVersion.current += 1; };
  }, [provider.id, provider.base_url, provider.api_key, providerIndex]);

  async function discoverModels() {
    const version = ++requestVersion.current;
    setDiscovering(true);
    setDiscoveryError('');
    setDiscovered(null);
    setSelected([]);
    const current = form.getFieldValue(['providers', providerIndex]) as ProviderFormValue;
    const connection = { id: current.id, base_url: current.base_url, api_key: current.api_key };
    try {
      await form.validateFields([['providers', providerIndex, 'id'], ['providers', providerIndex, 'base_url']]);
      const result = await api.discoverModels(connection);
      const latest = form.getFieldValue(['providers', providerIndex]) as ProviderFormValue | undefined;
      if (version !== requestVersion.current || latest?.id !== connection.id || latest?.base_url !== connection.base_url || latest?.api_key !== connection.api_key) return;
      setDiscovered(result.models);
    } catch (discoveryFailure) {
      if (version === requestVersion.current && !(typeof discoveryFailure === 'object' && discoveryFailure !== null && 'errorFields' in discoveryFailure)) {
        setDiscoveryError(localized('取得模型失敗：{{error}}', { error: localized(errorText(discoveryFailure)) }));
      }
    } finally {
      if (version === requestVersion.current) setDiscovering(false);
    }
  }

  function addSelectedModels() {
    const current = (form.getFieldValue(['providers', providerIndex, 'models']) ?? []) as ModelDefinition[];
    const existing = new Set(current.map((model) => model.id));
    const additions = (discovered ?? []).filter((model) => selected.includes(model.id) && !existing.has(model.id));
    form.setFieldValue(['providers', providerIndex, 'models'], [...current, ...additions.map((model) => ({ ...model, reasoning_efforts: model.reasoning_efforts ?? [] }))]);
    setSelected([]);
  }

  return (
    <article className="model-provider">
      <div className="model-provider-heading">
        <div><strong>{provider.name || provider.id || t('新 Provider')}</strong>{provider.key_configured ? <Tag color="green">{t('金鑰已設定')}</Tag> : <Tag>{t('尚無金鑰')}</Tag>}</div>
        <Space>
          <Form.Item name={[providerIndex, 'enabled']} valuePropName="checked" noStyle>
            <Switch aria-label={t('啟用 Provider')} checkedChildren={t('啟用')} unCheckedChildren={t('停用')} />
          </Form.Item>
          <Button danger type="text" icon={<DeleteOutlined />} onClick={onRemove} aria-label={t('移除 {{provider}}', { provider: provider.name || 'Provider' })} />
        </Space>
      </div>
      <div className="model-provider-fields">
        <Form.Item name={[providerIndex, 'id']} label="Provider ID" rules={[{ required: true, whitespace: true, message: t('請輸入唯一 ID') }]}>
          <Input placeholder={t('例如 openai-prod')} autoComplete="off" />
        </Form.Item>
        <Form.Item name={[providerIndex, 'name']} label={t('顯示名稱')} rules={[{ required: true, whitespace: true, message: t('請輸入名稱') }]}>
          <Input placeholder={t('例如 OpenAI Production')} />
        </Form.Item>
        <Form.Item
          className="model-provider-url"
          name={[providerIndex, 'base_url']}
          label={t('HTTPS API base URL')}
          rules={[
            { required: true, whitespace: true, message: t('請輸入 API base URL') },
            { validator: async (_, value: string) => {
              if (!value) return;
              try {
                if (new URL(value).protocol !== 'https:') throw new Error();
              } catch {
                throw new Error(t('請輸入有效的 HTTPS URL'));
              }
            } },
          ]}
        >
          <Input placeholder="https://api.example.com/v1" autoComplete="url" />
        </Form.Item>
        <Form.Item
          className="model-provider-key"
          name={[providerIndex, 'api_key']}
          label="API Key"
          extra={t('欄位不會回填已儲存的明文；留白保留現有金鑰。')}
        >
          <Input.Password autoComplete="new-password" visibilityToggle={false} placeholder={t('輸入新金鑰')} />
        </Form.Item>
      </div>
      <div className="model-list-heading"><strong>{t('可用模型 metadata')}</strong><Text type="secondary">{t('供 Agent 選擇使用')}</Text></div>
      <div className="model-discovery">
        <Button icon={<ReloadOutlined />} loading={discovering} disabled={!provider.id || !provider.base_url} onClick={() => void discoverModels()}>{t('從 API 取得模型')}</Button>
        <Text type="secondary">{t('使用目前連線讀取模型清單；留白的 API Key 會使用此 Provider 已儲存的金鑰。')}</Text>
        {discoveryError && <Alert type="error" showIcon message={t(discoveryError)} />}
        {discovered !== null && <>
          <Text>{t('API 回傳 {{count}} 個模型；選擇後加入，儲存設定才會生效。', { count: formatNumber(discovered.length) })}</Text>
          <Select
            className="full-width"
            mode="multiple"
            showSearch
            optionFilterProp="label"
            placeholder={t('搜尋並選擇 API 模型')}
            value={selected}
            onChange={setSelected}
            options={discovered.map((model) => ({ value: model.id, label: `${model.name} (${model.id})`, disabled: models.some((existing) => existing.id === model.id) }))}
          />
          <Button disabled={!selected.length} icon={<PlusOutlined />} onClick={addSelectedModels}>{t('加入所選模型')}</Button>
          <Text type="secondary">{t('API 未提供的 Context、輸出上限與推理強度需自行補填；現有模型設定會保留。')}</Text>
        </>}
      </div>
      <Form.List name={[providerIndex, 'models']}>
        {(fields, { add, remove }) => (
          <div className="model-definitions">
            {fields.map((field) => (
              <div className="model-definition-row" key={field.key}>
                <Form.Item name={[field.name, 'id']} label="Model ID" rules={[{ required: true, whitespace: true, message: t('請輸入 Model ID') }]}><Input placeholder="provider model id" /></Form.Item>
                <Form.Item name={[field.name, 'name']} label={t('名稱')} rules={[{ required: true, whitespace: true, message: t('請輸入模型名稱') }]}><Input placeholder={t('顯示名稱')} /></Form.Item>
                <Form.Item name={[field.name, 'context_window']} label="Context" rules={[{ required: true, type: 'number', min: 1, message: t('請輸入正整數') }]}><InputNumber min={1} precision={0} className="full-width" /></Form.Item>
                <Form.Item name={[field.name, 'max_output_tokens']} label={t('輸出上限')} rules={[{ required: true, type: 'number', min: 16, message: t('模型輸出上限至少為 16 tokens') }]}><InputNumber min={16} precision={0} className="full-width" /></Form.Item>
                <Form.Item name={[field.name, 'reasoning_efforts']} label={t('推理強度')} rules={[{ required: true, type: 'array', min: 1, message: t('至少選擇一項') }]}>
                  <Select mode="multiple" maxTagCount={2} placeholder={t('選擇支援項目')} options={Object.entries(reasoningEffortLabels).map(([value, label]) => ({ value, label: t(label) }))} />
                </Form.Item>
                <Button danger type="text" icon={<DeleteOutlined />} onClick={() => remove(field.name)} aria-label={t('移除模型')} />
              </div>
            ))}
            {fields.length === 0 && <div className="model-settings-empty">{t('尚未加入模型 metadata。')}</div>}
            <Button size="small" icon={<PlusOutlined />} onClick={() => add({ id: '', name: '', context_window: undefined, max_output_tokens: undefined, reasoning_efforts: [] })}>{t('新增模型')}</Button>
          </div>
        )}
      </Form.List>
      {models.length > 0 && <Text className="model-settings-help" type="secondary">{t('Context 與輸出上限是管理員提供的 metadata。')}</Text>}
    </article>
  );
}

export function AgentModelConfigFields({
  form,
  catalog,
  catalogLoading,
  catalogError,
  agent,
  onRetry,
}: {
  form: FormInstance;
  catalog: ModelCatalog | null;
  catalogLoading: boolean;
  catalogError: string;
  agent: Agent | null;
  onRetry: () => void;
}) {
  const { t } = useI18n();
  const mode = (Form.useWatch('modelMode', form) as 'inherit' | 'override' | undefined) ?? 'inherit';
  // Nested fields are incomplete while mounting or changing provider/model.
  const selectedConfig = Form.useWatch('model_config', form) as Partial<ModelSelection> | undefined;
  const providerId = Form.useWatch(['model_config', 'provider_id'], form) as string | undefined;
  const modelId = Form.useWatch(['model_config', 'model_id'], form) as string | undefined;
  const provider = catalog?.providers.find((item) => item.id === providerId);
  const model = provider?.models.find((item) => item.id === modelId);
  const effectiveSelection = mode === 'override'
    ? selectedConfig
    : agent?.effective_model_config ?? catalog?.default ?? null;

  if (form.getFieldValue('runtime') !== 'pi') {
    return (
      <>
        <Form.Item name="model" label={t('外部程式使用的模型（選填）')} extra={t('僅記錄外部程式使用的模型名稱；實際模型與連線由外部程式設定。')}>
          <Input placeholder={t('選填，例如 provider/model')} />
        </Form.Item>
      </>
    );
  }

  return (
    <div className="agent-model-config">
      {catalogError && <Alert type="error" showIcon message={t('可選模型目錄無法載入')} description={t(catalogError)} action={<Button size="small" onClick={onRetry}>{t('重試')}</Button>} />}
      {!catalogError && !catalogLoading && catalog && catalog.providers.length === 0 && <Alert type="info" showIcon message={t('目前沒有可選模型')} description={t('管理員尚未設定已啟用且有金鑰的 Provider。Agent 可先繼承全域設定，待模型連線設定完成後再選擇 override。')} />}
      <Form.Item name="modelMode" label={t('模型設定')}>
        <Segmented
          block
          options={[{ label: t('繼承全域預設'), value: 'inherit' }, { label: t('為此 Agent 指定'), value: 'override' }]}
          onChange={(value) => {
            if (value === 'override' && catalog?.default && !form.getFieldValue(['model_config', 'provider_id'])) {
              form.setFieldValue('model_config', catalog.default);
            }
          }}
        />
      </Form.Item>
      {mode === 'override' && (
        <>
          <div className="agent-model-grid">
            <Form.Item
              name={['model_config', 'provider_id']}
              label={t('Provider')}
              rules={[
                { required: true, message: t('請選擇 Provider') },
                { validator: async (_, value: string) => { if (value && !catalog?.providers.some((item) => item.id === value)) throw new Error(t('此 Provider 目前不可用，請重新選擇')); } },
              ]}
            >
              <Select
                placeholder={t('選擇 Provider')}
                loading={catalogLoading}
                disabled={catalogLoading || Boolean(catalogError)}
                options={catalog?.providers.map((item) => ({ value: item.id, label: item.name })) ?? []}
                onChange={(nextProviderId: string) => form.setFieldValue('model_config', { provider_id: nextProviderId, model_id: undefined, reasoning_effort: undefined, max_output_tokens: undefined })}
              />
            </Form.Item>
            <Form.Item
              name={['model_config', 'model_id']}
              label={t('模型')}
              rules={[
                { required: true, message: t('請選擇模型') },
                { validator: async (_, value: string) => { if (value && !provider?.models.some((item) => item.id === value)) throw new Error(t('此模型目前不可用，請重新選擇')); } },
              ]}
            >
              <Select
                showSearch
                optionFilterProp="label"
                placeholder={t('選擇模型')}
                disabled={!provider || catalogLoading || Boolean(catalogError)}
                options={provider?.models.map((item) => ({ value: item.id, label: item.name })) ?? []}
                onChange={(nextModelId: string) => {
                  const nextModel = provider?.models.find((item) => item.id === nextModelId);
                  form.setFieldValue('model_config', {
                    ...(form.getFieldValue('model_config') ?? {}),
                    model_id: nextModelId,
                    reasoning_effort: undefined,
                    max_output_tokens: nextModel ? Math.min(4096, nextModel.max_output_tokens) : undefined,
                  });
                }}
              />
            </Form.Item>
            <Form.Item
              name={['model_config', 'reasoning_effort']}
              label={t('推理強度')}
              rules={[
                { required: true, message: t('請選擇推理強度') },
                { validator: async (_, value: ReasoningEffort) => { if (value && !model?.reasoning_efforts.includes(value)) throw new Error(t('此模型不支援該推理強度')); } },
              ]}
            >
              <Select
                placeholder={t('選擇推理強度')}
                disabled={!model}
                options={model?.reasoning_efforts.map((effort) => ({ value: effort, label: `${t(reasoningEffortLabels[effort])} (${effort})` })) ?? []}
              />
            </Form.Item>
            <Form.Item
              name={['model_config', 'max_output_tokens']}
              label={t('輸出上限')}
              rules={[
                { required: true, type: 'number', min: 16, message: t('輸出上限至少為 16 tokens') },
                { validator: async (_, value: number) => {
                  if (value === undefined || !model) return;
                  if (value < 16) throw new Error(t('輸出上限至少為 16 tokens'));
                  if (value > model.max_output_tokens) throw new Error(t('不可超過此模型上限 {{max}}', { max: formatNumber(model.max_output_tokens) }));
                } },
              ]}
            >
              <InputNumber min={16} max={model?.max_output_tokens} precision={0} disabled={!model} className="full-width" />
            </Form.Item>
          </div>
          {model && <Text className="model-settings-help" type="secondary">{t('Context {{context}} · 輸出上限 {{output}}', { context: formatNumber(model.context_window), output: formatNumber(model.max_output_tokens) })}</Text>}
        </>
      )}
      <div className="agent-effective-model">
        <Text type="secondary">{t('有效模型')}</Text>
        {isCompleteModelSelection(effectiveSelection)
          ? <span><strong>{modelName(effectiveSelection, catalog)}</strong><small>{effectiveSelection.provider_id} · {t(reasoningEffortLabels[effectiveSelection.reasoning_effort])} ({effectiveSelection.reasoning_effort}) · {formatNumber(effectiveSelection.max_output_tokens)} tokens</small></span>
          : <Text type="secondary">{mode === 'override' ? t('請完成此 Agent 的模型設定') : t('尚未設定全域預設')}</Text>}
      </div>
      <Form.Item hidden name="model"><Input /></Form.Item>
    </div>
  );
}

export function modelName(selection: ModelSelection, catalog: ModelCatalog | null | undefined) {
  return catalog?.providers.find((provider) => provider.id === selection.provider_id)?.models.find((model) => model.id === selection.model_id)?.name ?? selection.model_id;
}
