// Import this module only from trusted Worker code, not browser assets.
import module from './reconciliation_wasm/axis_reconciliation_bg.wasm';
import { createCashReconciler } from './cash_reconciliation_adapter.mjs';
export const reconcileCashJSON = createCashReconciler(module);
