# Next delivery: portfolio exposures and concentration in Rust

Reviewed **20 November 2026**. Owner DC26/DC27 supersedes reconciliation-first
ordering and the description of Rust as only a bounded experiment. This is the next
implementation brief; the present documentation task does not begin development.

## Owner direction

Cash-change explanation/reconciliation and holding-quantity reconciliation are
deferred because the owner considers them unnecessary for the dashboard. Use
Trading 212 reported cash, positions, prices and values as authoritative. Keep
existing ingestion/evidence, revision/duplicate safeguards and cash income/funding
totals with transaction drill-down. Orders continue to execute on Trading 212.
AXIS remains one integrated dashboard; tax remains deferred.

Use Rust as the default for new AXIS application/domain/analytics development going
forward. Existing Python ingestion/database/session and JavaScript UI/Worker glue
can remain where needed. This is not a request for a whole-app rewrite. Document
any necessary non-Rust exception and qualify its actual integration/runtime path.

## Next useful outcome

Show where the portfolio is invested and concentrated: holding weights, largest
positions, available sector/country/currency breakdowns and cash allocation. Use
dated broker-reported primary-currency values and an explicit compatible denominator;
never sum overlapping cash components or apply FX twice. Expose unclassified/missing
coverage rather than inventing classifications. Distinguish listing currency from
underlying economic currency exposure and ETF look-through. Pure Rust owns derived
calculations; approved projections supply sourced, dated exact values to the UI.
Choose a bounded, useful vertical slice from verified current inputs. Cash/quantity
reconciliation is not a prerequisite for these broker-reported exposure views.

## Following phases

1. Historical portfolio value/income trends and benchmark comparisons; calculated
   returns require verified flow/history inputs and methods despite reconciliation
   being deferred. Do not manufacture openings or gains from deposits.
2. Risk: drawdown, volatility, correlations and scenarios when daily price/FX and
   coverage meet calculation contracts.
3. Monitoring: concentration/exposure thresholds, material changes, stale-data
   warnings and supported upcoming-event alerts.

## Completed evidence and preservation

Cash drill-down works per owner confirmation. Gateway `5709f30`, session owner/sync
`94042f2`; current status owns focused tests, deployment and 14:10 publication proof.
Do not restart that validation. Full account-lifetime completeness remains unproven.
Schema `0008`, restricted roles/RLS, native migration authority, existing three
Workers/private Rust service, ten-minute refresh and sixty-day detailed retention
with daily/latest/history/import/audit preservation remain unchanged. Do not modify
or re-import the real workbook. No full suites/CI matrices/sizing/repeated live probes.
Operational capacity/query-use/recovery gates remain separately recorded in status.
