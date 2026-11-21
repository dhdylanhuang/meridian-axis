import { WorkerEntrypoint } from 'cloudflare:workers';
import { decodeReviewedBinding, heldClassifications } from './portfolio_classification_catalog.mjs';
import { observedPerformanceJSON, portfolioExposuresJSON, reconcileCashJSON } from './cash_reconciliation.mjs';
import { summarizeCashReport, summarizeActivityDetails } from './cash_reconciliation_summary.mjs';

// Named service entrypoint only: no fetch method and no public HTTP route.
export class CashReconciliation extends WorkerEntrypoint {
  async portfolioExposures(input) {
    if (typeof input !== 'string' || input.length > 512 * 1024 ||
        this.env.RECONCILIATION_ENVIRONMENT !== 'live') return portfolioExposuresJSON(input);
    try {
      const request = JSON.parse(input);
      request.classifications = await heldClassifications(this.env, request.positions);
      return portfolioExposuresJSON(JSON.stringify(request));
    } catch {
      return portfolioExposuresJSON(input);
    }
  }
  async observedPerformance(input) {
    if (this.env.RECONCILIATION_ENVIRONMENT !== 'live') throw new Error('performance_unavailable');
    if (this.env.VUAG_GBP_BENCHMARK || this.env.RISK_DAILY_GBP) {
      try {
        const request = JSON.parse(input);
        const risk = Boolean(request.risk_range);
        const supplied = risk ? this.env.RISK_DAILY_GBP : this.env.VUAG_GBP_BENCHMARK;
        if (typeof supplied === 'string' && supplied) {
          request[risk ? 'risk_daily' : 'benchmark'] = (await decodeReviewedBinding(supplied).catch(() => null)) ?? {};
          if (!risk) request.benchmark_as_of = new Date().toISOString();
          const enriched = JSON.stringify(request);
          if (new TextEncoder().encode(enriched).byteLength <= 128 * 1024) {
            return observedPerformanceJSON(enriched);
          }
        }
      } catch {
        // Optional inputs must leave observed performance available.
      }
    }
    return observedPerformanceJSON(input);
  }
  async cashActivityDetails(input) {
    return summarizeActivityDetails(reconcileCashJSON(input), this.env.RECONCILIATION_ENVIRONMENT);
  }
  async reconcileCash(input) {
    return summarizeCashReport(input, reconcileCashJSON(input), this.env.RECONCILIATION_ENVIRONMENT);
  }
}
