// Import this module only from trusted Worker code, not browser assets.
import { portfolio_exposures_json } from './reconciliation_wasm/axis_reconciliation.mjs';
import module from './reconciliation_wasm/axis_reconciliation_bg.wasm';
import { createCashReconciler } from './cash_reconciliation_adapter.mjs';
let engine;
export function reconcileCashJSON(input) {
  engine ??= createCashReconciler(module);
  return engine(input);
}

export function portfolioExposuresJSON(input) {
  engine ??= createCashReconciler(module);
  if (typeof input !== 'string') throw new Error('request_invalid');
  try { return portfolio_exposures_json(input); }
  catch { throw new Error('exposures_unavailable'); }
}
