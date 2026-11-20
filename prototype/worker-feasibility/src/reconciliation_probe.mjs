// LOCAL ONLY: fixed invented fixture, no caller JSON, secrets, bindings or DB.
import { reconcileCashJSON } from './cash_reconciliation.mjs';
import { syntheticCashRequest } from '../tests/fixtures/cash_wasm.mjs';

export default {
  fetch(request) {
    const url = new URL(request.url);
    if (!['localhost','127.0.0.1'].includes(url.hostname) || url.pathname !== '/qualify') {
      return new Response('Not found', {status:404});
    }
    if (request.method !== 'GET') return new Response('Method not allowed', {status:405});
    const report = JSON.parse(reconcileCashJSON(JSON.stringify(syntheticCashRequest())));
    return Response.json({
      method:report.method,
      exact_cash_match:report.cash[0].unexplained_difference === '0',
      revisions_counted_once:report.records.length === 2 && report.records[0].evidence.length === 2,
      remains_provisional:report.availability === 'provisional',
    }, {headers:{'Cache-Control':'no-store'}});
  },
};
