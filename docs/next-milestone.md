# Proposed next task

Reviewed **13 November 2026**. Minute broker refresh is deployed and verified. Current application state, evidence and work scope are maintained in [status and handoff](status-and-handoff.md). The completed refresh brief is retained in [historical checkpoints](status-history.md#archived-broker-refresh-milestone-brief).

## Candidate outcome

**PROPOSED for owner selection:** produce a measured 90-day storage budget and a concrete retention/archive proposal for the existing free Cloudflare/Supabase deployment. Related requirements are P02, L03, O01 and QA02, with open question Q18.

The review should account for immutable refresh sources, approved projections, import/audit rows, indexes, history revisions and held-listing metadata. Report measured data and assumptions separately. Preserve the 60-second session target and the requested 90-day observations. A shorter retention period or reduced sampling requires an owner scope decision.

## Read for this task

1. The current status and [market-data retention contract](market-data-and-polling.md#storage-and-retention).
2. [Free-hosting capacity context](hosting-options.md) and [hosted recovery](hosted-recovery.md).
3. `backend/src/meridian/application/broker_sync.py`, `security/hosted_sync.py`, `persistence/models.py` and `hosted_backup.py`.

The first assignment can use synthetic payloads and existing private aggregate measurements. Access to real evidence follows the established private-data boundary. A clean clone does not contain private receipts or administrative helpers.

## Reviewable deliverable

One public-safe capacity report should state the baseline, generation frequency, bytes per generation, row/index overhead, session/unknown-coverage assumptions and projected growth. It should compare the result with the dated free-service budget and describe retrieval, integrity, backup, key custody and restore requirements for any proposed archive.

Acceptance requires reproducible measurement commands, exact precision/provenance assumptions and an explicit list of unresolved inputs. Proposed storage components and migrations need a separate implementation task with exact file ownership and tests after the approach is selected. The initial measurement task does not call for production cleanup, source deletion, schema changes or credential provisioning.

## Other open work

Normalized economics and corporate-action review, transaction CSV aliases, groups, daily market inputs, performance and analytics remain on the development plan. Choose those through a separate bounded brief when directed. The original seven-family capture and deployed refresh already supply broker observations.
