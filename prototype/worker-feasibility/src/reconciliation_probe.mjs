// LOCAL ONLY: fixed invented fixture, no caller JSON, secrets, bindings or DB.
import { reconcileCashJSON } from './cash_reconciliation.mjs';
export { CashReconciliation } from './cash_reconciliation_rpc.mjs';
import { syntheticCashRequest } from '../tests/fixtures/cash_wasm.mjs';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!['localhost','127.0.0.1'].includes(url.hostname) || !['/qualify','/qualify-rpc','/qualify-foreign','/qualify-details','/qualify-exposures'].includes(url.pathname)) {
      return new Response('Not found', {status:404});
    }
    if (request.method !== 'GET') return new Response('Method not allowed', {status:405});
    if (url.pathname === '/qualify-exposures') {
      const date = '2026-01-02T13:00:00Z';
      const input = {snapshot_id:'synthetic-exposures',account_as_of:date,positions_as_of:date,
        currency:'GBP',portfolio_value:'40',invested_value:'30',cash_components:{availableToTrade:'10'},
        positions:[{ticker:'ABC',current_value:'30.00000000000000000001',account_currency:'GBP',quote_currency:'USD'}]};
      return new Response(await env.RECONCILIATION.portfolioExposures(JSON.stringify(input)),
        {headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
    }
    if (url.pathname !== '/qualify') {
      const input = syntheticCashRequest();
      const scope = {account_id:url.pathname === '/qualify-foreign' ? 'foreign' : 'shared-isa',environment:'demo'};
      input.scope=scope;
      for (const row of [...input.observations,...input.opening_cash,...input.closing_cash]) row.scope=scope;
      input.broker_cash={currency:'GBP',available_to_trade:null,in_pies:null,reserved_for_orders:null,at:input.cutoff,snapshot_id:'synthetic-pending-snapshot'};
      try {
        if(url.pathname === '/qualify-details') {
          input.activity_since='2026-01-01T00:00:00Z';
          input.detail_query={category:'deposits',currency:'GBP',offset:0,limit:20};
          return new Response(await env.RECONCILIATION.cashActivityDetails(JSON.stringify(input)),{headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
        }
        const summary=await env.RECONCILIATION.reconcileCash(JSON.stringify(input));
        return new Response(summary,{headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
      } catch {return Response.json({error:'rpc_rejected'},{status:400});}
    }
    const report = JSON.parse(reconcileCashJSON(JSON.stringify(syntheticCashRequest())));
    return Response.json({
      method:report.method,
      exact_cash_match:report.cash[0].unexplained_difference === '0',
      revisions_counted_once:report.records.length === 2 && report.records[0].evidence.length === 2,
      remains_provisional:report.availability === 'provisional',
    }, {headers:{'Cache-Control':'no-store'}});
  },
};
