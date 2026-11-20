import { WorkerEntrypoint } from 'cloudflare:workers';
import { reconcileCashJSON } from './cash_reconciliation.mjs';
import { summarizeCashReport } from './cash_reconciliation_summary.mjs';

// Named service entrypoint only: no fetch method and no public HTTP route.
export class CashReconciliation extends WorkerEntrypoint {
  async reconcileCash(input) {
    return summarizeCashReport(input, reconcileCashJSON(input), this.env.RECONCILIATION_ENVIRONMENT);
  }
}
