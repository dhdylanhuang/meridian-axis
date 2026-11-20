// Import this module only from trusted Worker code, not browser assets.
import module from './reconciliation_wasm/axis_reconciliation_bg.wasm';
import { createCashReconciler } from './cash_reconciliation_adapter.mjs';
let engine;
export function reconcileCashJSON(input) {
  engine ??= createCashReconciler(module);
  return engine(input);
}
