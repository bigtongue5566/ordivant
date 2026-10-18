import type { Project } from '../../types';
import { createProductApi, productApiPrefix } from './productApi';

export type CompanionProduct = 'knowledge' | 'code';
export type CompanionResource = { id: string; key: string; name: string };
export type CompanionResult = { resource?: CompanionResource; error?: string };
export type CompanionResults = Partial<Record<CompanionProduct, CompanionResult>>;

const clients = {
  knowledge: createProductApi(productApiPrefix('knowledge')),
  code: createProductApi(productApiPrefix('code')),
};

export function companionKey(project: Pick<Project, 'key'>, product: CompanionProduct): string {
  return product === 'code' ? project.key.toLowerCase().replaceAll('_', '-') : project.key;
}

export async function createProjectCompanions(
  project: Project,
  selected: CompanionProduct[],
  previous: CompanionResults,
): Promise<CompanionResults> {
  const results = { ...previous };
  await Promise.all(selected.map(async product => {
    if (previous[product]?.resource) return;
    try {
      const resource = await clients[product].post<CompanionResource>(
        product === 'knowledge' ? '/spaces' : '/projects',
        { key: companionKey(project, product), name: project.name, description: project.description },
        { idempotencyKey: `work-project:${project.id}:${product}`, signal: AbortSignal.timeout(20000) },
      );
      // A proxy returning HTML must never be reported as a created project.
      if (!resource || typeof resource.id !== 'string' || typeof resource.key !== 'string' || typeof resource.name !== 'string') {
        throw new Error('產品服務回傳無效的建立結果，請確認服務設定後重試。');
      }
      results[product] = { resource };
    } catch (error) {
      results[product] = { error: error instanceof Error && 'status' in error && error.status === 409
        ? '此產品已有相同代碼，或建立操作發生衝突。請先確認既有項目。'
        : error instanceof Error && 'sourceMessage' in error
        ? String(error.sourceMessage)
        : error instanceof Error ? error.message : '發生未預期的錯誤。' };
    }
  }));
  return results;
}
