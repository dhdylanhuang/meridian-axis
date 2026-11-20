// Only this projection may cross back into snapshot publication. No raw evidence.
export async function summarizeCashReport(input, reportJSON, environment) {
  const report = JSON.parse(reportJSON);
  if (!['demo','live'].includes(environment) || report.scope?.account_id !== 'shared-isa' ||
      report.scope.environment !== environment || !report.broker_cash?.snapshot_id ||
      report.method !== 'cash_reconciliation_rust_v1') throw new Error('scope_mismatch');
  const review_counts = {};
  for (const row of report.records) {
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
    observation_count:report.records.reduce((n,row)=>n+row.evidence.length,0), review_counts,
    cash:report.cash.map(row=>({currency:row.currency,state:row.state,unexplained_difference:row.unexplained_difference})),
    warnings:report.warnings,
  });
}
