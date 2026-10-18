const placeholders = value => [...value.matchAll(/\{\{(\w+)\}\}/g)].map(match => match[1]).sort();

// Check authored translations without generating or changing their wording.
export function validateCatalog(source, catalog, label, { english = false } = {}) {
  if (!catalog || typeof catalog !== 'object' || Array.isArray(catalog)) {
    return [`${label}: expected a translation object`];
  }
  const errors = [];
  for (const key of Object.keys(source)) {
    if (!Object.hasOwn(catalog, key)) {
      errors.push(`${label}: missing translation: ${key}`);
      continue;
    }
    const value = catalog[key];
    if (typeof value !== 'string' || !value.trim()) {
      errors.push(`${label}: empty or non-string translation: ${key}`);
      continue;
    }
    if (english && /[\u3400-\u9fff]/u.test(value)) errors.push(`${label}: untranslated English: ${key}`);
    if (JSON.stringify(placeholders(key)) !== JSON.stringify(placeholders(value))) {
      errors.push(`${label}: interpolation mismatch: ${key}`);
    }
  }
  for (const key of Object.keys(catalog)) {
    if (!Object.hasOwn(source, key)) errors.push(`${label}: obsolete translation key: ${key}`);
  }
  return errors;
}
