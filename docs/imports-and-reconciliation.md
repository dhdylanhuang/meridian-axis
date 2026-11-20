# Imports, grouping and reconciliation

Status: ADOPTED processing contract, subject to real CSV field discovery. Supports D03–D05 and G01–G02.

## Source precedence is field-specific

**Owner clarification, 12 November 2026:** the first financial screen must use Trading 212 reported figures directly. Account total/cash components come from account summary; holding value/cost/PnL come from positions. Preserve separate retrieval timestamps and missing fields. Do not replace the broker total with a sum of positions or a reconstructed ledger total. Full ledger reconciliation is deferred from this snapshot delivery; basic account identity, precision, duplicate prevention and atomic evidence acceptance remain required. Historical calculations remain separate and unavailable until their inputs support them. This clarification supersedes reconciliation-as-a-blocker for displaying the broker snapshot, not the requirement to label calculated analytics.

| Fact | Authority | Reconciliation / fallback |
| --- | --- | --- |
| Executed economic event | Verified API history event, with CSV aliases | CSV event when absent; disagreeing economics requires review |
| Current broker position | Broker snapshot | Ledger replay compared with it, never added to it |
| Group label | Total-row Name supplies group context in the inspected holdings CSV; Slice is holding ticker | Reviewed manual assignment; API sync must not erase it |
| Historical workbook observation | Immutable Excel baseline record | Later ledger-derived history is shown separately/with precedence labels |
| Valuation price / FX | Selected market observation and quality policy | Broker-observed current value for labelled reconciliation only |
| Tax cost / returns | Versioned calculation contracts | Provider/workbook values are comparisons, not authoritative methods |

The inspected [holdings CSV](csv-contract.md) confirms that Slice is a holding ticker and the Total row's Name identifies group context. Preserve both original fields. Extract group metadata from the control before excluding its financial row from holdings. This resolves the snapshot part of Q02; transaction-history formats still need separate inspection. Imported Slice belongs on a transaction only if that execution source actually supplies it. Snapshot grouping is dated evidence and does not establish historical event classification.

## File lifecycle

1. Identify account/environment, file type, bytes and SHA-256. Accept UTF-8-sig CSV; detect an unsupported encoding explicitly rather than corrupting labels.
2. Create an operation log in `running` state. A hash of a successfully accepted file in that scope produces a clear duplicate-file rejection; log the attempt without financial changes.
3. Validate headers against the verified format version. Preserve original header names and raw row numbers. Reject ambiguous schema versions and explain the missing/extra required columns. Permissible additional columns do not have to break compatible files.
4. Parse typed fields without locale guesses. Validate dates, identifiers, currencies, numeric precision, negative quantities and event semantics. Separate holdings snapshots from execution files.
5. Exclude Total rows from economics, retaining source controls and an excluded count. Identify totals using verified schema/context rather than excluding a real instrument named by an incidental substring.
6. Normalise to staged evidence/events, resolve verified duplicates and detect changed-ID conflicts. Build row-level diagnostics and grouping candidates.
7. Default policy: one invalid required economic row rejects the financial import. Known Total controls and verified duplicates are permissible exclusions. Do not silently accept a partial ledger. If an explicit partial-import feature is later requested, give it a separate mode, coverage warning and acceptance contract.
8. Commit evidence links, accepted events, group evidence, audit and success counts in one transaction. A failure rolls everything financial back. Record the failure outcome in a separate short transaction after rollback.
9. Invalidate/rebuild dependent views. The import can be accepted while recomputation is pending, but the UI must show pending/stale derivatives rather than presenting them as current.

Report total rows read, added economic events, duplicate events skipped, control rows excluded, rejected rows and unresolved conflicts. Distinguish evidence rows from economic events: a fee component or multiple source observations need not be independent transactions.

## API sync lifecycle

Use the same staging, normalisation, identity, financial commit and audit services as file import. A sync has a run ID and source `trading212_api`, not a pretend CSV hash. It can reference payload digests and the verified contract version. Complete history families and checkpoints become visible together; failed or partial retrieval is not reported as a successful full refresh.

Positions and account summary are reconciliation observations. Handle an observed new position promptly, while marking historical cost/returns unavailable until supporting events/opening records exist. Record the time gap between snapshot and replay cutoffs so ordinary intervening trades do not become misleading corruption alarms.

## Group assignment

