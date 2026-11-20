import assert from 'node:assert/strict';
import test from 'node:test';
import { gzipSync } from 'node:zlib';
import { heldClassifications } from '../src/portfolio_classification_catalog.mjs';

const zip = value => 'gzip:' + gzipSync(JSON.stringify(value)).toString('base64');

test('compressed and legacy bindings expose only the requested instruments to Rust', async () => {
  const catalog = await heldClassifications({
    PORTFOLIO_FUND_CLASSIFICATIONS: zip({HELD: {sector: {}}, FOREIGN: {sector: {}}}),
    PORTFOLIO_ISSUER_CLASSIFICATIONS: JSON.stringify({OTHER: {issuer_domicile: {}}}),
  }, [{isin:'HELD'},{isin:'OTHER'}]);
  assert.deepEqual({...catalog},{HELD:{sector:{}},OTHER:{issuer_domicile:{}}});
});

test('malformed or oversized compressed input preserves the other binding', async () => {
  for (const binding of ['gzip:broken',zip({HELD:'x'.repeat(132_000)})]) {
    const catalog = await heldClassifications({
      PORTFOLIO_FUND_CLASSIFICATIONS: binding,
      PORTFOLIO_ISSUER_CLASSIFICATIONS: zip({OTHER: {issuer_domicile: {}}}),
    }, [{isin:'HELD'},{isin:'OTHER'}]);
    assert.deepEqual({...catalog},{OTHER:{issuer_domicile:{}}});
  }
});
