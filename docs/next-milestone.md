# Next delivery and closeout

Reviewed **22 November 2026**. Read the [handoff](status-and-handoff.md) first for
the deployed revisions, checks already run and open evidence gates.

## Delivered · Portfolio Changes

The signed-in dashboard compares the last approved observations on two UTC
dates. It exposes reported GBP changes, position flags, separate UTC capture
times, and dated holding drill-down for comparable allocations and top-five
concentration. See the [handoff](status-and-handoff.md#portfolio-changes-sprint)
for the deployed sources, focused checks and live evidence.

## Phase 1 · Verify automatic capture

The signed-in Risk tab shows two verified ISA statement-cutoff returns and
the automatic broker capture schedule. It runs at **22:00 UTC** on London
trading days using the existing Trading 212 sync. The first ten dates,
**23 November to 4 December 2026**, remain the initial review window. The owner reported that the broker cannot supply
a bulk daily valuation export.

- **After 22:02 UTC on 23 November**, check one signed-in Risk read for the
  first outcome. Confirm either the broker-reported GBP value and actual UTC
  capture time, or the explicit missed-window state.
- **After the 4 December window closes at 22:02 UTC**, review the ten slots,
  capture times, missed windows and completed funding coverage. Check that
  captured values have a consistent reporting basis and that no return spans
  a missed slot or an interval with incomplete funding evidence.
- Collection continues beyond the first ten days. Fix demonstrated gaps or
  timing problems and review the valuation basis independently of capture
  success. Ten eligible valuations could support up to nine adjacent returns.
  Keep the statement series on its separate basis.

The launch verified the scheduled slots and the approved statement returns.
The first automatic capture is pending. [Pilot handoff](status-and-handoff.md#fixed-cutoff-broker-capture-pilot)

## Phase 2 · Extend ISA performance and qualify market data

The ongoing series automatically displays provisional cash-flow-adjusted
returns once adjacent captures and funding qualify. When the valuation basis
is reviewed and authorised, install the effective-dated approval policy
for automatic publication as approved ISA returns.
Statistical risk needs at least **60 comparable eligible returns per
estimate**. A fully contiguous series needs 61 valuations. Preserve coverage
and return gaps. Continue the existing observed comparison and drawdown
within their available coverage. Use the
[reviewed input contract](api-and-ui.md#risk-tab) and
[calculation rules](calculation-contracts.md#risk-tab-coverage).

VUAG comparison and holding correlation have separate source requirements.
Qualify permitted GBP total-return levels, listing identity, FX convention,
split and dividend treatment, and timing on the reviewed calendar. Verify
each statistical measure on its own sample, using dated Bank Rate for
rate-dependent measures. The full correlation matrix and rolling views
remain in the [correlation roadmap](correlation.md#views).

## Phase 3 · Finish dashboard and operational acceptance

The remaining roadmap includes portfolio projections, stress scenarios and
remaining views. Verify a live sector and country comparison once two dates
have compatible saved classifications. Maintain dated classification sources
for new holdings and focus first on the largest uncovered fund exposures.
Complete the outstanding backup and restore checks. See the
[development stages](development-stages.md).

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