- Reserve a stable Unassigned group. Missing usable evidence, cash display rows and unresolved assignments go there with distinguishable warning reasons. Total controls never go there.
- A new listing with one unambiguous eligible group-context observation maps to its group; ticker Slice text is not that group. Multiple distinct labels produce a conflict; do not use the most recent/largest/first automatically.
- A reviewed override is authoritative until explicitly changed. New evidence can reopen a review warning without replacing the override.
- Rename changes the display name and records alias history. Raw source text remains unchanged.
- Merge moves effective memberships/mappings to the destination group, retires the source ID and records affected entities and before/after in audit. Do not delete referenced historical groups.
- Reassignment records a new effective interval and actor/reason. Exposure uses current groups; historical attribution uses effective-date membership unless a labelled restatement is requested.
- Do not model pies, target allocations, pie RAG or per-group projections. Group-level financial/risk aggregation and alerts are explicitly requested.

## Excel migration

Read the original workbook without saving it. Compute its digest in a private local migration manifest. The public [workbook baseline](workbook-baseline.md) deliberately omits the source hash and values; record a new source version when it changes. Import the six recorded observations and their notes, source cell addresses, date precision and group coverage. Store `Total Invested` as the source's recorded invested amount, **not** an external contribution figure.

Mark every baseline field `excel_migration` with file hash and import run. Keep the early incomplete group coverage, the owner-confirmed unknown July observation date and cumulative dividend semantics. Import no unpopulated future rows as zero observations. Reimporting the same workbook version is idempotent. A revised workbook is a new source version, not permission to overwrite prior facts.

Reconcile recorded totals and group sums within £0.01. Preserve original faulty calculated cells in private migration evidence for comparison only if needed; never make the app reproduce the wrong-denominator allocation or shifted holding gains.

## Reconciliation controls

| Control | Expected result / action |
| --- | --- |
| Group values versus holding values | Equal within defined penny tolerance; mismatches block trusted totals |
| Portfolio securities value versus group totals | Equal, including Unassigned; no duplicate Total rows |
| NAV decomposition | Securities + cash − supported liabilities = NAV; distinguish holdings-only baseline |
| Quantity replay versus broker | Exact to instrument/source precision; unexplained differences create a visible exception |
| Event overlap | API then CSV, CSV then API and repeated ranges yield identical ledger economics |
| Cash roll-forward | Opening cash + signed cash events = closing cash per currency |
| Dividends | Cumulative snapshot values never create recurring dividend payments |
| Historical coverage | Known start/end, gaps, unsupported events and opening records remain visible |
| Derived generation | Results reference the accepted ledger/price/settings revision |

Tolerances must follow source precision, not a blanket percentage that conceals missing trades. A broker-PnL mismatch can reflect method differences; explain the basis rather than forcing agreement.

## Corrections and recovery

An accepted import cannot simply be deleted while derived records remain. Preview the affected events/dates, preserve original evidence, add a reversal/superseding normalisation where supported, then replay dependent holdings/cash/tax/valuations. Log actor, reason and run. A correction must not reverse an event still supported by another accepted source alias.

Before the first real import, test a database backup and restore. Provide a dry-run report for imports and corrections. No financial transaction remains open while downloading files, fetching pages, waiting for rate limits or polling prices.

## Implemented boundary

The local holdings-snapshot evidence slice now implements full-file preview, short durable attempt logging, accepted-hash deduplication, atomic source/audit commit and rollback-safe failure categories. No normalized ledger event or current group membership is booked. Account/currency validation rejects invalid administrative scope before creating a run. Parser failures create failed scoped attempts with no financial/source residue. Failed oversized input has a null content hash rather than a misleading digest of its bounded prefix. Other lifecycle, replay, corrections and group workflows above remain target contracts. Three private PDF statements have been [inspected structurally](statement-source-contract.md); their availability does not establish a production PDF parser or complete opening history.

## Broker evidence acceptance slice

`adapters/broker_evidence.py` validates the captured seven-family contract, timestamps, scope, exact numeric encoding and source identities. `application/broker_ingestion.py` accepts immutable evidence into existing `source_records`, with a capture manifest, financial source rows and one retained array per metadata family. It books **zero economic events**. Split/scrip/unknown action types are retained as facts without being relabelled as cash-funded trades.

