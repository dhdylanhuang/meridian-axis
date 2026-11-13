# Next milestone: ongoing read-only broker snapshot refresh

Prepared **13 November 2026** at the owner's request for a fresh agent. Read `AGENTS.md` and the first section of [status and handoff](status-and-handoff.md) first. This brief does not authorise unrelated work or changes outside the owner's next instruction.

## Working baseline

- Deployed source **`e79fedc`**; native schema parity **`0006`**. Main contains that verified implementation plus documentation updates.
- [Private application](https://meridian-axis-session-gateway.meridian-worker-feasibility.workers.dev/) has working sign-in and AXIS/HOLDINGS using the saved Trading 212 capture. The separate public React preview still contains invented data.
- The owner requires **Trading 212 reported figures**: summary totals/cash and position value/cost/PnL. Do not replace them with reconstructed sums. Full ledger reconciliation is not a gate for the broker snapshot. Calculated analytics remain separately labelled.
- The owner confirms one GBP Stocks ISA, a cash-funded start and no earlier/transferred holdings. The captured account reference is independently matched to the statement's ISA section. Do not re-ask these scope questions.
- Both approved identities passed actual snapshot HTTPS access/denial/revocation checks. A deployed signed-in holdings view was observed in Chrome. Partner first-use browser confirmation and mobile walkthrough remain separate, unconfirmed acceptance.
- Snapshot data is saved and explicitly labelled. **No automatic broker refresh is configured.** The reload button reads saved data only.

## Concrete next outcome

An authorised hosted process fetches current account summary and positions from Trading 212 read-only, preserves their immutable source observations, and atomically publishes the matching approved snapshot. Existing users continue to see the last successful capture with accurate source/retrieval/failure states. Failed or overlapping jobs must not publish partial generations or fabricate a fresh quote time.

## First dependencies and boundaries

1. **Secure credential provisioning:** the broker key pair was used only in the owner's local hidden-prompt capture process and was not persisted. Neither Git nor the existing Worker contains it. Arrange provider secret bindings through a trusted private flow; never request values in chat, embed them in frontend/build files, log them, or infer read-only permissions from a successful summary request. No order creation/modification/cancellation.
2. Review the adapter contract and current provider specification before changing requests. Existing `adapters/trading212.py` already supplies the allowlisted reads, exact parsing and per-instance pacing. Hosted driver/provider HTTP compatibility and account-wide coordination still need qualification.
3. Define a legitimate **summary/positions refresh contract**. Do not manufacture empty completed history families to satisfy the seven-family capture validator. History and metadata need their own independently bounded cadence; do not re-download all instrument metadata or history each quote cycle.
4. Introduce one scheduled/manual authority with durable leases, next-attempt/rate state and retry bounds as needed. Requested freshness is 60 seconds subject to verified provider capability/free budgets. Preserve unknown quote age, since broker retrieval time is not a market quote timestamp.
5. The existing BFF role has SELECT on `broker_snapshots` and session permissions only. It cannot read raw history/import logs or write snapshots. Use reviewed narrow writer permissions for a sync authority; never place ephemeral administrator credentials into a Worker. Supabase native migrations remain the sole hosted DDL writer, with matching Alembic/model tests on a validation branch before main.
6. Source/publication must preserve account/environment binding, exact decimals, duplicate/revision semantics, immutable evidence/audit, observation-time ordering and safe rollback. No database transaction spans upstream HTTP/backoff waits.

## Relevant implementation

- `backend/src/meridian/adapters/trading212.py`: verified seven-read adapter.
- `adapters/broker_evidence.py`, `application/broker_ingestion.py`: complete capture validation and evidence-only acceptance. This books zero economic events.
- `application/broker_snapshot.py`: broker-reported browser projection.
- `application/snapshot_publish.py`: trusted publication from the accepted capture/run/reference; idempotent per source.
- `application/snapshot_access.py`, `security/http.py`, `app.py`: membership-checked snapshot read; no raw history returned.
- `backend/migrations/sql/0006_snapshot_access.sql` and matching native migration: existing immutable permission boundary.
- `prototype/worker-feasibility/signin/`: deployed private UI. `prepare_application.py` copies only an explicit public-source allowlist into the Worker bundle.
- `tests/test_snapshot_access.py`, `test_broker_ingestion.py`, `test_trading212.py`, Worker Node/UI tests: reuse synthetic fixtures and extend meaningful coverage.

## Verification and delivery

Use locked dependencies, targeted offline tests and disposable PostgreSQL tests through both migration paths. Existing baseline: **406 offline cases**, **71 PostgreSQL cases**, Worker **19 Python/25 Node cases**. Test failed upstream calls, shared-rate contention, duplicate invocation, crash/retry/lease expiry, no partial publication, old-generation ordering, exact broker figures and session/member/anonymous denial. Keep public CI synthetic; actual provider evidence and all financial values stay private.

Qualify the hosted path within free limits, observe actual migrations/deployment, check the running app, update authoritative docs and commit/push verified source as authorised. Do not declare live/real-time freshness from a local bundle build or saved capture. Minimise sub-agents and unnecessary repeated checks.

## Recovery and private context

Private runtime/resource/rollback manifests and bounded admin helpers exist only on the trusted machine, ignored by Git. Inspect privately without printing keys, financial source data, identifiers or digests. Old first-use identity/credential bootstrap helpers pin earlier schemas/empty databases; **do not rerun them or recreate/reset the working projects/users**. The current app's existing managed secrets and Hyperdrive origin must be preserved unless a separately qualified change requires otherwise.

Encrypted pre/post-migration backups and the separately protected key are retained privately. The actual `0006` financial snapshot passed a network-disconnected local restore with exact controls/RLS/read-only permissions; temporary target/volumes and the synthetic UI server were removed. This does not establish replacement hosted Auth/browser recovery, scheduled backup retention or an independent second key copy. Those operational tasks remain open. Private files do not travel with a Git clone.

## Other substantial work left

After refresh: requested market-data/daily-risk inputs, groups/mapping and editing, historical performance/projections, correlation/risk, remaining tabs, alerts, retention/capacity and complete operational/browser acceptance. Tax remains explicitly deferred. Preserve all original supported requirements; the current snapshot is the first useful financial view, not the finished nine-tab application.
