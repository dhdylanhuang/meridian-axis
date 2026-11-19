# Next agent assignment: transaction history and reconciliation

Reviewed **19 November 2026**. The execution quantity diagnostic is implemented locally. This brief records the remaining bounded work; it does not activate unrelated platform work.

## Outcome and first slice

Turn captured orders/executions, dividends, fees and cash movements into traceable economic records, then reconcile holding quantities and cash against Trading 212. Surface unexplained differences, source coverage gaps and corporate actions needing review. Preserve raw evidence and append-only provider revisions; repeated syncs must not duplicate economic effects.

Completed slice: `known_trade_quantity_v1`, a trusted read-only local report over
initial capture order evidence, accepted ongoing revisions and saved positions.
It deduplicates fill identity, replaces revised effects, retains evidence links,
excludes partial history runs, exposes quantity residuals/sign/corporate-action
review and never asserts lifetime completeness. No schema or deployed runtime
change. See [the implemented boundary](imports-and-reconciliation.md#execution-quantity-diagnostic--19-november-2026)
and the exact **12-test** evidence in current status. Reuse those passing checks.

Next useful slice: establish supported cash/dividend/fee semantics from existing
private evidence and verified contracts, then select one family for traceable
normalization and reconciliation. Keep real evidence out of Git. Until semantics
and opening/coverage support booking, retain unsupported states instead of guessing.
Dashboard integration and persisted economics need their own reviewed boundary;
do not grant the BFF raw-history access. Do not invent opening balances, CSV
schemas, aliases, corporate-action economics or returns. Transaction exports
currently available from the owner are PDFs; CSV format remains unverified.

## Read selectively

Read `AGENTS.md` and [current status](status-and-handoff.md), then only the relevant sections of [imports/reconciliation](imports-and-reconciliation.md), [data model](data-model.md), [broker integration](trading212-integration.md), requirements and calculation contracts. Inspect the related implementation/tests before choosing the slice. Historical checkpoints are on-demand evidence.

## Preserve and reuse

Native parity is `0008`; sync source is `0afd670`, session/gateway source `073ffca`. Ten-minute refresh remains enabled. Sixty-day expiry applies to detailed refresh pairs only; latest/daily observations, transaction history, imports and audit are retained. [Manual XLSX export](workbook-archive.md) is implemented locally. Do not modify or re-import the real workbook for ledger development. Hosted archive infrastructure stays deferred.

The owner requires minimal changes, targeted checks and reuse of passing evidence. Do not rerun prior CI matrices, storage sizing or live probes without a specific relevant change, failure or unresolved risk. Flag substantial expansion before proceeding. No separate role-based screens or permissions are needed; tax remains deferred.

## Separate operational gaps

Post-quota-reset login, automatic cadence and account query usage remain unverified. Keep any check bounded and separate from feature work. Scheduled backups, independent key custody, a `0008` restore drill and full capacity acceptance remain open. Backup daemon prerequisites and the resolved Docker diagnosis are documented; do not restart that investigation.