An independently verified expected broker reference is mandatory. First binding to `accounts.private_reference` is explicit and commits with accepted sources/audit; existing different references are refused. Complete parsing occurs outside the evidence write transaction. Successful canonical capture hashes are unique per account/kind, including re-encrypted or differently spaced JSON copies. Later captures can repeat old event observations without creating economics; ongoing history observation identities/revisions are implemented in the flow below, while cross-source economic reconciliation remains open. Scope/account locking and the database unique constraint protect competing acceptance. Failures roll back evidence/binding/audit and leave a safe failed attempt.

`application/broker_snapshot.py` projects broker-reported figures directly. It preserves exact decimal strings, exposes separate account/positions retrieval windows and unknown quote age, leaves absent fields unavailable and never derives account total or cash by summing components. Its tests deliberately use different account/position totals and require the reported account total to survive unchanged. The approved projection is served by the deployed authenticated snapshot route and private AXIS/HOLDINGS views. See [API and UI](api-and-ui.md#authenticated-broker-snapshot--13-november-2026).

## Ongoing sync implementation — 13 November 2026

`application/broker_sync.py` implements two independently bounded flows. Snapshot refresh validates the explicit version-2 summary/positions envelope and commits immutable source evidence, the approved browser projection, success health and publication audit together. It never supplies completed empty histories to the version-1 capture validator.

History jobs persist one page and its continuation per invocation. Each family retains a running import and private checkpoint until null continuation. Complete acceptance appends event revisions and marks the traversal successful in the same transaction. Readers must select revisions whose source import succeeded. An absent event in a later traversal never deletes an earlier fact. Fill IDs and dividend/cash references have separate namespaces. A repeated identical identity within a traversal is skipped, while conflicting payloads fail the entire acceptance. Provider revisions append an increasing revision with source links. Corporate actions preserve the original fill facts with `corporate_action_review`; supported economic action processing and cash/quantity replay remain open.

The adopted history cadence uses a one-hour cooldown anchored to each successful final-page attempt, advancing one family page per scheduled invocation and rotating three families. Pagination and retries may extend the actual interval. It catches late and revised rows without assuming cursor ordering or inventing date filters. The 1,000-page bound stops an unbounded traversal for review. `BrokerJobs.resume` supports trusted administrative retry or a traced restart after correcting a terminal failure. Its database transaction must use administration, since the runtime audit policy permits only ordinary sync actions.

The original Excel baseline is now privately hosted as six `excel_migration` source observations. The local CLI previews by default and accepts an explicit private JSON cell mapping. Revisions preserve earlier source versions. See the workbook contract for precision, missing-cost controls and actual-source verification. Holdings CSV remains evidence-only fallback. Transaction CSV normalization/aliases require verified export headers and samples. The owner currently has transaction history only in PDF.


## Execution quantity diagnostic — 19 November 2026

Implemented bounded slice of D03/C01: `application/history_reconciliation.py` builds
`known_trade_quantity_v1` from accepted initial capture order rows and ongoing
order revisions. `domain/quantity_history.py` owns pure Decimal replay. This is a
rebuildable, provisional read model; it creates no persisted ledger entries.

Identity is account-scoped `fill:<fill ID>` (or `order:<order ID>` for no-fill
observations). Distinct fills under one order remain distinct. Select the latest
observation timestamp, then revision number; initial captures use their retrieval
completion and revision zero, ongoing revisions use acceptance observation time.
Same-rank conflicting payloads produce review with no quantity effect. Every
source/revision ID, raw-row digest, order/fill ID and original execution timestamp
remains traceable. Repeated observations contribute once; a revised fill replaces
its previous effect, and disappearance from a later traversal is not a reversal.

Only `TRADE` quantities with BUY/nonnegative or SELL/nonpositive source signs
contribute their original signed quantity. Other sign combinations require review;
there is no `abs()` sign repair or assumption that all provider sell observations
follow this convention. Non-trade fill types require corporate-action review and
contribute no invented economics. No-fill orders contribute nothing. Executions
after the saved positions retrieval completion are excluded from that comparison.
Price is retained as source evidence with nullable order currency; no cost, FX,
cash or return calculation uses it.

The comparison is **broker quantity minus known trade deltas**, with exact Decimal
precision and no percentage tolerance. It includes closed/replay-only listings.
It does not assume an opening balance: even a zero residual says only
`matches_known_events_only`. Lifetime coverage, missing opening positions,
separate observation times and unimplemented cash/dividend/fee economics remain
explicit warnings. Latest ongoing order-attempt status and last completed order
traversal are reported independently; running/failed source pages do not enter
replay. A completed API traversal does not establish lifetime completeness.

Trusted local use, from `backend` with the existing environment:

```sh
python -m meridian.reconcile_history --database /path/to/private.sqlite3 --account-id ACCOUNT_ID
```

Use an existing private local evidence database. The command opens SQLite in
`mode=ro` with one explicit read transaction, cannot create a missing database,
and makes no broker/hosted requests. **Its JSON contains private financial records
and identifiers**; keep stdout/reports outside Git and public logs. The service
requires a caller-owned consistent read transaction and trusted evidence access;
it is not a new HTTP endpoint or BFF permission. Initial capture source digests,
revision payload identity/digest and saved snapshot digest are checked. Each of
the capture-row and revision reads is capped at 20,000 observations; exceeding a
cap fails the entire report rather than silently truncating it.

Remaining: verify source sign conventions against private evidence before broader
booking; establish supported opening/coverage and corporate-action treatment;
normalize dividend/cash/fee economics; persistence/aliases and integrated dashboard
presentation. Cash components retain the existing broker authority and are not
summed or reconciled by this slice. No schema, sync, retention or access change.


## Rust cash core — 20 November 2026

The owner selected Rust for the next reconciliation experiment, with Python
retaining ingestion and database access. The first implementation is a pure native
cash-family core and trusted read-only evidence exporter, not a hosted ledger or
complete cash reconciliation. [The crate contract](../rust/reconciliation/README.md)
owns typed input/output, exact-decimal bounds, latest-revision selection, explicit
sign/control evidence gates and local commands. The exporter preserves accepted
source rows/revisions and leaves every provider sign unverified. Separate broker
cash components are retained without choosing or summing a closing total.

Seven focused Rust tests and four Python bridge tests passed; current status
records exact commands and the next WASM/runtime integration boundary. No real
financial inputs, schema/BFF permissions, deployed source or refresh policy changed.


## Private Rust job integration — 20 November 2026

The Python refresh prepares cash evidence for the current pending broker snapshot
and calls the gateway's named `CashReconciliation` entrypoint through the sync
Worker's `RECONCILIATION` service binding. The gateway runs the qualified WASM and
returns a whitelisted summary. Python checks scope/as-of, pending snapshot identity,
exact input SHA-256, count/coverage shape and absence of invented residuals before
publication. Rust financial rules are unchanged; JavaScript only projects results.

Evidence reads use a short consistent read transaction (Postgres repeatable-read /
read-only with a two-second statement bound); it closes before the four-second RPC
window. At most 1,024 observations / 512 KiB are admitted. Excess is unsupported,
never silently truncated. Final snapshot, broker evidence, audit and job success
commit together under the existing fenced lease. Rust/transport/validation failure
publishes an explicit unavailable review alongside valid broker figures; failed
broker refresh still preserves the prior complete snapshot.

**Runtime coverage:** the existing restricted sync role can read ongoing cash
revisions, but cannot read initial capture imports. Runtime preparation deliberately
excludes captures and records `initial_capture=not_included_runtime`; offline trusted
export retains them. No RLS/grant is expanded. Sign basis remains unverified and
opening/closing controls remain absent, so this delivery exposes review/coverage,
not a reconciled cash balance or calculated return. Newly accepted history after a
snapshot is considered by the next successful refresh.

No new Worker, database table, schema writer, browser request or sync schedule.
The extra account/cash reads are bounded once per successful refresh; actual query
usage remains an operational verification item, not a claimed measurement.


## Observed cash component window — 20 November 2026

The hosted adapter now opts into `statement_checked_gbp_v1`. Independent read-only
ISA statement checks corroborated captured account identity, positive GBP cash
interest, and signed GBP transfers in both directions. The private proof and source
remain ignored. This rule grants no contribution classification, timestamp-zone
assertion, cross-source alias, or PDF importer. Other types/currencies, negative
interest corrections and demo data keep unverified signs. Rust preserves original
observations/revisions and records the applied policy/evidence ID separately.

For each refresh, one indexed bounded read selects the latest approved snapshot
observed before the current UTC day. Its digest, account/environment, currency and
available-to-trade component establish an actual opening observation; the pending
snapshot supplies the matching closing component. No inception opening or total
cash is inferred. Missing controls retain null residuals. Rust alone sums supported
unique effective movements in `(opening timestamp, cutoff]`, computes expected
component cash and closing-minus-expected residual, and counts included/excluded
cash events. The approved projection carries exact decimal strings, timestamps,
opening snapshot ID, current snapshot ID and input revision. Projection validation
rejects mismatched controls, policy, IDs, invalid decimal/count shapes and extra fields.

This is a provisional **available-to-trade component check**. Trade/dividend cash,
reservations, pie changes, incomplete capture/history and other unverified cash
families can explain residuals; they are not automatically assigned a cause. A zero
residual means only `matches_known_events_only`, even when excluded events remain.
No NAV, lifetime cash reconciliation, return, fee/FX or corporate-action booking.
No migration, grant, Worker, browser request or cadence change. Service failure
continues to preserve successful broker publication. Offline exporter defaults keep
signs unverified and controls empty unless explicitly opted in by a trusted caller.


## Reported income and funding — 20 November 2026

Owner DC25 requires useful monetary amounts rather than the review/window paragraph.
The hosted adapter opts into `activity_since` at January 1 00:00 UTC of the current
broker cutoff year. It reads succeeded cash **and dividend** revisions within the
unchanged shared 1,024-observation / 512 KiB bounds. Initial captures remain excluded
under existing RLS; coverage is explicitly incomplete/unverified. It no longer asks
for a prior-day cash control or runs that extra snapshot query in production.

Rust identity now includes source family, preserving original reference/revision/
digest evidence and preventing a dividend reference from colliding with a cash
reference. Optional observation `family` defaults to `transactions`; `dividends`
uses raw `paidOn`, `amount`, `currency` and original type (or explicit UNSPECIFIED).
The provider documents `amount`/`currency` as account-primary for paid dividends:
[paid payouts](https://docs.trading212.com/api/historical-events/dividends.md).
No gross/net tax treatment or corporate-action economics is inferred.

`reported_activity` is a descriptive source report, **not** additional cash booking.
It sums original signed reported amounts once per latest family/reference, by
category/currency in `[activity_since, cutoff]`, excluding conflicts. Dividend
records have `reported_activity_only` state and no cash delta, even with a caller's
sign claim. Unknown cash types stay separate as other activity. The window/core
remains available to explicit callers; it no longer drives the main dashboard.

The whitelist returns only dated monetary category totals, counts and excluded-
conflict count, with existing root snapshot ID/input digest provenance. Python
checks period/currency/category/decimal-string/count shapes and unique category/
currency pairs. Browser performs no aggregation or FX. Missing categories are
unestablished rather than invented zero; existing saved snapshots still display
current broker cash with an explicit unavailable activity state. Current cash and
historic income/funding remain separate because receipts may already be spent.
No schema, grant, Worker, poll, provider request or workbook change.


## Cash total drill-down and available-history coverage — 20 November 2026

`POST /api/v1/portfolio/cash-activity` accepts a saved snapshot ID/input revision,
category, currency, offset and limit (maximum 50; browser pages 20). Existing
session/member/origin/CSRF checks commit before forwarding to the fixed private
sync object. It uses the existing restricted read role, accepted revisions at or
before cutoff and the same canonical request behind the approved total. An input
hash mismatch/unavailable snapshot is 409, never a silently changed page.
Rust selects/sorts the latest family/reference records and returns only the page;
Python validates each row against input source/revision/digest, amount, currency,
date and issuer label. Raw observations/credentials remain private. The approved
snapshot stores only totals and small coverage metadata, not repeated history.

One bounded metadata statement selects the latest completed dividend/cash imports
at cutoff. Completion derives from the verified writer's terminal-pagination atomic
success and bounded page count, not an in-progress checkpoint. Coverage reports
last completed traversal and earliest/latest captured dates; it certifies currently
available broker history only. A private source-page/capture-reference audit found
no known missing captured references at this checkpoint, so no backfill was run.
No assertion of complete account lifetime, statement agreement or gross/net tax.
The offline exporter retains its previous defaults; hosted requests explicitly pin
accepted revisions to cutoff for stable drill-down. No new schema, RLS/grant,
Worker, polling cadence, workbook or provider call. On-demand requests have a
2-second read statement bound / 4-second private RPC bound; DB transactions close
before RPC. Unavailable details cannot modify saved financial totals.
