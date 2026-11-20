import { WorkerEntrypoint } from 'cloudflare:workers';
import { portfolioExposuresJSON, reconcileCashJSON } from './cash_reconciliation.mjs';
import { summarizeCashReport, summarizeActivityDetails } from './cash_reconciliation_summary.mjs';

// Named service entrypoint only: no fetch method and no public HTTP route.
export class CashReconciliation extends WorkerEntrypoint {
  async portfolioExposures(input) {
    if (typeof input !== 'string' || input.length > 512 * 1024 ||
        this.env.RECONCILIATION_ENVIRONMENT !== 'live') return portfolioExposuresJSON(input);
    const catalogs = [this.env.PORTFOLIO_FUND_CLASSIFICATIONS, this.env.PORTFOLIO_ISSUER_CLASSIFICATIONS];
    const classifications = Object.create(null);
    for (const catalog of catalogs) {
      if (!catalog || catalog.length > 5_120) continue;
      try { Object.assign(classifications, JSON.parse(catalog)); } catch {}
    }
    try {
      const request = JSON.parse(input);
      request.classifications = classifications;
      return portfolioExposuresJSON(JSON.stringify(request));
    } catch {
      return portfolioExposuresJSON(input);
    }
  }
  async cashActivityDetails(input) {
    return summarizeActivityDetails(reconcileCashJSON(input), this.env.RECONCILIATION_ENVIRONMENT);
  }
  async reconcileCash(input) {
    return summarizeCashReport(input, reconcileCashJSON(input), this.env.RECONCILIATION_ENVIRONMENT);
  }
}
