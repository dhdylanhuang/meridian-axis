# Current status and handoff

Reviewed **20 November 2026**. This file is the authoritative implementation snapshot. Dated delivery evidence and superseded instructions are retained in [historical checkpoints](status-history.md).

## Observed funding and performance

History adds the funding timeline, per-transaction evidence, valuation
coverage and Modified Dietz approximations for supported daily intervals.
Month-to-date and year-to-date require the prior period-end valuation and a
continuous chain verified by the available funding history. The chart stays
at 90 UTC days. The funding coverage is bounded by the completed traversal
and gaps remain visible. See [the published method](calculation-contracts.md#observed-modified-dietz).

Funding evidence stays within the private sync role and the Rust WASM
method uses the existing named service. Session authentication commits
before the private call. There is no schema or scheduling change.

Released gateway source `eee8a2f` and private owner/sync source `2b9364c`.
The first hosted read left the report unavailable. The private transport was
updated to pass the bounded Rust JSON directly and report fixed failure states.
Deployed asset digests, WASM health, existing bindings, anonymous denial and
the ten-minute schedule were verified. The final authenticated read matched the
funding rows, coverage timestamps and eligible daily return values against
the retained data and an independent decimal calculation. MTD and YTD were
unavailable with missing valuations. The short-lived session was revoked and
the publication receipt is private.

Focused checks passed for Rust timing/coverage and year chaining (3), the
generated WASM boundary (1), the History browser UI (3), and the Python
funding adapter/session and private Worker paths. A synthetic headless Chrome
check verified the funding marker link and expandable transaction details at
mobile width.


## Observed account history

The History tab reads the last approved Trading 212 snapshot for each of 90 UTC
days and shows exact GBP values, account capture and snapshot observation times,
coverage and gaps. The current UTC date is provisional. Cash, income and
funding drill-down remains available below the chart. See the
[API contract](api-and-ui.md#observed-account-history).

The session owner reuses its existing snapshot read grant and account scope.
The query bounds selection with the account and observation index and projects
only the approved daily account fields across Hyperdrive. This is a SQL and
Python integration read of saved broker values, so it uses the existing
Python session boundary. JavaScript positions pixels and formats exact values.
Schema 0008 and the existing refresh and retention schedules apply.

Gateway and session owner source `b23acfc` were deployed on 20 November 2026.
The sync release, protected bindings and ten-minute schedule were verified.
All four served asset digests matched. The new route returned 401 with
`no-store` without a session. One bounded live check with a short-lived
approved session reproduced all 90 UTC date outcomes and exact observed GBP
amounts and timestamps from retained data. The session was revoked after
verification. The private runtime holds the release and coverage receipts.

Focused validation on 20 November:

- `pytest -q -p no:cacheprovider backend/tests/test_snapshot_access.py` ran
  as separate SQLite and disposable loopback PostgreSQL selections, with
  4 and 5 passes respectively. The tests cover UTC boundaries, deterministic
  last capture, future exclusion, exact decimals, gaps, integrity and access.
- `node --test prototype/worker-feasibility/tests/test_{snapshot_ui,session_gateway}.mjs`
  passed 34 checks. A synthetic headless Chrome smoke check also verified
  mobile-width layout, canvas rendering and the exact daily table.


## Classification coverage across the held universe

The reviewed catalogue extends to all 80 instruments in the audited generation:
60 direct shares with sector and domicile, 18 equity funds and trusts with
dated sector and market coverage, and two non-equity instruments. A named
classification for the instrument does not imply 100% look-through. Fund
managers’ regional and taxonomy-specific weights retain their original basis.
Individual published percentages and coverage gaps remain inspectable.
The source files and actual portfolio list are private.

The same two gateway bindings now accept bounded gzip-encoded JSON as well as
legacy JSON. Only held ISIN entries pass to the Rust calculator. Each bound
value is below 5 KB. The operator retains the readable reviewed catalogue and
the encoded deployment inputs privately. A synthetic full-catalogue comparison
showed approximately 6 KB more per gzip-compressed allocation report. This is
not a measurement of hosted database storage or remaining capacity.

Five targeted Rust and three Node cases passed. A full-catalogue rehearsal using
synthetic values qualified all 80 records against the generated WASM. No full
suites, provider integration, schema changes or additional polling. Gateway
deployed at `61ef1be`, with the sync and session owner on their existing
sources. Exact no-store assets, hosted WASM, protected bindings and ten-minute
Cron passed release checks.

**Approved financial publication verified 20 November 2026 at 22:30:30 UTC.** The
retained generation included a sourced classification for each of its 80
nonzero positions. The sector residual contained fund fractions only. All 60
direct-share classifications and all 18 fund/trust groups matched their scope,
and gold and bonds were supported by asset evidence. Exact source-weight
multiplication, subtotal conservation, source dates, snapshot identity and
publication health matched. The private receipts contain counts and agreement
flags. Individual fund residuals can include unreported countries,
sector weights, manager-labelled Other, cash or rounding. The synthetic UI
case exercised the drill-down.

## Direct-share classification coverage expansion

The owner prioritised further exposure coverage before starting History.
A data-only release updated the existing private issuer binding with eight
reviewed direct-share classifications. The catalogue now covers thirteen
direct-share records. The fund binding, existing Worker code, protected
bindings, schema and ten-minute schedule were preserved. ISIN checksums,
effective dates, binding size and acceptance of all eight additions by the
existing WASM were checked before activation.

**Approved financial publication verified 20 November 2026 at 22:10:31 UTC.** The
source-linked sector and domicile allocations for all eight new records and the
exact amounts and source evidence for all three views matched. Cash drill-down
was still published and snapshot job health was clear. The receipts record only
counts, agreement flags and release metadata. The issuer binding is close to
its 5 KB limit. Further catalogue expansion needs a compact format or another
private binding and should be verified on the next approved generation.

## Sourced sector and country allocations

The dedicated Exposures tab shows broad equity sectors, direct-share issuer
domicile and fund-manager market allocations with coverage denominators,
unclassified remainders, exact constituent contributions and dated source links.
Verified gold and bonds appear separately within the sector view. The initial
private seed prioritises positions by broker value and includes source coverage
for five issuer holdings and eight funds, plus two sourced non-equity positions.
Individual fund dimensions remain unavailable where compatible data is missing.
The original quote-currency, concentration and cash component views stay in the
same tab. No returns, new polling, provider subscription or database migration.

The gateway uses two optional private Worker secret bindings holding manually
reviewed inputs, `PORTFOLIO_FUND_CLASSIFICATIONS` and
`PORTFOLIO_ISSUER_CLASSIFICATIONS`. Neither contains account values. The holding
list and source mappings stay out of Git and assets. The release stores the
reviewed local source privately. To update, review the issuer or fund-manager
documents and confirm the current ISIN, publish a reviewed JSON secrets file to
the same gateway, and verify the next approved generation. Rust validates date,
weight and scope before calculating values. The existing sync bridge publishes
results atomically without adding database reads. Older snapshots keep their
original exposures. Method details are in the
[exposure contract](calculation-contracts.md#approved-broker-snapshot-exposure).

Local focused validation passed four Rust exposure cases, one Python WASM
publication case and two Node browser-state cases. Checks cover exact allocation,
partial/cross-dimension eligibility, stale or over-allocated evidence, metadata
ISIN input, approved publication, and source links and drill-down. Targeted Ruff
passed. Gateway and sync source `f1de8a2` deployed with the session owner still
at `94042f2`. Release checks verified four exact no-store assets, WASM readiness,
existing protected bindings plus only the two private classification bindings,
and the ten-minute Cron. No schema operation was needed.

**Approved financial publication verified 20 November 2026 at 22:00:24 UTC.** One
bounded verification read matched the exact classified and unclassified
contributions to broker holding values and the reviewed classification source
weights, dates and URLs, with separate issuer domicile/fund market scopes.
The published generation had a succeeded source import, matched snapshot ID
and retrieval cutoff, retained cash drill-down and no snapshot job error.
Private verification retained counts and agreement flags without logging the
holding amounts. Live browser interaction needed a signed-in member. Tab and
drill-down were exercised with a synthetic snapshot.

## Original portfolio exposure delivery

The AXIS dashboard adds ranked positions, portfolio and invested weights,
largest/top-five/top-ten concentration, quote-currency allocations and
independent cash component weights. Allocation rows open constituent positions
in Holdings. Sector and country currently show the known value as unclassified
because the broker metadata supplies neither dimension. See the
[calculation contract](calculation-contracts.md#approved-broker-snapshot-exposure)
for the missing classification inputs, coverage and exact methods.

A new pure Rust calculator runs through the existing private gateway WASM
binding. Python retains broker ingestion, accepted metadata selection and atomic
approved snapshot publication. JavaScript retains Worker integration,
formatting and Holdings interaction. There is no new provider, network route,
schema migration, access grant or polling loop. Compute failure leaves the
authoritative broker snapshot publishable. Source values and cash drill-down
remain intact. Cash-change and quantity reconciliation and tax stay deferred.

Focused evidence passed using invented positions:

- `cargo test --manifest-path rust/reconciliation/Cargo.toml --locked --offline --test exposures --jobs 2`
  passed three cases covering exact amounts, top-k counts, rounding, missing and
  incompatible values, denominator guards and independent cash weights.
- `pytest -q -p no:cacheprovider -m 'not postgres' backend/tests/test_broker_sync.py::test_exposures_publish_atomically_and_fail_open prototype/worker-feasibility/tests/test_sync_worker.py::SyncWorkerTests::test_private_rust_binding_is_passed_to_python_job`
  passed two cases with generated WASM. Verified existing metadata fallback,
  snapshot/cutoff pinning, closed DB transaction during RPC, wrong-scope rejection,
  failed-calculation publication and last-good preservation on broker failure.
- `node --test --test-name-pattern='portfolio exposures|broker total stays exact|late response cannot repopulate' prototype/worker-feasibility/tests/test_snapshot_ui.mjs`
  passed three cases covering monetary formatting, constituent filtering,
  older snapshots and cleared private state. The exposure case passed again
  after the final accessibility labels and empty-state adjustment.
- `node --test --test-name-pattern='Cloudflare local' prototype/worker-feasibility/tests/test_cash_wasm.mjs`
  passed the private-service RPC case with actual workerd and the generated
  620,487-byte WASM (wasm-bindgen 0.2.130). The local loopback listener needed
  permission outside the managed sandbox.
- Targeted backend Ruff check and format passed. No test matrix, retention run,
  workbook access, sizing query or additional provider integration.

Gateway and sync are **deployed at `fb7cc8f`**. The session owner remains
at `94042f2`. Gateway was deployed first and the sync consumer second.
Active annotations, four exact no-store assets, hosted WASM readiness,
preserved secret/Hyperdrive/private bindings and the ten-minute Cron were
verified. Native schema remains `0008`.

**Actual approved publication verified** on 20 November at **16:30:30 UTC**
after the scheduled refresh. One bounded read-only check tied the approved
generation to the succeeded Trading 212 import and both retrieval cutoffs.
The broker denominators, position amounts and percentages, rank, measured
coverage, quote buckets, concentration amounts and independent cash component
weights agreed with the source or independently recomputed results. Cash
drill-down was still published and snapshot health reported no error. The
private receipts contain only release metadata and agreement flags. No real
financial values or source identifiers were printed. Browser interaction
was exercised with synthetic data. Reuse this evidence on resume.

## Completed cash total drill-down delivery

Cash total drill-down and specific broker coverage are **deployed**: gateway
`5709f30`, session owner/sync `94042f2`. Three Worker source annotations, preserved
secret/Hyperdrive/private bindings, exact no-store assets, WASM readiness and
ten-minute schedule were verified. The small gateway follow-up keeps details usable
after a failed saved-snapshot reload; only its two affected Node cases were rerun.
The working tree/release source was reviewed and pushed. Schema stays `0008`. Each monetary total opens a paginated authenticated read-only view with
payment date, issuer/type, exact amount, Trading 212 reference and collapsed
source/revision/digest evidence. Pages reconstruct the exact approved snapshot
inputs, excluding revisions observed after cutoff; hash mismatch returns 409.
No full transaction list is copied into recurring snapshots. One bounded metadata
query adds completed-traversal timestamps/pages and earliest/latest captured events.

A single private coverage audit verified contiguous, terminal-complete cash and
dividend traversals and found no retained initial-capture references absent from
accepted revisions. No identified capture gap needs backfill. This establishes
available broker history, not complete account lifetime or statement certification.
Initial capture RLS remains unchanged; private audit receipt stays ignored.

New focused evidence: **1 Rust, 5 Python and 4 Node cases passed**. Commands:
- Scoped Rust toolchain: `cargo test --manifest-path rust/reconciliation/Cargo.toml --locked --quiet --test cash details_ --jobs 2`.
- `AXIS_NODE_TEST_BINARY="$PWD/private/dev-tools/node_modules/.bin/node" /private/tmp/meridian-query-venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/test_cash_activity.py` → 2 passed (pages equal saved sum, later revisions stay pinned, issuer/source validation, unknown snapshots/hashes, partial history not complete).
- `/private/tmp/meridian-query-venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/test_cash_activity_http.py prototype/worker-feasibility/tests/test_sync_worker.py::SyncWorkerTests::test_activity_page_uses_readonly_service_without_broker_execution` → 2 passed (both members, denied auth/origin/CSRF, bounded body, no transaction spans RPC, no broker execution).
- `/private/tmp/meridian-query-venv/bin/python -m pytest -q -p no:cacheprovider prototype/worker-feasibility/tests/test_session_worker.py::SessionWorkerTests::test_activity_callback_forwards_only_to_fixed_private_sync_object` → 1 passed.
- `private/dev-tools/node_modules/.bin/node --test --test-name-pattern='activity detail route|activity drilldown|late activity' prototype/worker-feasibility/tests/test_session_gateway.mjs prototype/worker-feasibility/tests/test_snapshot_ui.mjs` → 3 passed.
- `private/dev-tools/node_modules/.bin/node --test --test-name-pattern='Cloudflare local' prototype/worker-feasibility/tests/test_cash_wasm.mjs` → 1 passed including new private detail RPC in real workerd.
WASM rebuilt/package verified with existing wasm-bindgen 0.2.130; 475,779 bytes.
Targeted Ruff/format and diff checks passed. Reuse prior economics/retention evidence;
no full suite/CI matrix/sizing or repeated live probes. Runtime remains three Workers,
private service binding, schema 0008, ten-minute cadence and unchanged RLS/roles.
Release order was gateway, session owner, sync, followed by the isolated gateway
retry guard. Chrome blocked browser verification because another extension UI was
open; no settings/permissions were changed. Actual browser clicks remain unverified.
A bounded server read first saw the 14:00 snapshot predating release. After the
natural 14:10 refresh, one final read verified the 14:10:29 UTC generation: detail
capability enabled, both broker histories traversed, coverage matched succeeded
source imports/page counts, input revision present, snapshot ID/cutoff matched and
no snapshot-job error. No financial amounts or private source IDs were printed.
Private receipts preserve release, coverage audit and publication evidence. The
owner reported refreshing the page; this does not itself verify a detail click.
Implementation, deployment and server publication are complete. Reuse these passing
checks rather than re-running them. Lifetime completeness and browser clicks remain
explicit limitations, not claims established by this delivery.

## Previous monetary totals release

Owner DC25 now requires meaningful monetary dashboard features. The prior cash
window/count paragraph was rejected as insufficient for use. Current implementation
replaces it with broker cash now and year-to-date dividend/distribution, interest,
deposit/withdrawal, fee/transfer/lending totals, separately by currency. Original
signed amounts are descriptive source totals, not a reconstruction or partition of
current cash. Runtime stops the opening-control query and includes accepted ongoing
dividend revisions under existing RLS. Missing categories/coverage stay explicit.
**Deployed at gateway/sync source `17aa7ea`**, session owner unchanged at `5cc8564`.
Reviewed source was committed/pushed; gateway producer deployed before opted-in sync.
Both active annotations match source; three no-store static assets match exact source
bytes and hosted WASM is ready. Protected secret/Hyperdrive/private RPC bindings,
restricted origin roles/TLS/cache settings and ten-minute schedule are preserved.
No schema/grant/new Worker. **Real monetary publication verified** at the natural
20 November 11:50 UTC refresh (snapshot cutoff 11:50:30 UTC). One read-only query
independently summed latest accepted completed dividend/cash revisions over the
published period and compared exact per-category/currency amounts and counts.
Published amounts matched accepted sources; cash-interest, dividend/distribution,
deposit, withdrawal, fee and transfer totals were present in the primary currency.
Money stayed strings; input revision, snapshot identity and cutoff matched, with no
snapshot-job error. No balances, financial amounts or private identifiers printed
or committed. Private receipt preserves agreement flags. This verifies actual
publication, not lifetime completeness or reconstructed cash economics.

Focused checks passed: one Rust `funding_` case (exact arithmetic, family identity,
latest revisions/repeated observations, currency/date boundaries/conflicts and no
dividend cash booking); three Python publication cases (new dividend/cash monetary
projection with strict amount/category validation, prior component opt-in diagnostic,
unchanged fail-open/atomic source publication); two Node `funding view` cases (amounts,
current cash, old summaries, absent categories/coverage, conflict exclusion and clear).
WASM rebuilt with existing Rust toolchain / wasm-bindgen 0.2.130; artifact 444,470 bytes.
Targeted Ruff format/check passed. Commands:
- Scoped Rust toolchain: `cargo test --manifest-path rust/reconciliation/Cargo.toml --locked --quiet --test cash funding_ --jobs 2`.
- `AXIS_NODE_TEST_BINARY="$PWD/private/dev-tools/node_modules/.bin/node" /private/tmp/meridian-query-venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/test_cash_publication.py::test_funding_totals_publish_dividends_and_cash_without_source_rows backend/tests/test_cash_publication.py::test_delivery_available_cash_window_and_projection_validation backend/tests/test_cash_publication.py::test_wasm_summary_commits_atomically_without_raw_history` → 3 passed.
- `private/dev-tools/node_modules/.bin/node --test --test-name-pattern='funding view' prototype/worker-feasibility/tests/test_snapshot_ui.mjs` → 2 passed.
No full suites, CI matrix, prior retention checks, sizing or live financial inputs.
Reuse passing evidence. Deploy compatible gateway producer then opted-in sync;
existing session owner unchanged. The single bounded actual monetary-publication
check above passed. Reuse this evidence; do not rerun it or prior checks on resume.

## Previous component-window delivery (not monetary dashboard acceptance)

Observed cash component window is **deployed at gateway/sync source `27da2f3`**
(session owner unchanged at `5cc8564`).
The private ISA transactions statement independently corroborated account identity
and signed GBP transfers (both directions) / positive GBP cash interest. Proof and
source remain ignored; no workbook/source PDF was modified. Hosted Rust policy now
supports only these cases. Other cash types, negative interest corrections, other
currencies and demo remain unverified. Python selects an actual prior-UTC-day
approved available-to-trade observation and pending closing observation; Rust
computes supported window movements and residual. Dashboard displays these controls,
counts and explicit component/coverage limitations. No total cash or return claim.

New focused evidence: two Rust `delivery_` cases passed; WASM release rebuilt and
packaged with existing wasm-bindgen 0.2.130. Three Python publication/validation/
legacy cases passed (new fixture corrected to append synthetic history after an
initial immutable-update fixture failure; reran only that failed case). Two Node
UI cases passed. Targeted Ruff check/format passed. Commands:
- Scoped Rust toolchain: `cargo test --manifest-path rust/reconciliation/Cargo.toml --locked --quiet --test cash delivery_ --jobs 2`.
- `AXIS_NODE_TEST_BINARY="$PWD/private/dev-tools/node_modules/.bin/node" /private/tmp/meridian-query-venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/test_cash_publication.py::test_delivery_available_cash_window_and_projection_validation backend/tests/test_cash_publication.py::test_wasm_summary_commits_atomically_without_raw_history backend/tests/test_cash_publication.py::test_activity_projection_validates_counts_and_accepts_older_results` (two legacy cases passed first; new case passed after fixture correction).
- `private/dev-tools/node_modules/.bin/node --test --test-name-pattern='delivery cash window|approved Rust review' prototype/worker-feasibility/tests/test_snapshot_ui.mjs`.

Reuse prior retention/RLS/private RPC/core evidence below. No full suite, CI matrix,
sizing, broker request or database probe for development. Reviewed source committed
and pushed; gateway producer deployed first (old requests retain the old summary
shape), sync consumer second. Both active source annotations matched `27da2f3`;
session owner version stayed unchanged. Three static assets matched exact source
bytes with no-store; hosted WASM health is ready. Protected credentials/Hyperdrive
and private RPC bindings, restricted origin roles/TLS/cache policy and ten-minute
schedule were preserved. Native schema remains `0008`; no migration/grant change.
Private release receipt records successful checks. No new financial SQL/live broker
probe or forced refresh was run. Actual publication of the **new window** remains
unverified pending the next successful automatic refresh; previous provisional
publication evidence below does not establish this window. Full-bound hosted
CPU/memory and realized query use remain open. Do not restart passing checks.

## Previous cash review interpretation correction

Cash review interpretation correction is **deployed at `f93a493` on gateway/sync**
(session owner unchanged at `5cc8564`): the former wording
counted the global unverified-sign prerequisite as a per-event manual-review task.
The updated panel separates provider-type activity counts, actual detected record
conflicts/unsupported types, and shared prerequisites. No economic sign, opening
balance or cash reconciliation result has been fabricated. The Rust core is
unchanged. Existing role/coverage/size gates remain.

Read-only inspection of retained encrypted evidence and the source contract did
not establish independent sign verification. Current [provider field documentation](https://docs.trading212.com/api/historical-events/transactions.md)
describes amounts/types without an explicit sign convention; pattern observations
alone are not sufficient. No financial values, source rows or private identifiers
were copied into Git; no live broker call or workbook/PDF modification occurred.

Focused evidence: two Python checks (the real WASM publication boundary and
activity-key/count validation including legacy compatibility) passed using
`AXIS_NODE_TEST_BINARY="$PWD/private/dev-tools/node_modules/.bin/node" /private/tmp/meridian-query-venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/test_cash_publication.py::test_wasm_summary_commits_atomically_without_raw_history backend/tests/test_cash_publication.py::test_activity_projection_validates_counts_and_accepts_older_results`.
Three Node checks passed using `private/dev-tools/node_modules/.bin/node --test --test-name-pattern='Cloudflare local|approved Rust|cash review distinguishes' prototype/worker-feasibility/tests/test_cash_wasm.mjs prototype/worker-feasibility/tests/test_snapshot_ui.mjs`.
Targeted Ruff/format passed. No Rust rebuild/full suite/CI matrix or extra live SQL.
The backwards-compatible accepting sync consumer deployed before the gateway
producer. Both active source annotations matched `f93a493`; the session owner
version remained unchanged. Protected secret/Hyperdrive bindings, private RPC
binding and ten-minute schedule were preserved; three static assets matched source
bytes, and hosted WASM health remained ready. No extra broker sync or live SQL
verification was performed for this display/projection correction. Reload an old
client once; category counts appear after the next successful snapshot if absent
from an older saved generation. Actual sign/opening/trade/dividend economics remain
unverified and balances are not claimed reconciled.

## Previous private Rust job integration

Private Rust job integration is **deployed at source `5cc8564`** to the existing
three Workers. The existing
sync DO calls the gateway's named `CashReconciliation` service entrypoint; approved
review summaries commit with broker snapshots and appear in the existing AXIS view.
No fourth Worker, schema/migration, grant or extra browser poll. RPC occurs outside
SQL transactions and cannot replace broker financial figures. Engine/limit/response
failures produce an unavailable review; failed broker refresh preserves the prior
complete snapshot. A fixed `/health` readiness header qualifies hosted WASM without
financial reads. Native/Rust arithmetic is unchanged.

Runtime uses ongoing cash revisions only: fixed-scope sync RLS excludes initial
captures, which remain available to the offline trusted exporter. Summary coverage
states this exclusion, unknown lifetime/signs and missing openings. No balances are
claimed reconciled. Limits stay 1,024 observations / 512 KiB with no truncation.
See [integration contract](imports-and-reconciliation.md#private-rust-job-integration--20-november-2026).

New focused checks: **13 Python cases passed** for atomic approved publication,
released transactions before RPC, failure/limit isolation, existing export behavior,
shared-helper compatibility, the Worker binding callback and bundle allowlist.
Command: `AXIS_NODE_TEST_BINARY="$PWD/private/dev-tools/node_modules/.bin/node" AXIS_RUST_TEST_BINARY=/private/tmp/meridian-rust-target/debug/axis-reconciliation /private/tmp/meridian-query-venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/test_cash_publication.py backend/tests/test_cash_history.py backend/tests/test_history_reconciliation.py::test_scope_missing_snapshot_and_observation_limit_fail_closed prototype/worker-feasibility/tests/test_sync_worker.py::SyncWorkerTests::test_private_rust_binding_is_passed_to_python_job prototype/worker-feasibility/tests/test_application_bundle.py`.
**3 Node cases passed** using `private/dev-tools/node_modules/.bin/node --test --test-name-pattern='Cloudflare local|approved Rust|Rust service' prototype/worker-feasibility/tests/test_cash_wasm.mjs prototype/worker-feasibility/tests/test_snapshot_ui.mjs prototype/worker-feasibility/tests/test_session_gateway.mjs`.
These include actual local workerd RPC, foreign-scope rejection, whitelisted output,
public-route denial and review rendering. Targeted backend Ruff/format passed;
prototype Python passed E/F/I/UP/B at the existing 100-column scope. Broader prototype
lint reports pre-existing blind-exception/nested-with style; no unrelated cleanup.
Earlier native seven Rust/four bridge and WASM evidence were reused. No full suite,
CI matrix, retention test, sizing or repeated live probe was run.

Release verification: gateway entrypoint deployed before its caller, followed by
session owner and sync. All three active deployment annotations matched `5cc8564`.
Existing managed secret/Hyperdrive binding sets and uncached TLS origin profiles
were preserved. The sync's new private `RECONCILIATION` binding independently matched
the gateway and `CashReconciliation` entrypoint. Cloudflare still reports exactly
`*/10 * * * *`. Three static assets matched source bytes with no-store headers;
`/health` returned the hosted `rust-wasm-ready` header after executing the fixed
nonfinancial self-check. No schema, credential, workbook or financial-input write.
Private version/rollback/artifact receipts remain ignored. Existing deployed source
labels below are current; earlier releases retain their original dated evidence.

Actual publication verified after the next scheduled slot: a narrowly selected
read returned `cash_reconciliation_rust_v1`, provisional availability, a present
input revision, matching approved snapshot identity and no refresh error. The
post-release job-attempt flag was true. This confirms the deployed private Rust
calculation/projection and atomic approved publication, not verified cash signs or
reconciled balances. No balances, amounts, references, actual hashes or transaction
rows were retrieved by the verification query. An earlier read found the old
snapshot; the post-cycle query needed one schema correction because UTC timestamps
are stored as TEXT (cast before comparing to timestamptz). No app fix/retest was
needed. There was no database polling or forced extra broker refresh.

Source `5cc8564` remains deployed; native parity is `0008`. Reload an older open
client once for the new cash-history review panel. Full-bound hosted CPU/memory,
password-login recovery, measured automatic cadence intervals and actual query use
remain unverified; a successful current refresh does not establish those separate
gates. The next feature boundary is supported sign/opening/closing evidence and
additional event families, preserving review-only semantics until verified.

## Prior WASM qualification

**WASM qualification completed, 20 November:** the existing Rust cash core now
builds for `wasm32-unknown-unknown` with generated, locked wasm-bindgen 0.2.130
bindings and a private JavaScript Worker adapter. The exact-decimal financial core
is unchanged. The package is 406,813 bytes; generated binary/glue/hash manifest are
ignored, reproducible artifacts. No extra hosted Worker or public endpoint.

Focused new evidence: `AXIS_RUST_TEST_BINARY=/private/tmp/meridian-rust-target/debug/axis-reconciliation node --test prototype/worker-feasibility/tests/test_cash_wasm.mjs`
passed native/WASM result parity and safe bounds/error recovery (**2 cases**).
The local workerd case stopped on Node 20, then passed on the existing compatible
Node with `AXIS_RUST_TEST_BINARY=/private/tmp/meridian-rust-target/debug/axis-reconciliation private/dev-tools/node_modules/.bin/node --test --test-name-pattern='Cloudflare local' prototype/worker-feasibility/tests/test_cash_wasm.mjs`
(**1 case**). It executes the imported WASM in Cloudflare's actual local workerd,
not a mocked SDK. Cargo formatting and targeted Ruff checks passed. An initial
strip setting hid target features; switching to `strip = "debuginfo"` removed the
generator warning before the checked package was produced. Reuse all three new
checks and the native/Python evidence below; no full suites, CI matrices or hosted
broker/database probes ran.

The WASM boundary rejects more than 512 KiB UTF-8 or 1,024 observations without
partial output. [Build/run details](../rust/reconciliation/README.md#wasm-packaging-and-local-worker-qualification)
record the already-installed temporary target/generator and reproducible commands.
Current production remains `e327fc9`. Next is the private Python-to-JavaScript job
call and approved summary publication, with hosted CPU/memory qualification;
local runtime success does not claim that integration, a deployed feature, actual
cash reconciliation or complete source semantics.

## Prior native Rust core

Owner-selected **Rust reconciliation experiment**, first bounded cash slice, is
implemented natively in `rust/reconciliation`, with a read-only Python accepted-
evidence bridge (`meridian.export_cash_history`). Typed scope/sign/control/review
states and exact decimals preserve source revisions and prevent duplicate effects.
Cash roll-forward requires explicit supported signed amounts and opening/closing
controls. Current exported provider signs are deliberately unverified; no openings,
cash-component totals, dividends, fill-wallet economics or returns are invented.
See [Rust contract and local command](../rust/reconciliation/README.md).

Completed checks, once per changed path:
- `DEVELOPER_DIR=/Library/Developer/CommandLineTools CARGO_HOME=/private/tmp/meridian-rust/cargo RUSTUP_HOME=/private/tmp/meridian-rust/rustup CARGO_TARGET_DIR=/private/tmp/meridian-rust-target /private/tmp/meridian-rust/cargo/bin/cargo test --manifest-path rust/reconciliation/Cargo.toml --locked --quiet --jobs 2`: **7 passed**.
- `AXIS_RUST_TEST_BINARY=/private/tmp/meridian-rust-target/debug/axis-reconciliation /private/tmp/meridian-query-venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/test_cash_history.py`: **4 passed**, including compiled Rust end-to-end.
- Cargo formatting and targeted Ruff check/format passed. Cargo's compile/test
  covers the new library and native CLI; no separate duplicate compile run.

The initial build failed solely because the selected full Xcode required license
acceptance; using already-installed standalone tools through a scoped environment
resolved it. No license/global tool selection/shell profile changed. Rust 1.100.0
and dependencies are in the temporary paths above; Cargo.lock is committed. Reuse
these checks. No full suite, CI matrix, live broker/database probe or real financial
input was used. Existing sync/retention/security evidence remains reusable.

This slice is **native/offline, not deployed**: the agreed experiment starts with a
pure core and synthetic tests. WASM packaging/local runtime qualification is complete above. Private job invocation
and approved result publication, plus verified sign/control evidence for actual
cash booking, remain.
The native binary is not compatible with the current Worker by itself; this is a
technical integration gate, not a missing deployment authorization. Deployed source
remains `e327fc9`, native schema `0008`, ten-minute refresh unchanged.

## Previous discovery/enrichment delivery

The owner selected **broker-led automatic holding discovery/enrichment** next:
orders remain in Trading 212; one integrated AXIS supports PM, trading-monitoring,
risk and portfolio cash/treasury workflows. Current prices and reported figures
come from the broker. A parallel current-account valuation/live-price engine is
removed from the delivery plan; historical price/benchmark/FX inputs remain for
risk/performance. See the [requirements amendment](product-requirements.md#broker-led-monitoring-amendment--19-november-2026)
and revised delivery order. No role or tax scope change.

Implemented source: new held tickers request the existing metadata job before its
successful daily cooldown ends, preserving leases, failures and provider retry
limits. Scheduled and manual success share that job. Snapshot publication adds
whitelisted listing enrichment/coverage/provenance and observed additions/closures;
the existing private view displays these states. Position facts always win, cash
components remain separate, and quote age remains unknown. Financial publication
precedes metadata lookup; fresh enrichment appears in the next successful snapshot.
The existing metadata reader is shared by session checks and publication. There
was no duplicate live-price service to delete; the unused sixty-second quote and
ninety-day local retention settings/sample environment entries were removed.
The fixed Worker bundle allowlist includes the new shared module. No schema,
credential, grant, ten-minute cadence, retention or workbook change.

Offline checks completed once for changed paths:
- `/private/tmp/meridian-query-venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/test_holding_discovery.py backend/tests/test_broker_sync.py backend/tests/test_snapshot_access.py -m 'not postgres'`: **31 passed, 42 deselected**.
- `node --test prototype/worker-feasibility/tests/test_snapshot_ui.mjs`: **9 passed**.
- `/private/tmp/meridian-query-venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/test_config.py prototype/worker-feasibility/tests/test_application_bundle.py`: **10 passed**.
- Targeted Ruff check/format passed for changed Python files. No full suite/CI
  matrix, retention test, sizing query or hosted database probe was repeated.

Coverage includes new/closed holdings, repeated and missing metadata, exact broker
figures, manual/scheduled dispatch, successful cooldown bypass, active leases,
retry/terminal pauses, metadata provenance/conflict/staleness, immutable snapshots,
unheld catalogue exclusion, UI notices and removal of unused configuration.
PostgreSQL execution and actual broker enrichment remain unverified. **Source
`e327fc9` is deployed to all three existing Workers.** Cloudflare active deployment
annotations independently matched the full source commit for sync, session owner
and gateway. Three nonfinancial asset reads matched local source bytes exactly,
returned HTTP 200 and `Cache-Control: no-store`. Managed secret/Hyperdrive binding
sets were preserved; preflight retained the existing uncached TLS origin profiles.
Cloudflare's schedule API still reports exactly `*/10 * * * *`. No schema,
credential, workbook or database operation was performed, and passing targeted
evidence above was reused without rerunning tests/CI.

The initial immediate static-asset check failed and its rollback completed for
sync/gateway but not the session owner. A bounded forward release restored all
three Workers to `e327fc9`, with source annotations, bindings, schedule and exact
asset checks passing. The failed and successful private receipts retain prior/
active version IDs; do not rerun the original first-use helpers or overwrite those
receipts. The initial asset mismatch's root cause is not established. Future
source-only releases should check active source and allow a bounded asset
propagation retry before deciding rollback. Quota exhaustion limits live database
verification, not authority to deploy the reviewed source.

Next operational check: bounded login/cadence/actual enrichment verification when
the quota incident allows it; actual query usage remains unverified. No financial
endpoint or database was probed for this release. An already open client needs one
reload to receive the updated metadata/change notices. Next feature work remains
integrated transaction/cash reconciliation under the revised delivery order.

## Previous completed slice

The preceding delivery (`c2cf7b3`) implements a **local, read-only execution quantity diagnostic**
(method `known_trade_quantity_v1`). It normalizes accepted initial capture order
rows and ongoing fill revisions into one effective quantity record per identity,
preserving evidence/revision links. It compares known signed trade deltas with the
latest saved Trading 212 positions and exposes unexplained residuals, corporate
actions, sign conflicts and incomplete coverage. It never invents opening balances.
Zero residuals remain provisional. Cash/dividend/fee economics, a persisted ledger,
CSV aliases and dashboard presentation remain unfinished.

Run from `backend`: `python -m meridian.reconcile_history --database /path/to/private.sqlite3 --account-id ACCOUNT_ID`.
The JSON is private financial output; keep it outside Git/logs. SQLite is opened
read-only in one consistent transaction. Each capture/revision read fails closed
above 20,000 observations. See [method and boundary](imports-and-reconciliation.md#execution-quantity-diagnostic--19-november-2026).
No hosted operation, migration, access change, deployment, polling/retention change
or workbook access was needed. Deployed sources/native parity below remain current.

New offline evidence (19 November):
`/private/tmp/meridian-query-venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/test_history_reconciliation.py`
passed **12 tests**. Coverage includes real synthetic evidence acceptance and
snapshot publication, repeated syncs, revised effects, running-page exclusion,
precise residuals, signed sells, distinct fills, closed positions, future fills,
conflicts, scope/limits, read-only CLI and digest failures. Targeted Ruff check and
format check passed for the three new modules, domain package and new test file.
The first nine-case run passed; after adding currency/integrity coverage the final
twelve-case run passed. A Ruff cache write was sandbox-denied; `--no-cache` checks
then passed. Reuse these results; no full suite, CI matrix, live probe or retention
check was run. No real-input reconciliation or PostgreSQL execution is claimed.

The manual Excel archive remains completed: the private **AXIS Archive** sheet has
1,360 retained refresh generations, with original sheets/formulas preserved. Use
[the manual export command](workbook-archive.md); no workbook was read or changed
for this delivery. [Next assignment](next-milestone.md) identifies the revised delivery sequence.

Bounded retention and the separately authorized backup repair are **complete and deployed**. Native schema parity is `0008`; the sync Worker source is `0afd670`. Session/gateway source remains `073ffca`. Detailed broker-refresh snapshot/source pairs expire after sixty days, in one daily batch of at most 200 pairs, while the final observed snapshot of every UTC day is kept indefinitely. The global latest snapshot, all transaction/dividend/cash history, revisions, initial captures, metadata, Excel/CSV evidence, imports and prior audit are retained. Referenced or mixed-source runs are skipped. Daily observations are not approved exchange closes or implemented historical performance.

The first actual capability execution completed with **zero snapshots and zero sources removed**. The ten-minute Cron was restored. No archive infrastructure, general DELETE grant, credential replacement or UI change was introduced. This implementation controls only the selected expiry workload; other capacity/RAM limits remain separate. No further task is activated automatically.

Reusable evidence: targeted local persistence/recovery/retention checks passed **43 tests**, with four PostgreSQL cases deselected; **six Worker tests** passed. [PostgreSQL CI](https://github.com/dhdylanhuang/meridian-axis/actions/runs/44611266327) passed through native and Alembic paths, including all four new retention execution/permissions cases. [Worker CI](https://github.com/dhdylanhuang/meridian-axis/actions/runs/44611266304) passed Linux/macOS. Linux backend CI had one outdated backup-version assertion and 462 other passing tests; the assertion was corrected and **eight targeted backup tests passed**. Windows was cancelled by fail-fast and is not claimed as verified. One additional secret-free Docker-error regression passed. Do not rerun these matrices on resume without a relevant new change or failure.

The encrypted pre-migration `0007` backup and authenticated read-back were verified. The release independently observed the native `0008` history marker, twelve RLS tables, function/table ownership, sync-only capability access and absence of broad DELETE privilege. The sync Worker update preserved existing secret and Hyperdrive bindings. Trusted maintenance exercised the fixed capability; automated invocation through Hyperdrive remains unobserved during the reported daily quota exhaustion. No `0008` restore drill is claimed.

Backup failure diagnosis: Docker Desktop was stopped, while formatted `docker info` returned zero alongside a daemon error. Starting the existing app repaired export; no new tool or license acceptance was needed. `recovery_docker_unavailable` and [the recovery prerequisite](hosted-recovery.md) now make this actionable. Future agents must check a nonempty `docker version --format` server version, not repeat sizing/tests or change sockets/install clients. Private release receipts, backup and key remain ignored.

**Validation discipline, explicit owner instruction on 19 November:** avoid unnecessary tests/checks and repeated validation. Run targeted checks for changed behaviour, reuse passing results and broaden/repeat only for new changes, failures or unresolved risk. Avoid repeated CI polling and live probes, especially during quota exhaustion. Preserve results and outstanding steps here for resumed agents.

## Deployed application

[Open Meridian](https://meridian-axis-session-gateway.meridian-worker-feasibility.workers.dev/) serves authenticated AXIS and HOLDINGS for two approved identities sharing one GBP Stocks ISA. Both users have equal application permissions. The separate [React preview](https://meridian-axis-preview.meridian-worker-feasibility.workers.dev) contains invented data.

- Gateway source is **`61ef1be`**, sync is **`f1de8a2`** and session owner is **`94042f2`**. Supabase native schema parity is **`0008`**, with 12 public tables and RLS enabled. Native GitHub migrations own hosted DDL.
- Trading 212 reported account/cash/position figures are authoritative. Exact decimal strings, separate retrieval windows, missing fields and unknown market quote age remain visible. Historical returns are unavailable.
- Scheduled refresh targets **ten minutes during relevant regular sessions**, per the 19 November owner amendment. Cron dispatch runs in the JavaScript gateway. Python Durable Objects execute bounded work, with PostgreSQL task leases, endpoint reservations and retry state. Unknown schedule coverage permits conservative polling.
- Manual refresh requires membership, session, Origin and CSRF checks. It queues a durable alarm promptly. Evidence, approved snapshot publication, success health and audit commit together. Failures preserve the last successful snapshot.
- The BFF reads approved snapshots and selected refresh-health columns. Raw imports, source evidence and event revisions remain closed to it. A separate restricted broker writer accesses only its fixed account and broker source kinds. Broker keys are held in managed secret bindings.
- The private browser client retrieves saved snapshots and health together every ten minutes while visible and exposes manual broker refresh. An older open client needs one reload to load that implementation. Authenticated SSE remains planned.

## History and import boundaries

Orders, dividends and cash transactions advance one family page per scheduled invocation, rotating families in ten-minute slots (at most one page per family per thirty minutes). Each family uses a one-hour cooldown anchored to its successful final-page attempt. Pagination may take longer, and lifetime completeness remains unverified. Running-page checkpoints and staging survive retries. Complete acceptance appends fill/reference revisions and deduplicates repeated observations. Corporate actions retain original facts with review quality states. A bounded local quantity diagnostic now replays supported signed trade observations; persisted economic replay, cash reconciliation and calculated performance remain open.

The verified holdings CSV supports preview and atomic evidence import. It retains group context and excludes Total controls from holdings. Transaction CSV formats and API/CSV aliases remain unverified. The owner currently has transaction history in PDF, including the previously inspected cash-only statement.

Six Excel baseline observations are accepted into private hosted evidence with exact read-back and duplicate rejection. Group-value controls reconcile within £0.01. Three observations retain month precision, two explicit days and July an unknown date. Historical group-cost controls are absent. Recorded invested values remain source costs. Original workbook bytes were preserved.

## Verification evidence

19 November fix, local evidence on `fix/ten-minute-query-budget`: `/private/tmp/meridian-query-venv/bin/python -m pytest -q backend/tests/test_broker_sync.py backend/tests/test_snapshot_access.py backend/tests/test_refresh_http.py -m 'not postgres'` passed **23 tests, 42 deselected**. Targeted Node snapshot/gateway checks passed **22 tests**; sync-worker checks passed **four tests**, including persistent outage pause and duplicate manual signal coalescing. Changed backend files passed targeted Ruff checks/formatting, and whitespace checks passed. The synthetic 1,101-event replay passed with three revision SELECTs. These checks need not be repeated on resume. Initial failures reflected old one-minute/three-second timing expectations; tests now follow the ten-minute contract. Existing backend virtualenv points to a removed temporary interpreter; the temporary Python 3.13 environment above holds current dependencies.

Validation-branch CI passed at `b79b90a`: [backend checks](https://github.com/dhdylanhuang/meridian-axis/actions/runs/44605588558) passed Windows/Linux and PostgreSQL, including native restricted-role/concurrency checks; [Worker checks](https://github.com/dhdylanhuang/meridian-axis/actions/runs/44605588372) passed Linux/macOS. A subsequent browser-only refinement applies the same failure pause to manual POST errors; its new targeted test passed (one test, seven unrelated cases deselected). Backend and Worker Python sources are unchanged from passing CI. Per owner instruction, reuse these results rather than retriggering the same CI matrices for promotion/documentation.

Actual 19 November deployment: all three existing Workers (sync, session owner and gateway) updated at `073ffca`. Cloudflare's schedule API reported exactly `*/10 * * * *`. Three nonfinancial asset reads confirmed the ten-minute UI notice, new polling code and updated sign-in lifecycle. Managed secret/Hyperdrive binding sets and the existing uncached TLS origin profiles were preserved. No schema, credential or evidence changes were made. The private deployment receipt retains previous versions for rollback.

**Remaining incident verification:** the owner-reported free query allowance resets at 00:00 UTC on 20 November. Do not claim login recovery, actual ten-minute broker cadence or a measured daily query reduction from deployment/configuration checks. Authenticated cadence and provider-reported account/configuration usage remain unverified until a bounded post-reset check. Avoid repeated probes or rerunning passing CI. Old open tabs need one reload to receive the new browser polling policy. See [query budget](market-data-and-polling.md#hyperdrive-query-budget--19-november-incident).

Earlier deployed acceptance, 13 November:

- [Backend validation](https://github.com/dhdylanhuang/meridian-axis/actions/runs/43404788223) passed Windows/Linux and disposable PostgreSQL checks for the refresh/import implementation. [Worker validation](https://github.com/dhdylanhuang/meridian-axis/actions/runs/43413867781) passed Linux/macOS for the deployed gateway/object correction. Historical test totals remain attached to their original checkpoints.
- Actual scheduled observations at **14:53, 14:54 and 14:55 London on 13 November** demonstrate minute cadence. Consecutive intervals were **51.353 seconds** during startup and **59.688 seconds** thereafter. Snapshot health showed zero consecutive failures. Held-listing metadata refresh completed.
- Both approved identities passed actual HTTPS snapshot/health/manual-queue checks. Responses matched stored projections, and anonymous/nonmember/Origin/CSRF/query/duplicate-cookie/logout denials passed. A further authenticated read returned a snapshot retrieved 50.07 seconds earlier with no-store headers. These checks used provider-verified short-lived test sessions. Password login was qualified in an earlier delivery.
- Native `0007`, restricted role flags, all 12 RLS tables, preserved source/member controls and the existing BFF credential were independently verified. Encrypted pre/post-migration exports were verified. The earlier actual `0006` financial snapshot passed a network-disconnected local restore. A `0007` restore drill remains unverified.
- Earlier desktop Chrome inspection verified the saved holdings view. Visual review of the refresh controls remains open because browser/computer access was unavailable. Partner first-use browser confirmation, mobile checks and the full browser-cookie audit remain open.

Private deployment IDs, receipts, source values, credential material and recovery keys stay outside Git. A clean clone lacks those private administrative resources. Historical first-use helpers pin earlier empty schemas and require inspection before use on an active deployment.

## Remaining delivery

Owner amendment, 19 November: site availability takes priority; 60-day observation retention is approved as a fallback if 90 days cannot fit safely. The same conservative model projects 275–301 MB for 60 additional days. Ninety days remains the capacity target; the sixty-day detailed-refresh cleanup is implemented and deployed as recorded above. Hosted archive infrastructure remains deferred. Storage capacity does not establish runtime RAM safety; preserve bounded processing and do not claim crash prevention from disk sizing.

The measured-input [storage report](storage-capacity-report.md) is complete. Physical qualification remains open: ten-minute compressed retention may fit, but around-the-clock raw retention exceeds the database allowance. Hosted lossless archive infrastructure remains deferred; scheduled backups and independent key custody remain open. Detailed-refresh retention is deployed. Replacement hosted Auth/browser recovery and active-data credential rotation also remain open.

Other supported requirements include normalized ledger/cash/quantity reconciliation, verified transaction CSV aliases, group mapping/editing, daily prices/FX and approved closes, historical performance, projections, correlation/risk, remaining screens and alerts. Tax remains owner-deferred. The contracts in [the documentation index](README.md) retain those requirements.
