// Reviewed inputs are private Worker bindings. The JSON format remains valid
// so data and code can be rolled forward or back independently.
const BINDING_LIMIT = 5_120;
const CATALOG_LIMIT = 128 * 1024;

export async function decodeReviewedBinding(value) {
  if (typeof value !== 'string' || !value || value.length > BINDING_LIMIT) return null;
  if (!value.startsWith('gzip:')) return JSON.parse(value);
  const bytes = Uint8Array.from(atob(value.slice(5)), character => character.charCodeAt(0));
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  const reader = stream.getReader();
  const decoder = new TextDecoder('utf-8', {fatal: true});
  let size = 0;
  let json = '';
  try {
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      size += value.length;
      if (size > CATALOG_LIMIT) return null;
      json += decoder.decode(value, {stream: true});
    }
    return JSON.parse(json + decoder.decode());
  } finally {
    await reader.cancel().catch(() => {});
  }
}

export async function heldClassifications(env, positions) {
  const keys = new Set(positions.map(row => row.isin));
  const selected = Object.create(null);
  for (const binding of [env.PORTFOLIO_FUND_CLASSIFICATIONS, env.PORTFOLIO_ISSUER_CLASSIFICATIONS]) {
    try {
      const catalog = await decodeReviewedBinding(binding);
      if (!catalog || Array.isArray(catalog) || typeof catalog !== 'object') continue;
      for (const isin of keys) {
        if (Object.hasOwn(catalog, isin)) selected[isin] = catalog[isin];
      }
    } catch {
      // An invalid binding must not prevent the other dimension from loading.
    }
  }
  return selected;
}
