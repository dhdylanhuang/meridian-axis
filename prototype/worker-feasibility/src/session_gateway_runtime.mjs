import { decodeDailyRisk } from './portfolio_classification_catalog.mjs';
import gateway from './session_gateway.mjs';
import { portfolioChangesJSON, portfolioMeridianJSON, portfolioProjectionJSON, portfolioSectorRollupJSON, portfolioStressJSON, reconcileCashJSON } from './cash_reconciliation.mjs';
export { CashReconciliation } from './cash_reconciliation_rpc.mjs';

export default {
  scheduled: gateway.scheduled,
  async fetch(request, env) {
    const response = await gateway.fetch(request, env, portfolioChangesJSON, {
      meridian: async (snapshot, options) => {
        const reviewed = await decodeDailyRisk(env).catch(() => ({}));
        return portfolioMeridianJSON(JSON.stringify({
          snapshot, reviewed, now: new Date().toISOString(), ...options,
        }));
      },
      projections: portfolioProjectionJSON,
      sectorRollup: portfolioSectorRollupJSON,
      "stress-tests": portfolioStressJSON,
    });
    if (new URL(request.url).pathname !== '/health' || !response.ok) return response;
    // Fixed operational self-check only. No caller data, database or real portfolio.
    let ready = false;
    try {
      const report = JSON.parse(reconcileCashJSON(JSON.stringify({
        schema_version:1, scope:{account_id:'synthetic-health',environment:'demo'},
        cutoff:'2000-01-01T00:00:00Z', observations:[], opening_cash:[], closing_cash:[],broker_cash:null,
      })));
      ready = report.method === 'cash_reconciliation_rust_v1';
    } catch {}
    const headers = new Headers(response.headers);
    headers.set('X-Meridian-Reconciliation', ready ? 'rust-wasm-ready' : 'unavailable');
    return new Response(response.body,{status:response.status,headers});
  },
};
