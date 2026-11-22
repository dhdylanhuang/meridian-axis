import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn, spawnSync } from 'node:child_process';
import { createCashReconciler, MAX_CASH_WASM_BYTES } from '../src/cash_reconciliation_adapter.mjs';
import { observed_performance_json } from '../src/reconciliation_wasm/axis_reconciliation.mjs';
import { syntheticCashRequest } from './fixtures/cash_wasm.mjs';

const prototype = fileURLToPath(new URL('..', import.meta.url));
const module = new WebAssembly.Module(fs.readFileSync(new URL('../src/reconciliation_wasm/axis_reconciliation_bg.wasm',import.meta.url)));
const reconcile = createCashReconciler(module);

test('generated WASM boundary matches the already-qualified native core exactly', {skip:!process.env.AXIS_RUST_TEST_BINARY}, () => {
  const input=JSON.stringify(syntheticCashRequest());
  const native=spawnSync(process.env.AXIS_RUST_TEST_BINARY,[],{input,encoding:'utf8',timeout:10_000});
  assert.equal(native.status,0);
  const expected=JSON.parse(native.stdout);
  assert.deepEqual(JSON.parse(reconcile(input)),expected);
  // Reuse the instance: no report/input retained by the adapter between calls.
  assert.deepEqual(JSON.parse(reconcile(input)),expected);
});

test('WASM validates input limits and failures safely, then accepts the next request', () => {
  assert.throws(()=>createCashReconciler(new Uint8Array()),/wasm_module_invalid/);
  assert.throws(()=>reconcile({}),/request_invalid/);
  assert.throws(()=>reconcile('sensitive-invalid-marker'),/^Error: request_invalid$/);
  assert.throws(()=>reconcile('λ'.repeat(MAX_CASH_WASM_BYTES / 2 + 1)),/input_size_limit/);
  const many=syntheticCashRequest();
  const small={...many.observations[0], reference:'x',source_id:'x',sign_basis:{state:'unverified'}};
  many.observations=Array(1025).fill(small);
  assert.ok(new TextEncoder().encode(JSON.stringify(many)).byteLength <= MAX_CASH_WASM_BYTES);
  assert.throws(()=>reconcile(JSON.stringify(many)),/wasm_observation_limit/);
  const foreign=syntheticCashRequest();
  foreign.observations[0].scope={account_id:'foreign',environment:'demo'};
  assert.throws(()=>reconcile(JSON.stringify(foreign)),/^Error: scope_mismatch$/);
  assert.equal(JSON.parse(reconcile(JSON.stringify(syntheticCashRequest()))).method,'cash_reconciliation_rust_v1');
});

test('Cloudflare local workerd executes the same precompiled WASM module', {timeout:45_000}, async () => {
  const child=spawn(process.execPath,[path.join(prototype,'node_modules/.bin/wrangler'),
    'dev','-c','wrangler.reconciliation-local.jsonc','--local','--ip','127.0.0.1','--port','8797',
    '--persist-to','/private/tmp/meridian-reconciliation-workerd',
  ],{cwd:prototype,detached:true,env:{...process.env,WRANGLER_SEND_METRICS:'false',WRANGLER_WRITE_LOGS:'false'},stdio:['ignore','pipe','pipe']});
  try {
    await new Promise((resolve,reject)=>{
      let logs='';
      const timeout=setTimeout(()=>reject(new Error('local_workerd_start_timeout')),30_000);
      const inspect=chunk=>{
        logs=(logs+chunk.toString()).slice(-8192);
        if (/Ready on http:\/\/127\.0\.0\.1:8797/.test(logs)) {clearTimeout(timeout);resolve();}
      };
      child.stdout.on('data',inspect);child.stderr.on('data',inspect);
      child.once('error',()=>{clearTimeout(timeout);reject(new Error('local_workerd_start_failed'));});
      child.once('exit',()=>{clearTimeout(timeout);reject(new Error('local_workerd_exited'));});
    });
    const response=await fetch('http://127.0.0.1:8797/qualify');
    assert.equal(response.status,200);
    assert.equal(response.headers.get('cache-control'),'no-store');
    assert.deepEqual(await response.json(),{method:'cash_reconciliation_rust_v1',exact_cash_match:true,revisions_counted_once:true,remains_provisional:true});
    const rpc=await fetch('http://127.0.0.1:8797/qualify-rpc');
    assert.equal(rpc.status,200);
    const summary=await rpc.json();
    assert.equal(summary.method,'cash_reconciliation_rust_v1');
    assert.equal(summary.event_count,2);
    assert.deepEqual(summary.activity_counts,{DEPOSIT:1,FEE:1});
    assert.equal(summary.observation_count,3);
    assert.equal(summary.input_revision.length,64);
    assert.equal(summary.source_snapshot_id,'synthetic-pending-snapshot');
    assert.equal('records' in summary,false);
    assert.equal('broker_cash' in summary,false);
    const detailsResponse=await fetch('http://127.0.0.1:8797/qualify-details');
    assert.equal(detailsResponse.status,200);
    const details=await detailsResponse.json();
    assert.equal(details.snapshot_id,'synthetic-pending-snapshot');
    assert.equal(details.details.total_count,1);
    assert.equal(details.details.entries[0].amount,'2.000000000000000000001');
    assert.equal(details.details.entries[0].revision_id,'revision-1');
    assert.equal('observations' in details,false);assert.equal('evidence' in details.details.entries[0],false);
    const exposure = await (await fetch('http://127.0.0.1:8797/qualify-exposures')).json();
    assert.equal(exposure.method,'broker_exposures_v1');
    assert.equal(exposure.quote_currencies[0].value,'30.00000000000000000001');
    assert.equal(exposure.holdings[0].portfolio_pct,'75');
    assert.equal(exposure.holdings[0].invested_pct,'100');
    assert.equal(exposure.cash_component_pct.availableToTrade,'25');
    assert.equal((await fetch('http://127.0.0.1:8797/qualify-foreign')).status,400);
    assert.equal((await fetch('http://127.0.0.1:8797/')).status,404);
  } finally {
    try {process.kill(-child.pid,'SIGTERM');} catch {}
    await new Promise(resolve=>{
      if (child.exitCode !== null) return resolve();
      const timeout=setTimeout(()=>{try {process.kill(-child.pid,'SIGKILL');} catch {} resolve();},3000);
      child.once('exit',()=>{clearTimeout(timeout);resolve();});
    });
  }
});

