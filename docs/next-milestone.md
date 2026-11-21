# Next delivery and closeout

Reviewed **21 November 2026**. Read the [handoff](status-and-handoff.md) first for
the deployed revisions, checks already run and open evidence gates.

## Next build · Explain portfolio changes

When the owner starts the next implementation, add an observed changes view
using two selected approved Trading 212 snapshots. Start with one comparable
interval and keep the snapshot capture times visible.

- Rank changes in reported holding value in GBP. Show beginning and ending
  values, quantities and portfolio weights, alongside the observed changes.
- Flag holdings added or closed and rows with quantity changes. Where quantity
  is stable and comparable, label the reported value change with its basis.
  The price, FX and trading components need their own evidence.
- Show material changes in sector, country and cash weights with their
  denominators and classification coverage. Link each change to its holdings.
- Verify the calculation against the saved endpoints. Record a focused
  synthetic check for missing data and changed quantities, plus a bounded
  live check of the approved result.

## Risk evidence gate

Qualify a portfolio GBP total-return series with comparable session valuations,
timed external funding evidence and UTC endpoints. For benchmark-relative
statistics, line it up with a permitted GBP VUAG total-return series on the
same reviewed session calendar. Check split and dividend treatment and use
dated Bank Rate for rate-dependent measures. Load only approved source rows
in the [daily risk input contract](api-and-ui.md#risk-tab).

The audit found no approved daily return intervals to backfill. The minimum
is 60 eligible sessions per statistical estimate. Existing broker marks
support the observed benchmark comparison and drawdown within their own
coverage. Reuse the audited evidence until a new input becomes available.
See the [calculation rules](calculation-contracts.md#risk-tab-coverage).

Maintain sourced classifications for new holdings. Prioritise fund coverage
gaps by invested value and preserve source date, basis and unallocated weight.

## Project closeout · Monitoring and alerts

The owner deferred new monitoring and alerts to closeout under
[DC28](decisions-and-questions.md#confirmed-decisions). Revisit event
rules, configurable weight limits, staleness and the existing two-trading-day
portfolio drawdown threshold after the core dashboard work and its data gates
have been reviewed. Use the eligibility and re-arming rules in the
[alert specification](alerts.md). Delivery outside the application requires
separate authorization.

## Operating constraints

Use Trading 212 reported prices, cash and positions for the observed dashboard.
Use Rust for new analytics and retain the existing Python/JavaScript service
boundaries. Preserve the two-member session scope, three Workers, schema
`0008`, ten-minute refresh, sixty-day detailed retention and retained daily
anchors. Keep exact records and release receipts private. Cash-change and
holding-quantity reconciliation and tax are deferred.
