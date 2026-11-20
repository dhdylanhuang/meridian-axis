# Next delivery: historical portfolio observations and eligible performance

Reviewed **20 November 2026**. See [current status](status-and-handoff.md) for
the portfolio exposure release and actual publication evidence. Reuse completed
focused tests. If a release gate remains open, close that gate before extending
the feature.

## Next outcome

Show historical portfolio value and income from eligible retained observations,
with dates, source coverage and sampling gaps. Qualify benchmarks and calculated
returns only where the inputs and methods in the
[calculation contracts](calculation-contracts.md) support them. Daily retained
broker snapshots are observed marks. Approved exchange closes, verified
cash-flow inputs and benchmark series require their own evidence. Flag any
additional provider work, infrastructure or cost before expanding scope.

Sector and country exposures require dated issuer classifications keyed by a
verified identifier, a sector taxonomy and a defined country basis. Underlying
fund exposure requires dated constituent positions and weights. Do not derive
these labels from the listing exchange or trading currency.

Subsequent phases cover risk from eligible daily price/FX series, then exposure
thresholds, material changes and supported alerts. Cash-change and holding-quantity
reconciliation remain deferred and are not gates for observed-value work. Tax
remains deferred. Prefer Rust for new logic and retain existing integration.

Preserve Trading 212 authority, existing cash totals and drill-down, the shared
two-member dashboard and three Workers, schema 0008 with native migration
authority, ten-minute refresh and sixty-day detailed retention. Daily and latest
snapshots, transaction/import/audit history and the private workbook stay intact.