test('WASM exports observed performance through the existing module initialization', () => {
  const days = Array.from({length:90}, (_,index) => ({
    date:new Date(Date.UTC(2026,0,1+index)).toISOString().slice(0,10),status:'missing',
  }));
  for (const [index,amount] of [[88,'100'],[89,'123']]) Object.assign(days[index], {
    status:'observed',total_value:amount,captured_at:days[index].date+'T16:00:00Z',
  });
  const report = JSON.parse(observed_performance_json(JSON.stringify({
    days, coverage:{start_at:'2026-01-01T00:00:00Z',end_at:days[89].date+'T19:00:00Z',completed_at:days[89].date+'T20:00:00Z'},
    events:[{reference:'invented-flow',kind:'DEPOSIT',currency:'GBP',amount:'20',at:days[89].date+'T04:00:00Z'}],
  })));
  assert.equal(report.latest_eligible.return_pct, '2.727273');
  assert.equal(report.funding[0].amount, '20');
  assert.equal(report.intervals.length, 89);
  assert.equal(report.benchmark.state, 'awaiting_approved_series');
  const matched = JSON.parse(observed_performance_json(JSON.stringify({
    days, coverage:{start_at:'2026-01-01T00:00:00Z',end_at:days[89].date+'T19:00:00Z',completed_at:days[89].date+'T20:00:00Z'},
    events:[], benchmark_as_of:days[89].date+'T19:00:00Z',
    benchmark:{ticker:'VUAG',isin:'IE00BFMXXD54',currency:'GBP',basis:'split_adjusted_lse_market_close_accumulating',
      source:'Invented',reviewed_at:days[89].date+'T18:00:00Z',rows:days.slice(-2).map((day,i)=>({
        date:day.date,pricing_at:day.date+'T16:35:00Z',price_gbp:i ? '102':'100',
      }))},
  }))).benchmark;
  assert.equal(matched.matched_intervals, 1);
  assert.equal(matched.intervals[0].benchmark_pct, '2');
  assert.equal(matched.intervals[0].difference_pp, '21');
});

test('planning WASM reports both approved-snapshot paths and safe validation errors', async () => {
  const { portfolio_projection_json, portfolio_stress_json } = await import('../src/reconciliation_wasm/axis_reconciliation.mjs');
  const snapshot = {
    source:'trading212',basis:'broker_reported',currency:'GBP',total_value:'1000',
    account_retrieval:{retrieval_completed_at:'2029-04-30T22:00:00Z'},
    positions_retrieval:{retrieval_completed_at:'2029-04-30T22:00:01Z'},
    cash_components:{availableToTrade:'200'},
    positions:[{ticker:'SYNTH',account_currency:'GBP',instrument_type:'STOCK',quantity:'1',current_value:'800'}],
  };
  const run = (calculate, assumptions) => JSON.parse(calculate(JSON.stringify({snapshot, assumptions})));
  const deposit = {first_date:'2030-04-30',frequency:'once',amount:'100',unit:'gbp',
    allocations:[{kind:'holding',name:'SYNTH',share:'100',growth_pct:'10'}]};
  const plans = [{deposits:[]},{deposits:[deposit]}];
  const projection = run(portfolio_projection_json, {opening_growth_pct:'0',plans});
  assert.equal(projection.baseline.target_value, '1000');
  assert.equal(projection.plans[1].target_value, '1100');
  deposit.allocations[0].share = '50';
  assert.throws(() => run(portfolio_projection_json, {opening_growth_pct:'0',plans}), error => error === 'allocation_total_invalid');
  const stress = run(portfolio_stress_json, {scenarios: ['-10','-20'].map(price_shock_pct =>
    ({scope:'all',price_shock_pct,basket:[],overrides:[]}))});
  assert.equal(stress.known_cash, '200');
  assert.deepEqual(stress.scenarios.map(row => row.stressed_value), ['920','840']);
});
