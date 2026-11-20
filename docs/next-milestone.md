# Next delivery: integrate the Rust reconciliation core

Reviewed **20 November 2026**. The owner selected Rust for reconciliation, keeping
Python broker ingestion and database access. The first pure native cash slice is
implemented; [current status](status-and-handoff.md) owns exact passing checks.

## Completed boundary

`rust/reconciliation` supplies typed account/environment, source/revision identity,
exact cash amounts, verified/unverified sign basis, explicit controls and review
states. It selects one effective cash-reference revision, preserves all evidence,
and compares supported per-currency roll-forwards without inventing openings.
The Python read-only bridge exports accepted cash captures/completed revisions.
It never asserts unknown signs or turns broker cash components into a ledger total.
Seven Rust and four Python tests passed, including the compiled native boundary.
Reuse those results for unchanged code. [Contract/run guide](../rust/reconciliation/README.md).

## Next bounded work

Qualify the Rust core's WASM packaging/call boundary within the existing application
before production integration. Preserve Python ingestion/persistence and the one
broker snapshot authority; no second sync engine, database grant or general-purpose
execution endpoint. Publish approved derived summaries, not raw evidence, to the
private dashboard. Keep verification bounded and record the result, input revision,
coverage and remaining limitations.

Actual cash economics separately require evidence for signed amounts and comparable
opening/closing controls. Current exports leave these unverified/missing. Dividends,
fill-wallet fees/FX, corporate actions, cash coverage and CSV aliases remain open.
The prior Python quantity diagnostic is retained, not silently replaced by a cash
module. Do not invent provider signs, corporate-action economics or returns.

## Preserve

Deployed broker discovery/enrichment source `e327fc9`; schema `0008`; ten-minute
refresh and sixty-day detailed retention unchanged. Financial history/daily/latest
observations stay retained. The manual XLSX archive is complete; do not touch the
real workbook. Post-reset login/cadence/enrichment/query use remains unverified;
operational checks are separate from feature work. No full suites, CI matrices,
sizing or repeated live probes. Existing commit/push/deploy authority persists;
Rust runtime qualification is an engineering gate, not a new permission request.

Following work retains portfolio/risk analytics with historical daily inputs,
integrated workflows/alerts/stress/attribution/projections, and operational backup/
recovery acceptance. Trading stays in Trading 212; tax remains deferred.
