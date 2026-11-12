import assert from 'node:assert/strict';
import test from 'node:test';
import {
  PREVIEW_NOTICE,
  groups,
  histories,
  holdings,
  snapshot,
} from '../src/demo.js';

function hundredths(value) {
  assert.equal(typeof value, 'string', 'Exact fixture values must remain decimal strings');
  const match = /^([0-9]+)(?:\.([0-9]{1,2}))?$/.exec(value);
  assert.ok(match, 'Expected a nonnegative decimal string with at most two decimal places');
  return BigInt(match[1]) * 100n + BigInt((match[2] ?? '').padEnd(2, '0'));
}

function signedHundredths(value) {
  assert.equal(typeof value, 'string');
  return value.startsWith('-') ? -hundredths(value.slice(1)) : hundredths(value);
}

const sum = (values) => values.reduce((total, value) => total + value, 0n);

test('the preview identifies invented GBP data and its fixed synthetic observation date', () => {
  assert.equal(PREVIEW_NOTICE, 'DEMO PREVIEW · Invented data · Not connected to your account');
  assert.equal(snapshot.environment, 'demo');
  assert.equal(snapshot.source, 'invented');
  assert.equal(snapshot.currency, 'GBP');
  assert.equal(snapshot.asOf, '2026-10-31');
  assert.equal(snapshot.nav, '40000.00');
  assert.equal(snapshot.holdingsValue, '38600.00');
  assert.equal(snapshot.cash, '1400.00');
});

test('holdings and cash reconcile to the displayed portfolio value exactly', () => {
  assert.equal(holdings.length, 8);
  assert.equal(new Set(holdings.map(({ ticker }) => ticker)).size, holdings.length);
  const invested = sum(holdings.map(({ value }) => hundredths(value)));
  assert.equal(invested, hundredths(snapshot.holdingsValue));
  assert.equal(invested + hundredths(snapshot.cash), hundredths(snapshot.nav));
});

test('each group includes all its holdings without overlap and reconciles to GBP totals', () => {
  assert.equal(groups.length, 3);
  assert.deepEqual(groups.map(({ name, value }) => [name, hundredths(value)]).sort(), [
    ['Core', 1660000n], ['Defensive', 430000n], ['Growth', 1770000n],
  ]);
  const groupNames = new Set(groups.map(({ name }) => name));
  assert.equal(groupNames.size, groups.length);
  assert.ok(holdings.every(({ group }) => groupNames.has(group)));
  for (const group of groups) {
    const members = holdings.filter((holding) => holding.group === group.name);
    assert.ok(members.length > 0);
    assert.equal(sum(members.map(({ value }) => hundredths(value))), hundredths(group.value));
  }
  assert.equal(sum(groups.map(({ value }) => hundredths(value))), hundredths(snapshot.holdingsValue));
});

test('holding and group weights use total NAV including cash', () => {
  const nav = hundredths(snapshot.nav);
  for (const entry of [...holdings, ...groups]) {
    const roundedWeight = (hundredths(entry.value) * 10000n + nav / 2n) / nav;
    assert.equal(hundredths(entry.weight), roundedWeight, entry.ticker ?? entry.name);
  }
});

test('invented daily holding changes reconcile to the portfolio change', () => {
  assert.equal(snapshot.dayChange, '184.00');
  assert.equal(snapshot.dayChangePercent, '0.46');
  assert.equal(sum(holdings.map(({ dayChange }) => signedHundredths(dayChange))), 18400n);
});

test('every selectable history has aligned finite samples and ends at the synthetic NAV', () => {
  assert.deepEqual(Object.keys(histories).sort(), ['1M', '3M', 'All']);
  for (const history of Object.values(histories)) {
    assert.ok(history.labels.length >= 2);
    assert.equal(history.labels.length, history.values.length);
    assert.ok(history.labels.every((label) => typeof label === 'string' && label.length > 0));
    assert.ok(history.values.every((value) => typeof value === 'number' && Number.isFinite(value) && value >= 0));
    assert.equal(history.values.at(-1), 40000);
  }
});
