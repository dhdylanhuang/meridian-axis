# Current delivery and next priorities

Reviewed **20 November 2026**. See [current status](status-and-handoff.md) for
the portfolio exposure release and actual publication evidence. Reuse completed
focused tests. If a release gate remains open, close that gate before extending
the feature.

## Current priority

Maintain the reviewed classification catalogue for new positions and updated
manager documents. Prioritise remaining partial fund weights by invested value,
and keep their published basis and residual visible. Use verified instrument IDs
and the existing authenticated snapshot. The expanded private input can use the
bounded gzip binding format, with no paid provider or polling change.

## Observed account history

History shows the last retained Trading 212 snapshot for each of 90 UTC days,
with exact GBP values, capture times and explicit gaps. Today is in progress.
The cash, income and funding totals and their transaction drill-down remain
accessible in the same workspace. Live publication has been verified. See
[the history contract](api-and-ui.md#observed-account-history).

## Observed funding and performance

History marks dated Trading 212 deposits and withdrawals and opens their
transaction evidence. It reports the longest eligible valuation stretch and
the reasons an interval is unavailable. Eligible intervals get a labelled
Modified Dietz approximation. MTD and YTD link eligible valuations from the
relevant period boundary. See [the calculation method](calculation-contracts.md#observed-modified-dietz).

## Following delivery

Qualify a permitted VUAG GBP close series for the implemented daily comparison.
Verify source permission for both members, exact price units, timestamp and split
treatment before supplying the private binding. Longer comparisons require a
supported portfolio period and matching benchmark endpoints. See the
[calculation contracts](calculation-contracts.md#vuag-gbp-benchmark-proxy).

Keep the private, dated classification catalogue current for new and existing
holdings. Expand remaining coverage by invested value first. Manager fund
breakdowns provide sector and market estimates. Constituent overlap and
underlying economic currency need separate source coverage.

Subsequent phases cover risk from eligible daily price/FX series, then exposure
thresholds, material changes and supported alerts. Cash-change and holding-quantity
reconciliation remain deferred and are not gates for observed-value work. Tax
remains deferred. Prefer Rust for new logic and retain existing integration.

Preserve Trading 212 authority, existing cash totals and drill-down, the shared
two-member dashboard and three Workers, schema 0008 with native migration
authority, ten-minute refresh and sixty-day detailed retention. Daily and latest
snapshots, transaction/import/audit history and the private workbook stay intact.
