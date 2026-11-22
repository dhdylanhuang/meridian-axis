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

The reviewed-session software path accepts dated GBP NAV and benchmark marks,
calculates external-flow-adjusted ISA session returns, and reports statistical
risk and ranked holding pairs when their respective samples qualify. To activate
this path with real data, complete the source review and supply the private
manifest in the [daily risk input contract](api-and-ui.md#risk-tab).

Qualify a portfolio GBP total-return series with comparable session valuations,
timed external funding evidence and UTC endpoints. For benchmark-relative
statistics, line it up with a permitted GBP VUAG total-return series on the
same reviewed session calendar. Check split and dividend treatment and use
dated Bank Rate for rate-dependent measures. Load only approved source rows
in the [daily risk input contract](api-and-ui.md#risk-tab).

The signed-in Risk tab shows two verified ISA statement-cutoff returns.
The owner reported that Trading 212 support cannot supply a bulk daily
account-value series. A bounded recent timing audit found one of ten
weekdays within ten minutes of the 21:59 UTC statement cutoff and zero
captures during the cutoff minute. Existing polling is unsuitable for
reliable fixed-cutoff capture. The pilot targets one provisional
account observation at 22:00 UTC on each of ten reviewed weekdays, 23
November through 4 December 2026. The existing sync tick supplies the capture.
The Risk tab reports actual capture times, missed windows, and funding coverage.
The hosted Risk tab showed all ten slots scheduled. Check the first
completed capture and review the series before using it for statistical risk.

The ISA sample needs 58 more eligible returns for statistical risk. VUAG
and holding correlation require separately qualified total-return data.
The existing broker observations continue to support the observed comparison
and drawdown within their coverage. See the
[calculation rules](calculation-contracts.md#risk-tab-coverage).

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
