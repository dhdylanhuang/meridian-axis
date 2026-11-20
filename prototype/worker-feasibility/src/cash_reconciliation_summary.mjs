// Only this projection may cross back into snapshot publication. No raw evidence.
export async function summarizeCashReport(input, reportJSON, environment) {
  const report = JSON.parse(reportJSON);
  if (!['demo','live'].includes(environment) || report.scope?.account_id !== 'shared-isa' ||
      report.scope.environment !== environment || !report.broker_cash?.snapshot_id ||
      report.method !== 'cash_reconciliation_rust_v1') throw new Error('scope_mismatch');
  const review_counts = {}, activity_counts = {};
  const cashTypes = new Set(['DEPOSIT','WITHDRAW','FEE','TRANSFER','INTEREST_ON_FREE_CASH','LENDING_INTEREST']);
  for (const row of report.records) {
    const kind = cashTypes.has(row.provider_type) ? row.provider_type : 'OTHER';
    activity_counts[kind] = (activity_counts[kind] || 0) + 1;
    if (['unverified_sign_review','identity_conflict_review','unsupported_type_review'].includes(row.state)) {
      review_counts[row.state] = (review_counts[row.state] || 0) + 1;
    }
  }
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  const input_revision = [...new Uint8Array(bytes)].map(x=>x.toString(16).padStart(2,'0')).join('');
  return JSON.stringify({
    method:report.method, availability:report.records.length ? 'provisional' : 'insufficient_data',
    scope:report.scope, as_of:report.cutoff, source_snapshot_id:report.broker_cash.snapshot_id,
    input_revision, event_count:report.records.length,
    observation_count:report.records.reduce((n,row)=>n+row.evidence.length,0), review_counts, activity_counts,
    cash:report.cash.map(row=>({currency:row.currency,state:row.state,unexplained_difference:row.unexplained_difference,
      ...(row.opening?.basis === 'broker_available_to_trade' && row.closing ? {
        basis:row.opening.basis, opening_balance:row.opening.amount, closing_balance:row.closing.amount,
        opening_source_snapshot_id:row.opening.source_id, window_start:row.window_start, cutoff:row.cutoff,
        known_signed_movements:row.known_signed_movements, replayed_cash:row.replayed_cash,
        included_movement_count:row.included_movement_count, excluded_movement_count:row.excluded_movement_count,
      } : {})})),
    ...(report.cash_sign_policy ? {cash_sign_policy:report.cash_sign_policy} : {}),
    warnings:report.warnings,
  });
}
