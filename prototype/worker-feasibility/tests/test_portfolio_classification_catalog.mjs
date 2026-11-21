import assert from 'node:assert/strict';
import test from 'node:test';
import { gzipSync } from 'node:zlib';
import { decodeDailyRisk, heldClassifications } from '../src/portfolio_classification_catalog.mjs';

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

test('reviewed risk concatenates bounded private binding parts and rejects gaps', async () => {
  const input = {sessions:[{date:'2000-01-03'}, {date:'2000-01-04'}]};
  const payload = zip(input).slice(5);
  const env = {RISK_DAILY_GBP:'gzip-parts:2',RISK_DAILY_GBP_01:payload.slice(0,17),
    RISK_DAILY_GBP_02:payload.slice(17)};
  assert.deepEqual(await decodeDailyRisk(env),input);
  assert.deepEqual(await decodeDailyRisk({RISK_DAILY_GBP:JSON.stringify(input)}),input);
  assert.equal(await decodeDailyRisk({...env,RISK_DAILY_GBP_02:undefined}),null);
  assert.equal(await decodeDailyRisk({...env,RISK_DAILY_GBP_02:'x'.repeat(5121)}),null);
});
