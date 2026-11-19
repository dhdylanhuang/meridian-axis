# Next agent assignment: transaction history and reconciliation

Reviewed **19 November 2026**. The owner requested a handoff prompt for the next agent to implement this stage. This brief records that intended assignment; it does not claim implementation has begun or activate unrelated work.

## Outcome and first slice

Turn captured orders/executions, dividends, fees and cash movements into traceable economic records, then reconcile holding quantities and cash against Trading 212. Surface unexplained differences, source coverage gaps and corporate actions needing review. Preserve raw evidence and append-only provider revisions; repeated syncs must not duplicate economic effects.

Start with one bounded end-to-end slice selected from the existing contracts and source shapes. State that boundary briefly before implementation. Do not try to complete every event family, import format, reconciliation screen and performance calculation in one unreviewable change. Do not invent opening balances, CSV schemas, aliases, corporate-action economics or returns. Transaction exports currently available from the owner are PDFs; CSV transaction format remains unverified.

## Read selectively

Read `AGENTS.md` and [current status](status-and-handoff.md), then only the relevant sections of [imports/reconciliation](imports-and-reconciliation.md), [data model](data-model.md), [broker integration](trading212-integration.md), requirements and calculation contracts. Inspect the related implementation/tests before choosing the slice. Historical checkpoints are on-demand evidence.

## Preserve and reuse

Native parity is `0008`; sync source is `0afd670`, session/gateway source `073ffca`. Ten-minute refresh remains enabled. Sixty-day expiry applies to detailed refresh pairs only; latest/daily observations, transaction history, imports and audit are retained. [Manual XLSX export](workbook-archive.md) is implemented locally. Do not modify or re-import the real workbook for ledger development. Hosted archive infrastructure stays deferred.

The owner requires minimal changes, targeted checks and reuse of passing evidence. Do not rerun prior CI matrices, storage sizing or live probes without a specific relevant change, failure or unresolved risk. Flag substantial expansion before proceeding. No separate role-based screens or permissions are needed; tax remains deferred.

## Separate operational gaps

Post-quota-reset login, automatic cadence and account query usage remain unverified. Keep any check bounded and separate from feature work. Scheduled backups, independent key custody, a `0008` restore drill and full capacity acceptance remain open. Backup daemon prerequisites and the resolved Docker diagnosis are documented; do not restart that investigation.
