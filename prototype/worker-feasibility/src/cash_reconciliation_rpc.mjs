import { WorkerEntrypoint } from 'cloudflare:workers';
import { heldClassifications } from './portfolio_classification_catalog.mjs';
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
    return observedPerformanceJSON(input);
  }
  async cashActivityDetails(input) {
    return summarizeActivityDetails(reconcileCashJSON(input), this.env.RECONCILIATION_ENVIRONMENT);
  }
  async reconcileCash(input) {
    return summarizeCashReport(input, reconcileCashJSON(input), this.env.RECONCILIATION_ENVIRONMENT);
  }
}
