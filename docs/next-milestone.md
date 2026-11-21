# Next delivery and closeout

Reviewed **21 November 2026**. Read the [handoff](status-and-handoff.md) first for
the deployed revisions, checks already run and open evidence gates.

## Delivered · Portfolio Changes

The signed-in dashboard compares the last approved observations on two UTC
dates. It exposes reported GBP changes, position flags, separate UTC capture
times, and dated holding drill-down for comparable allocations and top-five
concentration. See the [handoff](status-and-handoff.md#portfolio-changes-sprint)
for the deployed sources, focused checks and live evidence.

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
