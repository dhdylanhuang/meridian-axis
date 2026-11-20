// Private compute adapter: strings in/out; no database, requests or financial cache.
import { initSync, reconcile_cash_json } from './reconciliation_wasm/axis_reconciliation.mjs';

export const MAX_CASH_WASM_BYTES = 512 * 1024;
const SAFE_ERRORS = new Set([
  'input_size_limit', 'request_invalid', 'wasm_observation_limit', 'identity_invalid',
  'currency_invalid', 'timestamp_invalid', 'decimal_invalid', 'decimal_precision_limit',
  'balance_cutoff_invalid', 'duplicate_balance', 'schema_version_invalid',
  'observation_limit', 'scope_mismatch', 'broker_cutoff_invalid', 'digest_invalid',
  'currency_limit', 'cash_control_basis_mismatch', 'output_failed',
]);

export function createCashReconciler(module) {
  // Workers imports .wasm as a precompiled Module; never compile caller bytes.
  if (!(module instanceof WebAssembly.Module)) throw new Error('wasm_module_invalid');
  initSync({ module });
  return input => {
    if (typeof input !== 'string') throw new Error('request_invalid');
    if (new TextEncoder().encode(input).byteLength > MAX_CASH_WASM_BYTES) {
      throw new Error('input_size_limit');
    }
    try { return reconcile_cash_json(input); }
    catch (error) {
      throw new Error(typeof error === 'string' && SAFE_ERRORS.has(error)
        ? error : 'reconciliation_unavailable');
    }
  };
}
