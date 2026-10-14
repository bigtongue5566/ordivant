// Ephemeral, origin-local credentials. Never persist Agent bearer tokens in browser storage.
const credentials = new Map<string, string>();
export function setProductCredential(prefix: string, token: string | null) {
  if (token) credentials.set(prefix, token); else credentials.delete(prefix);
}
export function getProductCredential(prefix: string): string | null { return credentials.get(prefix) || null; }
