import gateway from './session_gateway.mjs';
import { portfolioChangesJSON, portfolioMeridianJSON, portfolioProjectionJSON, portfolioSectorRollupJSON, portfolioStressJSON, reconcileCashJSON } from './cash_reconciliation.mjs';
export { CashReconciliation } from './cash_reconciliation_rpc.mjs';

export default {
  scheduled: gateway.scheduled,
  async fetch(request, env) {
    const response = await gateway.fetch(request, env, portfolioChangesJSON, {
      exportConfig: env.AXIS_EXPORT_CONFIG,
      exportEvidence: async inputs => {
        const start = inputs.changes.start.account_captured_at;
        const end = inputs.changes.end.account_captured_at;
        const weekly = Object.fromEntries((inputs.weekly ?? [])
          .filter(row => row.status === "observed").map(row => [row.date, row.account_captured_at]));
        const service = env.SYNC.get(env.SYNC.idFromName("shared-isa"));
        const reply = await service.fetch(new Request("https://sync.internal/export-evidence", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ start: start < end ? start : null, end, weekly,
            turnover_open: inputs.turnover_open, securities_gbp: inputs.changes.end.invested_value }),
        }));
        return reply.ok ? reply.json() : null;
      },
      meridian: async (snapshot, options) => {
        const holdings = Object.fromEntries(snapshot.positions
          .filter(row => typeof row.isin === 'string' && /^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(row.isin))
          .map(row => [row.ticker, row.isin]));
        const id = env.SYNC.idFromName("shared-isa");
        const reply = await env.SYNC.get(id).fetch(new Request("https://sync.internal/cutoff-holdings", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ holdings }),
        }));
        const broker_cutoff = reply.ok ? await reply.json() : {};
        return portfolioMeridianJSON(JSON.stringify({
          snapshot, broker_cutoff, now: new Date().toISOString(), ...options,
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
