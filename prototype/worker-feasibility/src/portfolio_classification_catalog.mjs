// Reviewed inputs are private Worker bindings. The JSON format remains valid
// so data and code can be rolled forward or back independently.
const BINDING_LIMIT = 5_120;
const CATALOG_LIMIT = 128 * 1024;

export async function decodeReviewedBinding(value) {
  if (typeof value !== 'string' || !value || value.length > BINDING_LIMIT) return null;
  if (!value.startsWith('gzip:')) return JSON.parse(value);
  return decodeGzipJson(value.slice(5), CATALOG_LIMIT);
}

async function decodeGzipJson(base64, limit) {
  const bytes = Uint8Array.from(atob(base64), character => character.charCodeAt(0));
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
      if (size > limit) return null;
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

// A reviewed 252-session held-listing panel can exceed one Cloudflare binding.
// Parts are consecutive slices of a single base64 gzip stream.
export async function decodeDailyRisk(env) {
  const value = env.RISK_DAILY_GBP;
  if (typeof value !== 'string' || !value.startsWith('gzip-parts:')) {
    return decodeReviewedBinding(value);
  }
  const match = /^gzip-parts:([1-9]|1[0-9]|2[0-4])$/.exec(value);
  if (!match) return null;
  const parts = [];
  for (let i = 1; i <= Number(match[1]); i++) {
    const part = env['RISK_DAILY_GBP_' + String(i).padStart(2, '0')];
    if (typeof part !== 'string' || !part.length || part.length > BINDING_LIMIT) return null;
    parts.push(part);
  }
  return decodeGzipJson(parts.join(''), 512 * 1024);
}
