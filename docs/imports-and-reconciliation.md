# Imports, grouping and reconciliation

Status: ADOPTED processing contract, subject to real CSV field discovery. Supports D03–D05 and G01–G02.

## Source precedence is field-specific

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
