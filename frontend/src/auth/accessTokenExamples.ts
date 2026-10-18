import type { ProductKey } from './types';

const products = {
  work: { directory: 'backend', module: 'ordivant', url: 'ORDIVANT_API_URL', token: 'ORDIVANT_API_TOKEN' },
  knowledge: { directory: 'products/knowledge/backend', module: 'ordivant_knowledge', url: 'ORDIVANT_KNOWLEDGE_API_URL', token: 'ORDIVANT_KNOWLEDGE_API_TOKEN' },
  code: { directory: 'products/code/backend', module: 'ordivant_code', url: 'ORDIVANT_CODE_API_URL', token: 'ORDIVANT_CODE_API_TOKEN' },
};

/** Examples always use a placeholder. A one-time credential never enters copied configuration. */
export function accessTokenExamples(product: ProductKey, apiUrl: string) {
  const config = products[product];
  const base = apiUrl.replace(/\/$/, '');
  return {
    api: `curl "${base}/me" -H "Authorization: Bearer <PERSONAL_ACCESS_TOKEN>"`,
    mcp: JSON.stringify({ mcpServers: {
      [`ordivant-${product}`]: {
        command: 'uv',
        args: ['run', '--project', `<ORDIVANT_REPO>/${config.directory}`, 'python', '-m', `${config.module}.mcp_server`],
        env: { [config.url]: base, [config.token]: '<PERSONAL_ACCESS_TOKEN>' },
      },
    } }, null, 2),
  };
}
