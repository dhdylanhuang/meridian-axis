# Next delivery: integrate the Rust reconciliation core

Reviewed **20 November 2026**. The owner selected Rust for reconciliation, keeping
Python broker ingestion and database access. The pure native cash slice and WASM/local Worker qualification are
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

WASM addition: the same core now has generated bindings, a private Worker import,
a reproducible package tool and a localhost-only fixed-fixture workerd harness.
Two parity/bounds cases plus the targeted local-runtime case passed. Native seven
Rust/four Python results were reused. Inputs over 512 KiB or 1,024 observations are
rejected, not truncated. No production change or additional hosted Worker.

## Integrated source and release

Python-to-JavaScript service invocation, strict approved projection and atomic
snapshot publication are implemented. A named entrypoint on the existing gateway
runs WASM; the sync Worker calls it privately. The AXIS view shows review/coverage
and explicitly unreconciled cash, with fail-open preservation of broker figures.
Runtime RLS excludes initial captures; that gap is explicit, with no grant change.
Thirteen focused Python and three Node/RPC/UI cases passed; current status records
commands. Reuse prior core/WASM tests. No schema/new Worker/new browser poll.

The Rust pipeline is deployed; gateway/sync source is now `f93a493`, with the
session owner unchanged at `5cc8564`. The latest correction separates global sign
policy gaps from record exceptions and adds validated provider-type activity counts. Active source tags,
private binding target, preserved secret/Hyperdrive bindings, ten-minute schedule,
exact static assets and the hosted WASM readiness header were verified. No schema
or credential change. Actual approved publication is verified: the live snapshot has the Rust method,
provisional state, input revision and matching snapshot identity with no refresh
error. Current status records the bounded checks; do not restart them.
Full-bound hosted CPU/memory remains an open workload gate; failures leave broker
publication available. Do not repeat prior suites or expose a public compute API.

The next bounded cash component window is implemented; current status owns tests
and release evidence. Source verification supports positive GBP cash interest and
signed GBP transfers only. The private Rust job compares actual opening/closing
available-to-trade observations and exposes a provisional residual and exclusions.
This completes a useful component diagnostic, not the transaction ledger stage.

Remaining deliveries, in order:
1. Explain residuals with verified fill-wallet/dividend and reservation/pie effects;
   establish comparable total-cash controls before claiming full reconciliation.
2. Extend evidence-backed signs/coverage for deposits, withdrawals, fees/FX and
   corrections; maintain source revisions and duplicate protection. Backfill or
   expose incomplete history without expanding runtime raw-source grants casually.
3. Integrate the existing quantity diagnostic, with corporate actions requiring
   review; do not invent their economics or import formats.
4. Build portfolio/risk/treasury metrics only from eligible, dated, sufficiently
   covered inputs. Trading remains on Trading 212; no separate role screens or tax.

Full-bound hosted CPU/memory and actual query use remain separate unresolved gates.
Do not rerun previous suites or platform probes without a specific new risk.

## Preserve

Deployed gateway/sync `f93a493`, session owner `5cc8564`; schema `0008`; ten-minute
refresh and sixty-day detailed retention unchanged. Financial history/daily/latest
observations stay retained. The manual XLSX archive is complete; do not touch the
real workbook. Post-reset login/cadence/enrichment/query use remains unverified;
operational checks are separate from feature work. No full suites, CI matrices,
sizing or repeated live probes. Existing commit/push/deploy authority persists;
Rust runtime qualification is an engineering gate, not a new permission request.

Following work retains portfolio/risk analytics with historical daily inputs,
integrated workflows/alerts/stress/attribution/projections, and operational backup/
recovery acceptance. Trading stays in Trading 212; tax remains deferred.
