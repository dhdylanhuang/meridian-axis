// Entirely synthetic, fixed qualification input. No broker or private source rows.
export function syntheticCashRequest() {
  const scope = { account_id: 'synthetic-isa', environment: 'demo' };
  const observation = {
    scope, reference: 'synthetic-deposit-λ', provider_type: 'DEPOSIT', currency: 'GBP', amount: '1',
    occurred_at: '2026-01-02T10:00:00Z', observed_at: '2026-01-03T00:00:00Z',
    source_id: 'synthetic-source', revision_id: null, revision: 0, digest: 'a'.repeat(64),
    sign_basis: { state: 'verified_signed_amount', evidence_id: 'synthetic-sign-evidence' },
  };
  const balance = (amount, at) => ({ scope, currency: 'GBP', amount, at,
    source_id: 'synthetic-statement', basis: 'statement_cash' });
  return {
    schema_version: 1, scope, cutoff: '2026-01-03T00:00:00Z',
    observations: [observation,
      {...observation, amount:'2.000000000000000000001', revision:1, revision_id:'revision-1', digest:'b'.repeat(64)},
      {...observation, reference:'synthetic-fee', provider_type:'FEE', amount:'-0.5'}],
    opening_cash: [balance('10','2026-01-01T00:00:00Z')],
    closing_cash: [balance('11.500000000000000000001','2026-01-03T00:00:00Z')], broker_cash:null,
  };
}
